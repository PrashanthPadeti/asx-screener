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
**Status:** CONFIRMED 9 Nov 2026. Display is correct; the labels and the
liquidity filter are not.

### Confirmed against production

```
 index_code | snapshot_date | stock_count | total_market_cap_bn
------------+---------------+-------------+---------------------
 ASX200     | 2026-11-08    |         189 |       3315282273.66
 ASX300     | 2026-11-08    |         277 |       3411784977.37
```

3,315,282,273.66 cannot be billions — that would be 3.3 billion billion. It
is **thousands of AUD**: x 1,000 = A$3.32 trillion, the right order for the
ASX200. So `screener.universe.market_cap` is raw AUD, `SUM(...)/1000.0`
yields thousands, and the `_bn` suffix is wrong by a factor of 1,000,000.

### What is NOT broken: the displayed figure

Both frontend formatters divide correctly for a thousands basis:

- `frontend/app/market/page.tsx` `fmtCap`: `v / 1e9` -> `$3.3T`
- `frontend/app/indices/[code]/IndexDetailContent.tsx` `fmtIndexTotalCap`:
  `v / 1e6` -> "billions", then `/1e3` -> `$3.32T`

Customers see an accurate number. **Do not "fix" the stored value without
changing both formatters in the same release** — correcting the column
alone would make every displayed total wrong by a million.

### What IS wrong

1. **The column name.** `total_market_cap_bn` holds thousands. Any new
   consumer that reads the API field at its name is out by 1e6.
2. **The frontend comment is also wrong, and differently.**
   `IndexDetailContent.tsx:67` says *"stored in millions of AUD despite the
   `_bn` suffix"*. It is thousands, not millions — and the comment is
   inconsistent with the formula directly beneath it, since millions to
   billions is a divide by 1,000, not 1,000,000. The arithmetic is right
   for the wrong stated reason, which is the most fragile state to leave it
   in: the next person to trust the comment over the code will break it.
3. **The liquidity filter is inert.** `liquid_filter` requires
   `market_cap > 20`. On a raw-AUD basis that is **twenty dollars**, not
   twenty million, so every mover panel (GAINER/LOSER/ACTIVE/BUYING/
   SELLING) has effectively no market-cap floor. This is the one finding
   with a behavioural consequence rather than a labelling one: micro-caps
   can occupy the top-gainer panels the filter exists to keep them out of.

   **To confirm:**
   ```sql
   SELECT snapshot_type, count(*) AS rows,
          min(market_cap) AS smallest, max(market_cap) AS largest
   FROM market.mover_snapshots
   WHERE snapshot_date = (SELECT max(snapshot_date) FROM market.mover_snapshots)
   GROUP BY snapshot_type ORDER BY smallest;
   ```
   A `smallest` below 20,000,000 proves the floor is not operating as
   twenty million.

### Also visible in that output, and not yet explained

`stock_count` is **189** for ASX200 and **277** for ASX300, against
nominal 200 and 300. The filter is `<flag> = TRUE AND status = 'active'`,
so the shortfall is either suspended/delisted constituents or stale index
membership. `compute/engine/asx_indices.py` writes those flags and is
listed as NOT INDEPENDENTLY OBSERVABLE in the output-freshness registry
because it writes no timestamp — so a stale membership set would produce
exactly this and nothing would report it.

**To settle:** compare the flag counts against the published index
constituent lists, and give `asx_indices` an observable output.

---

## Tracking

| # | Finding | Table | Status |
|---|---|---|---|
| 1 | Window names, clock anchoring, unadjusted basis | `market.period_metrics` | OPEN |
| 2 | No backend reader found | `market.short_interest` | OPEN — not confirmed unused |
| 3 | `DO NOTHING` blocks corrections | `market.capital_raises` | OPEN |
| 4a | `_bn` column holds THOUSANDS (display is correct; fix needs both ends) | snapshot family | CONFIRMED |
| 4b | Frontend comment says "millions", also wrong, contradicts its own formula | `IndexDetailContent.tsx:67` | CONFIRMED |
| 4c | Liquidity filter `market_cap > 20` is twenty DOLLARS — panels have no floor | `market.mover_snapshots` | CONFIRMED by reading; one query shows the effect |
| 5 | `stock_count` 189/277 against nominal 200/300 | `market.index_snapshots` | OPEN — unexplained |
