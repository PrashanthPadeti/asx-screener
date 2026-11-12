# Finding 13 — measurement before the fix

The finding says the defect is that a derived metric is not governed. Reading
the code says something narrower and more fixable:

**`build_screener_universe.py` computes the 52-week extreme a second time,
with no coverage rule, and derives four columns from that second number.**

```sql
-- the lateral, build_screener_universe.py:1150
LEFT JOIN LATERAL (
    SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
    FROM market.daily_prices
    WHERE asx_code = c.asx_code
      AND time >= NOW() - INTERVAL '365 days'
) dp52 ON TRUE
```

`MAX(high)` over whatever rows exist inside the window. A stock with 196
days of history gets the maximum of 196 days and the builder calls it
`high_52w`. There is no minimum span, no anchor check, and nothing recorded.

The governed producer is different and correct. `technical_compute` uses
`rolling_extreme`, which blanks a row whose series does not span 365 days,
and `window_states` records why. So the system holds **two** definitions of
the same quantity:

| producer | rule | coverage check |
|---|---|---|
| `technical_compute.rolling_extreme` → `market.daily_metrics.high_52w` | spans 365 calendar days | yes, with a recorded reason |
| `dp52` in the builder → everything derived in the universe | `MAX(high)` over rows present | **none** |

The canonical commit overwrites `screener.universe.high_52w` with the
governed assessment, so that column goes NULL where coverage is
insufficient. The four columns derived from `dp52` are not governed and keep
the shadow number. That is the mechanism behind the 393 + 57 rows the
finding reports, and it also explains why `high_present` was exactly 0 while
`ratio_present` was exactly the row count: the two columns never came from
the same computation.

Two of the four are worse than a wrong ratio:

```sql
-- build_screener_universe.py:799
CASE WHEN dp.close IS NOT NULL AND dp52.high_52w IS NOT NULL
     AND dp.close >= dp52.high_52w THEN TRUE ELSE FALSE END AS new_52w_high
```

`ELSE FALSE`. Where the extreme is unknown this writes a confident "this
stock did not make a new 52-week high". Hand-written, not a pandas
collapse — the same defect as finding 10 in its most explicit form.

## What must be measured before the fix

### Q1 — is `FACTOR_MODEL_V3` frozen?

Governing the four derived metrics changes the contract. The freeze rule in
`metric_states.py` is explicit: once a production run is finalised under a
version, that version stops being amendable and the change goes to the next
one. This decides whether the governance half of the fix needs **V4**.

```sql
SELECT r.factor_model_version,
       count(*)            AS runs,
       count(f.run_id)     AS finalised,
       min(r.run_at)::date AS first_run,
       max(r.run_at)::date AS last_run
  FROM screener.compute_runs r
  LEFT JOIN screener.compute_run_finalizations f ON f.run_id = r.id
 GROUP BY 1
 ORDER BY 1;
```

Reading it: any row with `finalised > 0` names a frozen version.

### Q2 — current state of the four derived columns

Reproduces the finding's own measurement and adds the two booleans it did
not count. One scan of an ordinary 2,566-row table.

```sql
SELECT (u.high_52w IS NULL)                            AS high_withheld,
       count(*)                                        AS rows,
       count(u.price_to_52w_high)                      AS ratio_present,
       count(*) FILTER (WHERE u.new_52w_high IS TRUE)  AS new_high_true,
       count(*) FILTER (WHERE u.new_52w_high IS FALSE) AS new_high_false,
       count(*) FILTER (WHERE u.new_52w_high IS NULL)  AS new_high_null
  FROM screener.universe u
 GROUP BY 1
 ORDER BY 1;
```

```sql
SELECT (u.low_52w IS NULL)                            AS low_withheld,
       count(*)                                       AS rows,
       count(u.price_to_52w_low)                       AS ratio_present,
       count(*) FILTER (WHERE u.new_52w_low IS TRUE)   AS new_low_true,
       count(*) FILTER (WHERE u.new_52w_low IS FALSE)  AS new_low_false,
       count(*) FILTER (WHERE u.new_52w_low IS NULL)   AS new_low_null
  FROM screener.universe u
 GROUP BY 1
 ORDER BY 1;
```

The expected shape, if the diagnosis is right: in the `high_withheld = true`
group the ratio is present on most rows, `new_high_null` is 0, and
`new_high_false` is the whole group.

### Q3 — how far the shadow number is from the governed one

The decisive one, and it is cheap. Since v11.2.78 the builder computes the
ratio from `dp52.high_52w` while the stored `high_52w` is the governed
value. So on rows where both are present, differencing the stored ratio
against one recomputed from the stored high measures the disagreement
between the two producers directly.

```sql
SELECT count(*) AS both_present,
       count(*) FILTER (
         WHERE abs(u.price_to_52w_high - (u.price / NULLIF(u.high_52w, 0))) > 0.01
       ) AS differs_gt_1pct,
       round(max(abs(u.price_to_52w_high
                     - (u.price / NULLIF(u.high_52w, 0))))::numeric, 4) AS max_diff
  FROM screener.universe u
 WHERE u.price_to_52w_high IS NOT NULL
   AND u.high_52w > 0
   AND u.price IS NOT NULL;
```

If `differs_gt_1pct` is 0 the two producers agree wherever coverage is
sufficient, and the defect is confined to the insufficient-coverage rows.
If it is not 0 the shadow computation is wrong in the general case as well —
`MAX(high)` against `rolling_extreme` over the same span should agree, so a
difference would mean the two are reading different price series, which is
the adjusted-vs-unadjusted question from `docs/finding_2026-10-24`.

Either answer changes the fix, which is why this runs before the fix.

**Not included, deliberately:** reconstructing `dp52` from
`market.daily_prices` to compare the two producers directly. That is a
`MAX(high)` over 365 days for 2,566 companies against a hypertable, which is
the shape that OOM-killed PostgreSQL on 28 Oct. Q3 obtains the same answer
from the 2,566-row table that already holds both numbers.
