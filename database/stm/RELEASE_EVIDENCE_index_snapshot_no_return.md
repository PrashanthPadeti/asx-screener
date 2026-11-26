# Release evidence — `market.index_snapshots.no_return`

The index snapshot stage refused to publish from **20 November 2026**:

```
SnapshotIncomplete: ASX300: 1 of 277 constituents have no return_1w, and
index_snapshots has no column to record that. Add one rather than counting
them as unchanged.
```

The Market Overview page served 19 November index and sector figures for three
days as a result. The refusal was deliberate and correct: the table could hold
`gainers`, `losers` and `unchanged`, and the only bucket wide enough to take a
constituent whose 1-week return is unknown was `unchanged`, which asserts the
price did not move.

This release adds the destination the refusal asked for and replaces the
refusal with two checks that fail for different reasons.

## What changed

| Layer | File | Change |
|---|---|---|
| Store | `database/migrations/066_index_snapshot_no_return.sql` | `no_return INT`, NULLable, **no DEFAULT** |
| Producer | `backend/compute/engine/market_snapshot.py` | writes `no_return`; partition + coverage checks replace the refusal; logs the average's coverage |
| Contract | `backend/compute/engine/snapshot_stages.py` | `INDEX_PARTITION`, `MAX_UNATTRIBUTED_FRACTION`, `index_partition_gap`, `index_coverage_refusal` |
| API | `backend/app/api/v1/routes/market.py`, `app/schemas/market.py` | selects and returns it; `Optional[int]`, no `or 0` |
| Page | `frontend/app/market/page.tsx`, `lib/api.ts` | renders null, zero and non-zero as three distinct states |
| Tests | `backend/tests/test_market_snapshot_stages.py` | 25 tests, one per layer plus both outcomes of each check |

## Why the column has no DEFAULT

`no_return` carries "we do not know". A `DEFAULT 0` would back-fill a confident
*none were missing* across every snapshot written before today — performing in
the store the exact destruction the producer refused to perform. Three states,
and each one survives to the customer:

| Value | Meaning | Page |
|---|---|---|
| `NULL` | snapshot predates the measurement | "coverage not recorded" |
| `0` | measured; every constituent had a return | nothing |
| `> 0` | measured; this many did not | "*n* no 1W return" |

## The two checks

**`index_partition_gap`** — `gainers + losers + unchanged + no_return` must
equal `stock_count`. This could not be checked before: while `unchanged`
counted `return_1w = 0 OR return_1w IS NULL`, the four numbers still summed
correctly, because one bucket was absorbing another's rows. It also catches a
`NaN` return, which satisfies none of `> 0`, `< 0`, `= 0` or `IS NULL` and
would otherwise vanish from all four buckets while the total still claimed it.

**`index_coverage_refusal`** — `AVG(return_1w)` skips NULLs, so beyond a
declared bound (`MAX_UNATTRIBUTED_FRACTION = 0.02`) the published figure is the
average of a subset wearing the index's name. 1 of 277 (0.4%) publishes; 40 of
277 (14%) refuses, because at that scale the cause is a mid-rebuild universe or
a failed price load upstream, not a handful of companies without a week of
prices.

Both are pure functions in `snapshot_stages`, which imports nothing
third-party, so they are asserted without a database. The call site is asserted
separately — a pure function nobody calls is a comment.

## Deployment order (matters)

`deploy.sh` does **not** run migrations. The new INSERT names `no_return`, so
deploying the code first fails on a missing column and leaves the stage broken
in a new way.

1. Apply migration 066. Backward-compatible: the currently deployed producer
   never names the column.
2. Confirm the column exists and is NULLable with no default.
3. Deploy the code.
4. Run the snapshot and read the log line — it now prints `no_return=` and the
   coverage its average was taken over.
5. Confirm `market.index_snapshots` has a row for the run date with
   `no_return` populated, and that the four buckets sum to `stock_count`.
6. Confirm the Market Overview page shows the amber "*n* no 1W return" line.

## Mutation coverage

See the commit for the run. Each mutation restores from the commit under test,
not from `main` — a first attempt used `git checkout -- <path>` on uncommitted
work, which reverted to the index and silently deleted the changes it was
testing, making every result in that run void.

## Not fixed, and separate

`market.sector_snapshots` has no `unchanged` column at all. `gainers + losers`
there has never reconciled with `stock_count`, and a sector's average silently
covers whatever rows had a return. Same defect class, different table, its own
migration and page work — filed rather than folded into this release.
