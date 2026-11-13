# v11.2.85 — findings 6b and 6d

## What changes for a customer

**`price_to_fcf` (Price / FCF) stops being served.** Measured 13 Nov 2026:
**580 of 2,569 universe rows (22.6%)** carried a value before the repair.
After the recompute it is **0 of 2,570** — confirmed in production the
same day.

This is a deliberate loss, not a regression. Every one of those 580 values
was produced by a code path that no longer exists, and sits beside a
`computed_at` refreshed by a run that did not produce it. A reader has no
way to date them.

### Surfaces that change

| surface | location | behaviour after |
|---|---|---|
| Screener filter "Price / FCF" | `screener.py:244`, `u.price_to_fcf`, category Valuation | matches no rows; returns an empty result, not an error |
| Sort column | `screener.py:631` | every row sorts as NULL — membership preserved since v11.2.76, ordering arbitrary |
| Response field | `screener.py:1123`, `:1279`, `:2519` | `null` |
| CSV export column "P/FCF" | `screener.py:1538` | empty cell |
| Company detail | `companies.py:231`, `schemas/company.py:134` | `null`, rendered as unavailable |

A customer with a **saved screen** filtering on Price / FCF will get zero
results. That is the one visible consequence worth watching, and it is the
same shape as the `beta_1y` problem v11.2.81 solved with an explicit
withdrawal. **A withdrawal for `price_to_fcf` is NOT in this release** —
the column is expected to be repopulated properly rather than withdrawn
(see "Next"), and withdrawing a field we intend to restore within days
would churn the catalogue twice.

If the restoration slips, withdrawing it becomes the right call.

## What changes in the data

64 columns of `market.yearly_metrics` are emptied on conflict instead of
being preserved. They split into two findings:

- **6a, 27 columns** — never populated by anything. No behaviour change;
  NULL before, NULL after.
- **6b, 37 columns** — held values on 2.9%–22.6% of 33,864 rows. These are
  the ones that served a wrong answer rather than no answer.
- **6d** is a provenance claim about a subset of 6b, not a separate
  column set: three window pairs invert
  (`avg_roe_7y` 6,424 < `avg_roe_10y` 6,429, and two more), which
  `average_over` cannot produce, so those values came from the superseded
  `_avg` helper.

The explicit lists are `DEAD_6A`, `FROZEN_6B` and `INVERTED_PAIRS_6D` in
`tests/test_yearly_upsert_empties_retired_columns.py`, and a test asserts
they partition the retired set exactly — a column in neither is one nobody
has classified.

## Evidence

**Statement** — `test_yearly_upsert_empties_retired_columns.py`, 12/12.
Every non-key column assigned on conflict (122 `EXCLUDED` + 64 `NULL` =
186 = 188 − 2 keys), none twice, no `COALESCE`, no crossed `EXCLUDED`,
`computed_at` still refreshed, and the retired set reconciled against the
schema snapshot.

**Behaviour** — `tests/fixtures/prove_retired_columns_are_emptied.py`
drives the real statement through `execute_values` against a real
database and proves the valid-value → unavailable-value transition for a
6b column, the served 6b column, and a 6d column, while a written control
column still refreshes and the timestamp still moves. A `COALESCE` passes
every source assertion and fails this.

**Mutation** — 7 mutants, 7 killed.

## Deployment handoff

The repair is in the producer. Nothing changes until a run rewrites the
rows, and the next scheduled yearly recompute is **Monday 16 Nov, 08:00
Sydney**. Do not wait for it: run the recompute as part of this
deployment, in this order.

1. **Before.** Record the current state.
   ```
   PYTHONPATH=/opt/asx-screener/backend asx-venv/bin/python \
     /tmp/asxdiag/frozen.py --env-file /opt/asx-screener/backend/.env
   ```
   Expect: 580 served, 7,656 carriers, three inversions, and **zero
   value mismatches in the row-by-row reconciliation**. That last one is
   the precondition: if it is non-zero, the 580 is cardinality agreement
   rather than row identity and the exposure claim does not hold.

   **RUN 13 Nov 2026, 03:0x UTC — precondition MET.**

   ```
   instruments compared                 2,599
   in universe, no yearly row             720
   in yearly, not in universe              30
   value differs                            0
     served but latest is NULL              0
     latest has one, not served             0
   instruments present on both sides     1,849
   ```

   Zero value mismatches across all 1,849 matched instruments, in both
   directions. The served value IS the latest fiscal year's
   `p_fcf_ratio`, instrument by instrument.

   The two population figures are not mismatches and the first version of
   this check wrongly treated them as such. 720 universe rows carry no
   fundamentals at all — ETFs, funds, notes — and 30 companies with
   fundamentals sit outside the serving population. The join decomposes
   exactly: `2,599 = 2,569 universe + 30 yearly-only`, and
   `1,879 yearly companies = 1,849 matched + 30`.

   A second fact fell out of it: **905 companies carry a `p_fcf_ratio`
   somewhere, 580 on their latest fiscal year and 325 only on an older
   one.** Those 325 reach nobody, which is why 7,656 rows-with-a-value was
   never the right denominator for exposure.

