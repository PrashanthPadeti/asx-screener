# v11.2.86 — Price / FCF restored

## What changes for a customer

**`price_to_fcf` (Price / FCF) is served again**, after v11.2.85 emptied
it. The filter, the sort column, the CSV column "P/FCF" and the
company-detail field all return values once a yearly run has executed.

Coverage will **not** return to the 580 rows it held before. Three
populations are declined on purpose:

| declined | why |
|---|---|
| free cash flow ≤ 0 | a negative Price/FCF sorts FIRST on an ascending "cheapest" screen while describing a company with no free cash flow; zero has no finite ratio |
| an input missing | no market capitalisation or no cash flow, nothing to divide |
| foreign reporting currency | an AUD market capitalisation over a cash flow stated in another currency has no unit |

The expected after-count is therefore **lower than 580 and not yet
predicted**, because the three populations have not been measured. That
measurement is step 1 of the handoff, and predicting before measuring is
how the last two releases produced magnitudes that missed.

## The three things confirmed before any code was written

**1. Period — no mismatch, and the earlier note was wrong.**

```python
px  = price_at(prices, ped)      # close at/before the row's period end
fcf = _f(row.get("fcf"))         # annual cash flow for that same period
mc  = round(px * shares / 1e6, 2)
```

The v11.2.85 note said this would mix "a current price with a
fiscal-year cash flow" and that the mix must be stated. It does not mix.
`price_at` anchors on the row's own `period_end_date`, so both sides are
as of the fiscal year end. **That disclosure is withdrawn** — there is
nothing to disclose.

**2. The ratio is the reciprocal of a metric already served.**

`fcf_yield` is live and is `fcf / mc`; `p_fcf` is `mc / fcf`. One pair,
two presentations.

It is computed from the same `mc` and `fcf` rather than as
`1 / fcf_yield`. `_div` rounds to 4dp, so a yield of `0.00003` stores as
`0.0000`, and a reciprocal taken from the stored value would divide by
zero on exactly the companies whose ratio is largest. **Reading a rounded
output as an input is how a presentation becomes a second producer** —
the defect finding 13 was.

They deliberately do **not** share a guard. A negative FCF *yield* is a
reportable fact that reads as bad. A negative Price/FCF reads as cheap.
`test_negative_fcf_still_publishes_the_yield` pins the asymmetry so a
later consistency refactor cannot align them.

**3. The currency guard could not go where the note proposed.**

```
  fcf_yield      assessable=True   governed=False
  price_to_fcf   assessable=False  governed=False
```

Gate 1b runs on `governed | model_constituents`. `price_to_fcf` is in
neither, so an entry in `CROSS_CURRENCY` would have been **declared and
never read**. Making it assessable means `GOVERNED_METRICS`, and
FACTOR_MODEL_V3 is frozen by 13 finalised runs, so that means V4.

The guard therefore lives in the producer, where it is reached, and
`test_the_declaration_route_is_still_closed` fails the moment the column
becomes assessable — so the rule gets **moved** into `CROSS_CURRENCY`
rather than existing in two places.

## Evidence

**Contract** — `tests/test_price_to_fcf_contract.py`, 16/16. The
publishing case by value (`400/40 = 10.0`), the reciprocal identity
against `fcf_yield`, all three declining cases, case and whitespace on
the currency, and unstated currency publishing (silence is not evidence
of a mismatch).

**Statement** — `test_yearly_upsert_empties_retired_columns.py`, 12/12.
`p_fcf_ratio` is now in the written list and **not** in the NULL list;
both halves asserted, because a column in neither keeps whatever a prior
run left in it. The partition test caught the stale 6b count on the first
run, which is what it is for: 6b is 36, not 37, and it lost the name by
**restoration**, not reclassification.

**Behaviour** — `tests/fixtures/prove_retired_columns_are_emptied.py`
now distinguishes **three** outcomes for this column rather than two. The
incoming value differs from both the seeded one and NULL, so `12.34`
means preserved, `NULL` means still retired, and `7.5` means written. A
"not NULL" assertion would have accepted a value frozen since June.

**Mutation** — 8 mutants, **7 killed, 1 equivalent**. The survivor is
`fcf > 0` → `fcf >= 0`, which changes no output because `_div` already
declines a zero denominator. The comment claiming the `> 0` test excluded
zero was corrected, and `test_div_returns_none_on_zero_denominator` pins
the half that lives elsewhere so the equivalence cannot quietly stop
holding.

## Deployment handoff

Nothing changes until a yearly run rewrites the rows, and then the
universe must be rebuilt **through the canonical driver**.

1. **Before.** Size the three declining populations, so the after-count
   is a prediction rather than a rationalisation.
   ```
   PYTHONPATH=/opt/asx-screener/backend asx-venv/bin/python \
     /tmp/asxdiag/fcfcur.py --env-file /opt/asx-screener/backend/.env
   ```
   The control is the part to read first: if any of the eight
   gate-1b-guarded ratios publishes on a foreign reporter, the gate is
   not doing what finding 17 assumes and that finding is void.

2. **The canonical driver**, which runs yearly, universe build and the
   publication under one lease:
   ```
   cd /opt/asx-screener/backend && ../asx-venv/bin/python \
     scripts/p0a_canonical_run.py --execute --allow-production
   ```
   **Not the two scripts separately.** `build_screener_universe`
   invalidates the canonical contract atomically and leaves every row
   PROVISIONAL; between that and a `composite_score` carrying a run id,
   `row_projection` serves every governed metric as null. The v11.2.85
   handoff made that mistake and took the surface dark.

   Note: the driver has **no `load_dotenv` of its own** and inherits the
   credential from `PipelineTracker.connect()` inside the pipelines. Run
   as a script it needs the environment sourced first:
   ```
   cd /opt/asx-screener/backend && set -a && . ./.env && set +a && ...
   ```
   That is a defect in its own right and is not fixed here.

3. **After.** Same script as step 1. `price_to_fcf` on foreign reporters
   must be **0** while `fcf_yield` on the same rows is **unchanged** —
   that difference is finding 17, made visible.

## Not closed by this release

- **Finding 17** — `fcf_yield` carries the same unit mismatch, is
  reachable by gate 1b, and is a factor-model constituent. Fixing it
  changes scores under a frozen version name, so it needs V4. Deferred
  deliberately, with the measurement written first.
- **The asymmetry it leaves.** Until V4, the site declines Price/FCF for
  foreign reporters while publishing its reciprocal for the same
  companies. Recorded rather than hidden by withdrawing the safer one.
