#!/usr/bin/env python
"""
A credential must not reach the log sink
========================================
On 8 Oct 2026 a freshly-issued EODHD key was printed in full by the first
call made with it:

    INFO HTTP Request: GET https://eodhd.com/api/fundamentals/AXJO.INDX
         ?api_token=<the key>&fmt=json "HTTP/1.1 200 OK"

No line of this codebase logged it. `httpx` logs request URLs at INFO with the
query string intact, and `asx-backend.service` appends stdout to
`logs/backend.log` -- so every EODHD call the backend ever made wrote the key
to disk. That is how the original leaked, and it consumed its replacement too.

Two things this pins that a weaker test would not:

1. **The filter is on the HANDLER, not the logger.** A logger filter sees only
   records created by that logger, never records propagated from elsewhere.
   The offending records come from the `httpx` logger. A filter on the root
   logger would pass every test written against `logging.getLogger(__name__)`
   and still miss the actual defect.

2. **The secret arrives in `record.args`, not `record.msg`.** httpx logs
   `'HTTP Request: %s %s "%s"'` with the URL as an argument, so redacting
   `record.msg` alone catches nothing.

The central test therefore logs through the **real httpx logger** in the shape
httpx really uses, and asserts against what the sink actually received.

Run:  python tests/test_secrets_do_not_reach_the_log_sink.py
"""

import io
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.log_redaction import (                          # noqa: E402
    REDACTED, RedactingFormatter, SecretRedactingFilter,
    install_secret_redaction, protect_handler, redact)

#: Shaped like a real EODHD key, but not one. Never use a live value here.
FAKE_KEY = "68f3c1aa9b7e42.13579246"


class _Sink:
    """A root handler writing to a buffer, with the filter installed on it."""

    def __enter__(self):
        self.root = logging.getLogger()
        self.saved_handlers = self.root.handlers[:]
        self.saved_level = self.root.level
        self.buffer = io.StringIO()
        handler = logging.StreamHandler(self.buffer)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.root.handlers = [handler]
        self.root.setLevel(logging.INFO)
        install_secret_redaction()
        return self

    def __exit__(self, *exc):
        self.root.handlers = self.saved_handlers
        self.root.setLevel(self.saved_level)

    @property
    def text(self) -> str:
        return self.buffer.getvalue()


# ── The defect, reproduced ──────────────────────────────────────────────────

def test_the_httpx_request_line_is_redacted():
    """The exact record that leaked, through the logger that emitted it."""
    url = (f"https://eodhd.com/api/fundamentals/AXJO.INDX"
           f"?api_token={FAKE_KEY}&fmt=json")
    with _Sink() as sink:
        logging.getLogger("httpx").info(
            'HTTP Request: %s %s "%s"', "GET", url, "HTTP/1.1 200 OK")
    assert FAKE_KEY not in sink.text, (
        "the key reached the sink through the httpx logger -- this is the "
        f"8 Oct 2026 leak, unchanged:\n      {sink.text.strip()}")
    assert "api_token=" + REDACTED in sink.text, (
        f"redacted, but not in the expected shape: {sink.text.strip()}")
    assert "AXJO.INDX" in sink.text, (
        "redaction destroyed the rest of the line; the log entry must stay "
        "useful, otherwise it will be turned off again")


def test_a_logger_filter_would_not_have_caught_it():
    """Mutation control for the design decision, not just the code.

    Installing on the root LOGGER instead of the root HANDLER passes a naive
    test and misses the real defect. This proves the distinction is real, so
    nobody 'simplifies' the filter onto the logger later.
    """
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    root.handlers, root.level = [handler], logging.INFO
    root.addFilter(SecretRedactingFilter())           # the WRONG attachment
    try:
        logging.getLogger("httpx").info(
            'HTTP Request: %s', f"https://x/y?api_token={FAKE_KEY}")
        leaked = FAKE_KEY in buffer.getvalue()
    finally:
        root.filters = [f for f in root.filters
                        if not isinstance(f, SecretRedactingFilter)]
        root.handlers, root.level = saved_handlers, saved_level
    assert leaked, (
        "a filter on the root LOGGER redacted a propagated httpx record. If "
        "this ever becomes true the handler-vs-logger reasoning in "
        "log_redaction.py is wrong and should be rewritten -- but as of "
        "Python's logging design it is not")


