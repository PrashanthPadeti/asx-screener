# P0-A REOPENED — governed momentum input freshness

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

33 codes remained source-relative stale after run 6, so the condition recurs
whenever a technical run skips a code.

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
6. The exact current 33-code stale population preserved before repair.
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
