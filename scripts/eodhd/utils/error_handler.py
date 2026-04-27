"""
Error Handler
=============
Routes failed downloads to the correct Raw Zone subfolder:
  errors/     — HTTP 4xx, empty response, no data to retry
  quarantine/ — bad schema, symbol mismatch, needs manual review
  retry/      — HTTP 5xx, timeouts, rate limits (max 3 attempts)

Usage:
    handler = ErrorHandler(raw_base, run_date)
    handler.write_error(code, data, reason)
    handler.write_quarantine(code, data, reason)
    handler.write_retry(code, data, reason, attempt)
    if handler.retry_count(code) < MAX_RETRIES:
        ... retry ...
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

MAX_RETRIES = 3


class ErrorHandler:
    def __init__(self, exchange_dir: Path, run_date: str):
        """
        exchange_dir : e.g. /opt/asx-screener/data/raw/eodhd/exchange=AU
        run_date     : 'YYYY-MM-DD'
        """
        self.run_date   = run_date
        self.errors_dir     = exchange_dir / "errors"
        self.quarantine_dir = exchange_dir / "quarantine"
        self.retry_dir      = exchange_dir / "retry"
        for d in (self.errors_dir, self.quarantine_dir, self.retry_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── Errors (4xx / no data / empty) ────────────────────────────────────────

    def write_error(self, code: str, reason: str, data: bytes = b"") -> Path:
        filename = f"{code}.AU_{self.run_date}_{_slug(reason)}.json"
        path = self.errors_dir / filename
        _write_meta(path, code, reason, data)
        log.debug(f"  errors/ ← {filename}")
        return path

    # ── Quarantine (schema mismatch / manual review) ───────────────────────────

    def write_quarantine(self, code: str, reason: str, data: bytes = b"") -> Path:
        filename = f"{code}.AU_{self.run_date}_{_slug(reason)}.json.gz"
        path = self.quarantine_dir / filename
        _write_gzip_meta(path, code, reason, data)
        log.warning(f"  quarantine/ ← {code}: {reason}")
        return path

    # ── Retry (5xx / timeout) ─────────────────────────────────────────────────

    def write_retry(self, code: str, reason: str, attempt: int,
                    data: bytes = b"") -> Path:
        filename = f"{code}.AU_{self.run_date}_attempt{attempt}.json"
        path = self.retry_dir / filename
        _write_meta(path, code, reason, data, extra={"attempt": attempt})
        log.debug(f"  retry/ ← {filename} (attempt {attempt})")
        return path

    def retry_count(self, code: str) -> int:
        """How many retry files already exist for this code today."""
        return len(list(self.retry_dir.glob(f"{code}.AU_{self.run_date}_attempt*.json")))

    def should_retry(self, code: str) -> bool:
        return self.retry_count(code) < MAX_RETRIES


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slug(reason: str) -> str:
    return reason[:40].replace(" ", "_").replace("/", "_").replace(":", "_")


def _write_meta(path: Path, code: str, reason: str, data: bytes,
                extra: dict | None = None) -> None:
    meta = {
        "code":       code,
        "reason":     reason,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "data_bytes": len(data),
    }
    if extra:
        meta.update(extra)
    if data and len(data) < 10_000:
        try:
            meta["response_preview"] = data[:2000].decode("utf-8", errors="replace")
        except Exception:
            pass
    path.write_text(json.dumps(meta, indent=2))


def _write_gzip_meta(path: Path, code: str, reason: str, data: bytes) -> None:
    meta = {
        "code":       code,
        "reason":     reason,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "data_bytes": len(data),
    }
    payload = json.dumps(meta).encode() + b"\n" + (data or b"")
    with gzip.open(path, "wb") as f:
        f.write(payload)
