# ASX Screener — Data Pipeline Design (LLD)

> Version 1.0 | April 2026

---

## 1. Pipeline Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     DATA PIPELINE ARCHITECTURE                               │
│                      (Apache Airflow + Celery)                               │
│                                                                              │
│  TRIGGERS:                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Scheduled (Cron)     │   Event-Driven          │   Manual/On-demand │   │
│  │                       │                         │                    │   │
│  │  price_ingest         │   announcements_ingest  │   backfill_prices  │   │
│  │  4:15 PM AEST weekday │   every 5 min (market   │   recompute_stock  │   │
│  │                       │   hours: 9AM-8PM)       │   reload_financials│   │
│  │  compute_engine       │                         │                    │   │
│  │  5:30 PM AEST weekday │   asic_short_data       │                    │   │
│  │                       │   5:00 PM weekday        │                   │   │
│  │  alert_engine         │                         │                    │   │
│  │  6:30 PM AEST weekday │   dividend_events       │                    │   │
│  │                       │   As ASX announces      │                    │   │
│  │  financials_ingest    │                         │                    │   │
│  │  Quarterly (Feb/Aug)  │                         │                    │   │
│  │                       │                         │                    │   │
│  │  index_rebalance      │                         │                    │   │
│  │  Quarterly (Mar/Jun/  │                         │                    │   │
│  │  Sep/Dec)             │                         │                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  WORKER POOL: 4–16 Celery workers (auto-scales based on queue depth)        │
│  BROKER: Redis                                                               │
│  RESULT BACKEND: Redis                                                       │
│  MONITORING: Airflow Web UI + custom Slack/PagerDuty alerts                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. DAG 1 — price_ingest (Daily, 4:15 PM AEST)

```
TRIGGER: Cron "15 16 * * 1-5" (Australia/Sydney timezone)

price_ingest DAG
│
├── Task 1: validate_market_day
│   • Check if today is an ASX trading day (skip public holidays)
│   • Source: ASX trading calendar (pre-loaded into DB)
│   • If non-trading day → skip all downstream tasks
│   • Duration: < 1 second
│
├── Task 2: fetch_eod_prices (depends on: validate_market_day)
│   • Source: Yahoo Finance yfinance library
│   • Fetch all 2,200 ASX ticker symbols in batches of 100
│   • Retry logic: 3 retries with 30s backoff on HTTP errors
│   • Parallel: 10 concurrent batches (1,000 requests/batch)
│   • Fields: open, high, low, close, adj_close, volume
│   • Output: raw price DataFrame → staged in Redis (TTL: 2hr)
│   • Duration: ~5 minutes
│
├── Task 3: validate_prices (depends on: fetch_eod_prices)
│   • Check: no missing close prices for ASX 200 stocks
│   • Check: prices within ±30% of previous day (flag outliers)
│   • Check: volume > 0 for liquid stocks (flag suspensions)
│   • Action on failure: alert PagerDuty + use previous close fallback
│   • Output: validated_prices DataFrame + quality_report
│   • Duration: < 30 seconds
│
├── Task 4: calculate_vwap (depends on: fetch_eod_prices, parallel with validate)
│   • If intraday data available: compute true VWAP from tick data
│   • Otherwise: approximate VWAP = (H + L + C) / 3
│   • Duration: < 1 minute
│
├── Task 5: write_prices_to_db (depends on: validate_prices)
│   • Bulk INSERT INTO market.daily_prices using COPY (fastest method)
│   • Conflict handling: ON CONFLICT (time, asx_code) DO UPDATE
│   • Batch size: all stocks in single COPY statement
│   • Duration: ~30 seconds
│
├── Task 6: fetch_index_values (parallel with fetch_eod_prices)
│   • Fetch benchmark index values: XJO, XSO, XKO, XMO, XNO
│   •  (ASX 200, Small Ords, 100, 300, All Ords)
│   • Store in market.index_prices table
│   • Duration: < 1 minute
│
└── Task 7: signal_price_complete
    • Write pipeline_status: {dag: 'price_ingest', date: today, status: 'complete'}
    • Triggers downstream DAGs (compute_engine watches this)
    • Duration: < 1 second

TOTAL EXPECTED RUNTIME: 8–12 minutes
SLA: Must complete by 5:00 PM AEST
ALERT: PagerDuty if fails or exceeds 5:30 PM
```

