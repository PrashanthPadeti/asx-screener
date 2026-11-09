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

   **CONFIRMED BY EFFECT, 9 Nov 2026.** Smallest constituent per panel on
   the latest snapshot:

   ```
   LOSER_3M / LOSER_1M        2,734,455    (A$2.7M)
   GAINER_1M / 1W / GAINER    5,060,275
   GAINER_3M                  6,342,829
   LOSER / LOSER_1W           8,877,334
   SELLING                   10,029,406
   BUYING                    12,201,436
   ACTIVE                    32,104,284
   ```

   Six of eleven panels contain a constituent below A$20M; the smallest is
   roughly seven times under the intended floor. If `market_cap > 20` were
   being read as twenty million, no `smallest` could fall below
   20,000,000. The filter is operating at twenty dollars.

   The same output independently confirms two properties this mapping
   derived from reading the code, which is worth recording because it
   means the document is describing the system that is running:
   - **11 snapshot types, none ending `_1D`** -- the 1D panels are
     declared in RETURN_PERIODS and never written.
   - `GAINER` matches `GAINER_1W` on both bounds (5,060,275 /
     4,464,807,936) and `LOSER` matches `LOSER_1W` (8,877,334 /
     637,415,808) -- the legacy aliases are exact duplicates.

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

## 6. `market.yearly_metrics` — 64 of 188 columns are not written by its only writer

**Table:** `market.yearly_metrics` (188 columns)
**Writer:** `compute/engine/yearly_compute.py` (the only writer)
**Status:** CONFIRMED 9 Nov 2026 — it is BOTH findings at once

The INSERT statement names **124 columns**. The table has **188**. The 64
absent ones include `peg_ratio`, `pcf_ratio`, `p_fcf_ratio`, `ev_fcf`,
`ncavps`, `pe_5y_avg`, `tbvps`, `dps_grossed_up`, `fcf_per_share`,
`ocf_per_share`, `revenue_per_share`, `net_debt_per_share`, `roae`, `roaa`,
`croic`, `pretax_margin`, `tax_rate_effective`, `inventory_turnover`,
`inventory_days`, `payables_days`, `cash_conversion_cycle`,
`revenue_per_employee`, `quick_ratio`, `cash_ratio`, `debt_to_ebitda`,
`net_debt_to_equity`, `equity_multiplier`, `beneish_m_score`,
`ebit_growth_1y`, both `revenue_growth_median_*`, every `*_cagr_7y` and
`*_cagr_10y` for net income / EPS / EBITDA, all five `price_cagr_*`,
`avg_roe_7y/10y`, `avg_roce_7y/10y`, `avg_operating_margin_10y`,
`avg_net_margin_10y`, `avg_fcf_margin_3y/5y`, `avg_eps_growth_10y`,
`avg_ebit_5y/10y`, `beta_1y/3y/5y`, `volatility_3y`, `sharpe_3y`,
`sortino_1y`, `max_drawdown_3y`, `calmar_ratio`, `alpha_1y/3y`, and
`avg_current_ratio_3y`.

### Why this is not merely "unused columns"

The same file already names this hazard. For five retired price-return
columns it writes explicit NULLs, and says why:

> Written as NULL rather than simply dropped from the write. The columns
> still exist in market.yearly_metrics, and leaving them unwritten would
> freeze the last values this engine produced -- the exact mechanism that
> kept return_2y/4y/6y/8y/9y alive in screener.universe after their
> producer was removed.

The 64 columns above are omitted from the write entirely, which is the
mechanism that comment identifies as the defect.

### The two outcomes

```sql
SELECT count(*) AS rows,
       count(peg_ratio) AS peg, count(quick_ratio) AS quick,
       count(croic) AS croic, count(beta_1y) AS beta_1y,
       count(price_cagr_3y) AS price_cagr_3y,
       count(avg_roe_7y) AS avg_roe_7y,
       count(beneish_m_score) AS beneish,
       max(computed_at)::date AS last_write
FROM market.yearly_metrics;
```

### Measured

```
rows   33,864      max(computed_at)  2026-11-08
peg_ratio            0     dead
beta_1y              0     dead
price_cagr_3y    3,405     10.1% populated
beneish_m_score  3,772     11.1%
croic            4,384     12.9%
quick_ratio      6,261     18.5%
avg_roe_7y       6,424     19.0%
```