def test_the_secret_in_args_is_redacted():
    """`record.msg` alone is not enough; httpx passes the URL as an arg."""
    with _Sink() as sink:
        logging.getLogger("anything").info("calling %s", f"?api_token={FAKE_KEY}")
    assert FAKE_KEY not in sink.text, (
        "a secret passed via record.args survived; redacting record.msg "
        "alone catches nothing from httpx")


def test_an_exception_traceback_is_redacted():
    """The authentication-failure path, which is the one that matters.

    A filter alone never sees a traceback: `record.exc_text` is produced by
    the FORMATTER, after filters have run. And `httpx.HTTPStatusError` puts
    the full request URL in its message, while `_fetch_eodhd_constituents`
    calls `raise_for_status()` -- so an unredacted traceback publishes the
    credential exactly when the credential is bad.

    Measured leaking 9 Oct 2026 against the filter-only implementation.
    """
    url = f"https://eodhd.com/api/fundamentals/AXJO.INDX?api_token={FAKE_KEY}"
    with _Sink() as sink:
        try:
            raise ValueError(f"Client error '401 Unauthorized' for url '{url}'")
        except ValueError:
            logging.getLogger("httpx").exception("request failed")
    assert FAKE_KEY not in sink.text, (
        "the key reached the sink inside a traceback -- a filter cannot see "
        f"exc_text, only a formatter can:\n      {sink.text.strip()[:400]}")
    assert "401 Unauthorized" in sink.text, (
        "redaction destroyed the diagnostic; the traceback must stay useful")


def test_handle_error_output_cannot_leak():
    """logging's own error path writes record.msg and record.args to stderr.

    When a record cannot be formatted, `Handler.emit` calls `handleError`,
    which prints the raw msg and args. `asx-backend.service` appends stderr
    to logs/backend.log, so that is a real sink.

    Measured leaking 9 Oct 2026: the filter returned the record untouched
    when `getMessage()` raised, leaving the secret sitting in `args`.
    """
    captured = io.StringIO()
    saved_stderr, sys.stderr = sys.stderr, captured
    try:
        with _Sink():
            logging.getLogger("x").info("bad %s %s", f"?api_token={FAKE_KEY}")
    finally:
        sys.stderr = saved_stderr
    assert FAKE_KEY not in captured.getvalue(), (
        "logging's handleError printed the credential to stderr:\n      "
        + captured.getvalue().strip()[:300])


def test_every_handler_is_protected_not_only_the_first():
    """A process with two sinks must not leak into the second."""
    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    a, b = io.StringIO(), io.StringIO()
    root.handlers = [logging.StreamHandler(a), logging.StreamHandler(b)]
    root.setLevel(logging.INFO)
    try:
        install_secret_redaction()
        logging.getLogger("httpx").info("x %s", f"?api_token={FAKE_KEY}")
        leaks = [n for n, buf in (("first", a), ("second", b))
                 if FAKE_KEY in buf.getvalue()]
    finally:
        root.handlers, root.level = saved, level
    assert not leaks, f"credential reached handler(s): {leaks}"


