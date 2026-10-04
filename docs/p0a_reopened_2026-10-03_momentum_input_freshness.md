# P0-A REOPENED — technical evidence identity and freshness

**Final statement of the defect.** Governed `momentum_score` could inherit
stale OR cross-frequency technical evidence through unbounded/fallback serving
composition. Applicability propagation is correct once invalid inputs are
removed; the defect is that invalid evidence was allowed to acquire the
identity of current daily evidence.

## Measured exposure, 4 Oct 2026, before the patch

    freshness   33 codes with a daily metric row behind their latest price
                 0 of them served
    identity    20 fallback mappings; the fallback won on 2 rows in total
                 sma_50        <- weekly sma_10w      1 fallback, 1 ACTIVE
                 volatility_60d <- monthly vol_3m     1 fallback, 0 active
    governed     0 active rows where a momentum constituent came from a
                 coarser cadence

**Reconstruction control: 0 mismatches.** The diagnostic replays the
builder's lateral selection rather than reading what the universe stored, so
the counts were reconstructed until this was checked. Comparing
`COALESCE(daily_v, fb_v)` against the stored column, row by row, across all
20 mappings, reproduces every stored value. The counts are therefore
**measured evidence of run 6's served state**, not estimates.

The run now stamps its own provenance first — builder path, that file's
sha256, the canonical run compared against, rows served, comparisons made —
because "0 mismatches" is only meaningful about a specific implementation and
a specific publication. A rerun from a patched tree would otherwise report
zero exposure BY CONSTRUCTION and read exactly like a measurement.

One served row carries an identity substitution; none reach governed state.
The patch is **preventive on both axes**. The daily source is populated for
1,800–2,348 codes per field because run 6 wrote a technical row for all 2,346
codes with `keep_uncomputable`, so the fallbacks rarely fire — but the
mechanism was live, and a skipped technical run would fire them.

Two exposure claims made during this investigation were wrong: "current
exposure is zero" (measured freshness only, said nothing about identity) and
"expect identity exposure to be substantial" (predicted, not measured).

Instrument: `scripts/diagnostics/measure_evidence_identity_exposure.py`.

### The measurement, reproducibly stamped

    builder          : /opt/asx-screener/backend/scripts/eodhd/v2/build_screener_universe.py
    builder_sha256   : ea94a9dd9167
    canonical_run    : 6
    served_rows      : 2121 of 2539
    mappings_parsed  : 20
    comparisons      : 50780
    reconstruction_mismatches : 0

    artifact : logs/evidence_exposure_pre_fix_20261004.csv
    sha256   : c1ad434d41857dd31cee9f32cf7ef18717c8692bbfb850d327b4b525264ea34d

That header is what makes the zero meaningful. The same script run from a
patched tree parses 0 mappings and reports no identity exposure BY
CONSTRUCTION — indistinguishable, without the stamp, from a measurement that
looked and found none.

### Post-release acceptance: two different kinds of zero

    cross-frequency mappings = 0   STRUCTURAL -- a consequence of the new
                                   projection; true the moment it deploys
    served stale technical   = 0   RUNTIME -- a property of what the canonical
                                   run actually published

Both go in the acceptance record. The structural zero must not be allowed to
stand in for the runtime one; that substitution is the same error as a source
guard standing in for behaviour, which is what this whole branch was about.

Post-release acceptance is "no active served daily-semantic field is sourced
from stale or cross-frequency evidence" — NOT a manufactured example of a
suppressed `momentum_score`. Governed exposure is already zero, so there may
be no production row whose momentum visibly changes, and requiring one would
be requiring the wrong thing.

---

# Original entry — governed momentum input freshness

**3 October 2026. Narrow corrective scope.** This does not reopen the P0-A
architecture, FX, lifecycle, explainability, or technical metrics generally.

## The defect

Governed `momentum_score` consumed source-relative stale technical
observations through `screener.universe`. Stale inputs were not represented
as unavailable, so the governed score could publish with an ordinary valid
state instead of failing closed.

    FACTOR_MODEL_V2["momentum"] = _spec("momentum", [
        ("return_1m", +1), ("return_3m", +1), ("return_6m", +1),
        ("rsi_14", +1), ("adx_14", +1)])

