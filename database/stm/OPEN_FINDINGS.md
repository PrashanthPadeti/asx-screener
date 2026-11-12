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

### Latest-row exposure — MEASURED 11 Nov 2026

The 5.7% is a rate over company-YEARS of history. What reaches a customer is
the LATEST half row per company, and that is a different and much smaller
number:

```
 latest_matched | misassigned | in_universe | served_misassigned | served_with_a_value
           1797 |          19 |        1797 |                 19 |                  10
```

**Ten companies** serve an HoH value drawn from a misassigned company-year.
Not 5.7% of the customer base: ten rows.

The historical rate did not transfer because the misassigning patterns --
`{4}`, `{3,4}`, `{1,2}`, `{3}` -- are concentrated in older, sparser years.
A company reporting all four quarters today lands on `{1,2,3,4}` or `{2,4}`,
and the positional assignment is correct for those.

**What this measurement does NOT establish.** 1,797 of 2,567 universe rows
matched a quarter set for their latest half's fiscal year. The other 770
have no quarterly rows for that year, so their assignment is UNVERIFIED by
this method, not verified correct. The ten is a floor on exposure, not a
ceiling.

### Containment

Ten rows is small enough that withholding is cheap and large enough that
serving a mis-paired interval is not acceptable. The withholding rule must
be the general one, not a list of ten codes: derive the half from the
quarter number or the period end date, and withhold HoH wherever the derived
half disagrees with the stored one. A hardcoded list goes stale on the next
ingest; the rule does not.

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

### FIXED 12 Nov 2026

The defect was deeper than the `False` default, and fixing only that would
have changed nothing. In pandas a comparison against NaN yields **False**,
not NaN, so `sma_10 > sma_40` had already collapsed unknown into false
before the default was ever consulted.

Each signal is now masked on its inputs being present, and converted with a
None-preserving helper rather than `bool()` — because `bool(None)` is False
and would restore the conflation one line later. All four columns are
nullable with no default, so the schema could always hold the answer.

Four mutants, four killed: the original `bool(g(..., False))` reinstated,
the mask removed, `bool()` reintroduced in the helper, and a mask made too
wide so that computable signals were withheld.

### Consumer question — ANSWERED: none of them reach the customer

`build_screener_universe.py` joins `market.weekly_metrics` as `wm`, and
**no column in the universe's SELECT reads from it**. The universe's own
`golden_cross`, `death_cross`, `above_sma50` and `above_sma200` all come
from `dm` — `market.daily_metrics`.

So no newly listed company was excluded from a bullish screen *by this
defect*. The false readings were real and were stored, but they stopped at
the Gold layer. That is luck rather than design: the weekly fallback that
would have carried them was removed for an unrelated reason (a 14-month
`rsi_14` being served as a 14-day one), and the join was left behind.

**Requirement, met:** unknown stays distinguishable from a measured false —
in `market.weekly_metrics`.

> #### CORRECTION, 13 Nov 2026
>
> The sentence above originally continued "…come from `dm` —
> `market.daily_metrics` — **which already writes NULL for an uncomputable
> signal**." That is **false**, and it was asserted without being checked.
>
> `technical_compute.py:570-578` writes the daily signals as plain pandas
> comparisons:
>
> ```python
> df["above_sma200"] = c > df["sma_200"]
> df["golden_cross"] = (df["sma_50"] > df["sma_200"]) & (...)
> df["new_52w_high"] = (h >= df["high_52w"]) & (h > h.shift(1))
> ```
>
> A comparison against NaN yields **False**, not NaN — the same trap this
> finding is about — and `_v()` converts `np.bool_(False)` to `False`
> rather than to None. So `market.daily_metrics` carries measured falses in
> exactly the situation `market.weekly_metrics` did, and unlike the weekly
> ones **these reach the customer**, because the universe reads four of
> them straight from `dm`.
>
> Recorded as finding 15. The claim was comforting, load-bearing, and
> wrong: it is what let this finding close as "none of them reach the
> customer" when a larger instance of the same defect sat one table over.

### The fix is forward-only, and that is acceptable here

