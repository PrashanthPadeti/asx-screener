# Open findings from the source-to-target mapping

Findings surfaced while authoring the mapping documents, which are **not**
resolved and must not be treated as resolved because they are written down.

Each entry says what is established, what is not, and what would settle it.
A finding leaves this file when it is fixed or when it is deliberately
accepted with a reason — not when it stops being mentioned.

Nothing here has been changed in the pipeline. Authoring a mapping is a
read-only activity, and these are observations about code that is running in
production today.

---

## 1. Period metrics — window definitions, price watermark, adjustment basis

**Table:** `market.period_metrics` (23 columns)
**Writer:** `compute/engine/period_metrics_compute.py`
**Status:** OPEN — do not treat these metrics as production-ready

Three separate problems, all of which must be settled before any consumer
should rely on the values.

### 1a. Window names do not describe the windows

Every window is a count of **calendar days**, declared in `WINDOWS`:

| Column suffix | Calendar days | What the name suggests |
|---|---|---|
| `_1d`  | 3   | one day |
| `_1w`  | 7   | one week |
| `_1m`  | 35  | one month |
| `_3m`  | 100 | three months |
| `_6m`  | 185 | six months |
| `_1y`  | 365 | one year |
| `_52w` | 364 | 52 weeks |

`high_1d` is the highest high over roughly three calendar days, not today's
high. The 3-day choice is deliberate and commented ("catches Mon after a
weekend") — the **column name** is the problem, not the code.

`_1y` and `_52w` differ by a single calendar day, so they are near-duplicate
columns that will carry the same number except when that one day holds the
extremum, with nothing on the row saying which case applies.

**To settle:** decide, per window, whether the intended unit is calendar time
or trading sessions. If calendar, the names should say so. If sessions, the
implementation has to change — a calendar-day filter cannot express "the last
20 trading days" when sessions are missing.

### 1b. Windows anchor on the clock, not on the data

Each filter is `time >= CURRENT_DATE - <interval>` — measured from the day
the job runs, not from the newest price available.

When ingestion is behind, the short windows select no rows and the columns
are written `NULL`. That NULL is indistinguishable from "this instrument did
not trade", and the job still reports success because its population proof
counts **rows written**, not **columns populated**.

This is the same clock-versus-watermark shape as the incremental window
defect fixed in v11.2.77, in a different place.

**To settle:** anchor the windows on `MAX(time)` in `market.daily_prices`, or
refuse to compute when the watermark is behind, rather than emitting NULLs
that read as observations.

### 1c. Highs and lows are unadjusted

`high` and `low` come from `market.daily_prices` unchanged. A window spanning
a split mixes pre- and post-split prices, and the extremum is whichever side
is numerically larger. `market.splits` carries the ratio; nothing here
applies it.

This connects to the existing price-adjustment-basis work: returns already
run on unadjusted close.

**To settle:** as part of the adjustment-basis decision, not separately.

---

## 2. `market.short_interest` — no backend reader found

**Table:** `market.short_interest` (6 columns)
**Writers:** `scripts/asic/load_short_positions.py`,
`scripts/asic/transforms/transform_short.py`
**Status:** OPEN — **not** confirmed unused

### What is established

Every reference to `market.short_interest` in the **backend Python and SQL**
is a write or a comment. No module, route or SQL file selects from it.
Searched 9 November 2026.

Both surviving justifications for the table are stale:

- `transform_short.py` calls it *"the hypertable used by the existing
  short_pct join in build_screener_universe.py"*.
- `build_screener_universe.py` comments *"Prefer market.short_positions (has
  WoW change); fall back to short_interest."*

The lateral join beneath that second comment reads `market.short_positions`
and has **no fallback branch at all**.

### What is NOT established

- Whether anything outside the scanned Python/SQL reads it: database views,
  materialized views, grants, scheduled SQL, BI or notebook access, or a
  frontend path reaching it by another name.
- Whether it is retained deliberately for a reason not written down.

### Therefore

Do **not** present it as a user-facing feature — nothing serves it.
Do **not** remove it — the search covered backend code, not the database
catalog or the application surface.

**To settle:** check `pg_depend` / `information_schema.view_table_usage` for
database objects referencing it, and grep the frontend, before any decision
either way.

Contrast with the `market_snapshot.py` family, where all four tables have
verified consumers in `app/api/v1/routes/market.py`.

---

## 3. `market.capital_raises` — `DO NOTHING` means corrections never land

**Table:** `market.capital_raises`
**Writer:** `compute/engine/capital_raise_tracker.py`
**Status:** OPEN — write-correctness finding

The insert uses `ON CONFLICT ... DO NOTHING`. An existing row is left
untouched, so a corrected or re-parsed value for a key already present can
never replace what is stored. The first write wins permanently.

This matters more than usual here because the rows are parsed from
announcement **titles** by regular expression: a parser improvement cannot
repair history, only affect keys not yet seen.

**To settle:** decide whether first-write-wins is intended. If it is,
say so at the insert. If not, `DO UPDATE` on the fields that can legitimately
change, with the provenance of the correction recorded.

---

## 4. `market_cap` unit in the snapshot aggregates

**Tables:** `market.index_snapshots`, `market.sector_snapshots`,
`market.mover_snapshots`
**Writer:** `compute/engine/market_snapshot.py`
**Status:** OPEN — unconfirmed, one query settles it

`screener.universe.market_cap` is populated from
`market.valuation_snapshot.market_cap` (`build_screener_universe.py`, the
`vs.market_cap` entry in the SELECT list), which carries EODHD's
**full-currency-unit** figure. `build_screener_universe.py` calls it "raw
AUD" in its own comment, and the market-cap tier flags beside it test against
`50000000000` — consistent with raw AUD.

Two constants in `market_snapshot.py` only make sense against a **millions**
basis:

```
total_market_cap_bn = SUM(market_cap) / 1000.0
liquid_filter       = market_cap > 20
```

On a raw-AUD basis the first stores **thousands of AUD** in a column named
`_bn`, and the second admits anything above **twenty dollars** rather than
twenty million — which would make the liquidity filter on every mover panel
effectively inert.

**Not confirmed.** This rests on reading the SELECT-list alignment in a long
INSERT, which is exactly the kind of column-position reasoning that should
not be trusted on its own.

**To settle** — one query:

```sql
SELECT index_code, snapshot_date, stock_count, total_market_cap_bn
FROM market.index_snapshots
ORDER BY snapshot_date DESC, index_code
LIMIT 4;
```

ASX200's total market capitalisation is on the order of A$2 trillion.

- `total_market_cap_bn` ≈ **2000** → `market_cap` is in millions, the
  derivation is correct, and this finding closes.
- `total_market_cap_bn` ≈ **2,000,000,000** → it is thousands of AUD under a
  billions label, and the liquidity filter is inert. Both are defects.

---

## Tracking

| # | Finding | Table | Status |
|---|---|---|---|
| 1 | Window names, clock anchoring, unadjusted basis | `market.period_metrics` | OPEN |
| 2 | No backend reader found | `market.short_interest` | OPEN — not confirmed unused |
| 3 | `DO NOTHING` blocks corrections | `market.capital_raises` | OPEN |
| 4 | `market_cap` unit in aggregates | snapshot family | OPEN — one query settles it |