---

## 3. DAG 2 — asic_short_data (Daily, 5:00 PM AEST)

```
TRIGGER: Cron "0 17 * * 1-5" (Australia/Sydney)
SOURCE: https://asic.gov.au/regulatory-resources/markets/short-selling/short-position-reports/

asic_short_data DAG
│
├── Task 1: download_short_report
│   • ASIC publishes daily short position CSV at ~3:30 PM AEST
│   • Download current day CSV
│   • URL pattern: /short-position-reports/YYYY-MM-DD/
│   • Retry: 5 retries (ASIC sometimes publishes late)
│   • Duration: < 1 minute
│
├── Task 2: parse_short_report
│   • Parse CSV: ASX code, gross short position, % of issued capital
│   • Map ASX codes to our companies table (handle code changes)
│   • Calculate short_interest_change vs previous day
│   • Duration: < 30 seconds
│
└── Task 3: write_short_data
    • Bulk INSERT INTO market.short_interest
    • Update computed_metrics.short_interest_pct (direct update, no recompute needed)
    • Duration: < 30 seconds

TOTAL EXPECTED RUNTIME: 3–5 minutes
```

---

## 4. DAG 3 — announcements_ingest (Continuous, Every 5 min)

```
TRIGGER: Cron "*/5 8-20 * * 1-5" (Australia/Sydney)
         (Active 8 AM – 8 PM weekdays)

announcements_ingest DAG
│
├── Task 1: poll_asx_api
│   • GET https://www.asx.com.au/asx/1/company/{code}/announcements
│     (or ASX official data service if licensed)
│   • Fetch announcements published since last poll timestamp
│   • For ASX200 stocks: poll every 5 min
│   • For other stocks: poll every 30 min (lower priority)
│   • Duration: < 1 minute
│
├── Task 2: filter_new_announcements
│   • Deduplicate against asx_announcements (by ASX announcement ID)
│   • Filter out already-processed announcements
│   • Duration: < 5 seconds
│
├── Task 3: classify_announcements (for each new announcement, parallel)
│   │
│   ├── Sub-task: download_document
│   │   • Download PDF from ASX CDN
│   │   • Store in S3: s3://asx-screener-documents/{asx_code}/{date}/{id}.pdf
│   │   • Extract text with PyMuPDF (first 3 pages for classification)
│   │
│   ├── Sub-task: classify_with_ai (Claude Haiku — fast, cheap)
│   │   Prompt: "Classify this ASX announcement. Return JSON:
│   │   {
│   │     category: one of [earnings, capital_raise, director_change,
│   │                       operational, material_event, dividend,
│   │                       agm, guidance, quarterly_activity, other],
│   │     sentiment: positive|negative|neutral,
│   │     materiality: 1-5,
│   │     is_price_sensitive: true|false,
│   │     summary: '2-3 sentence summary',
│   │     key_points: ['point1', 'point2', 'point3']
│   │   }"
│   │   • Cost per announcement: ~$0.001 (Haiku pricing)
│   │   • Duration: < 5 seconds
│   │
│   └── Sub-task: extract_capital_raise_details
│       • If category == capital_raise:
│         Parse: raise_type, raise_amount, price, discount %, new_shares
│       • Use regex patterns + Claude for structured extraction
│
├── Task 4: write_announcements
│   • INSERT INTO market.asx_announcements
│   • Batch write for all new announcements
│
├── Task 5: trigger_announcement_alerts
│   • Query users.alerts WHERE alert_type = 'new_announcement'
│     AND asx_code IN (new_announcements)
│   • Push to notification queue (Redis)
│
└── Task 6: push_to_websocket_feed
    • Publish to Redis pub/sub channel: 'feed:{asx_code}'
    • WebSocket server broadcasts to subscribed users in real-time

TOTAL EXPECTED RUNTIME: 1–3 minutes per run
```

