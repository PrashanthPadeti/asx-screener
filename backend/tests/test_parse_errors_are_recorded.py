#!/usr/bin/env python
"""
A refusal the customer sees must be a refusal the server records
================================================================
Query Mode returned 422 with the reason in the response body and wrote
nothing anywhere.

When v11.2.29 broke the feature -- every query in the documented syntax
failing with "'>' is not a permitted operator" -- the log held no trace.
Six releases shipped over the top, each gated green. It surfaced when a
customer pasted a screenshot.

The outage's size is still unknown. `grep -c "is not a permitted operator"`
over backend.log returns 0, and that 0 means nothing was ever written, not
that nobody was affected. Reading it as "no impact" would be the same error
as every other instrument failure this week: a measurement taken with the
instrument switched off.

Three properties:

    recorded     every QueryParseError handler logs before it raises
    one line     a multi-line query collapses to one log line
    bounded      a pathological paste cannot flood the file

The middle one is not cosmetic. Query Mode queries are written across many
lines -- `return_1y > 0 AND` on each -- so a raw newline in the log would
split one refusal across fourteen lines and make any count of them wrong in
the other direction.

Run:  python tests/test_parse_errors_are_recorded.py
"""

import ast
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

for _k, _v in (("DATABASE_URL", "postgresql+asyncpg://unused/unused"),
               ("DATABASE_URL_SYNC", "postgresql://unused/unused"),
               ("JWT_SECRET", "test-only-not-a-secret")):
    os.environ.setdefault(_k, _v)

ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "screener.py"


def test_every_parse_error_handler_records_before_it_raises():
    """Structural, over the population of handlers.

    Not "a log call exists somewhere in the file" -- each handler must have
    one, because the one that does not is the one that goes silent.
    """
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    handlers = [h for h in ast.walk(tree)
                if isinstance(h, ast.ExceptHandler)
                and h.type is not None
                and "QueryParseError" in ast.unparse(h.type)]

    assert len(handlers) >= 2, (
        f"expected at least 2 QueryParseError handlers in screener.py, found "
        f"{len(handlers)}; the endpoints have moved and this is watching "
        f"nothing")

    for h in handlers:
        calls = [n for n in ast.walk(h) if isinstance(n, ast.Call)]
        records = any(
            (isinstance(c.func, ast.Attribute)
             and c.func.attr in ("warning", "error", "exception"))
            or (isinstance(c.func, ast.Name)
                and c.func.id == "_log_parse_error")
            for c in calls)
        raises = any(isinstance(n, ast.Raise) for n in ast.walk(h))
        assert records, (
            f"screener.py:{h.lineno} refuses a query and records nothing. "
            f"The customer sees the reason; nobody else ever does.")
        assert raises, f"screener.py:{h.lineno} records but does not refuse"


def test_a_multiline_query_becomes_one_log_line():
    """Query Mode queries span many lines; a refusal must not."""
    from app.api.v1.routes.screener import _log_parse_error
    import logging

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("app.api.v1.routes.screener")
    handler = _Capture()
    logger.addHandler(handler)
    try:
        _log_parse_error("return_1w > 0 AND\nreturn_1m > 0 AND\nreturn_1y > 0",
                         ValueError("'>' is not a permitted operator"))
    finally:
        logger.removeHandler(handler)

    assert records, "nothing was logged"
    assert "\n" not in records[0], (
        "the logged message contains a newline; one refusal would occupy "
        "several lines and any count of them would be wrong")
    assert "return_1w" in records[0] and "return_1y" in records[0], (
        "the query was lost; the reason alone cannot be acted on")


def test_a_pathological_query_is_truncated():
    from app.api.v1.routes.screener import _log_parse_error
    import logging

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("app.api.v1.routes.screener")
    handler = _Capture()
    logger.addHandler(handler)
    try:
        _log_parse_error("x" * 50_000, ValueError("nope"))
    finally:
        logger.removeHandler(handler)

    assert records
    assert len(records[0]) < 1000, (
        f"a 50,000-character query produced a {len(records[0])}-character log "
        f"line; one bad paste could fill the disk")
    assert "50000 chars" in records[0], (
        "the true length is not recorded, so the truncation hides how much "
        "was dropped")


def test_the_reason_survives():
    """The message must carry what was wrong, not merely that something was."""
    from app.api.v1.routes.screener import _log_parse_error
    import logging

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("app.api.v1.routes.screener")
    handler = _Capture()
    logger.addHandler(handler)
    try:
        _log_parse_error("is_reit > 5",
                         ValueError("'>' is not valid for a boolean field"))
    finally:
        logger.removeHandler(handler)

    assert "boolean" in records[0], (
        "the refusal's reason is missing; a run of identical reasons is the "
        "signal that a release rejected something it used to accept")


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
