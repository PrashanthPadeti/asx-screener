# Pipeline Development Standards

Standards for writing ingestion, transform, and compute jobs across all projects.
Following these patterns ensures every pipeline is debuggable, resumable,
idempotent, and consistent with other projects on the platform.

---

## General Principles

1. **Idempotent** — running a pipeline twice for the same date produces the same result
2. **Resumable** — a failed step can be re-run without corrupting data
3. **Observable** — every run produces structured logs with counts and timings
4. **Isolated** — a pipeline never reads or writes to another project's schemas
5. **Datestamped** — every job accepts `--date YYYY-MM-DD` to target a specific date

---

## Standard Script Structure

Every pipeline script (download, staging load, transform, compute, build) follows
this structure:

```python
"""
{Script Name} — {Project Name}
================================
{One paragraph: what it does, what it reads, what it writes}

Usage:
    python {script_name}.py
    python {script_name}.py --date 2026-05-16
    python {script_name}.py --codes BHP CBA    (if applicable)
    python {script_name}.py --mode historical   (if applicable)
"""

import logging
import os
import argparse
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
DB_URL    = os.getenv("DATABASE_URL_SYNC")
DATA_LAKE = Path(os.getenv("DATA_LAKE_PATH", "/opt/data-lake/raw"))
MARKET    = "au"          # set to your market code: au / in / us

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="Target date YYYY-MM-DD")
    args = parser.parse_args()

    log.info(f"Starting {__name__} — date: {args.date}")

    conn = psycopg2.connect(
        DB_URL,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        options="-c statement_timeout=0",
    )
    try:
        # ... your logic here ...
        conn.commit()
        log.info(f"Done — {n:,} rows processed")
    except Exception:
        conn.rollback()
        log.exception("Fatal error — rolled back")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

---

## Logging Standards

### Progress Logging

For loops over stocks/rows, log progress every 50 or 100 items:

```python
BATCH_LOG_EVERY = 50

for i, code in enumerate(codes, 1):
    # ... process ...
    if i % BATCH_LOG_EVERY == 0 or i == len(codes):
        log.info(f"  [{i:4d}/{len(codes)}] {done} done | {skipped} skipped | {errors} errors")
```

### Summary Line

Every script ends with a summary line in a consistent format:

```python
# Single metric
log.info(f"DONE — {n:,} rows upserted into {SCHEMA}.{TABLE}")

# Multiple metrics
log.info(f"Done! {done:,} stocks | {skipped} skipped | {errors} errors | {rows:,} rows upserted")
```

### Section Dividers

Use dividers around major loops for log readability:

```python
DIVIDER = "─" * 60

