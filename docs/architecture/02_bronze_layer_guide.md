# Bronze Layer — Shared Raw Zone Guide

The Bronze Layer is the single source of truth for all raw downloaded data.
It is shared across every project. This document defines how it is organised,
how to read from it, and how new data sources are added.

---

## Location

```
/opt/data-lake/raw/
```

This path is accessible to all projects in read-only mode.
Only the `datalake_ingest` service account has write access.

---

## Directory Structure

```
/opt/data-lake/
├── raw/
│   │
│   ├── eodhd/                          ← EODHD provider directory
│   │   ├── exchange=AU/                ← ASX (Australian Securities Exchange)
│   │   │   ├── eod_prices/             ← End-of-day OHLCV prices
│   │   │   │   └── date=YYYY-MM-DD/    ← date partition
│   │   │   │       └── *.json.gz
│   │   │   ├── fundamentals/           ← Balance sheet, P&L, cashflow
│   │   │   │   └── date=YYYY-MM-DD/
│   │   │   ├── dividends/
│   │   │   ├── splits/
│   │   │   ├── exchange_symbols/       ← Full symbol list
│   │   │   ├── valuation_snapshot/     ← PE, PB, EV ratios (weekly refresh)
│   │   │   ├── audit/                  ← Download manifests (JSON)
│   │   │   ├── errors/                 ← Failed download records
│   │   │   └── quarantine/             ← Suspicious/malformed files
│   │   │
│   │   ├── exchange=NSE/               ← India NSE
│   │   │   └── (same sub-structure as AU)
│   │   │
│   │   ├── exchange=BSE/               ← India BSE
│   │   │   └── (same sub-structure as AU)
│   │   │
│   │   ├── exchange=NYSE/              ← US NYSE
│   │   │   └── (same sub-structure as AU)
│   │   │
│   │   ├── exchange=NASDAQ/            ← US NASDAQ
│   │   │   └── (same sub-structure as AU)
│   │   │
│   │   └── exchange=AMEX/              ← US AMEX
│   │       └── (same sub-structure as AU)
│   │
│   ├── asic/                           ← ASX Screener only
│   │   └── short_positions/
│   │       └── date=YYYY-MM-DD/
│   │           └── *.csv
│   │
│   ├── asx/                            ← ASX Screener only
│   │   └── announcements/
│   │       └── date=YYYY-MM-DD/
│   │
│   ├── nse-india/                      ← India Screener only
│   │   ├── bulk_deals/
│   │   │   └── date=YYYY-MM-DD/
│   │   ├── block_deals/
│   │   ├── fii_dii/                    ← FII/DII institutional flows
│   │   ├── promoter_holdings/          ← SEBI quarterly disclosure
│   │   └── circuit_breakers/           ← Daily circuit limit files
│   │
│   ├── sec/                            ← US Screener only
│   │   ├── 10-K/                       ← Annual filings
│   │   ├── 10-Q/                       ← Quarterly filings
│   │   ├── form4_insider/              ← Insider trade disclosures
│   │   └── 13f_institutional/          ← Quarterly institutional holdings
│   │
│   └── finra/                          ← US Screener only
│       └── short_interest/
│           └── date=YYYY-MM-DD/
│
├── ingestion_logs/                     ← Pipeline run logs (all jobs)
└── quarantine/                         ← Bad files held for manual review
```

---

## File Naming Convention

All downloaded files follow this pattern:

```
{dataset}_{exchange}_{date}_{run_id}.{ext}
```

Examples:
```
eod_prices_AU_2026-05-16_083002.json.gz
fundamentals_AU_2026-05-01_120000.json.gz
short_positions_AU_2026-05-14_090000.csv
fii_dii_NSE_2026-05-16_093000.csv
form4_insider_NYSE_2026-05-16_233500.json.gz
```

---

## Audit Manifests

Every download job writes an audit manifest alongside the data file:

```json
{
  "run_id": "eod_prices_incremental_2026-05-16_083002",
  "dataset": "eod_prices_incremental",
  "run_date": "2026-05-16",
  "started_at": "2026-05-16T08:30:02.573775+00:00",
  "finished_at": "2026-05-16T08:30:58.123456+00:00",
  "total_stocks": 2489,
  "success": 2489,
  "errors": 0,
  "quarantine": 0,
  "retried": 2,
  "skipped": 0,
  "duplicates": 0,
  "files": [
    {
      "code": "2026-05-16",
      "file": "/opt/data-lake/raw/eodhd/exchange=AU/eod_prices/date=2026-05-16/eod_prices_AU_2026-05-16_083002.json.gz",
      "status": "success",
      "size_bytes": 1482304,
      "checksum": "sha256:abc123..."
    }
  ]
}
```