---

## 5. DAG 4 — financials_ingest (Quarterly: Feb, May, Aug, Nov)

```
TRIGGER: Manual (triggered when new financial statements are available)
         OR: Cron quarterly after ASX results season ends

financials_ingest DAG
│
├── Task 1: identify_new_reports
│   • Check asx_announcements for new annual/half-year results
│   • Flag companies with report_date > last_financials_date
│   • Duration: < 1 minute
│
├── Task 2: fetch_financial_data (for each company, parallel batches)
│   │
│   ├── Source Option A (Phase 1): Scrape ASX announcement PDFs
│   │   • Download annual report PDF from ASX
│   │   • Use Claude claude-sonnet-4-6 to extract structured data:
│   │     - P&L: Revenue, EBITDA, EBIT, PAT, EPS
│   │     - Balance Sheet: Assets, Liabilities, Equity, Debt, Cash
│   │     - Cash Flow: CFO, CFI, CFF, FCF
│   │   • Prompt uses few-shot examples with Australian reporting format
│   │   • Manual QA for top 50 stocks (high priority accuracy)
│   │
│   └── Source Option B (Phase 2): Morningstar/Refinitiv API
│       • Structured JSON response
│       • No parsing needed
│       • Higher accuracy, faster
│
├── Task 3: validate_financials
│   • Check: Balance sheet balances (Assets = Liabilities + Equity)
│   • Check: Cash flow reconciles (Opening + Net change = Closing)
│   • Check: Revenue > 0 for non-early-stage companies
│   • Check: No extreme YoY changes (>500%) without prior announcement
│   • Flag anomalies for manual review
│   • Duration: < 5 minutes
│
├── Task 4: write_financials
│   • INSERT INTO financials.annual_pnl (or half_year_pnl)
│   • INSERT INTO financials.annual_balance_sheet
│   • INSERT INTO financials.annual_cashflow
│   • ON CONFLICT: update if restated
│   • Duration: < 5 minutes
│
├── Task 5: recompute_historical_growth_rates
│   • For updated companies: recompute all CAGR metrics
│   • 3Y, 5Y, 7Y, 10Y growth rates for revenue, profit, EPS, FCF
│   • These only change when new annual data lands
│   • Duration: ~30 minutes (full recalculation for updated stocks)
│
└── Task 6: trigger_full_compute
    • For updated companies: trigger compute_engine for today's metrics
    • Ensures screener reflects new financials immediately

TOTAL EXPECTED RUNTIME: 2–8 hours (depending on number of companies updated)
```

---

## 6. DAG 5 — index_rebalance (Quarterly)

```
TRIGGER: After ASX announces quarterly S&P/ASX index rebalancing (Mar/Jun/Sep/Dec)

index_rebalance DAG
│
├── Task 1: download_index_factsheets
│   • Download S&P/ASX index constituents from ASX website
│   • Parse: ASX20, ASX50, ASX100, ASX200, ASX300, All Ords, Small Ords
│
├── Task 2: update_index_flags
│   • UPDATE market.companies SET is_asx200 = TRUE/FALSE
│   • For additions/removals: create market.corporate_events record
│
└── Task 3: invalidate_affected_cache
    • Flush Redis keys for all changed companies
    • Companies joining/leaving indices often have significant interest

TOTAL EXPECTED RUNTIME: < 30 minutes
```

---

## 7. Pipeline Monitoring & Error Handling

