# Canonical orchestration — frozen design

> **The pipeline chooses the plan; the fingerprint validates the plan; the
> derived dependency boundary determines ownership; the canonical driver owns
> governed mutation; the lease serializes shared mutable execution;
> finalisation grants authority; freshness monitoring proves that authority is
> still current.**

**Status: frozen, 23 September 2026.** Implementation against this note should
be mechanical. Reopening any rule below is a deliberate design decision with
its own evidence, not something settled in passing during implementation.

---

## The defect this exists to fix

Production published its first canonical V2 run on 23 September 2026 — run 1,
`FULL_FUNDAMENTALS_CANONICAL`, 2,118 rows, 0 violations, Gate B green. Within
hours it became clear the publication could not survive a day.

`build_screener_universe` ends its UPSERT with `metric_states = NULL,
compute_run_id = NULL`. That is correct and deliberate: the V2 temporal
invariant says any writer changing one of the 72 governed columns must either
be part of a canonical run ending in finalisation, or **invalidate the old
contract atomically with its write**. It chooses invalidation.

Three pipelines call it — `daily_pipeline` (08:30 UTC, Mon–Fri),
`weekly_pipeline` (21:00 UTC, Sunday) and `monthly_pipeline` (manual) — and
**none of them ends in a canonical run.** `daily_pipeline` never runs
`composite_score` at all; `weekly_pipeline` runs `composite_score.py` directly,
producing no run id and no finalisation.

So every weekday morning the contract is revoked and nothing re-establishes
it. The governed surface fails closed, which is the contract working; the
product shows blanks, which is not a product. The fix is not to stop
invalidating. It is to make every universe rebuild part of a canonical run.

**Exclusivity is not the fix.** Two *sequential* runs in a day are the A→B
pattern already rehearsed, and are harmless. Two *concurrent* runs are not —
see the lease, below. Scheduling exclusivity addresses duplicated compute, a
cost question, and must not be mistaken for the correctness fix.

---

## The shape

```
INGESTION PREFIX
    ↓
canonical execution boundary       ← acquire lease
    ↓
PLAN ADMISSION                     ← fingerprint validates the requested plan
    ↓
CANONICAL DRIVER                   ← create_run, fixed stage dispatcher
    ↓
FINALISATION                       ← authority granted here
    ↓
POST-PUBLICATION SUFFIX            ← conditional on finalisation success
    ↓
release lease
```

Plan selection by pipeline:

```
daily pipeline                        → DAILY_CANONICAL
weekly pipeline                       → FULL_FUNDAMENTALS_CANONICAL
monthly / manual fundamentals refresh → FULL_FUNDAMENTALS_CANONICAL
```

The suffix is conditional. A failed or refused driver means suffix consumers
do not execute at all.

---

## Rule 1 — a plan never changes identity after admission

**A precondition may reject a plan. It may not rewrite one.**

`DAILY_CANONICAL` reuses the previous run's yearly output only while the
yearly source fingerprint still matches the current sources. When it has
moved:

```
DAILY requested
→ fingerprint mismatch
→ no create_run
→ no derived-table mutation
→ no universe rebuild
→ previous finalised snapshot remains serving
→ operational alert
```

**No auto-promotion to `FULL_FUNDAMENTALS_CANONICAL`.** Promotion would hide
the exact event the fingerprint was built to detect — that something changed
fundamentals outside the expected full-refresh path. It would also silently
convert a ~30-minute scheduled operation into a ~60-minute one, and make the
persisted `plan_name` less meaningful as evidence, which is the entire reason
it is persisted and immutable.

Remediation may be easy — log and alert that a `FULL_FUNDAMENTALS_CANONICAL`
run is required — but the decision to execute a materially different plan
stays explicit.

If evidence later shows self-healing promotion is operationally preferable,
that is a new orchestration policy adopted deliberately, not something
smuggled into a fingerprint check.

---

## Rule 2 — the dependency boundary is derived, never documented