`weekly_pipeline.py` step 6 computes weekly metrics **incrementally, last
week** (`0 21 * * 0`, Sunday 21:00 UTC). The conflict path does reassign all
four signals from `EXCLUDED`, so a recomputed week replaces a stored `false`
with `NULL` — but only the weeks a run recomputes.

Every company's early history therefore keeps its stored falses: roughly the
first 40 weekly rows per company for `golden_cross`, `death_cross` and
`above_sma40w`, the first 10 for `above_sma10w`. Deployed 12 Nov 2026; the
first corrected week is the run of Sunday 15 Nov 2026.

This is left as data hygiene rather than a repair because the exposure
answer above holds for the historical rows too: nothing under `app/`
references `weekly_metrics` at all, and the one statement that joins it
reads no column from it (finding 14). If any reader is ever wired to this
table, the backfill becomes a precondition, not an option.

## 11. `screener.universe` — ten columns that no statement writes

**Table:** `screener.universe` (376 columns)
**Writers:** nine, per the lineage graph — one INSERT, eight UPDATE-in-place
**Status:** MEASURED 10 Nov 2026 — nine are empty as stated, and the tenth is WORSE
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

### Measured, 2,566 rows

```
rows  short_name listing_date fcps pay_date dps_fy0 dps_fy1
2566           0            0    0        0       0       0

      analyst_upside shares_float price_to_52w_high  adl
                   0            0              2290    0
```

Nine of the ten are empty for every company, as stated.

### `price_to_52w_high` — the claim above was WRONG, and the truth is worse

It is populated on 2,290 of 2,566 rows. No writer was missed: there is none.
`monthly_compute.py` writes a same-named column on `market.monthly_metrics`,
which is a different column.

Migration `052_screener_universe_tier3_inline_calcs.sql` adds six columns and
backfills none of them. The other five — `price_to_52w_low`, `fcf_per_share`,
`ocf_per_share`, `revenue_per_share`, `working_capital` — are all in the
builder's INSERT. `price_to_52w_high` is the one that was left out when the
batch was wired up.

The consequence follows from the builder's own comment:

> The upsert can only add or update — it never removes.

The statement is `INSERT ... ON CONFLICT DO UPDATE`, and this column is in
neither the insert list nor the SET list. An existing row's value is
therefore **never touched by any run**. It is frozen at whatever wrote it,
whenever that was, for as long as the row survives — and the only DELETE in
the job removes excluded security types, not ordinary companies.

2,290 frozen and 276 NULL is the shape that predicts: a population carried
from an older build, plus the companies listed since, which take the NULL an
omitted column gets on first insert.

So this is not a dead column. It is a **stale value served as current**
through a registered filter, a sort column and a response field — which is
strictly worse than empty, because empty is visible and stale is not.

A filter over it does return rows. They are ranked and selected on a ratio
computed against a 52-week high from an unknown earlier date, beside a
`price` and a `high_52w` in the same row that were refreshed today.

### FIXED 10 Nov 2026

Three lines in `build_screener_universe.py`: the column at position 247 of
the INSERT list, directly after `price_to_52w_low`; the SELECT expression at
the same position, since the two lists bind by position and nothing else;
and the conflict assignment.

```sql
CASE WHEN dp52.high_52w > 0
     THEN ROUND((dp.close / dp52.high_52w)::numeric, 4) END AS price_to_52w_high
...
price_to_52w_high       = EXCLUDED.price_to_52w_high,
```

The `CASE` yields NULL when the high is absent, and the assignment takes
`EXCLUDED` plainly, so a row whose high disappears has its stale ratio
REPLACED by NULL rather than keeping it. A `COALESCE` with the stored value
would have preserved the stale number whenever the new one could not be
computed — the same defect in a form that looks like care.

The guard is `test_universe_upsert_refreshes_every_column`, and it is
deliberately not about this column: it asserts over all 342 that every
inserted column is reassigned on conflict, that the only unlisted
assignments are the two the builder deliberately revokes, that every
assignment takes `EXCLUDED` plainly, that no column is assigned twice, and
that every ratio guards its denominator. Seven mutants, seven killed.

