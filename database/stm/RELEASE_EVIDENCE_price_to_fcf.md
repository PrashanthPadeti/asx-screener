# v11.2.86 — Price / FCF restored

Candidate `3ab4bcb` · baseline `a2d11a2` (main) · branch
`fix/price-to-fcf-restoration` · **not deployed**

## What changes for a customer

**`price_to_fcf` (Price / FCF) is served again**, after v11.2.85 emptied
it. The filter, the sort column, the CSV column "P/FCF" and the
company-detail field all return values once a yearly run has executed.

**Predicted served count: 471 universe rows** on 16 Nov's data, against
the 580 the frozen column held before. It is the producer's own output
over the universe's own selection rule — `ORDER BY fiscal_year DESC LIMIT
1`, intersected with universe membership — not a forecast from whichever
inputs happen to be stored. The v11.2.84 forecast missed by 542 rows by
doing the opposite.

**And the number moves.** The same instrument on the same producer gave
**438** on 15 Nov and **471** on 16 Nov, because `weekly_pipeline` ran a
FULL canonical run on Sunday 15 Nov at 21:00 UTC and moved the
fundamentals underneath it. A served-row count is a function of data that
changes weekly, so it is only an acceptance criterion against a baseline
measured **immediately before** the run it gates. Quoting 438 two days
later would have produced a miss and an explanation.

## The populations, measured over all 33,864 yearly rows

| | rows | |
|---|---|---|
| **publishable** | **5,670** | 16.7% |
| an input missing | 7,797 | 23.0% |
| market capitalisation ≤ 0 | 623 | 1.8% |
| free cash flow ≤ 0 | 17,550 | 51.8% |
| a stated foreign currency | 949 | 2.8% |
| no currency stated at all | 1,261 | 3.7% |
| declined by `_clamp` (> 9,999) | 7 | 0.0% |
| rounds to 0.00 at the stored scale | 7 | 0.0% |
| | 33,864 | |

13,499 rows satisfy more than one decline predicate. Each is counted
once, under the producer's own short-circuit order, so the column sums to
the row total exactly.

The 5,670 publishable yearly rows become **438 served rows** because the
universe takes one row per company — `ORDER BY fiscal_year DESC LIMIT 1`
— and 1,849 of the universe's 2,570 companies reach this producer at all.
Of those 1,849, the latest fiscal year is publishable for 438, declines
on free cash flow for 1,124, on a missing input for 90, and on a
non-positive market capitalisation for 3.

### Both reconciliations held, over every row

The counts above mean nothing without these, so the instrument prints
them first and exits 1 if either fails:

| | |
|---|---|
| **R1** the attributed reason predicts each row's exact stored ratio | 0 failures of 33,864 |
| **R2** the price read for the staleness measurement equals the stored `price_at_compute` | 0 failures |

**R1 earned its place.** The first after-measurement reported **1,261
failures** and refused to print a single population count. The instrument
had restated the currency predicate as `currency is None or currency ==
BASE_CURRENCY`; the producer went strict and the copy did not. That is
now one function, `yearly_compute.currency_is_coherent`, called by both.
A predicate with two implementations has two answers.

## The six guards

```python
currency_coherent = currency_is_coherent(reporting_currency)
p_fcf = (_clamp(_div(mc, fcf))
         if (mc is not None and mc > 0
             and fcf is not None and fcf > 0
             and currency_coherent)
         else None)
if p_fcf is not None and p_fcf < P_FCF_MIN_REPRESENTABLE:
    p_fcf = None
