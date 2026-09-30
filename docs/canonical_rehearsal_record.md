# Canonical orchestration rehearsal — release record

**Date:** 30 September 2026
**Branch:** `orchestration-design`
**Target:** `asx_screener_scratch` (clone of production, taken 30 Sep 2026)
**Authorization:** scratch rehearsal only. No `main` push, no deploy, no
restoration of production scheduling.

**Board:**

| | |
|---|---|
| P0-A-2 orchestration rehearsal | **PASS** |
| Phase 6 production rollout | **BLOCKED** — upstream ingestion completeness and non-vacuous producer proof |

This document is the release record. The Phase 6 decision depends on it and on
the machine evidence it cites, not on a reconstruction from a terminal session.

---

## Why this exists

The programme's governing principle: **no number may be served that the system
cannot substantiate.** The rehearsal was designed to prove the orchestration
contract in `canonical_orchestration.md`:

> The pipeline chooses the plan; the fingerprint validates the plan; the derived
> dependency boundary determines ownership; the canonical driver owns governed
> mutation; the lease serializes shared mutable execution; finalisation grants
> authority; freshness monitoring proves that authority is still current.

Phases 1–5 prove that contract holds. They also exposed a hole *upstream* of
it, which is why Phase 6 does not follow from a green rehearsal.

---

## Phase results

### Phase 1 — clone · PASS

`CLONE ACCEPTED`, 6,894,580 rows. Two prior attempts failed; the second was
interrupted at 1.4% populated and was caught by `CLONE NOT ACCEPTED` rather
than by inspection. Cause: the clone was not run detached. Re-cloned under
`nohup`.

### Phase 2 — baseline · PASS

Database `asx_screener_scratch`. No yfinance staging table. Baseline run 1,
2,118 rows, `price_as_of 2026-09-23`, 2,118 attributed of 2,534 universe rows.

### Phase 3 — daily wrapper · PASS

Log: `/var/backups/p0a/discovery/rehearsal_daily_20260930T032010Z.log`

```
03:28:11  canonical execution lease acquired by daily_pipeline
03:28:11  target database: asx_screener_scratch
03:29:21  reuse PERMITTED: yearly source fingerprint is unchanged
          [6 stages, each missing 0 / extra 0, stage SUCCESS recorded]
04:02:48  ✓ yearly source fingerprint still current at publication: 8a805d098b4d74ec
04:02:59  read-back rows: 2,114 / validation: PASS / validator elapsed: 1.65s
04:02:59  PUBLISHED: run 2, 2,114 rows, 0 violations
```

The lease is taken **before** plan admission, which is the ordering the design
requires — the fingerprint is evaluated inside the lease, not outside it.

### Gate B against run 2 · PASS

```
snapshot=snap_44e7018e401104d8  run_ids=[1, 2]  total=2114  capped=False
rows-in-scope=50/50  served=2782  unexplained-blanks=0  out-of-scope-suppressions=0
unfiltered: total=2114  ranked_total=1985  excluded=129 (storage says 129 cannot participate)
csv: 194 served, 56 blank because suppressed, 0 leaked, 0 dropped
```

`run_ids=[1, 2]` is correct, not a defect: run 2 was `DAILY_CANONICAL`, which
republishes a subset, so served rows legitimately carry attribution from both
runs. The gate separately confirmed some sampled rows are run 2's.

**Gate B has no freshness predicate.** `unexplained-blanks=0` means every blank
has a contract reason; it does **not** mean every served value is current. See
"Open, not blocking" below.

### Phase 4 — contention · PASS

First attempt was **inconclusive, not failed**. `short_positions` returned at
`short_positions.py:168` because ASIC published no report for 20–30 Sep, and
never reached the lease at line 190. It wrote nothing, but proved nothing.

Re-run driving the lease at the job's own call site, with its own `_sync_dsn()`,
holding the lock from an independent session:

```
lease key 8090141026 held by 1 session(s)
A contended         -> permitted=False   (waited the full configured 300s)
B contended+inherit -> permitted=True
C uncontended       -> permitted=True
```

**C is what makes A meaningful.** Without the uncontended control, a lease
hard-wired to refuse would produce an identical pass. The contended case defers
after waiting — it does not hang, and it does not write.

Scope limit: this entered below the ASIC download, so the lease and its DSN
resolution are proven; the download path above them is not.

### Phase 5 — weekly wrapper · PASS

Log: `/var/backups/p0a/discovery/rehearsal_weekly_20260930T043116Z.log`

| # | assertion | evidence |
|---|---|---|
| 1 | lease before admission | `05:17:54 canonical execution lease acquired by weekly_pipeline`; run 3 created `05:17:55` |
| 2 | plan not downgraded | `── canonical execution: FULL_FUNDAMENTALS_CANONICAL ──` |
| 3 | finalised, 0 violations | `06:16:05 PUBLISHED: run 3, 2,114 rows, 0 violations` |
| 4 | `pros_cons` **inherits** | `06:16:06 pros_cons: running inside the caller's canonical lease` |
| 5 | lease released after suffix | `06:16:08 ... released by weekly_pipeline`, after steps 9b and 9c |
| 6 | no unexplained failure | no ERROR/FAILED/Traceback |

Assertion 4 is the one this phase existed for. Without it the suffix would
defer against its own wrapper's lock — silently, every week.

Run 3 stage evidence, all `success`, all `expected_set_hash = written_set_hash`:

