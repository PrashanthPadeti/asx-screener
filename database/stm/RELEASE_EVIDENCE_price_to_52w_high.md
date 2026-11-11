# Release evidence — `price_to_52w_high`

**Branch:** `fix/price-to-52w-high-frozen`, from `main` at `f4f1c24` (v11.2.77)
**Change:** three lines in `build_screener_universe.py` — the column list at
position 247, the SELECT expression at the same position, the conflict
assignment.

A green test is not evidence for this fix. The defect was that a value never
changed; the evidence has to be that values changed, and that the changed
values reached the surfaces serving them.

---

## Before — measured 10 Nov 2026

```
rows                                             2,566
held a stored value                              2,290
recomputable from their own row                  1,837
differed by more than 0.01                       1,674   (91.1%)
median absolute error                             0.10
worst                                             0.93
```

A ratio whose useful range is 0–1 was off by 0.10 at the median. A stock
actually at 0.95 of its 52-week high could be stored as 0.85, and the
screener would rank and filter on the stored figure.

---

## Step 0 — before deploying, measure what the fix will NOT reach

The builder upserts `market.companies_current`, minus `EXCLUDED_TYPES`,
narrowed again by `current_source_predicate()`. The job's only `DELETE`
removes excluded security types. **A universe row whose code is outside that
population is never touched by any run**, so it keeps its frozen value after
this fix lands.

That number has to be known before the repair, not discovered after it:

The predicates below are the ones the code uses, read from
`compute/engine/serving_population.py` rather than approximated:
`EXCLUDED_COMPANY_TYPES = ('notes', 'preferred_stock')` and
`RETIRED_PRICE_SOURCES = ('yahoo',)`. The builder applies the first; the
second reaches the statement through `current_source_predicate()`.

```sql
WITH reachable AS (
  SELECT asx_code
    FROM market.companies_current
   WHERE COALESCE(company_type, '') NOT IN ('notes', 'preferred_stock')
)
SELECT count(*) AS universe_rows,
       count(*) FILTER (WHERE u.asx_code NOT IN (SELECT asx_code FROM reachable))
         AS outside_the_upsert_population,
       count(*) FILTER (WHERE u.price_to_52w_high IS NOT NULL
                          AND u.asx_code NOT IN (SELECT asx_code FROM reachable))
         AS frozen_and_unreachable
  FROM screener.universe u;
```

If `frozen_and_unreachable` is non-zero, those rows keep a stale ratio after
the fix lands and need a separate one-off correction or deletion. **The
repair is not complete without that number being zero or explained.**

The two predicates are spelled inline in the source, deliberately, because
they land in queries carrying their own parameters — so this query copies
them rather than importing them, and that copy is exactly the kind that
drifts. Re-read both constants before running it.

---

## Step 1 — deploy and run

Merge to `main`, tag, deploy via `deploy.sh`, then one universe build. The
fix corrects existing rows through the `ON CONFLICT` path, so no backfill is
needed for rows inside the population.

---

## Step 2 — the value moved

The same query as the Before measurement. **Acceptance: `differs_gt_1pct` is
0.**

```sql
SELECT count(*) AS have_stored,
       count(*) FILTER (
         WHERE abs(price_to_52w_high - (price / NULLIF(high_52w, 0))) > 0.01
       ) AS differs_gt_1pct,
       round(max(abs(price_to_52w_high
                     - (price / NULLIF(high_52w, 0))))::numeric, 4) AS max_diff
  FROM screener.universe
 WHERE price_to_52w_high IS NOT NULL
   AND price IS NOT NULL AND high_52w > 0;
```

A non-zero result here means the column is still not being written, and no
other evidence matters.

---

## Step 3 — unavailable replaced a stale value with NULL

The direction that distinguishes this fix from one that only writes when it
can. 453 rows held a stored value and could not be recomputed, because their
`price` or `high_52w` was absent. After the run those rows must hold NULL,
not the old ratio.

```sql
SELECT count(*) AS cannot_compute,
       count(price_to_52w_high) AS still_holding_a_value
  FROM screener.universe
 WHERE price IS NULL OR high_52w IS NULL OR high_52w <= 0;
```

**Acceptance: `still_holding_a_value` is 0.** A non-zero result means a
stale ratio survived its own inputs disappearing, which is the original
defect in a smaller population.

---

## Step 4 — the refreshed value reaches users

Three surfaces, checked through the API rather than the database, because
the database agreeing with itself proves nothing about what is served.

1. **Response field.** Fetch a company whose stored value moved in step 2,
   and confirm the served `price_to_52w_high` equals `price / high_52w` from
   the same response.
2. **Filter.** `price_to_52w_high` between 0.95 and 1.0 must return
   companies near their 52-week high, and each returned row must satisfy
   the predicate against its own served `price` and `high_52w`.
3. **Sort.** Ordering by `price_to_52w_high` descending must put companies
   at their high first, and — per v11.2.76 — must not drop companies whose
   value is NULL from the result set.

Record the company codes used, so the check can be repeated.

---

## What the tests do and do not establish

`test_universe_upsert_refreshes_every_column` asserts the general property
over all 342 columns: every inserted column is reassigned on conflict, the
only unlisted assignments are the two the builder deliberately revokes,
every assignment takes `EXCLUDED` plainly rather than `COALESCE`-ing with
the stored value, no column is assigned twice, and every ratio guards its
denominator.

Seven mutants were run against it and all seven were killed, including the
two that look like care — a `COALESCE` preserving the old value, and a ratio
with its `CASE` guard removed.

None of that shows a single number changed in production. Steps 2 to 4 do.

---

## First production run: the statement could not execute (10 Nov 2026)

The deploy shipped the code. The first canonical run after it died before
writing a row:

    IndexError: list index out of range
      build_screener_universe.py:2118, in cur.execute(sql, params)

Not a data problem. psycopg2 interpolates a query client-side with Python's
`%` operator and sends one finished string, so the statement is a FORMAT
STRING — and a `--` comment is invisible to Postgres but fully visible to
`%`. The comment added above the repair contained

    -- 1,674 (91.1%) were wrong by more than 0.01

with the percent undoubled. Every other percent in that 2,000-line statement
is correctly `%%`. The comment documenting the repair is what prevented the
repair from ever running.

The pipeline then failed a second time, in the handler reporting the first:

    TypeError: finish_step() got an unexpected keyword argument 'error'

The parameter is `error_msg`. Four older call sites pass it correctly; the
two added when the canonical driver was wrapped pass `error`, and both are
reached only after something has already failed — so neither had ever
executed. The step was never marked failed, and the operator's log shows a
keyword-argument traceback instead of the database error that mattered.

### What this says about the evidence above

Every claim in the preceding sections was true and none of it was sufficient.
The statement was parsed, its column list counted, its `ON CONFLICT` set
checked column by column, and seven mutants killed — by tests that read the
SQL as text and never asked the driver to accept it. Structural evidence
establishes machinery; only execution establishes that the machinery runs.

That gap is now closed at the gate rather than in production:

* `tests/test_sql_constants_are_executable.py` interpolates every SQL
  constant and every inline statement the way psycopg2 does, plus the upsert
  assembled exactly as `main()` assembles it, and checks placeholder arity
  against the parameters `main()` passes, for several `--codes` lists.
* `tests/test_pipeline_calls_bind_to_their_signatures.py` binds every call
  site in the pipeline to the signature it names, and refuses two spellings
  of one argument.

Ten mutants were run against the pair — including both real defects, at both
of their call sites — and all ten were killed.

The acceptance thresholds in steps 2 to 4 are unchanged and still unmet. They
remain the only evidence that a user's number moved.
