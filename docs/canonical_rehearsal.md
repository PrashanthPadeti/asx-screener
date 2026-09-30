# Rehearsal runbook — items 5 and 6

Everything that can be proved without data is done: 923 tests, boundary
clean, both pipelines rewritten as wrappers. What remains is runtime, and
this exists so the window is spent **running** the sequence rather than
deciding it.

Written before the window deliberately. The last freeze that was planned
inside its own window overran and cost production its 08:30 daily pipeline.

---

## What this proves

| | |
|---|---|
| **Item 5** | prefix → lease → driver → finalisation → leased suffix, against real data, both plans |
| **Item 2 remainder** | yfinance rows survive staging until consumed; merged transform matches the old direct write; acquisition is idempotent; acquisition failure leaves `market.daily_prices` untouched |
| **Item 3/4 runtime** | the lease actually serializes; an auxiliary writer defers rather than writing alongside |

## Window

**~3 hours, operator present.** Weekend morning UTC, well clear of 08:30 —
the daily cron is disabled, but production's other jobs are not, and the
scratch clone is taken from production.

Nothing in phases 1–5 touches production. Phase 6 does, and stops for an
explicit decision first.

---

## Phase 1 — scratch, fresh (~30 min)

1. Fresh clone via `p0a_discovery.sh`. It now verifies
   `staging_au.yfinance_prices`; a clone that lost it fails here rather than
   four stages into the run.
2. Apply `migrations/add_yfinance_price_staging.sql` **to scratch only**.
3. Confirm the table exists and is empty.

## Phase 2 — acquisition into staging (~20 min)

4. Run `backfill_yfinance_prices.py --days 3` against scratch.
5. **Prove rows landed in staging and NOT in `market.daily_prices`.** Compare
   `max(time)` in `market.daily_prices` before and after: it must not move.
   This is the item-2 property that matters most — the acquisition has no
   publication authority.
6. Run it a second time. Row count unchanged, `fetched_at` updated:
   idempotence on `(asx_code, date)`.

## Phase 3 — the daily wrapper (~90 min)

7. Capture the baseline: finalised run id, `universe_built_at`,
   `price_as_of`, attributed row count.
8. Run `daily_pipeline.py` end to end against scratch.
9. Expect: prefix completes; lease acquired; driver admits, runs seven
   stages, finalises; suffix runs.
10. **Prove the merge.** Every `(asx_code, date)` present in both feeds must
    carry `data_source = 'eodhd'`; rows only yfinance supplied must carry
    `'yfinance'`. Precedence is declared — this is where it is observed.
11. Gate B against the new run id.

## Phase 4 — contention (~15 min)

12. While the driver is running, start `short_positions` manually.
13. **Expect it to DEFER**, log the holder, and exit without writing. This is
    the one proof that the lease does something; without it, "the lease is
    taken" is a claim about code that never contended.

## Phase 5 — the weekly wrapper (~60 min)

14. Run `weekly_pipeline.py` against scratch.
15. Expect `FULL_FUNDAMENTALS_CANONICAL`, eight stages, a second finalisation,
    then `pros_cons` and `sector_benchmarks` in the suffix — with `pros_cons`
    **inheriting** the lease rather than deferring. If it defers, the
    inheritance marker is not reaching the subprocess and the weekly suffix
    would silently stop running.
16. Gate B against that run id too.

## Phase 6 — production (STOP HERE FOR A DECISION)

Nothing below happens without explicit authorization, and the phases above
must be green first.

17. Merge `orchestration-design` → `main`.
18. Deploy. Expect the Server Action login symptom for stale tabs.
19. Apply `add_yfinance_price_staging.sql` to **production**.
20. Re-enable the `daily_pipeline` and `weekly_pipeline` cron entries;
    **remove** the independent 09:00 yfinance cron, which the daily prefix
    now owns.
21. Watch the first unattended daily run. Confirm a finalisation appeared and
    Gate B is green against it.

---

## Abort conditions

Stop and do not proceed to the next phase if:

- the clone fails verification, or the migration does not apply cleanly;
- `market.daily_prices` moves during phase 2 — the acquisition is still
  publishing, and the whole of item 2 is unproven;
- the driver refuses admission for a reason the runbook did not predict;
- `short_positions` does **not** defer in phase 4 — the lease is decorative;
- `pros_cons` **does** defer in phase 5 — the weekly suffix would silently
  stop running in production;
- Gate B is red against either run id.

Every one of these leaves scratch in a state that can be thrown away, which
is the point of rehearsing there.

## What failure means here

A phase failing is the rehearsal working. The alternative is discovering the
same thing at 08:30 UTC on a weekday with the contract revoked and no
attended operator — which is the exact situation the disabled crons exist to
prevent.