def test_a_handler_added_later_can_be_protected():
    """`protect_handler` is the entry point for a sink added after startup."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    protect_handler(handler)
    protect_handler(handler)                      # idempotent
    assert isinstance(handler.formatter, RedactingFormatter)
    assert sum(1 for f in handler.filters
               if isinstance(f, SecretRedactingFilter)) == 1
    log = logging.getLogger("late"); log.handlers = [handler]
    log.propagate = False; log.setLevel(logging.INFO)
    log.info("x %s", f"?api_token={FAKE_KEY}")
    assert FAKE_KEY not in buf.getvalue()


def test_wrapping_preserves_the_original_format():
    """Redaction must not silently discard the configured log format."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("PREFIX %(levelname)s %(message)s"))
    protect_handler(handler)
    log = logging.getLogger("fmt"); log.handlers = [handler]
    log.propagate = False; log.setLevel(logging.INFO)
    log.info("hello")
    assert "PREFIX INFO hello" in buf.getvalue(), (
        f"the wrapped formatter lost its format: {buf.getvalue()!r}")


# ── Coverage of the patterns ────────────────────────────────────────────────

def test_every_credential_parameter_is_covered():
    for param in ("api_token", "apikey", "api_key", "access_token", "token",
                  "password"):
        out = redact(f"https://x/y?{param}={FAKE_KEY}&fmt=json")
        assert FAKE_KEY not in out, f"{param} is not redacted"
        assert "fmt=json" in out, f"{param} redaction swallowed the next param"


def test_a_bearer_header_is_covered():
    out = redact(f"Authorization: Bearer {FAKE_KEY}")
    assert FAKE_KEY not in out


def test_redaction_is_case_insensitive():
    assert FAKE_KEY not in redact(f"?API_TOKEN={FAKE_KEY}")


def test_a_clean_line_is_untouched():
    """Redaction must not rewrite records that contain no secret."""
    line = "HTTP Request: GET https://eodhd.com/api/eod/BHP.AU?fmt=json"
    assert redact(line) == line


# ── Installation properties ─────────────────────────────────────────────────

def test_installation_is_idempotent():
    """Called from both main.py and compute/engine/__init__.py."""
    with _Sink() as sink:
        install_secret_redaction()
        install_secret_redaction()
        filters = [f for f in logging.getLogger().handlers[0].filters
                   if isinstance(f, SecretRedactingFilter)]
        assert len(filters) == 1, f"filter attached {len(filters)} times"
        logging.getLogger("httpx").info("x %s", f"?api_token={FAKE_KEY}")
    assert FAKE_KEY not in sink.text


def test_a_later_basicconfig_cannot_displace_the_filter():
    """The reason installation happens from a package __init__.

    Twenty-plus compute engines call basicConfig at import. basicConfig is a
    no-op once a root handler exists, so installing first makes those calls
    harmless. If that ever stopped holding, every engine process would log
    unredacted again while the backend stayed clean.
    """
    with _Sink() as sink:
        logging.basicConfig(level=logging.INFO, format="%(message)s")  # no-op
        logging.getLogger("httpx").info("x %s", f"?api_token={FAKE_KEY}")
    assert FAKE_KEY not in sink.text, (
        "a later basicConfig replaced the guarded handler, so engine "
        "processes would write credentials to logs/backend.log")


def test_a_malformed_record_passes_the_filter_unharmed():
    """Redaction must not become a way to lose logs.

    Asserted against the filter itself rather than the sink. A record with
    mismatched args never reaches the handler's output anyway -- logging
    catches the formatting error and calls handleError, which is pre-existing
    behaviour this filter neither causes nor cures. The property that belongs
    to this file is narrower: the filter must not raise, and must not return
    False, when it cannot read the message.
    """
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="bad format %s %s", args=("only-one-arg",), exc_info=None)
    assert SecretRedactingFilter().filter(record) is True, (
        "the filter dropped a record it could not format, so redaction has "
        "become a way to lose logs")
    assert record.msg == "bad format %s %s", (
        "the filter mutated a record it could not read")


# ── The entry points really install it ──────────────────────────────────────

def test_both_entry_points_install_redaction():
    for rel in ("app/main.py", "compute/engine/__init__.py"):
        src = (BACKEND / rel).read_text(encoding="utf-8")
        assert "install_secret_redaction(" in src, (
            f"{rel} no longer installs redaction; one of the two process "
            f"families is writing credentials to the log again")


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