log.info(DIVIDER)
log.info(f"Computing metrics — {len(codes):,} stocks | mode: {mode}")
log.info(DIVIDER)
# ... loop ...
log.info(DIVIDER)
log.info(f"Done! {done:,} | {skipped} skipped | {errors} errors")
```

### Log Level Usage

| Level | When to use |
|---|---|
| `INFO` | Normal progress, step start/end, row counts |
| `WARNING` | Missing data (expected occasionally), fallback used, slow query |
| `ERROR` | A stock failed to process (but pipeline continues) |
| `CRITICAL` | Fatal — pipeline must stop |

Never use `print()` in pipeline scripts. Always use the logger.

---

## Database Connection — Always Use Keepalives

Long-running queries (especially the screener.universe build) will hit SSL timeout
on managed databases without TCP keepalives:

```python
conn = psycopg2.connect(
    DB_URL,
    keepalives=1,
    keepalives_idle=30,      # send first keepalive after 30s idle
    keepalives_interval=10,  # retry keepalive every 10s
    keepalives_count=5,      # drop connection after 5 failures
    options="-c statement_timeout=0",  # no per-query timeout
)
```

This is mandatory for any script that runs a query longer than ~60 seconds.

---

## Idempotency Patterns

### Pattern 1 — UPSERT (preferred for all transform tables)

```sql
INSERT INTO mkt_au.daily_prices (asx_code, time, open, high, low, close, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (asx_code, time) DO UPDATE SET
    open   = EXCLUDED.open,
    high   = EXCLUDED.high,
    low    = EXCLUDED.low,
    close  = EXCLUDED.close,
    volume = EXCLUDED.volume;
```

Run it again → same result. Safe to re-run on failure.

### Pattern 2 — DELETE + INSERT (for staging tables)

```sql
DELETE FROM stg_au.eod_prices WHERE date = %(date)s;
INSERT INTO stg_au.eod_prices (...) VALUES ...;
```

Used when you want staging to reflect exactly what was in the Bronze file for a date.

### Pattern 3 — Conditional INSERT (for immutable history)

```sql
INSERT INTO fin_au.annual_pnl (asx_code, fiscal_year, revenue, ...)
VALUES (%s, %s, %s, ...)
ON CONFLICT (asx_code, fiscal_year) DO NOTHING;
```

Used when historical rows should never be overwritten once written.

---

## Error Handling in Stock Loops

When processing a list of stocks, a single bad stock must not stop the pipeline:

```python
done = skipped = errors = 0

for i, code in enumerate(codes, 1):
    try:
        rows = process_stock(cur, code, target_date)
        if rows == 0:
            skipped += 1
        else:
            done += 1
    except Exception as e:
        errors += 1
        log.error(f"[{code}] Failed: {e}")
        conn.rollback()
        # Start a new transaction for the next stock
        conn = get_new_connection()
        cur  = conn.cursor()

    if i % COMMIT_EVERY == 0:
        conn.commit()

conn.commit()
```

**Commit strategy**:
- Commit every `COMMIT_EVERY` stocks (default: 50) to avoid one giant transaction
- Never commit inside the individual stock try/except — commit at the batch level

---

## The Build Script (Golden Record)

The `build_screener_universe.py` pattern is the same for every screener project.

### Must-haves

1. **Single INSERT...SELECT** — one query, not a loop
2. **ON CONFLICT DO UPDATE SET** — must list every column explicitly
3. **DO UPDATE SET must be complete** — every column in INSERT must appear in DO UPDATE SET
4. **No bare `%` in SQL strings** — psycopg2 treats `%` as a parameter placeholder
   - Use `pct` in comments: `-- 10 pct below` not `-- 10% below`
5. **TCP keepalives** on connection (see above)
6. **Redis cache flush** after successful build

### DO UPDATE SET completeness check

A common bug: adding a column to INSERT and SELECT but forgetting DO UPDATE SET.
The column gets written on first INSERT but all subsequent runs leave it NULL
(because ON CONFLICT uses the UPDATE path, not the INSERT path).

Before every build script deployment, verify:
```bash
# Count should be identical in all three sections
grep -c "column_name" build_screener_universe.py
# Check INSERT list, SELECT list, and DO UPDATE SET separately
```

### Redis cache flush

```python
def _flush_screener_cache(market: str) -> None:
    try:
        import redis as sync_redis
        r = sync_redis.from_url(os.getenv("REDIS_URL"), ...)
        deleted = sum(1 for key in r.scan_iter(f"{market}:screener:*") if r.delete(key))
        log.info(f"Cache invalidated: {deleted} {market}:screener:* keys flushed")
    except Exception as e:
        log.warning(f"Redis cache flush skipped: {e}")
```

---

## Pipeline Orchestrator

Every project has a single `jobs/daily_pipeline.py` that orchestrates all steps
using `subprocess.run()`:

```python
def run(label: str, cmd: list[str]) -> None:
    log.info(f"▶  {label}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        log.error(f"✗  {label} failed (exit {result.returncode})")
        sys.exit(result.returncode)
    log.info(f"✓  {label} done")
```

### Step ordering

```
Step 1   Download Bronze files (read-only — may be skipped if already downloaded)
Step 2   Load staging (stg_{market}.*)
Step 3   Transform (mkt_{market}.daily_prices)
Step 4   Daily compute (mkt_{market}.computed_metrics)
Step 4b  Technical compute (mkt_{market}.daily_metrics)
Step 4c  Half-yearly or quarterly compute (market-dependent)
Step 4d  Period metrics
Step 5   Build screener.universe (screener_{market}.universe)
```

Steps 1-4 are fast (<2 min each). Step 5 (build screener.universe) takes 3-8 minutes
depending on universe size — that is expected.

---

## Backfill Procedures

### Backfill missing prices for one date

```bash
# Run Step 1 for a specific past date
python scripts/{provider}/v1/download_eod_prices.py --date 2026-05-01 --force

# Then run the full pipeline for that date
python jobs/daily_pipeline.py --date 2026-05-01
```

### Backfill daily_metrics for N days

```bash
python jobs/compute/compute_daily.py --days 30
```

### Full historical rebuild

```bash
# Only needed when adding a new column to yearly_metrics
python compute/engine/yearly_compute.py

# Then rebuild the Golden Record
python scripts/{provider}/v1/build_screener_universe.py
```

---

## Crontab Management

### Rules

1. Every project has its **own crontab line** — never combine two projects in one line
2. Every project writes to its **own log file** — `logs/daily_pipeline_{market}.log`
3. Pipeline steps are **not individually cron'd** — only the orchestrator is
4. Bronze download jobs are in the **data lake crontab**, not any project crontab

### Crontab template (adjust time for market close)

```cron
# {MARKET} Screener — daily pipeline
# Runs at {HH:MM UTC} Mon-Fri, ~{N} hours after market close
{MM} {HH} * * 1-5 cd /opt/{market}-screener && /opt/{market}-screener/venv/bin/python jobs/daily_pipeline.py >> /opt/{market}-screener/logs/daily_pipeline_{market}.log 2>&1
```

### Checking pipeline health

```bash
# See last 50 lines of today's run
tail -50 /opt/{market}-screener/logs/daily_pipeline_{market}.log

# See step outcomes only
grep -E "▶|✓|✗" /opt/{market}-screener/logs/daily_pipeline_{market}.log | tail -20

# See errors only
grep -i "error\|failed\|exception" /opt/{market}-screener/logs/daily_pipeline_{market}.log | tail -20
```

---

## Adding a New Column to screener.universe

Every new column requires changes in exactly 4 places. Missing any one causes bugs:

1. **Database migration** — `ALTER TABLE screener_{market}.universe ADD COLUMN ...`
2. **Build script INSERT list** — add column name to INSERT column list
3. **Build script SELECT body** — add the SQL expression
4. **Build script DO UPDATE SET** — add `col = EXCLUDED.col`
5. **Pydantic schema** — add `Optional[type] = None` field
6. **ALLOWED_FIELDS** in `screener.py` route — add entry with col, scale, type, label, unit, cat
7. **SORTABLE_COLS** (if numeric/sortable) — add entry

Common bug: forgetting step 4. Result: column is NULL for all existing rows after the next rebuild (because ON CONFLICT takes the UPDATE path, not INSERT path, for existing rows).

Verification after deployment:
```sql
SELECT COUNT(*) FILTER (WHERE new_column IS NOT NULL) AS populated,
       COUNT(*) AS total
FROM screener_{market}.universe;
```

Expected: `populated` > 0 and reasonable (non-zero data exists for this field).