### 7.1 Pipeline Health Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│              PIPELINE STATUS DASHBOARD (Internal)            │
│                                                              │
│  Last Run Summary:                                           │
│  ┌──────────────────┬──────────────┬────────┬─────────────┐ │
│  │ Pipeline         │ Last Run     │ Status │ Duration    │ │
│  ├──────────────────┼──────────────┼────────┼─────────────┤ │
│  │ price_ingest     │ 4:23 PM today│ ✅ OK  │ 8m 12s      │ │
│  │ asic_short_data  │ 5:02 PM today│ ✅ OK  │ 3m 45s      │ │
│  │ compute_engine   │ 5:38 PM today│ ✅ OK  │ 18m 30s     │ │
│  │ alert_engine     │ 6:34 PM today│ ✅ OK  │ 4m 12s      │ │
│  │ announcements    │ 8:15 PM today│ ✅ OK  │ 1m 30s/run  │ │
│  └──────────────────┴──────────────┴────────┴─────────────┘ │
│                                                              │
│  Data Freshness:                                             │
│  Prices:    2,187/2,200 stocks updated ✅ (13 suspended)    │
│  Short:     2,156/2,200 stocks ✅                           │
│  Metrics:   2,200/2,200 stocks computed ✅                  │
│  Alerts:    247 alerts evaluated, 12 triggered              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Error Handling Strategy

```python
# Every pipeline task follows this pattern:

class PipelineTask:
    max_retries = 3
    retry_delay = 60  # seconds

    def execute(self):
        try:
            result = self._run()
            self._write_status(status='success', result=result)
            return result

        except DataSourceUnavailableError as e:
            # External source down: retry up to max_retries
            self._log(f"Source unavailable: {e}")
            if self.retry_count < self.max_retries:
                raise AirflowException(f"Retry {self.retry_count}: {e}")
            else:
                # After all retries: use fallback
                self._use_fallback()
                self._alert_slack(severity='warning')

        except DataValidationError as e:
            # Data looks wrong: don't load it, alert human
            self._alert_pagerduty(severity='high', message=str(e))
            self._write_status(status='validation_failed', error=str(e))
            raise  # Stop pipeline — don't compute on bad data

        except DatabaseError as e:
            # DB error: always alert immediately
            self._alert_pagerduty(severity='critical', message=str(e))
            raise

    def _use_fallback(self):
        # For price_ingest: use previous day's close price
        # For short_data: use previous day's short interest
        # For compute: use yesterday's computed metrics
        pass
```

### 7.3 Data Quality Checks

```python
PRICE_QUALITY_RULES = [
    # Rule: No more than 10 missing ASX200 stocks
    {"check": "missing_asx200_count < 10",   "severity": "critical"},

    # Rule: No price movements > 50% without halt notice
    {"check": "max_daily_change_pct < 50",   "severity": "warning", "exclude_halted": True},

    # Rule: Volume should be > 0 for liquid stocks
    {"check": "zero_volume_large_cap < 5",   "severity": "warning"},

    # Rule: Total market cap within 5% of ASX reported figure
    {"check": "mcap_deviation_pct < 5",      "severity": "info"},
]

FINANCIAL_QUALITY_RULES = [
    # Rule: Balance sheet must balance
    {"check": "abs(assets - liabilities - equity) < 1",  "severity": "critical"},

    # Rule: Cash flow must reconcile
    {"check": "abs(closing_cash - opening_cash - net_change) < 1", "severity": "critical"},

    # Rule: Revenue should not be negative
    {"check": "revenue >= 0",                            "severity": "warning"},

    # Rule: EPS × shares ≈ Net Profit (within 5%)
    {"check": "eps_times_shares_vs_profit_pct < 5",      "severity": "info"},
]
```

---

## 8. Backfill & Recovery Procedures

### 8.1 Backfill Historical Prices

```python
# Run when: setting up new database, or recovering lost data

def backfill_prices(asx_code: str, start_date: date, end_date: date):
    """
    Backfill historical EOD prices for a stock.
    Uses Yahoo Finance max history (15 years).
    """
    # Fetch from Yahoo Finance
    ticker = yf.Ticker(f"{asx_code}.AX")
    hist = ticker.history(start=start_date, end=end_date, auto_adjust=True)

    # Write to TimescaleDB in batches
    batch_insert_prices(asx_code, hist)

    # Compute technical indicators for the backfill period
    compute_technical_indicators(asx_code, start_date, end_date)


# Airflow DAG: backfill_all_prices
# Run once on setup for all 2,200 stocks
# Estimated time: 6–12 hours (rate-limited by Yahoo Finance)
# Split into batches of 200 stocks per worker
```

