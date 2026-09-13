"""
Did the run cover what it is responsible for?
=============================================
One invariant, stated once, usable by any producer:

    A full producer must define an expected population independently of its
    own loop, and prove that the population it successfully wrote is equal to
    it, before its stage can be marked complete.

The loop's counters are not evidence. They describe only what the loop was
admitted to see. The first discovery rebuild made that concrete: yearly_compute
reported ``1626 stocks | 0 skipped | 0 errors`` -- clean by every signal it
emitted -- while leaving 2,954 rows with a live source untouched, because its
selection excluded 224 delisted codes that build_screener_universe nonetheless
reads. No counter could have caught it. The codes were filtered out before
anything started counting.

Two failure classes, named apart because they are not equally serious:

    missing source   the source row is gone. Legitimate unavailability may
                     result, and the metric says so.
    missed source    the source row is present and the run did not rewrite it.
                     A prior value stays readable and looks current. This is a
                     run-integrity failure, and it is what this module exists
                     to make impossible to ignore.

Evidence is append-only and terminal. A stage computes everything and then
writes exactly one row: success or failed. A retry is a new run, not an edit,
so the evidence never has to be read as "what it said at the time".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

#: How many keys of each kind to keep on the record. The hashes carry the
#: proof; the sample carries the diagnosis, and a successful run should not
#: persist thousands of codes to say nothing happened.
SAMPLE_LIMIT = 25


#: Every full producer whose output the canonical writer re-emits. Both must
#: have proven their own population before a run may be attributed or served.
#:
#: yearly_compute alone is not enough: it can prove perfect coverage while the
#: build silently misses rows, and the canonical writer would then faithfully
#: publish stale provisional values -- the same defect wearing a completeness
#: certificate.
#:
#: Declared here rather than in composite_score so the resolver can require the
#: same set without importing a module that needs psycopg2. The writer and the
#: reader must agree on what "published" means, and two copies of this tuple
#: would eventually disagree.
REQUIRED_STAGES: tuple[str, ...] = ("yearly_compute", "universe_build")


class StageIncomplete(RuntimeError):
    """A stage did not cover its source population, so nothing may publish."""


def set_hash(keys: Iterable[str]) -> str:
    """A deterministic fingerprint of a key set.

    Sorted and newline-joined before hashing, so two runs that covered the same
    population agree regardless of the order they processed it in. Equality of
    hashes is the positive form of the invariant -- not "missing_count is
    zero", which is the same claim stated in a way that cannot be re-checked
    later.
    """
    joined = "\n".join(sorted(keys))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StageResult:
    """What a producer proved about its own coverage."""

    stage_name: str
    expected: frozenset[str]
    written: frozenset[str]
    details: Mapping[str, object] = None

    @property
    def missing(self) -> frozenset[str]:
        """Expected and not written. The missed-source class."""
        return self.expected - self.written

    @property
    def extra(self) -> frozenset[str]:
        """Written and not expected. Also suspicious: the producer wrote
        something its own definition of scope does not account for, which
        means one of the two is wrong and we do not know which."""
        return self.written - self.expected

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra

    @property
    def status(self) -> str:
        return "success" if self.ok else "failed"

    def summary(self) -> str:
        if self.ok:
            return (f"{self.stage_name}: covered {len(self.expected):,} of "
                    f"{len(self.expected):,} expected")
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing):,} expected but not written")
        if self.extra:
            parts.append(f"{len(self.extra):,} written but not expected")
        return f"{self.stage_name}: {'; '.join(parts)}"

    def payload(self) -> dict:
        """The details column: bounded samples, plus anything the stage added."""
        out: dict[str, object] = dict(self.details or {})
        if self.missing:
            out["missing_sample"] = sorted(self.missing)[:SAMPLE_LIMIT]
            out["missing_truncated"] = len(self.missing) > SAMPLE_LIMIT
        if self.extra:
            out["extra_sample"] = sorted(self.extra)[:SAMPLE_LIMIT]
            out["extra_truncated"] = len(self.extra) > SAMPLE_LIMIT
        return out


def record_stage(cur, run_id: int, result: StageResult) -> bool:
    """Write the one terminal row for this stage. Returns whether it passed.

    Writes on failure as well as on success, deliberately. A stage that failed
    silently leaves no trace of having been attempted, and the absence of a
    row would then be indistinguishable from a run that never reached the
    stage at all -- two situations needing different responses.
    """
    cur.execute("""
        INSERT INTO screener.compute_run_stages (
            run_id, stage_name, status,
            expected_count, written_count, missing_count, extra_count,
            expected_set_hash, written_set_hash, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb);""",
        (run_id, result.stage_name, result.status,
         len(result.expected), len(result.written),
         len(result.missing), len(result.extra),
         set_hash(result.expected), set_hash(result.written),
         json.dumps(result.payload(), sort_keys=True, default=str)))
    return result.ok


def stages_passed(cur, run_id: int, required: Iterable[str]) -> list[str]:
    """Which required stages do NOT have a success row. Empty means proceed.

    Asks for the positive record rather than the absence of a failure: a stage
    that never ran has no failed row either, and treating that as permission
    would make the whole mechanism optional by omission.
    """
    required = sorted(set(required))
    if not required:
        return []
    cur.execute("""
        SELECT stage_name FROM screener.compute_run_stages
         WHERE run_id = %s AND stage_name = ANY(%s) AND status = 'success';""",
        (run_id, required))
    passed = {r[0] for r in cur.fetchall()}
    return [s for s in required if s not in passed]


def require_stages(cur, run_id: int, required: Iterable[str]) -> None:
    """Raise unless every required stage recorded success under this run."""
    outstanding = stages_passed(cur, run_id, required)
    if outstanding:
        raise StageIncomplete(
            f"run {run_id} has no success record for: {', '.join(outstanding)}. "
            f"A canonical row may not be attributed to a run whose input "
            f"populations were not proven complete -- the attribution would "
            f"assert a coherence nobody established.")


def finalise(cur, run_id: int, *, rows_written: int,
             persistence_violations: int, required_stages: Iterable[str],
             snapshot_id: Optional[str] = None,
             details: Optional[Mapping[str, object]] = None) -> None:
    """The publication boundary. Refuses on an incomplete or dirty run.

    Nothing else makes a run eligible to be served. The resolver looks for this
    row, so a run that cannot reach here simply never becomes servable -- which
    is the property we wanted: there is no log line for anyone to heed or
    ignore.
    """
    require_stages(cur, run_id, required_stages)

    if persistence_violations:
        raise StageIncomplete(
            f"run {run_id} wrote {persistence_violations:,} rows that violate "
            f"the persistence contract. Publishing it would serve values the "
            f"contract itself says are unexplained.")

    cur.execute("""
        INSERT INTO screener.compute_run_finalizations (
            run_id, rows_written, persistence_violations, snapshot_id, details)
        VALUES (%s, %s, %s, %s, %s::jsonb);""",
        (run_id, rows_written, persistence_violations, snapshot_id,
         json.dumps(dict(details or {}), sort_keys=True, default=str)))


def is_published(cur, run_id: int) -> bool:
    """Whether a run has a finalisation record. The resolver's question."""
    cur.execute("""
        SELECT 1 FROM screener.compute_run_finalizations WHERE run_id = %s;""",
        (run_id,))
    return cur.fetchone() is not None