Audit manifests are written to the `audit/` subdirectory of each exchange.
Manifests are the handshake between the Bronze download layer and each project's
staging ingestion — the staging job reads the manifest to know which files to load.

---

## Immutability Rules

1. **Never modify a file after it is written.** If a file has bad data, quarantine it and write a corrected replacement with a new `run_id` timestamp.
2. **Never delete raw files.** Retention policy: keep all files ≥ 7 years (regulatory minimum for financial data).
3. **Never overwrite.** If a file for the same date already exists, the download job skips it (idempotent) unless explicitly run with `--force`.
4. **File contents must match their checksum** as recorded in the audit manifest. Staging jobs validate this before loading.

---

## How Projects Read from Bronze

### Step 1 — Find the latest audit manifest

```python
import json
import os
from pathlib import Path

RAW_ZONE = Path("/opt/data-lake/raw")

def get_latest_manifest(exchange: str, dataset: str, run_date: str) -> dict:
    audit_dir = RAW_ZONE / "eodhd" / f"exchange={exchange}" / "audit"
    pattern   = f"{dataset}_{run_date}_*.json"
    manifests = sorted(audit_dir.glob(pattern))
    if not manifests:
        raise FileNotFoundError(f"No manifest for {exchange}/{dataset}/{run_date}")
    return json.loads(manifests[-1].read_text())
```

### Step 2 — Validate checksum and load file

```python
import gzip
import hashlib

def load_price_file(file_path: str, expected_checksum: str) -> list[dict]:
    data = Path(file_path).read_bytes()
    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != expected_checksum:
        raise ValueError(f"Checksum mismatch: {file_path}")
    return json.loads(gzip.decompress(data))
```

### Step 3 — Insert into project's own staging table

```python
# Each project inserts into its OWN staging schema
# ASX Screener:
cur.execute("INSERT INTO stg_au.eod_prices ...")

# India Screener:
cur.execute("INSERT INTO stg_in.eod_prices ...")

# US Screener:
cur.execute("INSERT INTO stg_us.eod_prices ...")
```

**Projects never read from each other's staging tables.**

---

## Adding a New Data Source

When a new data provider or dataset is needed:

1. **Create the directory** under `/opt/data-lake/raw/{provider}/{dataset}/`
2. **Write the download job** in `/opt/data-lake/jobs/download_{provider}_{dataset}.py`
3. **Write an audit manifest** using the standard schema above
4. **Add to the platform crontab** (not any project's crontab)
5. **Update this document** with the new directory path and provider details
6. **Notify all project teams** that the new Bronze source is available

Do not add the download job to a specific project's pipeline. The Bronze layer
download is always shared and always lives in `/opt/data-lake/jobs/`.

---

## Data Availability SLAs

| Exchange | Market Close (local) | Market Close (UTC) | Data Available (UTC) | Pipeline Trigger |
|---|---|---|---|---|
| ASX (AU) | 16:00 AEST (UTC+10) | 06:00 UTC | ~18:30 UTC | 18:30 UTC |
| NSE/BSE (IN) | 15:30 IST (UTC+5:30) | 10:00 UTC | ~13:00 UTC | 13:30 UTC |
| NYSE/NASDAQ (US) | 16:00 ET (UTC-4/-5) | 20:00/21:00 UTC | ~23:30 UTC | 23:30 UTC |

EODHD bulk EOD files are typically available 1-2 hours after market close.
Download jobs have a 3-retry policy with 5-minute backoff.

---

## Troubleshooting

### "file not found" in staging job

The audit manifest exists but the data file does not. Causes:
1. Download failed with HTTP 4xx/5xx — check `errors/` directory
2. EODHD API subscription expired — check `/opt/data-lake/jobs/check_api_status.py`
3. Disk full — check `df -h /opt/data-lake`

### HTTP 404 from EODHD

```bash
# Check API key and subscription status
EODHD_KEY=$(grep EODHD_API_KEY /opt/data-lake/.env | cut -d'=' -f2)
curl -s "https://eodhd.com/api/user?api_token=${EODHD_KEY}&fmt=json"
```

### Checksum mismatch

File was corrupted in transit. Re-download with `--force --date YYYY-MM-DD`.
The original file is automatically moved to `quarantine/` by the download job.

### Backfilling missing dates

```bash
# Re-run download for a specific date (safe — idempotent with --force)
cd /opt/data-lake
python jobs/download_eodhd_prices.py --exchange AU --date 2026-05-01 --force
```