The 64 columns are **two different defects wearing one shape**.

#### 6a. Dead schema — `peg_ratio`, `beta_1y` (and others at zero)

Never populated by anything. A consumer reading them gets NULL on every
row of every year. This is at least honest, and it explains the
long-standing observation that `beta_1y` is barren: nothing writes it.

Fix: populate or drop. Low urgency, no wrong answers served.

#### 6b. Frozen values under a fresh timestamp — the real defect

`quick_ratio`, `croic`, `avg_roe_7y`, `beneish_m_score`, `price_cagr_3y`
and others hold values on 10-19% of rows, written by a code path that no
longer runs.

The upsert's `DO UPDATE SET` lists only the 124 INSERT columns, so these
survive every rewrite untouched. `max(computed_at)` is today, meaning rows
are being restamped as freshly computed while carrying columns no current
run produced. **A reader has no way to date those values** — the row's own
timestamp asserts they are current.

**Proven, not inferred.** Of the 6,261 rows carrying a `quick_ratio`:

```
with_quick   oldest       newest       stamped_today
     6,261   2026-11-08   2026-11-08           6,261
```

Every one was rewritten by today's run. `min(computed_at)` equals
`max(computed_at)` equals today, so there is no population of untouched old
rows to explain the values: the rows were restamped as freshly computed
while carrying a column that run did not produce.

This is precisely the mechanism `yearly_compute.py` describes when it
explains why it writes explicit NULLs for five retired return columns:
leaving a column unwritten freezes the last value the engine produced. The
protection was applied to five columns and not to these.

### Census complete — 9 Nov 2026, 33,864 rows

**27 columns never populated** (dead schema): `alpha_1y`, `alpha_3y`,
`avg_eps_growth_10y`, `beta_1y`, `beta_3y`, `beta_5y`, `calmar_ratio`,
`cash_conversion_cycle`, `dps_grossed_up`, `eps_cagr_7y`, `eps_cagr_10y`,
`ev_fcf`, `fcf_per_share`, `max_drawdown_3y`, `ncavps`,
`net_debt_per_share`, `ocf_per_share`, `payables_days`, `pcf_ratio`,
`pe_5y_avg`, `peg_ratio`, `pretax_margin`, `revenue_per_employee`,
`revenue_per_share`, `sortino_1y`, `tax_rate_effective`, `tbvps`.

**37 columns frozen**, 969 to 7,656 rows (2.9% – 22.6%). Largest:
`p_fcf_ratio` 7,656; `volatility_3y` 6,575; `equity_multiplier` 6,505;
`avg_ebit_10y` 6,504; `avg_roe_10y` 6,429; `cash_ratio` 6,327; `roaa`
6,292; `roae` 6,290; `quick_ratio` 6,261; `ebit_growth_1y` 6,017.

### The frozen values were computed by a method this codebase rejected

Three window-length pairs are **inverted**:

```
avg_roe_10y    6,429  >  avg_roe_7y    6,424
avg_roce_10y   6,405  >  avg_roce_7y   6,404
avg_ebit_10y   6,504  >  avg_ebit_5y   6,502
```

Under `average_over` — the exactly-*n*-named-fiscal-years contract the
written `avg_*` columns use — a longer window is strictly harder to
satisfy, so a 10-year count **can never exceed** a 7-year count. This
ordering is only producible by the superseded `_avg` helper, which took the
last *n* list entries and dropped Nones before averaging.

That helper's own docstring records what it was replaced for:

> a company reporting 2016, 2019, 2022 had its "3-year average" computed
> across seven years … `avg_roe_3y` could be a single year's ROE labelled
> as three

So these are not merely undated values. They are values produced by a
method the project identified as defective and replaced — still sitting on
rows restamped as freshly computed.

### Severity

The two populations need different handling:

- **Dead (27)** — a consumer reads NULL everywhere. No wrong answer is
  served. Populate or drop; low urgency.
- **Frozen (37)** — a consumer reads a number computed by rejected logic,
  on up to 22.6% of rows, with the row's own `computed_at` asserting it is
  current. This is the one to fix, and the fix is the one the file already
  applies to five retired return columns: write explicit NULLs.

