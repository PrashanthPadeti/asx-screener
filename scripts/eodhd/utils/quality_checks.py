"""
Raw Zone Quality Checks
=======================
Run before committing any downloaded file to its final output path.
All checks return a QualityResult; callers route the file based on outcome.

Usage:
    result = check_fundamentals(response_bytes, requested_code)
    if result.ok:
        write_to_raw(result.data)
    elif result.destination == "quarantine":
        write_to_quarantine(result.data, result.reason)
    else:
        log_to_errors(result.reason)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


# ─── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class QualityResult:
    ok: bool
    reason: str = ""
    destination: str = ""   # "" (ok), "errors", "quarantine", "skip"
    checksum: str = ""
    data: bytes = field(default=b"", repr=False)

    @classmethod
    def good(cls, data: bytes, checksum: str) -> "QualityResult":
        return cls(ok=True, data=data, checksum=checksum)

    @classmethod
    def error(cls, reason: str, data: bytes = b"") -> "QualityResult":
        return cls(ok=False, reason=reason, destination="errors", data=data)

    @classmethod
    def quarantine(cls, reason: str, data: bytes = b"") -> "QualityResult":
        return cls(ok=False, reason=reason, destination="quarantine", data=data)

    @classmethod
    def skip(cls, reason: str) -> "QualityResult":
        return cls(ok=False, reason=reason, destination="skip")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_json(data: bytes) -> Optional[object]:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


REQUIRED_FUNDAMENTALS_KEYS = {
    "General", "Highlights", "Financials",
}

REQUIRED_PRICE_KEYS = {"date", "close"}


# ─── Check: HTTP status ───────────────────────────────────────────────────────

def check_http_status(status_code: int, data: bytes = b"") -> Optional[QualityResult]:
    """Return a failure result if the HTTP response was not 200, else None."""
    if status_code == 200:
        return None
    if status_code in (404, 422):
        return QualityResult.error(f"http{status_code}")
    if status_code == 401:
        raise RuntimeError("API key invalid — aborting run")
    if status_code == 429:
        return QualityResult.error("rate_limited", data)
    if 400 <= status_code < 500:
        return QualityResult.error(f"http{status_code}", data)
    # 5xx — goes to retry folder, not errors
    return QualityResult(ok=False, reason=f"http{status_code}",
                         destination="retry", data=data)


# ─── Check: fundamentals response ─────────────────────────────────────────────

def check_fundamentals(data: bytes, requested_code: str,
                       known_checksums: Optional[set] = None) -> QualityResult:
    """
    Full quality gate for a /fundamentals/{code}.AU response.

    Checks: valid JSON, not empty, required keys present,
            symbol match, file size, duplicate checksum.
    """
    csum = sha256(data)

    if known_checksums is not None and csum in known_checksums:
        return QualityResult.skip(f"duplicate checksum {csum[:12]}")

    if len(data) < 500:
        return QualityResult.quarantine("file_too_small", data)

    parsed = _parse_json(data)
    if parsed is None:
        return QualityResult.quarantine("invalid_json", data)

    if not isinstance(parsed, dict) or not parsed:
        return QualityResult.error("empty_response", data)

    missing = REQUIRED_FUNDAMENTALS_KEYS - set(parsed.keys())
    if missing:
        return QualityResult.quarantine(f"missing_keys:{','.join(sorted(missing))}", data)

    general = parsed.get("General", {})
    raw_code = general.get("Code", "")
    if raw_code and raw_code.upper() != requested_code.upper():
        return QualityResult.quarantine(
            f"symbol_mismatch:got_{raw_code}_want_{requested_code}", data)

    return QualityResult.good(data, csum)


# ─── Check: EOD price response (per-stock) ────────────────────────────────────

def check_prices_historical(data: bytes, requested_code: str,
                             known_checksums: Optional[set] = None) -> QualityResult:
    """Quality gate for a /eod/{code}.AU historical price response (JSON array)."""
    csum = sha256(data)

    if known_checksums is not None and csum in known_checksums:
        return QualityResult.skip(f"duplicate checksum {csum[:12]}")

    if len(data) < 100:
        return QualityResult.quarantine("file_too_small", data)

    parsed = _parse_json(data)
    if parsed is None:
        return QualityResult.quarantine("invalid_json", data)

    if not isinstance(parsed, list):
        return QualityResult.error("not_a_list", data)

    if len(parsed) == 0:
        return QualityResult.error("empty_list", data)

    first = parsed[0] if parsed else {}
    missing = REQUIRED_PRICE_KEYS - set(first.keys())
    if missing:
        return QualityResult.quarantine(f"missing_price_keys:{','.join(sorted(missing))}", data)

    return QualityResult.good(data, csum)


# ─── Check: EOD bulk price response (all ASX stocks for one date) ─────────────

def check_prices_bulk(data: bytes, min_rows: int = 1500,
                      known_checksums: Optional[set] = None) -> QualityResult:
    """Quality gate for a /eod/bulk-download/AU response."""
    csum = sha256(data)

    if known_checksums is not None and csum in known_checksums:
        return QualityResult.skip(f"duplicate checksum {csum[:12]}")

    parsed = _parse_json(data)
    if parsed is None:
        return QualityResult.quarantine("invalid_json", data)

    if not isinstance(parsed, list):
        return QualityResult.error("not_a_list", data)

    if len(parsed) < min_rows:
        return QualityResult.quarantine(
            f"bulk_too_few_rows:{len(parsed)}_min_{min_rows}", data)

    return QualityResult.good(data, csum)


# ─── Check: dividend response ─────────────────────────────────────────────────

def check_dividends(data: bytes, requested_code: str,
                    known_checksums: Optional[set] = None) -> QualityResult:
    """Quality gate for a /div/{code}.AU response."""
    csum = sha256(data)

    if known_checksums is not None and csum in known_checksums:
        return QualityResult.skip(f"duplicate checksum {csum[:12]}")

    parsed = _parse_json(data)
    if parsed is None:
        return QualityResult.quarantine("invalid_json", data)

    # Empty list is valid — stock pays no dividends
    if not isinstance(parsed, list):
        return QualityResult.error("not_a_list", data)

    return QualityResult.good(data, csum)


# ─── Check: splits response ───────────────────────────────────────────────────

def check_splits(data: bytes, known_checksums: Optional[set] = None) -> QualityResult:
    """Quality gate for a /splits/{code}.AU response."""
    csum = sha256(data)

    if known_checksums is not None and csum in known_checksums:
        return QualityResult.skip(f"duplicate checksum {csum[:12]}")

    parsed = _parse_json(data)
    if parsed is None:
        return QualityResult.quarantine("invalid_json", data)

    if not isinstance(parsed, list):
        return QualityResult.error("not_a_list", data)

    return QualityResult.good(data, csum)


# ─── Check: exchange symbol list ──────────────────────────────────────────────

def check_symbol_list(data: bytes, min_rows: int = 1000,
                      known_checksums: Optional[set] = None) -> QualityResult:
    """Quality gate for /exchange-symbol-list/AU response."""
    csum = sha256(data)

    if known_checksums is not None and csum in known_checksums:
        return QualityResult.skip(f"duplicate checksum {csum[:12]}")

    parsed = _parse_json(data)
    if parsed is None:
        return QualityResult.quarantine("invalid_json", data)

    if not isinstance(parsed, list):
        return QualityResult.error("not_a_list", data)

    if len(parsed) < min_rows:
        return QualityResult.quarantine(
            f"symbol_list_too_few:{len(parsed)}_min_{min_rows}", data)

    return QualityResult.good(data, csum)