**Not yet proven in production.** A green test shows the statement changed;
it does not show a value changed. `RELEASE_EVIDENCE_price_to_52w_high.md`
carries the four acceptance steps, including the one that matters most: the
builder upserts `companies_current` minus excluded types, so a universe row
outside that population is touched by no run and keeps its frozen value.
That count must be zero or explained before this finding closes.

The other nine columns are unchanged and still unwritten.

### Why the guard still reported it correctly

`test_universe_column_has_a_writer` asserts that a statement writes each
column. It does not assert that the column is NULL, and it should not: those
are different properties and only the first is checkable from the code. The
measurement is what distinguishes "empty" from "frozen", and the finding was
written before the measurement came back.

This is the same lesson as the yearly_metrics census — 37 columns there were
not dead but frozen, restamped `computed_at` by a writer that no longer
produced them. A column with no writer and a non-zero count is a staleness
finding, not a coverage one.

### Pending

How far the frozen ratio has drifted from the row it sits in. `price` and
`high_52w` are refreshed every run, so recomputing the ratio from the same
row and differencing it measures the staleness directly:

```sql
SELECT count(*) AS have_stored,
       count(*) FILTER (
         WHERE abs(price_to_52w_high - (price / NULLIF(high_52w, 0))) > 0.01
       ) AS differs_gt_1pct,
       max(abs(price_to_52w_high - (price / NULLIF(high_52w, 0)))) AS max_diff
  FROM screener.universe
 WHERE price_to_52w_high IS NOT NULL
   AND price IS NOT NULL AND high_52w > 0;
```

2,566 rows, ordinary table, one statement: safe.

Containment is not a question of whether to fix it but of which fix. Wiring
the column into the INSERT and the SET list corrects every row on the next
run and is four lines. Until then the stored value should not be served:
a frozen ratio presented beside a current price is a wrong answer, where a
NULL would have been an honest one.

## 12. Market-cap tier flags report unknown as six measured falses

**Table:** `screener.universe`
**Writer:** `scripts/eodhd/v2/build_screener_universe.py` (INSERT)
**Status:** MEASURED 10 Nov 2026 — 641 of 2,566 rows (25.0%)

### The mechanism

The six tier flags and the tier label are computed from the same input and
disagree about what an absent input means:

```sql
COALESCE(vs.market_cap >= 50000000000, FALSE)  AS is_mega
COALESCE(vs.market_cap >= 10000000000
     AND vs.market_cap <  50000000000, FALSE)  AS is_large
...
CASE WHEN vs.market_cap >= 50000000000 THEN 'mega'
     ...
     WHEN vs.market_cap > 0            THEN 'nano'
     ELSE NULL END                             AS market_cap_tier
```

`market_cap_tier` returns NULL for an unknown cap, which is honest. The six
flags wrap the comparison in `COALESCE(..., FALSE)`, so a NULL market cap is
written as a measured `false` on all six.

The schema removes the alternative: all six are `NOT NULL DEFAULT false`, so
an honest unknown is not storable in them even if the expression wanted to
write one.

### Measured

```
rows  cap_null  cap_not_positive  tier_null  no_tier_flag
2566       639                 2        641           641
```

641 companies — 25.0% of the universe — carry six falses and a NULL tier.
The two counts agree exactly, which confirms the flags and the label are
computed from the same input and differ only in how they report its absence.

### Consequence, and why it is narrower than finding 10

Three consumers read these flags, and all three test `= TRUE`:

- `app/api/v1/routes/market.py:109-118` — cap-tier filter
- `app/api/v1/routes/market.py:326-331` — the same filter on a second endpoint
- `app/api/v1/routes/admin.py:1928-1929`

`= TRUE` is the safe direction. No company is reported as belonging to a tier
it does not belong to. What happens instead is that a quarter of the universe
is invisible to every tier filter, and there is no "unknown" tier to ask for,
so the omission is not visible from the API either. Asking for all six tiers
in turn returns 1,925 of 2,566 companies with nothing stating that 641 were
not classified rather than not matching.

None of the seven columns is a registered screener field in `ALLOWED_FIELDS`,
so the customer-facing screener does not expose them directly.

A consumer written as `NOT is_mega` — none exists today — would read all 641
as positively not-mega, and that is the shape finding 10 describes.