### 8.2 Re-run Failed Compute

```python
# Manual trigger: recompute a specific stock for today
def recompute_stock(asx_code: str, date: date):
    """Recompute all metrics for a single stock. Used for error recovery."""
    engine = MetricComputeEngine()
    engine.compute_single_stock(asx_code, date)
    invalidate_redis_cache(asx_code)
    sync_elasticsearch(asx_code)
```

---

## 9. Pipeline Dependency Graph

```
ASX Market Close (4:00 PM)
        │
        ▼ [4:15 PM]
┌───────────────────┐     ┌──────────────────────┐
│   price_ingest    │     │  announcements_ingest │ ←── Runs continuously
│   (8-12 min)      │     │  (1-3 min per run)    │     every 5 min all day
└─────────┬─────────┘     └──────────────────────┘
          │
          │ [~4:25 PM]
          ├──────────────────────────────────┐
          │                                  │
          ▼ [5:00 PM]              ▼ [concurrent]
┌──────────────────┐        ┌──────────────────────┐
│  asic_short_data │        │   financials_ingest   │
│  (3-5 min)       │        │   (quarterly only)    │
└────────┬─────────┘        └──────────┬────────────┘
         │                             │
         └──────────┬──────────────────┘
                    │
                    ▼ [5:30 PM — waits for BOTH price + short data]
         ┌──────────────────────────────┐
         │      compute_engine          │
         │      (15-25 min)             │
         │                              │
         │  Stage 1: Technical (5 min)  │
         │  Stage 2: Valuation (4 min)  │
         │  Stage 3: Profitability (3 min) │
         │  Stage 4: Growth (3 min)     │
         │  Stage 5: Scores (3 min)     │
         │  Stage 6: ASX-specific (3 min) │
         │  Stage 7: Cache invalidate   │
         └──────────┬───────────────────┘
                    │
                    ▼ [~5:55 PM]
         ┌──────────────────────────────┐
         │      alert_engine            │
         │      (5-10 min)              │
         └──────────┬───────────────────┘
                    │
                    ▼ [~6:10 PM]
         ┌──────────────────────────────┐
         │   notification_dispatch      │
         │   Email + Push notifications │
         └──────────────────────────────┘

✅ ALL DATA FRESH AND ALERTS SENT BY ~6:15 PM AEST
```

---

## 10. Technology Configuration

### 10.1 Airflow Setup

```python
# airflow.cfg key settings
[core]
executor = CeleryExecutor
parallelism = 32              # Max concurrent tasks across all DAGs
max_active_tasks_per_dag = 16

[celery]
broker_url = redis://redis:6379/1
result_backend = redis://redis:6379/2
worker_concurrency = 8        # Tasks per worker process

[scheduler]
dag_dir_list_interval = 30    # Scan for new DAG files every 30s
min_file_process_interval = 30
```

### 10.2 Celery Workers

```yaml
# docker-compose scaling for workers
celery-worker:
  image: asx-screener-worker:latest
  deploy:
    replicas: 4               # 4 workers in Phase 1, scale to 16 in Phase 3
  environment:
    - CELERY_CONCURRENCY=8    # 8 threads per worker = 32 total task slots
  command: celery -A app.celery worker --loglevel=info --queues=default,priority
```

### 10.3 Redis Configuration

```
# Redis used for:
# DB 0: Application cache (prices, metrics, sessions)
# DB 1: Celery task broker
# DB 2: Celery result backend
# DB 3: WebSocket pub/sub channels

maxmemory 8gb
maxmemory-policy allkeys-lru   # Evict least recently used on memory pressure
```

---

*Next: See `04_Compute_Engine_LLD.md` for the metric computation engine*
