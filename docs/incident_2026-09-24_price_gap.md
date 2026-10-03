# 24–29 September 2026 — price gap, and an unresolved write

## What was missing

`staging_au.eod_prices` held nothing for 24, 25, 28 and 29 September 2026.
Four consecutive trading days, discovered 3 October while auditing the
freshness anchors added in v11.2.1.

## Why it happened — settled

A deliberate halt, not a malfunction. Recorded at the moment it was done:

    # DISABLED 2026-09-23 p0a bridge — legacy path revokes canonical
    # attribution unattended

(root crontab, preserved in shell history; matches commit `23da496` of 1 Oct,
"restore unattended daily and weekly scheduling".)

The defect is not that the pipeline stopped. Stopping it was correct. The
defect is that a deliberate halt produced **no customer-impact signal** for
six days, and the output-freshness check was green throughout because it did
not watch prices. v11.2.1 added the `daily_prices` anchor for exactly this.

## Provenance — UNRESOLVED, and deliberately left so

**September-gap provenance unresolved. The rows were already present when the
bounded transform ran; no known authority has contemporaneous execution
evidence explaining their appearance. Available Timescale/chunk evidence
cannot distinguish an unknown write from an erroneous opening observation.
Do not attribute the repair to the transform.**

The sequence, as observed:

| time (UTC) | event |
|---|---|
| ~06:20 | `market.daily_prices` reports **0 rows** for all four dates |
| 06:29–06:42 | four bulk files downloaded; `staging_au.eod_prices` loaded, 0 → 9,392 rows |
| 06:57:15 | pre-transform snapshot: all four dates **already full** (2,352/2,348/2,348/2,344); total 6,909,773 |
| 06:57:16–21 | bounded transform runs; writes 9,392 rows; population proof passes |
| 06:57:22 | post-transform: identical counts, total **unchanged** at 6,909,773 |

An unchanged total across 9,392 writes means every write was an
`ON CONFLICT DO UPDATE`. The rows pre-existed the transform.

Excluded by their own records, not by inference: `ops.job_executions` (only
the 15-minute checkers), running processes (none), triggers and rules on both
tables (none), service restart (backend up since 05:24), and today's entries
in `daily_pipeline`, `weekly_pipeline`, `weekly_refresh` and
`output_freshness` logs (all empty).

Two routes to row provenance were attempted and both are closed:

- `pg_xact_commit_timestamp(xmin)` — `track_commit_timestamp` is `off`.
- `xmin` ordering — the hypertable has compression enabled, so it raises
  *"transparent decompression only supports tableoid system column"*.
- chunk compression state — **inconclusive**: all six recent chunks are
  uncompressed, and the gap dates share chunk `_hyper_1_20452` with 30 Sep
  and 1 Oct, days that were never in question. No contrast to measure.

Two hypotheses remain live, and nothing available discriminates them:

1. An unidentified authority wrote the rows between 06:42 and 06:57.
2. The opening observation was wrong, and only *staging* was ever empty —
   making the repair a no-op against a canonical table that was already
   complete.

## What is established about the data

- The four dates now hold 2,352 / 2,348 / 2,348 / 2,344 rows,
  `data_source = eodhd`.
- The transform's own pre-commit proof reported set equality against staging
  — per-code date-set digests, `expected 2367 == written 2367`, zero missing,
  zero extra. This certifies staging and market agree. It says nothing about
  who wrote the rows.
- **No canonical republish is required.** `source_fingerprint` scopes
  `market.daily_prices` per company to
  `max(period_end_date) FROM financials.annual_pnl`. The maximum such bound
  across every company is 2026-05-31; every gap date is later. The scoped
  intersection is empty — confirmed by query, and entailed by the supremum.

## The prospective control this argues for

Stop reconstructing single incidents; make the next one a lookup. A mutation
record for `market.daily_prices` carrying writer identity, invocation/run id,
start and end, affected date range, row counts and digest, and the authority
under which it ran would have answered this in one query.

Row-level audit forever is not required. A per-mutation record is.