`momentum_score` is one of the 72 governed metrics. All five constituents are
**ungoverned** columns served from `market.daily_metrics` through a LATERAL
that read the latest row ever written for the code, with no relationship to
the prices it claimed to describe.

## The concrete instance

ALPH held exactly two rows in `market.daily_metrics`:

    2026-06-19   sma_200 11.0564   dma200_ratio 1.0175   rsi_14 70.80
    2026-10-01   sma_200 NULL      dma200_ratio NULL     <- written by run 6

Until run 6, the unbounded lateral served the June row against prices running
to 1 October. The governed contract was satisfied in form — a value, a state,
a cause — while the evidence underneath did not correspond to the instrument's
current price state.

## Exposure: historical real, current none

Measured 4 Oct, after run 6:

    stale codes (metric row behind their own latest price)   33
    of those, present in screener.universe                    0
    of those, actually served (compute_run_id NOT NULL)       0

So the patch is **preventive**, not corrective of live customer data. Every
code still carrying a source-relative stale metric row is outside the served
universe; run 6 cleared the condition for everything customers can see.

The HISTORICAL exposure is real and proven — ALPH served a June value against
October prices, and its governed `momentum_score` was built from June's
`rsi_14` and `adx_14`. The before/after sample of run 4 → run 6 is the
evidence. "33 codes affected" would be the wrong claim: the served count was
zero when measured.

The recurrence condition remains, and that is what the patch closes: it
returns whenever a technical run skips a code that IS in the universe.

## Why this crosses the reopening threshold

A canonical-serving governed value was capable of inheriting invalid evidence
without the governed contract detecting it.

## Scope boundary

- `dma200_ratio`, `sma_200`, `high_52w`, `rsi_14` and the rest are **not**
  governed. A plain dash for an ungoverned technical blank is acceptable under
  the current contract and does not violate the v11.1.0 promise, which is
  scoped to governed suppressed blanks.
- Extending governance to technical metrics is a **V3** question. It would
  change the 72-metric set, the readback contract and model identity. A narrow
  second sidecar would be worse: a competing applicability system to reconcile
  later with `metric_states`, canonical identity and frontend resolution.
- A governed `momentum_score` built from stale inputs is a different matter,
  and is what this reopening covers.

## Repair direction

`2cd67ff` fixes the evidence boundary **before** the governed calculation
rather than special-casing `momentum_score`. Once the stale row is ineligible,
the five inputs are absent and the existing governed logic gets the chance to
fail closed.

    AND date = dp.price_date

Not an age threshold: a suspended instrument correctly has an old latest price
AND an old latest metric, and those agreeing is not staleness.

## Closure evidence required

1. Scratch: price 2026-10-01, metric row 2026-06-19 → stale technical values
   do not enter `screener.universe`.
2. Control: both 2026-10-01 → technical values serve normally.
3. No-price case → no stale technical values serve.
4. Same stale fixture through `composite_score` → `momentum_score` is
   governed-absent with the appropriate state/cause. **Never zero, never a
   normal score.**
5. Matching fixture → `momentum_score` computes normally.
6. The stale population preserved before repair. DONE 4 Oct: 33 codes stale,
   **0 of them served**, so the preserved served-population file is empty by
   fact rather than by omission
   (`logs/stale_metric_population_pre_fix_20261003.csv`, header only,
   sha256 `39ce32ac9133175143f26cffb1ba0b8625c73bb529f347338ecfecaaa75c9a70`).
7. Patch released independently, then one `DAILY_CANONICAL` publication.
8. Post-publication: zero source-relative stale technical joins among served
   values; governed readback and finalisation clean; previously affected
   momentum cases fail closed or recompute from current evidence.

**If nulling those inputs does not produce a governed cause for
`momentum_score`, that is a SECOND P0-A defect and the patch is incomplete.**

## Status

**P0-A REOPENED.** `2cd67ff` is the implementation checkpoint on
`fix/stale-derived-serving`, local only. Closure awaits scratch behavioural
proof, independent patch release, DAILY canonical republication and live
zero-stale verification.

## Explicitly not in scope

The 18–19 June producer event — 379 codes carrying an `sma_200` first written
when fewer than 200 prices existed, clustered on two days when 1,844 codes
were written against ~1,500 either side. Historical derived values unsupported
by the currently retained price lineage and impossible under the current
implementation. Worth provenance work; does not block this repair, because the
stale-serving mechanism is proven independently.