Fix: write explicit NULLs for every retired column, exactly as the five
return columns already are — not a schema drop, because dropping loses the
record that the column was once produced and does nothing for the rows
already served.

**None of the 64 should be treated as current.** The partial population is
the trap: a column that is NULL everywhere is obviously absent, while one
populated on 18% of rows looks like a metric with coverage gaps.

---

## 7. `market.computed_metrics` — dynamic write leaves stale values; 103 dead columns

**Table:** `market.computed_metrics` (147 columns)
**Writer:** `compute/engine/daily_compute.py` (the only writer)
**Status:** 7a OPEN (correctness) · 7b CONFIRMED (dead schema)

### 7a. The dynamic write — OPEN, and the live one

`upsert_metrics` builds BOTH the INSERT column list and the
`ON CONFLICT DO UPDATE SET` clause from `metrics.keys()`:

```python
cols       = ["time", "asx_code"] + list(metrics.keys())
update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in metrics.keys())
```

A metric whose guard fails is not written as NULL — it is **absent from the
statement**. On a re-run against the same `(time, asx_code)` the column is
never touched and keeps whatever the previous run wrote.

The project already knows this class of bug. `dividends.py` carries the
docstring *"The five dividend fields, always all five, never partially
written"*, and `daily_compute.py` names the incident: an omitted field
*"is how OEL carried a 480% grossed-up yield against a zero dividend"*.

The repair reached six columns — the five dividend fields and
`dividend_payout_ratio`, which was given an explicit `else: None`.
**Twenty-nine conditional columns still carry the defect**, including
`market_cap`, `pe_ratio`, `pb_ratio`, `roe`, `roa`, `roce` and every
margin.

The trigger is ordinary, not exotic. `fetch_latest_price` takes the newest
price row, so **every run while price ingestion is behind lands on the same
`price_date` and upserts into the same row** — which is exactly the
30 Oct – 6 Nov window.

**To settle:** whether any row currently holds a value from an earlier run.
Harder to measure than the `yearly_metrics` case, because a stale value is
indistinguishable from a correct one by inspection — the evidence would be
a column inconsistent with the row's own inputs. The structural fix does
not need the measurement: emit every key on every run, as the dividend
module already does.

### 7b. 103 of 147 columns are dead — CONFIRMED

Census 9 November 2026: **all 103 unwritten columns are zero**. Nothing has
ever written them. Unlike `market.yearly_metrics`, this table carries no
frozen values — every unwritten column is honestly NULL.

Dead columns include `roic`, `earnings_yield`, `ev_sales`,
`asset_turnover`, `altman_z_score`, `beneish_m_score`, `quick_ratio`,
`working_capital`, `fcf`, `debt_to_assets`, `short_interest_pct`, all four
`roe_avg_*` and all four `roce_avg_*`, and every `*_growth_5y/7y/10y`.

So the table is 147 columns with 44 producers.

**Consumer note:** the covering index `idx_cm_screener` INCLUDEs
`altman_z_score` and `short_interest_pct`, both dead. The index carries
permanently-NULL columns, and any screen filtering on them matches nothing.
This connects to the standing "presets still unanswerable" item.

---

## 8. INCIDENT 9 Nov 2026 — a census query OOM-killed PostgreSQL

**Not a finding about the pipeline.** A defect in the inventory work itself,
recorded here because the artifacts that caused it were committed to this
directory.

### What happened

A generated census ran seventeen `count(column)` aggregates in one statement
against `market.daily_metrics`, a TimescaleDB hypertable of several million
rows, on a 4 GB host. The backend reached 3.5 GB resident and the kernel
killed it:

```
Out of memory: Killed process 3218641 (postgres)
total-vm:5287312kB  anon-rss:3532396kB
```

PostgreSQL was down until restarted. Recovery: `systemctl start postgresql`,
then `smoke_primary_features.py` — 13 ok, 0 failed, version 11.2.77.

### Why it was not caught

The same pattern had run safely twice, against `market.yearly_metrics`
(39,454 rows) and `market.computed_metrics`. It was reused without checking
the size of the third table.