A hand-maintained list of "steps that can affect a governed value" is true
when written and stops being true silently. This codebase has already paid
for that: the discovery clone's exclusion list was derived from the code when
plans had four stages, and `transform_prices` — which reads
`staging_au.eod_prices` — killed Cycle A 1.4 seconds in once plans had eight.
The cure already exists in
`tests/test_stage_dispatch.py::test_every_table_the_plan_stages_touch_is_proven_by_verify`,
which re-derives the table set from each stage's own SQL on every run.

The boundary uses the same extractor.

**`canonical_dependency_tables`** — machine-produced: every table read or
written by every stage of every canonical plan.

Each wrapper step's touched-table set is derived the same way. **Wherever the
two intersect, an explicit classification is required**, and an unclassified
intersection fails the test. Adding a table to a plan, changing a producer's
dependency, or adding a pipeline step then moves the boundary automatically
instead of leaving this note stale.

### Classifications and their directional rules

| Classification | May do | May not do |
|---|---|---|
| `PRE_INGESTION` | populate source/staging state the plan will subsequently consume | mutate derived/canonical outputs owned by the driver |
| `CANONICAL_DRIVER` | the derived mutation sequence, admission through finalisation | — |
| `POST_PUBLICATION` | read the published universe; write its own downstream artifacts | mutate canonical dependency state |

The boundary is not "ingestion versus computation" by filename. It is one
question: **can this step mutate a table whose state can affect one of the 72
governed values?** Raw downloads into isolated staging, announcement updates
and unrelated snapshots stay outside.

In practice `daily_pipeline` becomes a wrapper that performs its genuinely
upstream work and hands off once. The canonical-affecting compute and universe
steps are **removed** from the wrapper, not executed there and again in the
driver.

This preserves the ordering property that matters most:

> **Plan admission occurs before the first canonical-affecting derived
> mutation.**

A daily fingerprint refusal therefore leaves yesterday's validated snapshot
intact, rather than creating today's unattributed universe.

---

## Rule 3 — one lease serializes shared mutable execution

> **Only one canonical-affecting execution may be in flight at once.**

A PostgreSQL session-scoped advisory lease. It is *not* the fix for the blank
screener and it must not influence plan selection. Canonical producers write
shared mutable tables rather than run-private copies, so genuinely overlapping
executions can interleave their producer writes before either universe is
built. The publication-time fingerprint recheck catches some versions of that
race; serialization is cheaper and clearer than relying on a late detector.

### Scope includes the suffix

Releasing at finalisation leaves a race:

```
run A finalises
lease released
suffix A starts reading screener.universe

run B acquires lease
run B provisional rebuild revokes attribution / rewrites universe
→ suffix A observes B's provisional state, not A's published state
```

> **Hold the lease through every required suffix consumer that reads mutable
> live canonical state.**

Two eventual implementations: the lease owner spans driver + suffix, or suffix
consumers become explicitly bound to the finalised `run_id` and can prove a
stable snapshot independently. **The first implementation chooses the former** —
simpler, and it matches today's consumers.

Consequently: session-scoped is right, but *driver*-scoped is right only if
driver scope includes the suffix. If the wrapper executes the suffix, the
wrapper owns the lock. If the driver owns the lock, it must stay alive and
orchestrate the suffix before releasing.

A crashed owner has its lease released by PostgreSQL session closure. Whatever
state the lifecycle had reached remains governed by the fail-closed rules
below.

### Contention policy

| Caller | Policy |
|---|---|
| Scheduled canonical run | bounded wait, **90 minutes**. Prior finalised output keeps serving while waiting. On timeout, refuse without creating a run or mutating canonical state. |
| Manual canonical run | **fail fast** by default. An operator may request a bounded wait when that is intentional. |

**All plan admission checks, including fingerprint equality, are evaluated
after the lease is acquired — never before the wait.** A fingerprint proved
before a 90-minute wait proves nothing about the state the run will compute
against.