```

**`mc > 0`, not `mc is not None`.** The earlier condition coincided with
the policy through two other expressions' truthiness and was not the
policy. `mc` is rounded to 2dp, so one share at $4.00 gives exactly
`0.0` — which `mc >= 0` would divide into a published Price/FCF of 0.00,
the cheapest value the column holds and the top of an ascending screen.
**623 rows** decline here; the guard is not theoretical.

**`fcf > 0`.** A company burning cash gets a negative ratio, which sorts
FIRST on "cheapest" while describing a company with no free cash flow.
`fcf_yield` publishes the same fact safely, because −4% reads as bad and
−4× reads as cheap. The two reciprocals deliberately do **not** share a
guard, and a test pins the asymmetry.

**A stated AUD, and nothing else** — see below.

**`_clamp` at 9,999.** It **suppresses**: returns None, never substitutes
a boundary value, so no customer sees a fabricated 9,999.00 in a sort
column. It is **not an overflow guard here** — `p_fcf_ratio` is
NUMERIC(10,2) and holds 99,999,999.99. 9,999 is the threshold every
NUMERIC(10,2) valuation ratio in this producer already uses (pe, pb, ps,
ev_ebitda, ev_ebit, ev_revenue), and Price/FCF matches them deliberately
rather than protecting its column. **7 rows.**

**Below 0.005.** See the corrected diagnosis below. **7 rows.**

## The silence rule

**Publishing requires a stated AUD. An unstated currency withholds.**

The first candidate published on silence, arguing that an unknown
currency is not evidence of a mismatch. True, and beside the point:
publishing a ratio asserts its unit, and silence establishes none. The
source contract says so in writing — `add_reporting_currency.sql`: *"NULL
is meaningful and is NOT a default of 'AUD'"* — and the producer was
reading it as one.

Decided on the measurement, not the argument. Under the permissive rule
**1,261 of 6,938 publishable rows (18%)** published only because the
currency was unstated. About 13% of statement-bearing ASX companies
report in a foreign currency, so roughly **160** of those were wrong by
an exchange rate with nothing in the row to say so. 1,261 rows of
coverage is recoverable; 160 wrong ratios are wrong.

**The cost is an inconsistency and it is deliberate.** `unit_gate`
publishes on silence for the eight ratios it covers, so one company-year
can now show a P/E and no Price/FCF for the identical reason. Those eight
are governed model constituents; changing them moves composite scores
under a version name 13 finalised runs reference, which needs
FACTOR_MODEL_V4. The inconsistency runs in the conservative direction and
is recorded as **finding 20** rather than resolved by relaxing the safer
side.

## What the gate found, that nothing local could

Running the gate against main blocked the first candidate on two
findings. Both were invisible to a green local suite and to the mutation
run.

**1. The contract never ran.** `gate_full_suite.sh` executes each suite
as `python tests/<file>.py`, and `test_price_to_fcf_contract.py` was
pytest-only — fixtures, parametrize, no `__main__` block. Run as a script
it defined 21 functions, called none, and exited 0. The gate reported it
INCONCLUSIVE, which is the correct verdict and a damning one: **the file
written to certify this restoration certified nothing**, while passing
21/21 locally.

It now has a runner that expands parametrize, injects the fixture by
name, and **checks its own coverage** — invocations must equal the number
the marks imply, and a case whose signature it cannot satisfy is an
ERROR, never a skip. Both modes report 26, and agreeing on the number is
the check.

**2. The currency was an unfingerprinted input.** Reading
`staging_au.fundamentals` made `yearly_compute` consume a table
`source_fingerprint` does not project, and
`test_every_table_yearly_compute_reads_is_fingerprinted` said so.

Not cosmetic. `DAILY_CANONICAL` reuses `market.yearly_metrics` when the
fingerprint matches, so a company restating from USD to AUD would change
the correct value of every `p_fcf_ratio` row it has while the fingerprint
stayed put, reuse was granted, and the stored ratios kept a currency the
source no longer states. **Silent staleness, introduced by the feature
that made the currency matter.**

Projected as `(asx_code, reporting_currency)` and nothing else. The table
also holds `raw_json`, `snapshot_date`, `loaded_at` and `checksum`, each
of which moves on every fundamentals reload — projecting those would make
`DAILY_CANONICAL` promote itself to the full plan after every load, which
is the failure the two scoped tables are shaped to avoid.

`FINGERPRINT_SCHEMA_VERSION` 1 → 2. **Operational consequence: the first
canonical run after this deploys reports "not comparable", refuses to
reuse `market.yearly_metrics`, and recomputes.** That refusal is designed
behaviour, not a fault.

## The corrected diagnosis

The published distribution's minimum printed as `0.00`, so a guard went
in testing `p_fcf == 0` on the theory that `_div`'s 4dp rounding produced
it.

**The measurement refuted the theory.** Over 33,864 rows, zero rows had
`_div` return 0.0, the bucket was empty, and the published minimum was
still under 0.005. The rounding that destroys the value happens at the
**column**: `p_fcf_ratio` is NUMERIC(10,2), so `_div`'s 0.0001 is stored
as 0.00. A guard built on an explanation tests the explanation, and that
one passed while the defect shipped.

The threshold is now the column's — `P_FCF_STORED_SCALE = 2`,
`P_FCF_MIN_REPRESENTABLE = 0.005` — asserted against the NUMERIC
declaration in `008_compute_metrics_tables.sql` so the constant cannot
drift from the column it describes. The published minimum is now
**0.0065**.

The boundary is `<`, not `<=`, checked against the server rather than
against Python:

```
SELECT 0.005::numeric(10,2)   ->  0.01
SELECT 0.0049::numeric(10,2)  ->  0.00
```

PostgreSQL rounds half away from zero, so 0.005 is representable and must
publish. `round(0.005, 2)` in Python is 0.0. The `<=` mutant survived the
contract until a test asserted the boundary value publishes.

The instrument now prints the minimum at full precision first — `{:.2f}`
is how a sub-0.005 value hid inside the published set looking like a
stored zero.

## The three questions answered before any code was written

**1. Period — no mismatch, and the earlier note was wrong.** `px =
price_at(prices, ped)` anchors on the row's own `period_end_date` and
`fcf` is that same period's annual figure. The v11.2.85 note said this
would mix "a current price with a fiscal-year cash flow" and that the mix
must be stated. **That disclosure is withdrawn** — but see finding 18,
which is a different and larger problem with the same `px`.

**2. The ratio is the reciprocal of a metric already served.** `fcf_yield`
is live and is `fcf / mc`; `p_fcf` is `mc / fcf`. It is computed from the
same `mc` and `fcf` rather than as `1 / fcf_yield`: `_div` rounds to 4dp,
so a yield of 0.00003 stores as 0.0000 and a reciprocal taken from the
stored value would divide by zero on exactly the companies whose ratio is
largest. **Reading a rounded output as an input is how a presentation
becomes a second producer** — the defect finding 13 was.

**3. The currency guard could not go where the note proposed.** Gate 1b
runs on `governed | model_constituents`; `price_to_fcf` is in neither, so
a `CROSS_CURRENCY` entry would have been **declared and never read**. The
guard lives in the producer, where it is reached, and
`test_the_declaration_route_is_still_closed` fails the moment the column
becomes assessable — so the rule gets **moved** rather than duplicated.

## Evidence

| | |
|---|---|
| **Gate** | **no detected regression under this gate** — see the paragraph below for what that does and does not establish |
| **Contract** | `test_price_to_fcf_contract.py` 26/26 under pytest **and** 26/26 as a standalone script |
| **Statement** | `test_yearly_upsert_empties_retired_columns.py` 12/12. `p_fcf_ratio` in the written list and **not** in the NULL list; both halves asserted |
| **Behaviour** | the fixture distinguishes **four** outcomes now: 12.34 preserved, NULL still retired, 7.5 written — and a second act proves an incoming NULL **clears** a stored 7.5 |
| **Mutation** | 13 mutants on the guards: 12 killed, 1 the known equivalent (`fcf > 0` → `>= 0`, which `_div` already decides) |
| **Control** | all eight gate-1b ratios are **0** on the 164 attributed foreign-reporter rows, so the gate does enforce where it is applied and finding 17's comparison is valid |

**The clearing proof matters as much as the writing proof.** A restored
column must be able to take a value *away*: a company that reported
positive free cash flow last year and negative this year now produces an
incoming NULL over a row that already holds a number. Softening `DO
UPDATE SET p_fcf_ratio = EXCLUDED.p_fcf_ratio` to a COALESCE would leave
the writing proof passing while a ratio computed when the company was
profitable stayed on screen forever — finding 6b returning through the
column that repaired it.

## Deployment handoff

Nothing changes until a yearly run rewrites the rows, and then the
universe must be rebuilt **through the canonical driver**.

1. **Before.** Re-run the population measurement and the finding-17
   control, so the after-state has a same-day baseline.
   ```
   cd /tmp/pfcf/src/backend && PYTHONPATH=/tmp/pfcf/src/backend \
     /opt/asx-screener/asx-venv/bin/python \
     scripts/diagnostics/measure_p_fcf_populations.py \
     --env-file /opt/asx-screener/backend/.env
   ```
   Read the reconciliation block first. If R1 or R2 fails, the script
   exits 1 and prints no counts — that is the instrument refusing to
   report numbers about code that behaves differently from its model.

2. **The canonical driver**, which runs yearly, the universe build and
   the publication under one lease:
   ```
   cd /opt/asx-screener/backend && set -a && . ./.env && set +a \
     && ../asx-venv/bin/python scripts/p0a_canonical_run.py \
        --execute --allow-production
   ```
   **Not the two scripts separately.** `build_screener_universe`
   invalidates the canonical contract atomically and leaves every row
   PROVISIONAL; between that and a `composite_score` carrying a run id,
   `row_projection` serves every governed metric as null. The v11.2.85
   handoff made that mistake and took the surface dark.

   **Expect the fingerprint to refuse reuse on this first run** and the
   full plan to execute — `FINGERPRINT_SCHEMA_VERSION` moved 1 → 2. That
   is the designed consequence of adding a projection, not a fault.

   The driver has **no `load_dotenv` of its own** and inherits the
   credential from `PipelineTracker.connect()` inside the pipelines, so
   run as a script it needs the environment sourced first — hence the
   `set -a`. That is a defect in its own right and is not fixed here.

3. **After.** The acceptance criteria, each a number rather than a
   direction:

   | | expected |
   |---|---|
   | `price_to_fcf` served in `screener.universe` | **438** rows |
   | rows publishing on an unstated currency (P7) | **0** |
   | minimum published ratio | **≥ 0.005** |
   | `price_to_fcf` on foreign reporters | **0** |
   | `fcf_yield` on foreign reporters | **167**, unchanged |
   | R1 / R2 reconciliation failures | **0** |

   The last two together are finding 17 made visible: the same companies,
   one column declining and its reciprocal publishing.

## Finding 18 reaches this column. There is no predicate that stops it.

I wrote that finding 18 was "not a Price/FCF defect". That is
indefensible and withdrawn:

```
p_fcf = mc / fcf
mc    = px * shares
px    = price_at(prices, period_end)
```

**There is no freshness predicate anywhere in this producer** — not in
the six Price/FCF guards, not in `mc`, not in `price_at`. A stale price
reaches the restored ratio exactly as it reaches P/E. The only
defensible claim is the narrower one: this release adds no *new*
exposure, because the column inherits the same `px` as its eleven
siblings. An exclusion must be shown by a predicate, and there is none.

**Documented freshness limit: none.** So "the count exceeding the limit"
is reported against candidate thresholds rather than answered with a
figure that would imply a limit exists.

### Measured on the 471 served rows

| | |
|---|---|
| median | 0 days |
| p75 / p95 / p99 | 0 / 0 / 0 days |
| **max** | **4 days** |

The four oldest, with the ratio each produced:

```
PMM  FY2025  period end 2025-06-30  price 2025-06-26   4d   37.0
CTD  FY2024  period end 2024-06-30  price 2024-06-28   2d   15.9105
IME  FY2025  period end 2025-12-31  price 2025-12-30   1d   85.375
JMS  FY2026  period end 2026-02-28  price 2026-02-27   1d   42.1558
```

### Coverage impact of a scoped withholding rule

| threshold | withheld | remaining | % lost |
|---|---|---|---|
| 7d | 0 | 471 | 0.0% |
| 30d | 0 | 471 | 0.0% |
| 90d | 0 | 471 | 0.0% |
| 180d | 0 | 471 | 0.0% |
| 365d | 0 | 471 | 0.0% |
| 730d | 0 | 471 | 0.0% |

**Zero at every threshold.** The 6,644-day cases are old fiscal years of
companies whose price feed stopped; the served row is a company's *latest*
fiscal year, and a company with a recent year and positive free cash flow
is still trading, so its price history reaches its period end.

So: the mechanism is present and the exposure is nil. A scoped rule would
cost nothing and would also protect nothing today — unexercised machinery
in the release's critical path, deepening the asymmetry of finding 20 for
no measured benefit. **Recommendation: do not add it in this release.**
P11 is now a standing instrument output, so a non-zero appears the moment
one exists, and finding 18's real repair is table-wide.

### Currency provenance of the served rows: INFERRED, not established

For all 471. `staging_au.fundamentals` is `UNIQUE (asx_code)`: one row,
one `reporting_currency`, read from whichever of Income_Statement /
Balance_Sheet / Cash_Flow first carries a `currency_symbol` **in the
latest snapshot**, applied to every fiscal year. Measured alongside it:
**0** served rows have a fiscal year older than the company's most recent
reported year, so the inference spans no gap on the served set today —
but it is still an inference. Finding 19.

## What "the gate result" does and does not establish

**It establishes no detected regression under this gate.** It does not
establish correctness, and "gated clean" overstated it.

| | candidate | baseline |
|---|---|---|
| files | 147 | 146 |
| passed | 145 | 144 |
| failed | 2 | 2 |
| inconclusive | **0** | 0 |

INTRODUCED: none. REPAIRED: none. UNVERIFIABLE: none. P0 primary-feature
contracts hold. `EXIT=0`.

The two failures, by name, relevance and disposition:

**`test_company_reads_are_current.py::test_no_new_ingestion_script_joins_the_base_table`**
— `scripts/stm/universe_prose.py` and `scripts/stm/universe_sidecars.py`
read `market.companies` unbounded and are not in the frozen legacy set.
Relevance to this release: **none** — both are STM documentation
generators, and the test's own docstring explains that an unbounded
worklist read "costs a repeated download, not a wrong number".
Disposition: pre-existing at the baseline, unchanged by this candidate,
not touched by it.

**`test_no_bindparam_followed_by_cast.py::test_no_bind_parameter_is_followed_by_a_double_colon_cast`**
— one offender, `scripts/stm/census_unwritten.py:85`, `SELECT
%s::regclass::oid`. **This is a false positive.** The matcher is
`BAD = r':[a-zA-Z_]\w*::[a-zA-Z]'`, which matches `:regclass::o` inside a
psycopg2 **double cast**; the script uses `%s` placeholders and has no
named bind parameter at all. The suite's own docstring warns about this
class — "a matcher reading its own explanation as the offence it warns
about" — and the executable AST-based property in the same file passes.
Disposition: pre-existing, a textual-matcher false positive in
diagnostics tooling, not a defect in the product and not blocking.

**The two Markdown-only commits were not re-gated separately.** The
executable tree is identical: `git diff --stat` between the gated SHA and
HEAD touches `database/stm/OPEN_FINDINGS.md` and this file only.

## The fingerprint bump recomputes rather than refuses — verified in code

`run_plans.check_yearly_reuse` returns `ReuseDecision(False, ...)` on a
schema mismatch, with the diagnosis *"fingerprint projection changed
(schema 1 → 2); the recorded fingerprint is not comparable and says
nothing about whether the sources moved"*. A refusal of **reuse**, not a
run failure — so `DAILY_CANONICAL` promotes to the full plan and
recomputes. The version is checked before the aggregate purely so the
message does not send someone looking for a source correction that never
happened. **Still to be confirmed in production** on the first run after
deploy; it is an acceptance criterion, not a settled fact.

## Not closed by this release

- **Finding 17** — `fcf_yield` carries the same unit mismatch, is
  reachable by gate 1b, and is a factor-model constituent. **Measured:
  167 of 178 foreign-reporter rows publish it, 78 inside the scored
  population**, so it moves a ranking rather than merely displaying.
  Fixing it changes scores under a frozen version name, so it needs V4.
- **Finding 18** — `price_at` has no floor. See the section above: the
  mechanism reaches Price/FCF, the measured exposure on served rows is
  nil, and the sibling-wide repair is its own release.
- **Finding 19** — one reporting currency per company, from the latest
  snapshot, applied to all history. Not fixable from this source.
- **Finding 20** — the P/E-publishes-where-Price/FCF-does-not
  inconsistency this release deliberately creates. Needs V4, with 17.