### Why market_cap is absent for 639 rows

Not established. `vs.market_cap` comes from `market.valuation_snapshot`,
joined on its primary key, so the absence is in the source rather than the
join. Whether those are suspended securities, recent listings, or companies
whose shares-outstanding never arrived is a separate question from how the
absence is reported, and is not answered here.

### FIXED 11 Nov 2026, and reconciled

All three consumers now read `market_cap_tier` from one declaration, and
`unknown` is a selectable tier so those companies are askable-for rather
than silently absent.

```
 tier      | count
 nano      |   993
 (unknown) |   642
 micro     |   449
 small     |   289
 mid       |   130
 large     |    48
 mega      |    16
                2567   = screener.universe
```

The seven partition the table exactly. No row is unaccounted for, and the
unknown group is 25.0% of the universe — the figure that was previously
reachable through no filter at all.

Found while fixing it, and recorded as its own defect: `asx300` in
`market.py` was `market_cap >= 300` with a comment reading "≥$300M".
`screener.universe.market_cap` is RAW AUD, so the predicate meant three
hundred dollars against a query that already required `market_cap > 0`. It
admitted essentially the whole universe while presenting as a large-cap
filter.

The screener route had it right all along: `ALLOWED_FIELDS["market_cap"]`
carries `"scale": 1_000_000` and `parsed_query` applies it, so its 22
presets using values of 50 to 500 are correct. Two routes over one column
disagreed about its unit, and only one of them scaled.

### Requirement

The same one finding 10 states: unknown must stay distinguishable from a
measured false. Here the type system is in the way, so the fix is either a
nullable flag or — more simply — consumers reading `market_cap_tier`, which
already carries the distinction, and the flags being documented as a
derived convenience that cannot express it.

## 13. A derived metric escapes the governance of its input

**Tables:** `screener.universe`, `market.daily_metrics`
**Status:** CONFIRMED in production 11 Nov 2026, 520 rows
**Source:** the acceptance run for finding 11

`week_52_high` is governed. It stores into `high_52w`, and when the series
is too short the canonical writer withholds it and records a reason:

> the series spans 196 days; a 52-week extreme needs 351

`price_to_52w_high`, `price_to_52w_low`, `new_52w_high` and `new_52w_low`
are **functions of that extreme and are not governed**, because assessing a
derived metric from its input's assessment needs a producer that does not
exist. `compute/engine/metric_states.py:383-397` already records this gap in
writing.

So the canonical commit nulls the extreme, the derivative keeps the
builder's number, and the row is published and served:

```
 week_52_high state                         | rows | high_present | ratio_present
 (supplied)                                 | 2047 |         1891 |          1891
 insufficient_data / insufficient_history   |  393 |            0 |           393
 … 9 further spans (195, 176, 154, 91 days) |   57 |            0 |            57
```

In every withheld group `high_present` is 0 and `ratio_present` equals the
row count. The derivative survives in **100%** of the rows where its input
was withheld. That is not a correlation.

### What the customer sees

The screener renders **52W High: —** beside **Price / 52W High: 0.9972**,
and that 0.9972 was computed from a `MAX(high)` over 196 days. A six-month
ratio labelled as a 52-week one, carrying a current run's attribution.

This is worse than the staleness it replaced. A stale value is at least a
real 52-week ratio from an earlier date; this is a ratio over a window
nobody named, presented as current and precise.

**The absence was established, stated, and destroyed one column over.**

### The mechanism was not what this finding said it was

Written as "a derived metric escapes the governance of its input", which
implied the fix was a derived-metric producer. Reading the statement on
13 Nov 2026 found something narrower and more fixable.

The builder computed the extreme a **second time**:

```sql
-- build_screener_universe.py, the dp52 lateral
SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
  FROM market.daily_prices
 WHERE asx_code = c.asx_code
   AND time >= NOW() - INTERVAL '365 days'
```

`market.daily_metrics.high_52w` already existed and was governed. Two
definitions of one quantity, disagreeing three ways:

| | governed producer | `dp52` |
|---|---|---|
| coverage | blank until the series spans 365 days, reason recorded | `MAX` over whatever rows exist |
| price basis | split-**adjusted** (`*_adj` feed the indicators) | **raw** `high` — a real difference, measured to produce none |
| state | `window_states` entry | nothing |

