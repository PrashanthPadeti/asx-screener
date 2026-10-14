# A fund can be counted `obtained` and still not be current

**Found:** 14 October 2026, verifying the v11.2.22 deployment
**Status:** OPEN — recorded, not fixed
**Scope:** `ProducerTally.obtained()` / the definition of a usable outcome

## What was observed

The 06:37 UTC `fund_prices` run reported:

```
fund_prices population: 55 eligible, 55 configured, 0 omitted, 0 stale
fund_prices: 53/55 obtained, 0 refused, 2 empty, 157 rows
```

Read against the database, the funds without a 14 October price are **four**,
not two:

```
PMC      None          <- no price rows at all
DIV      None          <- no price rows at all
AUST     2026-10-13
ETPMAG   2026-10-13
```

`DIV` and `PMC` are the two `empty`. **`AUST` and `ETPMAG` are among the 53
counted as `obtained`.**

## Why both statements are true

`backfill_days=3`, so each fund is fetched over a three-day window and 157
rows across 53 funds is roughly three rows each. `obtained(code, rows)` is
recorded whenever the upsert wrote at least one row in that window:

```python
count = await upsert_price_rows(db, code, rows, dry_run)
tally.obtained(code, count)
```

A fund whose provider served 12 and 13 October but not 14 October writes two
rows, is counted `usable`, contributes to `53/55`, and is a session behind.
The count is of **rows written in the window**, not of **the last expected
session being present**.

## Why this matters

It is the same shape as the defects this workstream has been closing, one
level further in. The population is now derived from the source, and the
per-entity outcomes now say which entities failed — but `usable` itself is a
verdict computed from a window, and a window cannot see what falls outside
it. A fund can satisfy every check the producer makes and still be stale on
the site.

Note what it does *not* do: nothing here publishes a wrong number. The
freshness layer (`series_provenance`) reads `max(price_date)` independently
and will mark these funds `delayed`, then `stale`, on their own merits. The
defect is in what the **producer** claims, not in what the customer is
served.

## What is not established

- **Why** AUST and ETPMAG are short a session. The provider served *some*
  rows for both, so this is not a refusal and not an empty response. Whether
  the provider lacks 14 October for these two, or something in the window
  filtering drops it, is unmeasured.
- Whether this is persistent or a single day's behaviour. One observation.
- ETPMAG was previously noted as missing its 13 October row and now has it,
  which suggests late arrival rather than permanent absence — but one
  recovery is not a pattern.

## The open question

Should `obtained` require the last expected session, or should a new outcome
sit between `usable` and `empty` — served, but not current?

This is a verdict-definition question and deserves its own evidence.
Tightening `obtained` to demand the latest session would reclassify every
fund on any day its provider publishes late, which is the behaviour
`freshness_status` already models with `delayed` and deliberately does not
treat as a fault. Picking either answer today would be inventing a
completeness rule without measuring it first — the same reasoning that kept
a partial-run threshold out of `producer_contract`.

**Next step:** measure it. Count, over a fortnight, how often a fund counted
`obtained` lacks the last expected session, and whether it recovers on the
following run. A rule that fires on normal late publication is worse than no
rule.

## Related

- `docs/design_fund_population_and_lifecycle.md` — the population half
- `engineering_rule_verdict_from_filtered_view` — the family this belongs to
- `backend/app/core/series_provenance.py` — where currency *is* measured