```
daily_compute           1859 / 1859      universe_build         2538 / 2538
halfyearly_compute     32039 / 32039     yearly_compute        33809 / 33809
period_metrics_compute  2404 / 2404      technical_compute      1870 / 1870
transform_prices           0 /    0
```

### Production sentinel · UNCHANGED

`max(run_id) = 1`, 2,534 universe rows. Nothing escaped scratch.

---

## Blockers for Phase 6

The rehearsal exposed a chain that lets a production FULL run publish
successfully on incomplete inputs:

> `files → staging` can lose rows (loader rollback defect) → downstream stages
> derive their expected populations from that already-incomplete staging →
> every downstream set-equality proof therefore passes → canonical publication
> finalises cleanly while an upstream refresh was silently incomplete.

This is precisely the failure the population-proof architecture exists to
prevent. Containment held in the observed case, but **a failed refresh
disappeared from the proof chain**, and that is release-gating.

### B1 — loader transaction and miscount defect

`scripts/eodhd/v2/load_to_staging_fundamentals.py` commits every
`BATCH_COMMIT = 50` files, but its per-file `except` calls `conn.rollback()`,
which is per-connection. One bad file discards every row staged since the last
commit. Those files already incremented `done`, so `DONE — N files loaded`
counts rows the database threw away.

Observed 30 Sep: `ATM` (Aneka Tambang, an Indonesian listing whose
rupiah-denominated figures overflow a column sized for AUD) failed ten weekly
snapshots. `ATH` — Alterity Therapeutics, a real ASX company — and its
deferred-settlement line `ATHDA` are alphabetically adjacent, shared those
batches, and lost every staging row. 2,019 codes have files; 2,016 reached
staging.

**Required:** written evidence must follow commit boundaries. The compute
engines already do this — `technical_compute.py` and `halfyearly_compute.py`
split `written` (survived a COMMIT) from `pending` (accepted since the last
one) and document exactly this hazard. The loader is the place the pattern was
not applied. A per-file `SAVEPOINT` is the narrower alternative.

Separately: widen the overflowing column, or reject non-AUD reporting
currencies at parse time. Fixing only the overflow leaves the amplifier armed
for the next bad file.

### B2 — independent `files → staging` population proof

Every stage proves it covered **its own source population**, which is exactly
what `add_compute_run_stages.sql` promises and is the correct contract. But the
one transition where rows were actually lost is outside every stage's contract.

**Required:** an expected population derived from the input files / source
manifest, never from staging itself. A missing company or period must fail the
load, not silently shrink the domain that downstream stages then prove
themselves against.

### B3 — no vacuous producer success

`transform_prices` recorded `status=success`, `expected 0 / written 0`,
`hashes_equal = true`. Set equality over two empty sets is vacuously true: a
proof-shaped record containing no proof.

**Required:** `expected=0, written=0` must not automatically be SUCCESS.
`transform_prices` needs either a positive expected population, or an explicit
and independently proved `NO_WORK_EXPECTED` condition for that window.

---

## Corrections

Recorded because a release record that omits what was claimed wrongly is worth
less than one that includes it.

| claimed | actual |
|---|---|
| serving would drop 2,118 → 2,110 after deleting the yfinance backfill | 2,114. Deleting the job stops acquisition; it does not remove the 1,849 existing rows |
| Phase 4 attempt 1 was an abort | inconclusive — the job returned before reaching the lease |
| the batch rollback might have shredded coverage across hundreds of codes | measured: 3 codes |
| ATH's `roe` came from stale `market.yearly_metrics` | ATH has **0** rows there |
| a `COALESCE(EXCLUDED.x, universe.x)` was preserving stale values | the rebuild overwrites unconditionally (`roe = EXCLUDED.roe`) |
| ATH is serving a value the system cannot substantiate | ATH's `roe = -0.2866` was computed by run 3 **today**; the loader failure cost the refresh, not the basis |
| the `plan_name` migration might be missing | `plan_name` and `factor_model_version` are on `screener.compute_runs`; finalisation carries the plan in `details` |
| production sentinel should read 2,118 rows | 2,118 is the **attributed/served** count; the table holds 2,534 |

Containment held throughout. `ATHDA` carries `quality_score = 26` with
`compute_run_id` NULL — unattributed, outside the published 2,114, never
served. Gate B's `total=2114` is that boundary working.

---

## Open, not blocking

- **Eight instruments served at 35–49 days stale.** MTN, USIG, FRGG, XASG,
  DVDY (49d); IMLC, APW (48d); HGODB (35d). The frozen decision of 30 Sep says
  *"instruments without a sufficiently current supported price source are
  excluded from the serving population"* — that is **not yet implemented**.
  Deleting the job stopped acquisition only. Two routes: delete the 1,849
  yahoo rows (targeted, matches the decision), or add a freshness predicate so
  a stale price is not a served price (more general, changes a frozen
  contract). Product decision.
- **`compute_run_finalizations.snapshot_id` is NULL on all three scratch runs**,
  reproducing the known backlog item.
- **ATH's `computed_metrics` frozen since 12 Jun 2026** — `daily_compute`
  never expected it, because it has no current price. Contractually legitimate.

---

## What a re-proof needs

The fixes are upstream of orchestration and should not require repeating the
full three-hour rehearsal unless they alter orchestration semantics. Minimum:

1. rerun the affected load/transform path on scratch
2. prove the new failures **bite** under induced omission and induced rollback —
   a fix that cannot be made to fail has not been shown to work
3. one FULL canonical cycle through Gate B