So `high_present = 0` beside `ratio_present` = every row was never a
correlation to explain: **the two columns never came from the same
computation.** The canonical commit withheld one and had no opinion about
the other.

And the two flags were a hand-written `ELSE FALSE`, publishing "this stock
did not make a new 52-week high" wherever the high was unknown.

### MEASURED 13 Nov 2026, before the fix

```
 governed extreme PRESENT    1,895 rows   ratio present on 1,895
 governed extreme WITHHELD     674 rows   ratio present on 519
                                          new_52w_high FALSE on 659
                                          new_52w_high TRUE  on  15
                                          new_52w_high NULL  on   0
 the two producers, where both values exist
                                          0 rows differing by >1%
                                          max difference 0.0001
```

The coverage defect is real and sizeable. **519 ratios and 674 flags were
published from a window that did not span 52 weeks**, and 15 of those rows
claim a **new** 52-week high measured against a six-month maximum. `NULL`
appears zero times in 2,569 rows, which is the whole point: the column
could never say "we do not know".

#### The price-basis claim is WITHDRAWN

An earlier version of this finding stated that the raw-vs-adjusted
difference was "the worse half", that `dp52` came out "ten times too
small", and that a stock at its 52-week high published at 10% of it. **The
measurement does not support that, and it was written before measuring.**

The mechanism is real — `technical_compute`'s indicators are fed by the
`*_adj` columns and `dp52` read raw `high` — but where both values exist
the two agree to rounding. A split restates the dates *before* it, so raw
and adjusted agree on every date after the most recent split.

112 companies split inside the window and all 112 publish a ratio, so the
cohort is not empty. What is not established is where those 112 sit: Q3
can only see rows whose governed extreme is present, so its silence may
mean the cohort is concentrated in the withheld group rather than that the
basis never mattered. Q6 of `measure_shadow_52w_extreme.py` settles it and
has not yet been run.

Recorded as a basis difference, not as a demonstrated error. It does not
change the fix: two producers for one quantity is a defect because the row
contradicts itself, not because the numbers happened to diverge.

### FIXED 13 Nov 2026

The lateral is **deleted**, not left unused. The extremes and all four
derived columns read `dm`, whose as-of predicate is already correct and
already fails closed. The flags return the comparison from the `CASE`, so
TRUE, FALSE and NULL stay three answers.

Deleting rather than orphaning is the point: a lateral computing a
plausible number nobody reads is how the next column acquires an ungoverned
source. It is already in scope and already looks right.

`test_one_producer_per_quantity.py` asserts the **class**, not these four
columns: no lateral may produce a quantity a joined producer already
publishes; a ratio must read its denominator from the alias that publishes
it; no boolean may fall back to a literal after guarding its input for
NULL. Five mutants, five killed.

Governing the four as a backstop is still worth doing and is **not** done
here — it needs a model-version decision (V3 is frozen the moment a
production run finalises under it) and the booleans need `BOOLEAN_METRICS`
entries. The source fix does not depend on it, and makes the governed and
published values agree by construction rather than by enforcement.

### Two defects found while fixing this one

`universe_joins.py` read line numbers from another generator's **cached**
output and never checked them. A stale `universe_pairs.json` pointed it at
a window ending three laterals early: 30 sources instead of 32, one
invented with alias `None` from the truncated tail — and
`test_universe_join_cardinality` passed all seven assertions on it. The
anchors are now verified against the file.

The join evidence recorded what every lateral **reads** and nothing about
what it **produces**, which is exactly why no guard could ask whether a
lateral shadows a producer. It now records outputs.

### Not yet proven in production

A green test shows the statement changed. `measure_shadow_52w_extreme.py`
carries the before-measurement above; the same script re-run after a
canonical run is the after.

The expected effect, stated before the run so it can be wrong:

| | before | after |
|---|---|---|
| `price_to_52w_high` present | 2,414 | **1,895** |
| `new_52w_high` NULL | 0 | **674** |
| `new_52w_high` TRUE | 83 | **68** |