2. **The canonical driver**, which runs the whole plan under one lease and
   ends in a publication:
   ```
   cd /opt/asx-screener/backend && ../asx-venv/bin/python \
     scripts/p0a_canonical_run.py --execute --allow-production
   ```
   `FULL_FUNDAMENTALS_CANONICAL` is the default plan and already contains
   `yearly_compute`, `universe_build` and `composite_score` in order.

   **Do NOT run `yearly_compute.py` and `build_screener_universe.py`
   directly.** The first version of this handoff did, and it was wrong.
   `build_screener_universe` invalidates the canonical contract atomically:
   it clears `metric_states` and `compute_run_id` and leaves every row
   PROVISIONAL. Nothing re-attributes them without a `composite_score` run
   carrying a `--run-id` from an open lifecycle, and only the driver can
   open one. Between the bare rebuild and the next canonical publication,
   `row_projection` reads every governed metric as *outside the snapshot*
   and serves `null` with a state — correct behaviour, dark surface. The
   comment at `weekly_pipeline.py:339` documents this exact failure; the
   handoff reproduced it anyway.

3. **After.** Same script as step 1.
   Expect: **served 0, carriers 0**, and the inversion rows reading 0/0.

The inversions going to 0/0 rather than staying inverted is itself the
proof that these columns were not being rewritten by any current code: if
something still wrote them, the counts would persist.

**RUN 13 Nov 2026, 04:3x UTC — every expectation met.**

```
universe rows                     2,570
serving a frozen ratio                0  (0.0%)
latest fiscal year has a value        0
companies carrying a value anywhere   0
rows 33,864   p_fcf_ratio present     0
avg_roe_7y  0   avg_roe_10y  0
avg_roce_7y 0   avg_roce_10y 0
avg_ebit_5y 0   avg_ebit_10y 0
```

The yearly run reported `0 skipped | 0 errors | 33,864 rows upserted`,
`Prune: no orphaned yearly_metrics rows`, and `Coverage: every sourced
yearly_metrics row was rewritten by this run` — so the 0s are the result
of rewriting the whole population, not of skipping it. All three
inversions collapsed, which is the provenance proof: no current code
writes those columns.

The `** NON-ZERO` line in that output is the stale verdict from
`origin/main`, which does not yet carry the fix described in step 1.
`value differs` was 0 in both directions again; 721 and 30 are the two
population figures.

## Not closed by this release

- **Price basis (finding 13)** — UNVERIFIED. Two explanations were
  withdrawn after measurement contradicted them; producer agreement does
  not establish that the underlying series is right, because two
  consumers of one wrong series agree. Settling it needs ingestion or
  corporate-action evidence about what `market.daily_prices.high` holds
  for a pre-split date.
- **Findings 13 and 15** remain pending their own canonical-run
  verification. The 13 Nov measurements are the **before-state**.

## Next: restore Price / FCF under one contract

Proposed, and to be confirmed against the producer before implementation:

| input state | result |
|---|---|
| FCF > 0 and market cap > 0 | compute the ratio |
| FCF ≤ 0 | NULL, reason: a Price/FCF on non-positive free cash flow has no meaningful sign |
| either input missing | NULL, reason: missing input, named |
| extreme result | flag for review; a threshold only with a written rationale |

Three things to confirm first, because each would change the number:

1. **FCF period** — `fcf` in `yearly_metrics` is a fiscal-year figure;
   `STORAGE_COLUMN` maps `free_cash_flow` → `fcf_fy0` for the universe,
   and there is no `fcf_ttm`. A Price/FCF mixing a current price with a
   fiscal-year cash flow is defensible and must be *stated*.
2. **Currency** — gate 1b already marks 8 ratios NOT_MEANINGFUL when
   `reporting_currency` ≠ AUD. A price in AUD over an FCF in USD is the
   same defect, and Price/FCF is not currently in that set.
3. **As-of** — `market_cap` on the yearly row is `price_at_compute ×
   shares`, so the ratio's as-of date is the row's, not today's.

And one thing to verify rather than assume: that `p_fcf_ratio` is what
feeds the served `price_to_fcf`. The row-by-row reconciliation in step 1
establishes exactly this, which is why it runs before the repair rather
than after.
