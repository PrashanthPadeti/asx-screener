"""
Credentials must not reach the log, and must not leave it if they already did
============================================================================
Found 7 Oct 2026. httpx logs the full request URL at INFO, and EODHD takes its
token as a query parameter, so every outbound call wrote this to
`logs/backend.log`:

    INFO HTTP Request: GET https://eodhd.com/api/fundamentals/ATLI.INDX
         ?api_token=<the key>&fmt=json "HTTP/1.1 200 OK"

Two layers, because either alone fails in a predictable way.

**Suppression** (`httpx` at WARNING, set in `app/main.py`) stops the routine
case. On its own it is brittle: log levels get raised during an incident,
which is exactly when those URLs would start printing again, and it only
covers the one library anyone thought of.

**Redaction** (this module) makes the class impossible regardless of level,
logger or library. It is applied in two places on purpose:

  1. on the handler, so secrets never enter the file;
  2. again in the admin log viewer, so lines written BEFORE this shipped
     cannot be served to a browser.

The second matters more than it looks. A log viewer turns a root-readable
file on one host into something that appears in an admin session, in browser
history, and in screenshots — which is how the key reached a chat transcript
in the first place.

Redaction does not clean the existing file and is not a substitute for
rotating a key that has already been written.
"""

from __future__ import annotations

import logging
import re

REDACTED = "***REDACTED***"

#: Parameter names whose VALUE is a secret, in query strings, form bodies and
#: JSON. Matched case-insensitively. Deliberately a list of named parameters
#: rather than an attempt to recognise secrets by shape: a pattern loose
#: enough to catch an unknown key is loose enough to mangle ordinary data, and
#: a log that silently corrupts its own contents is worse than one that leaks
#: a parameter nobody listed.
SECRET_PARAMS = (
    "api_token", "api_key", "apikey", "access_token", "refresh_token",
    "token", "secret", "client_secret", "password", "passwd", "pwd",
    "auth", "signature", "sig",
)

_NAMES = "|".join(SECRET_PARAMS)

#: `?api_token=abc123&fmt=json` -> `?api_token=***REDACTED***&fmt=json`
#: Stops at & # " ' space or end, so the rest of the line survives intact.
_QUERY = re.compile(rf"(?i)\b({_NAMES})=([^&\s\"'#]+)")

#: `"api_token": "abc123"` and `'password': 'x'`
_JSON = re.compile(rf"(?i)([\"']({_NAMES})[\"']\s*:\s*)[\"'][^\"']*[\"']")

#: `Authorization: Bearer abc` / `authorization=Basic abc`
_AUTH = re.compile(
    r"(?i)(authorization\s*[:=]\s*)(bearer|basic|token)?\s*\S+")


def redact(text: str) -> str:
    """Replace credential values in a line of text.

    Pure and total: anything not recognised is returned unchanged, so this
    can be applied to every record without risk of dropping information.
    """
    if not text:
        return text
    out = _QUERY.sub(rf"\1={REDACTED}", text)
    out = _JSON.sub(rf'\1"{REDACTED}"', out)
    out = _AUTH.sub(rf"\1\2 {REDACTED}", out)
    return out


class SecretRedactingFilter(logging.Filter):
    """Redact credentials from every record passing through a handler.

    The record's message is formatted here and `args` cleared, because a
    secret may live in an argument rather than the format string --
    `log.info("GET %s", url)` has nothing to redact in `msg` alone. Formatting
    early is what makes the filter total; the cost is that `%`-style
    formatting happens once per record whether or not the handler emits it,
    which is negligible against writing the line.

    Never raises. A redaction fault must not lose the log line it was
    protecting.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            cleaned = redact(message)
            if cleaned != message:
                record.msg = cleaned
                record.args = ()
        except Exception:                                   # noqa: BLE001
            pass
        return True


def install(logger: logging.Logger | None = None) -> None:
    """Attach the filter to every handler on `logger` (root by default).

    On the handlers rather than the logger: a filter on a logger does not
    apply to records propagated from its children, so a logger-level filter
    would cover `app.*` and miss `httpx`, which is the one that started this.
    """
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if not any(isinstance(f, SecretRedactingFilter)
                   for f in handler.filters):
            handler.addFilter(SecretRedactingFilter())
