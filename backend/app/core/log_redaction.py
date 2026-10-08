"""
Secrets must not reach the log sink
===================================
On 8 Oct 2026 a freshly-issued EODHD key was written to the terminal, in full,
by the *first* call made with it:

    INFO HTTP Request: GET https://eodhd.com/api/fundamentals/AXJO.INDX
         ?api_token=<the key>&fmt=json "HTTP/1.1 200 OK"

Nothing in this codebase logged it. `httpx` logs every request URL at INFO,
query string included, and `logging.basicConfig(level=INFO)` lets it through.
`asx-backend.service` appends stdout to `logs/backend.log`, so every EODHD
call the backend has ever made put the key on disk in plaintext. That is how
the original key leaked, and it would have consumed every replacement in turn.

**Viewer redaction is not sink redaction.** Masking secrets when rendering
logs in an admin UI leaves the plaintext on disk, in backups, and in anything
that ships those files onward. This redacts at the sink, before the record is
emitted.

Why a handler filter, not a logger filter
-----------------------------------------
A filter attached to a *logger* only sees records created by that logger --
not records that propagate up from elsewhere. The offending records come from
the `httpx` logger, so a filter on the root logger never sees them. A filter
on the root *handler* sees everything that reaches the sink, whoever logged
it. That distinction is the whole reason this file works.

Why it is installed from a package __init__
-------------------------------------------
Over twenty modules under `compute/engine/` call `logging.basicConfig` at
import. `basicConfig` is a no-op once the root logger has a handler, so
installing from `compute/engine/__init__.py` -- which runs *before* any engine
module body -- wins the race and those later calls become no-ops.
"""

import logging
import re

#: Query parameters and header values whose contents are credentials.
#: Matching on the NAME rather than the shape, so a key is redacted whatever
#: it happens to look like, and a rotated key of a different shape is still
#: covered. `api_token` is EODHD's; the rest are here because a provider
#: added later must not need a new incident to get redacted.
_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"(api_token=)[^&\s\"'\\]+",
    r"(apikey=)[^&\s\"'\\]+",
    r"(api_key=)[^&\s\"'\\]+",
    r"(access_token=)[^&\s\"'\\]+",
    r"(token=)[^&\s\"'\\]+",
    r"(password=)[^&\s\"'\\]+",
    r"(Authorization:\s*Bearer\s+)\S+",
))

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Replace credential values, keeping the parameter name visible.

    The name is kept deliberately: `api_token=[REDACTED]` still shows that a
    call was authenticated, which is what the log line was for.
    """
    for pattern in _PATTERNS:
        text = pattern.sub(r"\1" + REDACTED, text)
    return text


def _redact_arg(value):
    return redact(value) if isinstance(value, str) else value


class SecretRedactingFilter(logging.Filter):
    """Rewrites a record's message in place. Never drops a record.

    Formatting happens here via `getMessage()` because the secret usually
    arrives in `record.args` rather than `record.msg` -- httpx logs
    `'HTTP Request: %s %s "%s"'` with the URL as an argument, so redacting
    `record.msg` alone would miss it entirely. Once merged, `args` is cleared
    so the handler does not re-interpolate.

    When the message CANNOT be formatted, `msg` and each `args` member are
    redacted individually and the arity is left wrong on purpose. A record
    with mismatched args fails in `Handler.emit`, and `handleError` then
    prints `record.msg` and `record.args` to stderr -- which
    `asx-backend.service` appends straight into `logs/backend.log`. Measured
    9 Oct 2026: a secret in `args` leaked by exactly that route.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:                                      # noqa: BLE001
            # Unformattable: redact the parts, preserve the breakage.
            record.msg = _redact_arg(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(_redact_arg(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _redact_arg(v)
                               for k, v in record.args.items()}
            return True        # never let redaction suppress a log record
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """Wraps a handler's formatter and redacts the fully rendered string.

    The filter alone is not enough, because a traceback never passes through
    it. `record.exc_text` is produced by the formatter, *after* filters have
    run, so an exception is rendered straight to the sink unredacted.

    That is not hypothetical: `httpx.HTTPStatusError` puts the full request
    URL in its message, and `_fetch_eodhd_constituents` calls
    `raise_for_status()`. So the credential leaks on exactly the
    authentication-failure path -- the one that executes when the key is bad.

    Redacting the final string is the only place that catches the message,
    the arguments, the traceback and any `stack_info` together.
    """

    def __init__(self, inner: logging.Formatter):
        super().__init__()
        self.inner = inner

    def format(self, record: logging.LogRecord) -> str:
        return redact(self.inner.format(record))


def protect_handler(handler: logging.Handler) -> None:
    """Give one handler both defences. Idempotent."""
    if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
        handler.addFilter(SecretRedactingFilter())
    if not isinstance(handler.formatter, RedactingFormatter):
        handler.setFormatter(RedactingFormatter(
            handler.formatter or logging.Formatter()))


def install_secret_redaction(**basic_config_kwargs) -> None:
    """Protect every handler on the root logger. Idempotent.

    Ensures a root handler exists first, so that later `basicConfig` calls in
    other modules are no-ops and cannot replace the sink this guards.

    Every handler, not just the first: a process with a stream handler and a
    file handler would otherwise write the credential to one of them. Call
    this again after adding a handler -- `protect_handler` is the single-
    handler entry point for that.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(**basic_config_kwargs)
    for handler in root.handlers:
        protect_handler(handler)