And the obvious guard would not have helped: **`pg_class.reltuples` is −1 for
both `market.daily_metrics` and `market.computed_metrics`**, because a
hypertable's parent relation holds no rows. A row-count check is blind on
exactly the tables large enough to matter — the same blind-instrument shape
as findings 1b, 4c and 6.

### What changed

- The three generated `.sql` census files are **deleted**. A raw diagnostic
  file in a repository is a loaded gun for whoever runs it next.
- Replaced by `backend/scripts/stm/census_unwritten.py`, which sizes the
  relation **including its inheritance children**, refuses above a 2 GiB
  ceiling unless `--force` is passed, counts **one column per statement**,
  and sets a `statement_timeout`.
- `market.daily_metrics`' 17 unwritten columns are recorded as **population
  deliberately unmeasured**, with the reason. That statement is accurate and
  costs the mapping nothing.

### The rule, restated

An instrument must not consume the resources of the system it observes.
Read-only is not harmless. A measurement is optional; an outage is not.

This is the second occurrence — a read-only query also OOM-killed production
on 28 October 2026.

---

## 9. `market.halfyearly_metrics` — halves grouped by a CALENDAR year

**Tables:** `market.halfyearly_metrics` (28 cols), `market.quarterly_metrics`
**Writers:** `compute/engine/halfyearly_compute.py`,
`scripts/eodhd/load_fundamentals.py`
**Status:** MEASURED 9 Nov 2026 — smaller than predicted, and my prediction was wrong

### Established from the code

`load_fundamentals.py` derives both key fields from the balance date:

    def fy_quarter(d: date) -> tuple[int, int]:
        """(fiscal_year, quarter) using calendar quarters."""
        q = (d.month - 1) // 3 + 1
        return d.year, q

So `market.quarterly_metrics.fiscal_year` is the **calendar year of the
balance date** and `.quarter` is the **calendar quarter**. Neither is the
company's own fiscal period.

`_agg_halves` then groups by `fiscal_year` and branches on how many quarters
that group holds:

- 3 or more → Q1+Q2 = H1, Q3+Q4 = H2 (summed)
- 2 or fewer → **half assigned by row position**: the first row present
  becomes `half = 1` whatever its quarter number

### Predicted, and explicitly not yet asserted

For a June-year-end issuer reporting half-yearly, the half ending 31 Dec
falls in `(N, Q4)` and the half ending 30 Jun in `(N+1, Q2)` — different
groups, each alone, each labelled `half = 1`.

If the data looks like that, then `half = 2` is rare, `revenue_growth_hoh`
is NULL (its lookup is `(fy-1, half 2)`), and `revenue_growth_yoy` pairs
periods **six months apart** under a year-on-year name.

**None of that is claimed until measured.** An earlier draft of this finding
asserted "its second half is published as its first", which was wrong: in a
four-quarter year Q2 belongs to H1. The demonstrated defect is **assignment
by row position rather than from verified reporting periods** — the rest is
hypothesis.

### Measured — and the prediction above was WRONG

Three queries were run. Both halves of the hypothesis failed.

**Wrong 1: `half = 2` is not rare.**

```
half | rows   | companies | with_hoh | with_yoy
   1 | 32,263 |     1,797 |   21,480 |   21,064
   2 | 31,026 |     1,792 |   22,352 |   21,182
```

**Wrong 2: a June-year-end half-yearly reporter does NOT split across
groups.** Because `fiscal_year` is the *calendar* year of the balance date,
a Jun/Dec reporter has both halves in the same group. That is the `{2,4}`
pattern — 4,658 company-years, 1,544 companies — and the positional
assignment is **correct** for it (Q2→H1, Q4→H2).

The cadence query also contradicts the premise: this is genuine quarterly
reporting at calendar quarter-ends, with 1,603–1,768 companies at each of
March, June, September and December. `quarter` is derived correctly, since
calendar quarter-end months map cleanly onto calendar quarters.

### What IS wrong

```
company-years                     32,263
  take the positional branch       6,858   21.3%
  MISASSIGNED                      1,827    5.7%

  {4}    1,110 cy  1,024 companies   Q4 -> H1   (Q4 belongs to H2)
  {3,4}    636 cy    579 companies   Q3 -> H1   (Q3 belongs to H2)
  {1,2}     59 cy     54 companies   Q2 -> H2   (Q2 belongs to H1)
  {3}       22 cy     22 companies   Q3 -> H1
```