Coverage falls by 519 ratios, and that is the fix working rather than a
regression: those 519 rows were answering a question nobody could answer.
The 15 lost TRUEs are the rows claiming a new 52-week high against a
six-month maximum.

If the after-run does not show roughly these numbers, the fix did
something other than what is claimed here.

## 14. A dead join in the statement that publishes the universe

**Table:** `screener.universe`
**Status:** CONFIRMED from the statement, 12 Nov 2026

`build_screener_universe.py` carries a `LEFT JOIN LATERAL` over
`market.weekly_metrics` aliased `wm`, with an as-of predicate and an
`ORDER BY week_date DESC LIMIT 1`. **No column in the SELECT reads from it.**

It is a leftover. The weekly fallback it fed was removed after a 14-month
`rsi_14` was served as a 14-day one — the comment above the join still
explains that removal — and the join itself stayed.

Not a correctness defect: it contributes no value, so it corrupts nothing.
It costs one lateral per company per run, and it misleads a reader into
believing weekly data reaches the universe, which was exactly the question
finding 10 could not answer from the code.

Removing it is a one-line change to the publishing statement and should be
its own commit with its own gate, not a passenger on another fix. The
cardinality guard's `EXPECT_SOURCES`, `EXPECT_LATERALS` and
`EXPECT_LIMIT_1` move with it.

## 15. `market.daily_metrics` conflates unknown with false, and it is served

**Table:** `market.daily_metrics` → `screener.universe`
**Status:** CONFIRMED from the producer, 13 Nov 2026
**Source:** found while fixing finding 13; **corrects finding 10**

Finding 10 closed partly on the claim that `market.daily_metrics` "already
writes NULL for an uncomputable signal". It does not.

```python
# technical_compute.py:570-578
df["above_sma20"]   = c > df["sma_20"]
df["above_sma200"]  = c > df["sma_200"]
df["golden_cross"]  = (df["sma_50"] > df["sma_200"]) & (df["sma_50_prev"] <= df["sma_200_prev"])
df["new_52w_high"]  = (h >= df["high_52w"]) & (h > h.shift(1))
```

A pandas comparison against NaN yields **False**, and `_v()` converts
`np.bool_(False)` to `False` rather than None. Nine boolean columns —
`above_sma20/50/100/200`, `golden_cross`, `death_cross`, `new_52w_high`,
`new_52w_low`, `volume_breakout`, plus `obv_rising` — are written as
measured falses wherever their inputs do not exist.

**This one reaches the customer.** Finding 10's falses stopped at the Gold
layer because nothing read `weekly_metrics`. These do not: the universe
reads `above_sma50`, `above_sma200`, `golden_cross` and `death_cross`
straight from `dm`.

The warm-up filter (`df = df[df["rsi_14"].notna()]`, ~15 bars) removes the
most extreme cases and not the ones that matter: a stock with 100 bars has
an RSI and no `sma_200`, so its `above_sma200` and both crosses are
confident negatives drawn from nothing.

### FIXED 13 Nov 2026

All 15 boolean columns are nullable with no default, checked against the
schema snapshot rather than assumed — so the schema could always hold the
third answer.

Twelve signals now mask on their inputs being present: the four
`above_smaN`, both crosses, the three new-extreme flags, `obv_rising`,
`volume_breakout` and `above_vwap`. The mask is applied **after** the
comparison, which is the only order that works: changing a default would
have changed nothing, because the collapse happens inside the comparison
before any default is consulted. That is the subtlety that made finding 10
more than a one-word fix, and it is the same here.

`above_vwap` loses its `.astype(int)`. The column is `smallint` and an int
cast cannot represent the third state.

The previous bar is treated as an input like any other, so "did it make a
new high today" is unanswerable on the first row rather than no.

`test_daily_signals_withhold_unknown.py` runs the real `compute_indicators`
over real short series and reads what it produces, **including through
`_v()`** — the mask is worth nothing if the conversion that follows turns
NaN back into False. Six mutants, six killed, among them a mask applied to
too few inputs, which looks guarded and is not.