90 minutes is chosen to serialize the ~hour-long FULL path ahead of a daily
run without converting an ordinary overlap into a missed trading-day
publication. Production timings on 23 Sep: FULL 57 minutes. If measured
runtimes later justify a different number, change it as an **operational
parameter**, not as a semantic change.

Fail-fast for manual runs exists so an unnoticed manual monthly or backfill
invocation cannot queue behind — or ahead of — the scheduled job.

---

## Rule 4 — freshness proves that authority is still current

A refusal is correct and it is also invisible: the universe is not rebuilt, so
`screener.universe` keeps serving yesterday's prices, attributed and honest,
while quietly ageing. That is the failure shape of `weekly_pipeline`, which
completed one of its last eight Sundays while `yearly_metrics` read 30 August
for three weeks. Every existing signal missed it. The loud failures were the
survivable ones.

> **A pipeline may fail while yesterday's snapshot remains valid. Once the
> expected publication deadline passes without a new finalised snapshot,
> system health becomes explicitly stale/degraded.**

That condition must be **queryable through health/admin instrumentation and
monitoring, independently of email.** An alert may accompany it. The alert
must not be the evidence.

Surface the latest finalised canonical publication time and the market-data
date it represents — conceptually `canonical_published_at` and `price_as_of`.
Prefer deriving these from **immutable finalisation and run evidence** over
introducing a second mutable timestamp that another writer can forget to
maintain. Where a trustworthy `universe_built_at` already exists, surface it.

See `memory/engineering_rule_output_freshness.md`: scheduled-job health is
proved by the freshness and completeness of its authoritative output, not by
process exit and not by alert delivery.

---

## Failure semantics

| Point of failure | Canonical state | Customer surface |
|---|---|---|
| Prefix ingestion fails | prior finalised run untouched | prior snapshot serves |
| Lease timeout | prior finalised run untouched | prior snapshot serves; freshness can degrade |
| DAILY fingerprint mismatch | no run created; prior state untouched | prior snapshot serves; freshness can degrade |
| Producer fails before provisional universe commit | prior finalised run untouched | prior snapshot serves |
| Universe population proof fails | rebuild rolled back | prior snapshot serves |
| Provisional rebuild commits, canonical tail fails | new values unattributed | governed surface fails closed |
| Canonical finalisation succeeds | new run authoritative | new snapshot serves |
| Required suffix fails | canonical publication remains valid | canonical snapshot serves; suffix-specific health fails |

The last row matters. Once finalisation succeeds, a downstream snapshot or
export consumer failing **must not retroactively invalidate a correct
canonical publication.** It needs its own health evidence.

---

## What implementation must satisfy

1. `canonical_dependency_tables` derived from plan stage SQL by the existing
   extractor; a test that fails on any unclassified intersection.
2. Wrapper steps classified `PRE_INGESTION` / `CANONICAL_DRIVER` /
   `POST_PUBLICATION`, with the directional rules enforced, not described.
3. Canonical-affecting steps **removed** from `daily_pipeline`,
   `weekly_pipeline` and `monthly_pipeline` — not duplicated.
4. Lease acquired before the first canonical-affecting mutation; for
   weekly/monthly that is before the transform publishing fundamentals into
   tables the canonical DAG consumes, not before raw downloads.
5. Lease held through the required suffix.
6. Admission evaluated after lease acquisition.
7. Contention policy per the table; contention reported explicitly, never a
   silent indefinite wait.
8. Freshness queryable from finalisation evidence, independent of email.
9. Failure semantics above covered by tests, each proved capable of failing.

## Not frozen here

- Which specific steps of each pipeline fall into which classification — that
  is derived, and the derivation is the answer.
- The advisory lock key.
- Whether suffix consumers eventually become run-pinned rather than
  lease-protected. The first implementation uses the lease; run-pinning is the
  better long-term answer and is deliberately deferred.
