"""
Audit Logger
============
Writes run manifests to the Raw Zone audit/ folder.
One JSON file per dataset per run: audit/{dataset}_{YYYY-MM-DD}_{HHMMSS}.json

Usage:
    logger = AuditLogger("fundamentals", run_date, audit_dir)
    logger.record(code="BHP", file="BHP.AU_2026-04-27.json.gz",
                  size_bytes=48221, checksum="sha256:abc...", status="ok")
    logger.finish(total=1978, success=1954, errors=12, quarantine=8, retried=4)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, dataset: str, run_date: str, audit_dir: Path):
        """
        dataset   : e.g. 'fundamentals', 'eod_prices_historical'
        run_date  : e.g. '2026-04-27'
        audit_dir : Path to raw zone audit/ folder
        """
        self.dataset   = dataset
        self.run_date  = run_date
        self.audit_dir = audit_dir
        self.started_at = datetime.now(timezone.utc)
        ts = self.started_at.strftime("%H%M%S")
        self.run_id = f"{dataset}_{run_date}_{ts}"
        self.files: list[dict] = []
        audit_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        code: str,
        file: str,
        status: str,              # 'ok', 'error', 'quarantine', 'retry', 'skip', 'duplicate'
        size_bytes: int = 0,
        checksum: str = "",
        reason: str = "",
    ) -> None:
        self.files.append({
            "code":       code,
            "file":       file,
            "status":     status,
            "size_bytes": size_bytes,
            "checksum":   f"sha256:{checksum}" if checksum else "",
            "reason":     reason,
        })

    def finish(
        self,
        total: int,
        success: int,
        errors: int,
        quarantine: int,
        retried: int,
        skipped: int = 0,
        duplicates: int = 0,
    ) -> Path:
        finished_at = datetime.now(timezone.utc)
        manifest = {
            "run_id":       self.run_id,
            "dataset":      self.dataset,
            "run_date":     self.run_date,
            "started_at":   self.started_at.isoformat(),
            "finished_at":  finished_at.isoformat(),
            "total_stocks": total,
            "success":      success,
            "errors":       errors,
            "quarantine":   quarantine,
            "retried":      retried,
            "skipped":      skipped,
            "duplicates":   duplicates,
            "files":        self.files,
        }
        out_path = self.audit_dir / f"{self.run_id}.json"
        out_path.write_text(json.dumps(manifest, indent=2))
        log.info(f"Audit manifest written → {out_path}")
        return out_path

    def summary_line(self) -> str:
        ok  = sum(1 for f in self.files if f["status"] == "ok")
        err = sum(1 for f in self.files if f["status"] == "error")
        qua = sum(1 for f in self.files if f["status"] == "quarantine")
        dup = sum(1 for f in self.files if f["status"] in ("skip", "duplicate"))
        return (f"run_id={self.run_id}  ok={ok}  errors={err}  "
                f"quarantine={qua}  skipped/dup={dup}")


# ─── Checksum registry (simple in-memory set, populated from audit files) ──────

def load_known_checksums(audit_dir: Path) -> set[str]:
    """
    Read all past audit manifests in audit_dir and return the set of known SHA-256
    checksums. Used for deduplication — skip re-downloading unchanged files.
    """
    checksums: set[str] = set()
    for f in audit_dir.glob("*.json"):
        try:
            manifest = json.loads(f.read_text())
            for entry in manifest.get("files", []):
                raw = entry.get("checksum", "")
                if raw.startswith("sha256:"):
                    checksums.add(raw[7:])
        except Exception:
            pass
    return checksums