**Nothing downstream coerces.** The response schema already declares these
`Optional[bool] = None`, no API SELECT wraps them in `COALESCE`, and the
universe reads them plainly. Checked rather than assumed, because v11.2.32
fixed `is_reit` in the data and the API destroyed the distinction on the
way out — the same fix undone one layer later.

### Not yet proven in production

`measure_confident_negatives.py` takes the measurement from
`screener.universe` and not from `market.daily_metrics`. The hypertable
holds every trading day for every company, counting a predicate across it
is the shape that OOM-killed production on 28 Oct, and a false on a row
from 2023 is served to nobody. The universe holds the latest row per
company and carries both the flags and their inputs, so 2,569 ordinary
rows answer the question that matters.

`above_sma200 = false` beside `sma_200 IS NULL` cannot be anything but a
comparison against a value that was not there.

The counts for `golden_cross` and `death_cross` are a **lower bound**: they
also need the previous averages, which the universe does not carry.

## 16. Four boolean columns of `market.daily_metrics` have no writer

**Table:** `market.daily_metrics` → `screener.universe`
**Status:** CONFIRMED from the producer, 13 Nov 2026
**Source:** found while fixing finding 15

`technical_compute` is the **only** writer of `market.daily_metrics`, and
its `INSERT_COLS` does not contain:

```
rsi_overbought   rsi_oversold   macd_bullish_cross   macd_bearish_cross
```

All four exist in the table, all four are selected by the universe's `dm`
lateral, and all four are therefore NULL on every row. Finding 11's shape,
one layer down.

`rsi_overbought` is a **registered screener filter** — `screener.py:452`,
`"col": "u.rsi_overbought"`, label "RSI Overbought (≥70)", category
Technicals. A filter over an all-NULL column returns zero rows and reports
no error.

One detail that makes this more than a missing writer: the label promises
**≥70**, while `pros_cons.py:93` uses **75** for the same name. Adding a
writer requires deciding which threshold is the product's, so this is not
a drive-by fix — it is a product decision with two existing answers.

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
| 9 | Half assigned by row position. 5.7% of company-years, but only **10 companies serve a mis-paired value today**; 770 of 2,567 unverified | `market.halfyearly_metrics` | MEASURED — exposure far smaller than the historical rate |
| 10 | Insufficient history written as FALSE, not NULL | `market.weekly_metrics` | **FIXED** — masked at source; none of the four reached the customer |
| 11 | Ten columns no statement writes. Nine remain empty; `price_to_52w_high` was FROZEN on 2,290 of 2,566 rows (91.1% wrong by >0.01, median error 0.10) and is **FIXED** | `screener.universe` | **PARTIALLY CLOSED** — ratio repaired, nine columns still unwritten |
| 12 | Unknown market cap written as six measured falses; 642 of 2,567 rows (25%) were invisible to every tier filter | `screener.universe` | **FIXED** — consumers read the label, `unknown` selectable, seven tiers reconcile to 2,567 |
| 13 | Not a governance gap but a **second producer**: a `dp52` lateral recomputed the 52-week extremes from raw, unadjusted `daily_prices` with no coverage rule, and four published columns derived from it while the extreme beside them came from the governed producer. The split basis made a stock at its 52-week high publish at a fraction of it | `screener.universe` | **FIXED** — lateral deleted, all four read `dm`; governance backstop deferred, awaiting the model-version decision |
| 14 | Dead `weekly_metrics` lateral in the publishing statement; no column reads it | `screener.universe` | CONFIRMED — wasteful, not wrong |
| 15 | Boolean columns written as pandas comparisons against NaN, so unknown was stored as a measured FALSE. **Four are served** — the universe reads `above_sma50`, `above_sma200`, `golden_cross`, `death_cross` straight from `dm`. Corrects finding 10's claim that this table writes NULL | `market.daily_metrics` | **FIXED** — twelve signals masked on their inputs; 6 mutants killed; exposure measurement pending a run |
| 16 | `rsi_overbought`, `rsi_oversold`, `macd_bullish_cross`, `macd_bearish_cross` have no writer — NULL on every row, and `rsi_overbought` is a registered screener filter. The label says ≥70, `pros_cons` uses 75 | `market.daily_metrics` | CONFIRMED — needs a threshold decision, not just a writer |