Correct by coincidence in the same branch: `{2,4}` 4,658, `{1,3}` 256,
`{2}` 68, `{1}` 37, `{2,3}` 7, `{1,4}` 5.

The dominant case is a **single December period labelled H1**: 1,110
company-years across 1,024 companies. A row holding Jul–Dec is published as
the first half of the year.

### Consequence, and why it is not a coverage problem

HoH is populated on 43,832 of 63,289 rows (69%), so values are being served
rather than withheld. For a misassigned row both lookups mis-pair:

- `revenue_growth_hoh` looks up `(fy-1, half 2)`
- `revenue_growth_yoy` looks up `(fy-1, half)`

A `{4}`-only year labelled `half = 1` therefore pairs its December figure
against the *prior year's* H2 for "half-on-half" — twelve months apart — and
against the prior year's H1 for "year-on-year" — eighteen months apart.
Neither interval matches its column name.

### Severity

5.7% of company-years, reaching the surfaces listed below. Not a reason to
withhold the whole column set; it IS a reason to fix the grouping before
anyone relies on HoH for screening.

**Still unmeasured:** how many companies' *latest* half row — the one the
universe's `ORDER BY period_end_date DESC LIMIT 1` actually serves — comes
from a misassigned company-year. That is the number that decides whether
the two starred screener filters need containment now or at the fix.

```sql
WITH latest AS (
  SELECT DISTINCT ON (asx_code) asx_code, fiscal_year, half, period_end_date
  FROM market.halfyearly_metrics
  ORDER BY asx_code, period_end_date DESC
), q AS (
  SELECT asx_code, fiscal_year, array_agg(quarter ORDER BY quarter) AS qtrs
  FROM market.quarterly_metrics
  WHERE fiscal_year IS NOT NULL AND quarter IS NOT NULL
  GROUP BY asx_code, fiscal_year
)
SELECT q.qtrs, count(*) AS companies
FROM latest l JOIN q USING (asx_code, fiscal_year)
GROUP BY q.qtrs ORDER BY companies DESC;
```

Small tables; safe.

### Acceptance criterion for any fix, restated

Derive the half from the **quarter number or the period end date**, never
from row position. A sparse quarterly reporter must stay classified as
quarterly: `{3,4}` is a year with no first half, not a year whose first
half is Q3.

### Customer exposure — traced, and it is broad

| Surface | Columns |
|---|---|
| Screener filters, sortable, starred | `revenue_growth_hoh`, `net_income_growth_hoh` |
| Company page half-yearly table | `period_label`, margins, HoH and YoY growth |
| Company detail payload | all three HoH columns |
| AI context string | Revenue HoH and Net Income HoH |

`screener.universe.revenue_growth_hoh` / `net_income_growth_hoh` /
`eps_growth_hoh` are fed by a lateral join taking the **latest**
`period_end_date` per company.

### The measurement that decides containment

1. **Cadence** — which months companies report, and the quarter assigned:

       SELECT EXTRACT(MONTH FROM period_end_date)::int AS end_month, quarter,
              count(*) AS rows, count(DISTINCT asx_code) AS companies
       FROM market.quarterly_metrics WHERE period_end_date IS NOT NULL
       GROUP BY 1,2 ORDER BY 1,2;

2. **Grouping** — how many company-years take the positional branch:

       WITH y AS (SELECT asx_code, fiscal_year, count(*) AS n_q,
                         array_agg(quarter ORDER BY quarter) AS qtrs
                  FROM market.quarterly_metrics
                  WHERE fiscal_year IS NOT NULL AND quarter IS NOT NULL
                  GROUP BY asx_code, fiscal_year)
       SELECT n_q, qtrs, count(*) AS company_years,
              count(DISTINCT asx_code) AS companies
       FROM y GROUP BY n_q, qtrs ORDER BY n_q, qtrs;

3. **Exposure** — does `half = 2` exist, and is HoH populated:

       SELECT half, count(*) AS rows, count(DISTINCT asx_code) AS companies,
              count(revenue_growth_hoh) AS with_hoh,
              count(revenue_growth_yoy) AS with_yoy
       FROM market.halfyearly_metrics GROUP BY half ORDER BY half;

