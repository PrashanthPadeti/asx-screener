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


#: Every full producer whose output the canonical writer re-emits. All must
#: have proven their own population before a run may be attributed or served.
#:
#: No one of them is enough on its own. yearly_compute can prove perfect
#: coverage while the build silently misses rows, and the canonical writer
#: would then faithfully publish stale provisional values -- the same defect
#: wearing a completeness certificate.
#:
#: daily_compute is here because build_screener_universe consumes
#: market.computed_metrics. A finalised run cannot truthfully claim its
#: required computed inputs were current while that producer sits outside the
#: lifecycle with no equivalent proof: the run would certify rows assembled
#: from stale computed inputs.
#:
#: Ordering follows the real dependencies -- yearly_compute and daily_compute
#: both feed universe_build, so both must succeed before it runs -- but this
#: tuple is a SET of requirements, not a sequence. The driver owns the order.
#:
#: Declared here rather than in composite_score so the resolver can require the
#: same set without importing a module that needs psycopg2. The writer and the
#: reader must agree on what "published" means, and two copies of this tuple
#: would eventually disagree.
REQUIRED_STAGES: tuple[str, ...] = (
    "yearly_compute", "daily_compute", "universe_build",
)


class StageIncomplete(RuntimeError):
    """A stage did not cover its source population, so nothing may publish."""


#: Separates the parts of a composite key. A unit separator, because it cannot
#: occur in an ASX code, an ISO date or a period label, so rendering is
#: unambiguous and two different keys can never collide into one string.
KEY_SEP = "\x1f"


def render_key(key) -> str:
    """One canonical string for a key at any grain.

    Producers do not share a grain and must not be made to pretend they do.
    technical_compute's population is (code, date); halfyearly_compute's is
    (code, period_end_date); daily_compute's is a bare code. Collapsing them
    all to codes would make three different questions look like one, and the
    two that are really about dates would be answered by a proof that never
    examined a date -- passing while the row for today was missing.

    Dates are rendered with isoformat(), so a date and a datetime for the same
    instant never hash as different members.
    """
    if isinstance(key, (tuple, list)):
        return KEY_SEP.join(render_key(part) for part in key)
    if hasattr(key, "isoformat"):
        return key.isoformat()
    return str(key)


def set_hash(keys: Iterable) -> str:
    """A deterministic fingerprint of a key set.

    Sorted and newline-joined before hashing, so two runs that covered the same
    population agree regardless of the order they processed it in. Equality of
    hashes is the positive form of the invariant -- not "missing_count is
    zero", which is the same claim stated in a way that cannot be re-checked
    later.

    Sorting happens on the rendered strings, so a set of tuples orders the same
    way on every run and on every platform.
    """
    joined = "\n".join(sorted(render_key(k) for k in keys))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StageResult:
    """What a producer proved about its own coverage."""

    stage_name: str
    expected: frozenset
    written: frozenset
    details: Mapping[str, object] = None
    #: The semantic identity the two sets are populations OF, named on the
    #: record. Without it a reader of compute_run_stages cannot tell whether
    #: "2,103 expected" means 2,103 companies or 2,103 company-days, and two
    #: stages whose counts look comparable may not be measuring the same thing
    #: at all. Recorded, not inferred, because a grain that has to be guessed
    #: from a count is not evidence.
    grain: str = "asx_code"

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
                    f"{len(self.expected):,} expected, by {self.grain}")
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing):,} expected but not written")
        if self.extra:
            parts.append(f"{len(self.extra):,} written but not expected")
        return f"{self.stage_name}: {'; '.join(parts)} (by {self.grain})"

    def payload(self) -> dict:
        """The details column: bounded samples, plus anything the stage added.

        The counts alone cannot distinguish "wrote the right number of the
        wrong members" from a clean run -- two sets of equal size can be
        disjoint -- so the samples and the set hashes are what make a passing
        record re-checkable.
        """
        out: dict[str, object] = dict(self.details or {})
        out["grain"] = self.grain
        for name, keys in (("missing", self.missing), ("extra", self.extra)):
            if keys:
                out[f"{name}_sample"] = sorted(
                    render_key(k) for k in keys)[:SAMPLE_LIMIT]
                out[f"{name}_truncated"] = len(keys) > SAMPLE_LIMIT
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


def report_population(cur, run_id: Optional[int], result: Optional[StageResult],
                      log, *, scoped_reason: str = "") -> bool:
    """Print the proof, record it when there is a run to record it against,
    and answer whether the producer covered its domain.

    The caller turns a False into a non-zero exit. That separation is
    deliberate: the proof is printed on every run, including ones with no run
    id, so a developer running the producer by hand sees the same evidence the
    lifecycle would; but the failure has to be executable, because a log line
    is something a person may read and an exit code is something the
    orchestrator cannot ignore.

    A scoped run records nothing. Its expected population is not the source
    domain, and a stage row claiming otherwise would be a false claim -- worse
    than no claim, because the resolver would act on it.
    """
    if scoped_reason:
        log.info("population proof skipped: %s", scoped_reason)
        return True

    if result is None:
        # Only a scoped run may arrive without a result. Reaching here with
        # nothing to report would otherwise return success for a producer that
        # proved nothing -- the exact shape of an inert check.
        raise ValueError(
            "report_population called with no result and no scoped_reason: a "
            "producer cannot pass by having nothing to say")

    log.info("─" * 60)
    log.info("population proof — %s (grain: %s)", result.stage_name, result.grain)
    log.info("  expected  %8d   %s", len(result.expected), set_hash(result.expected))
    log.info("  written   %8d   %s", len(result.written), set_hash(result.written))
    log.info("  missing   %8d   (expected, not written)", len(result.missing))
    log.info("  extra     %8d   (written, not expected)", len(result.extra))

    if result.ok:
        # Stated as set equality, not as two zero counts. Equal counts over
        # different members is a failure, and a proof that reports only counts
        # cannot tell the two apart.
        log.info("  RESULT    sets are equal")
    else:
        log.error("  RESULT    POPULATION NOT COVERED")
        for name, keys in (("missing", result.missing), ("extra", result.extra)):
            if keys:
                sample = sorted(render_key(k) for k in keys)[:SAMPLE_LIMIT]
                log.error("  %s sample: %s%s", name, ", ".join(sample),
                          " …" if len(keys) > SAMPLE_LIMIT else "")
    log.info("─" * 60)

    if run_id is not None:
        record_stage(cur, run_id, result)
        log.info("stage %s: %s — %s",
                 result.stage_name, result.status, result.summary())
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

    # Already published. The primary key would refuse this anyway, but as a
    # raw UniqueViolation from inside psycopg2 -- which reads as a driver
    # fault rather than as the design working.
    #
    # A run is finalised exactly once. Re-running a producer against a
    # published run to re-measure something is editing history under an
    # identity other people may already have read, and the append-only rule
    # exists precisely to make that impossible. A retry is a new run.
    if is_published(cur, run_id):
        raise StageIncomplete(
            f"run {run_id} is already finalised and cannot be published "
            f"again. Its rows, stage evidence and finalisation record stand "
            f"as written. To measure a change, start a new run -- re-running "
            f"a producer under a published run id would rewrite history "
            f"beneath an identity that has already been read.")

    if persistence_violations:
        raise StageIncomplete(
            f"run {run_id} produced {persistence_violations:,} persistence "
            f"contract violations in its read-back sample. Publishing it would "
            f"serve values the contract itself says are unexplained. The "
            f"offending metrics are named in the run log immediately above "
            f"this line -- they are not recoverable afterwards, because the "
            f"rows roll back with the refusal.")

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