Both tables are small — 111,632 and 63,289 rows — so these are safe, unlike
the scan that caused finding 8.

Query 3 is the containment answer. If `with_hoh` is near zero the two
starred screener filters match almost nothing: a coverage problem, not wrong
numbers served. If `with_hoh` is substantial while `half = 2` is rare, the
served values need withholding until the grouping is corrected and
recomputed.

### Acceptance criterion for any fix

A sparse quarterly reporter must stay classified as quarterly. Missing
quarters produce an **incomplete half**, not a change of reporting cadence.

Establish also whether the source figures are standalone-period or
cumulative year-to-date before summing them. `parse_quarterly_pnl` takes
EODHD's `Income_Statement.quarterly` entries as-is, and nothing in the code
settles that question — if they are cumulative, every half-year sum in
`market.halfyearly_metrics` double-counts.

---

## 10. Insufficient history written as FALSE

**Table:** `market.weekly_metrics`
**Writer:** `compute/engine/weekly_compute.py`
**Status:** OPEN — affected signals listed; consumer impact to confirm

Four boolean signals are built as `bool(g(series, False))`, and `g()` maps
NaN to None, so a signal that **cannot be computed** is written `FALSE`:

| Signal | Needs | False when |
|---|---|---|
| `golden_cross` | `sma_40w` and its prior | under 41 weekly bars |
| `death_cross` | `sma_40w` and its prior | under 41 weekly bars |
| `above_sma10w` | `sma_10w` | under 10 weekly bars |
| `above_sma40w` | `sma_40w` | under 40 weekly bars |

`market.daily_metrics` writes **NULL** in the identical situation,
deliberately, so that a short series is not reported as a bearish reading.
The two tables disagree about what an uncomputable signal means.

**Consumer:** `build_screener_universe.py` reads `market.weekly_metrics`
(line 1343). Which of these four reach `screener.universe`, and whether any
screen filters on them, still needs confirming — that decides whether a
newly listed stock is being excluded from bullish screens by a measured
`false` rather than an honest unknown.

**Requirement:** unknown must stay distinguishable from a measured false.

## 11. `screener.universe` — ten columns that no statement writes

**Table:** `screener.universe` (376 columns)
**Writers:** nine, per the lineage graph — one INSERT, eight UPDATE-in-place
**Status:** CONFIRMED from code; production NULL counts pending
**Guard:** `backend/tests/test_universe_column_has_a_writer.py` (9 tests)

### How the question was asked

Three writer populations were extracted independently and reconciled against
the table's own column list, taken from a dated snapshot:

| Population | Count | How |
|---|---|---|
| builder `INSERT` column list | 341 | position-paired with its `SELECT` |
| builder `ON CONFLICT DO UPDATE SET` | 342 | all 341 plus the two it revokes |
| `UPDATE screener.universe` in engine modules | 25 update-only | AST literals, 6 modules |
| canonical writer's governed registry | 80 | `persisted_governed()` at runtime |

The union covers 366. Ten columns are claimed by nothing:

```
adl                        analyst_upside           dps_fy0
dps_fy1                    franking_credit_per_share listing_date
pay_date                   price_to_52w_high         shares_float
short_name
```

### Why none of them looked wrong

Every one has a written sibling immediately beside it:

| Unwritten | Written, in the same statement |
|---|---|
| `price_to_52w_high` | `price_to_52w_low` — `CASE WHEN dp52.low_52w > 0 THEN ...` |
| `analyst_upside` | `analyst_upside_pct` — computed from `ar.target_price` |
| `dps_fy0`, `dps_fy1` | `eps_fy0`, `eps_fy1` — `COALESCE(pnl0.eps, ym.eps)`, `pnl1.eps` |
| `franking_credit_per_share` | `franking_pct`, `grossed_up_yield` |
| `shares_float` | `shares_outstanding` — `ss.shares_outstanding` |
| `pay_date` | `ex_div_date` — `div_latest.ex_date` |
| `adl` | `obv`, `cmf_20` — both `dm.*` |
| `short_name` | `company_name` — `c.company_name` |

A reader checking "are dividends mapped?" sees `dps_ttm`, `franking_pct`,
`grossed_up_yield` and `ex_div_date` all present and concludes yes.

### Exposure

`price_to_52w_high` is live on three surfaces:

- a registered filter field — `screener.py:457`, label "Price / 52W High",
  category "Market Data", `"col": "u.price_to_52w_high"`
- a sort column — `screener.py:705`
- a response field — `schemas/screener.py:183`

A filter over an all-NULL column returns zero rows and reports no error. A
sort by one orders every row by NULL, which after v11.2.76 means membership
is preserved and the ordering is arbitrary — the correct behaviour for a
sort, and still not a ranking.

The other nine are not registered filter fields. `franking_credit_per_share`
and `dps_fy1` appear nowhere under `app/` or `frontend/src/`; the rest are
referenced, but whether those references read THIS column or a same-named
column on another table is not established and must not be assumed.

### Why the suite could not see it

`test_universe_insert_alignment.py` asserts the INSERT column list and the
SELECT expression list have equal arity. That is the right guard for a
positional shift and it is structurally blind to this defect: a column
present in the table and absent from every statement changes neither count.

The new guard asserts each of the four populations **before** the property,
because an extraction that silently returns nothing reports full coverage.
Four mutants were run and all four were killed; the one that matters is the
parse breaking, which fails `test_the_updater_population_did_not_collapse`
and names the seven modules rather than passing.

`KNOWN_UNWRITTEN` holds the ten and may only shrink. A column added to it
needs its own finding, because adding one is shipping a column the product
cannot populate.

### Pending

Production NULL counts for all ten, which decide whether `price_to_52w_high`
needs containment now or at the fix:

```sql
SELECT count(*) AS rows,
       count(short_name), count(listing_date),
       count(franking_credit_per_share), count(pay_date),
       count(dps_fy0), count(dps_fy1), count(analyst_upside),
       count(shares_float), count(price_to_52w_high), count(adl)
  FROM screener.universe;
```

2,566 rows, ordinary table, one statement: safe.

## Tracking

| # | Finding | Table | Status |
|---|---|---|---|
| 1 | Window names, clock anchoring, unadjusted basis | `market.period_metrics` | OPEN |
| 2 | No backend reader found | `market.short_interest` | OPEN — not confirmed unused |
| 3 | `DO NOTHING` blocks corrections | `market.capital_raises` | OPEN |
| 4a | `_bn` column holds THOUSANDS (display is correct; fix needs both ends) | snapshot family | CONFIRMED |
| 4b | Frontend comment says "millions", also wrong, contradicts its own formula | `IndexDetailContent.tsx:67` | CONFIRMED |
| 4c | Liquidity filter is twenty DOLLARS — smallest panel constituent A$2.7M | `market.mover_snapshots` | **CONFIRMED by effect** |
| 5 | `stock_count` 189/277 against nominal 200/300 | `market.index_snapshots` | OPEN — unexplained |
| 6a | Dead schema: `peg_ratio`, `beta_1y` never populated | `market.yearly_metrics` | CONFIRMED |
| 6b | Frozen values restamped today — all 6,261 rows `computed_at` = today | `market.yearly_metrics` | **PROVEN** |
| 6c | Census complete: 27 dead, 37 frozen | `market.yearly_metrics` | CONFIRMED |
| 6d | Frozen values produced by the SUPERSEDED `_avg` (window inversions prove it) | `market.yearly_metrics` | **CONFIRMED** |
| 7a | Dynamic write: 29 conditional columns keep prior values on re-run | `market.computed_metrics` | OPEN — structural fix needs no measurement |
| 7b | 103 of 147 columns dead (all zero); covering index includes two | `market.computed_metrics` | CONFIRMED |
| 8 | INCIDENT: census query OOM-killed PostgreSQL; .sql files removed, guarded script added | inventory tooling | CLOSED |
| 9 | Half assigned by row position: 1,827 of 32,263 company-years (5.7%) misassigned, 1,024 companies on `{4}` alone | `market.halfyearly_metrics` | MEASURED — fix before HoH is relied on |
| 10 | Insufficient history written as FALSE, not NULL | `market.weekly_metrics` | OPEN — 4 signals listed |
| 11 | Ten columns no statement writes; `price_to_52w_high` is a live filter, sort and response field | `screener.universe` | **CONFIRMED** from code — NULL counts pending |
