"""
Writing governed state without losing its meaning
=================================================
The last dangerous boundary. Everything upstream computes the right state in
memory; this proves the database can store and return it intact.

Two design rules shape the whole module.

**Canonical identity in, physical names out.** Every function here takes and
returns canonical metric identity. The only place a storage column name
appears is ``STORAGE_COLUMN`` and the SQL it builds. That is deliberate: the
``ev_to_ebitda`` defect was a consumer comparing spellings, and a writer that
accepted physical names would reintroduce it one layer lower, where it would
be even harder to see.

**The SQL is built, not executed, by testable code.** ``build_update`` returns
a statement and its parameters and touches no connection, so the atomicity and
the column mapping can be asserted without a database. Execution is a thin
wrapper around it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional, Sequence

from compute.engine.applicability import Assessment
from compute.engine.metric_registry import normalise
from compute.engine.metric_states import (
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
    SourceHealth,
    UnsupportedModelVersion,
    assert_complete,
    encode,
    governed_for,
    persist_row,
    violations,
)


class WriteRefused(Exception):
    """The writer declined to persist something it could not persist honestly."""


# ── Canonical identity -> physical column ─────────────────────────────────────
# Only the exceptions are listed; everything else stores under its own name.
# This is the single translation point in the system.

STORAGE_COLUMN: dict[str, str] = {
    "ev_ebitda": "ev_to_ebitda",
    "ev_ebit": "ev_to_ebit",
    "dividend_payout_ratio": "payout_ratio",

    # The horizon CAGRs whose storage spelling predates the canonical naming.
    # Their three-year forms are stored as "growth ... cagr" while every other
    # horizon is stored as "cagr ... y", so the canonical name missed them and
    # they read as governed-with-no-column. They are filterable fields: a
    # predicate runs against these columns, which makes an unmapped alias the
    # exact failure ev_to_ebitda already demonstrated -- the filter works and
    # the governance does not.
    "revenue_cagr_3y": "revenue_growth_3y_cagr",
    "eps_cagr_3y": "eps_growth_3y_cagr",
    "net_income_cagr_3y": "earnings_growth_3y_cagr",

    # These two are judgements, not spellings, and are called out as such.
    # The canonical name says what the metric is; the column says which window
    # the stored figure covers, and there is only one candidate for each.
    #
    #   dividend_per_share -> dps_ttm    trailing twelve months, the only DPS
    #                                    the universe carries
    #   free_cash_flow     -> fcf_fy0    the fiscal-year figure; no fcf_ttm
    #                                    column exists
    #
    # If either is meant to denote a different window, the fix is a new column
    # rather than a different alias -- mapping a canonical name onto a column
    # that answers a different question is the defect this table exists to
    # prevent, performed deliberately.
    "dividend_per_share": "dps_ttm",
    "free_cash_flow": "fcf_fy0",
}


#: Governed nowhere, because there is nowhere to put them.
#:
#: A governed metric with no column can never hold a value or a state, so
#: violations() reports missing_governed for it on every row, forever -- which
#: would make Gate B's `violations() == 0` unreachable by construction. None of
#: these is on ScreenerRow and none has a column, so none can be served or
#: filtered: governing them was vacuous.
#:
#: Removing them from V1 is safe *now* and will not be later. No row anywhere
#: is attributed to any model version -- compute_run_id and metric_states are
#: both zero in production as well as in the scratch clone -- so the pin's
#: premise, that rows already written under V1 are validated against it, is
#: currently vacuous. After the first canonical run it stops being vacuous and
#: this becomes impossible.
NOT_PERSISTED: dict[str, str] = {
    "grossed_up_dividend":
        "a franking-inclusive dividend in dollars; the universe carries "
        "grossed_up_yield, which is a different quantity, and no column for "
        "this one",
    "earnings_quality":
        "no column; fcf_conversion is the stored expression of the same idea "
        "and is governed in its place",
    "gross_profit_cagr_3y":
        "computed by yearly_compute.cn() into market.yearly_metrics but never "
        "carried into screener.universe",
    "gross_profit_cagr_5y":
        "computed by yearly_compute.cn() into market.yearly_metrics but never "
        "carried into screener.universe",
}


def column_for(metric: str) -> str:
    """The physical column a canonical metric is stored in."""
    canonical = normalise(metric)
    return STORAGE_COLUMN.get(canonical, canonical)


#: The inverse of STORAGE_COLUMN, built once and checked for collisions.
#:
#: normalise() recovers the canonical name for aliases the metric registry
#: already knows -- ev_to_ebitda -> ev_ebitda -- but it cannot know the ones
#: declared only here. revenue_growth_3y_cagr does not normalise to
#: revenue_cagr_3y by any rule, so without an explicit inverse the round trip
#: breaks in one direction only: the writer puts a value in the right column
#: and the reader cannot tell which metric it belongs to.
_CANONICAL_BY_COLUMN: dict[str, str] = {}
for _metric, _column in STORAGE_COLUMN.items():
    if _column in _CANONICAL_BY_COLUMN:
        raise RuntimeError(
            f"two canonical metrics claim column {_column}: "
            f"{_CANONICAL_BY_COLUMN[_column]} and {_metric}. One column cannot "
            f"answer for two metrics -- a read-back would have to guess.")
    _CANONICAL_BY_COLUMN[_column] = _metric
del _metric, _column


def canonical_for(column: str) -> str:
    """The inverse, for reading a row back."""
    if column in _CANONICAL_BY_COLUMN:
        return _CANONICAL_BY_COLUMN[column]
    return normalise(column)


# ── The run ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ComputeRun:
    """One run's identity, created before any governed state is written.

    The writer must know its run id and model version *before* it persists
    anything, because both travel with every row. A run created afterwards
    could only be attached by matching timestamps, which is the lineage gap
    compute_run_id exists to close.
    """

    run_id: int
    engine: str
    factor_model_version: str
    source_health: Optional[SourceHealth] = None

    def __post_init__(self) -> None:
        governed_for(self.factor_model_version)   # raises on unknown


def create_run(cur, engine: str, source_health: SourceHealth,
               model_version: str = LATEST_MODEL_VERSION) -> ComputeRun:
    """Open a run and return its identity. Call before computing anything."""
    governed_for(model_version)          # refuse an uninterpretable contract

    cur.execute("""
        INSERT INTO screener.compute_runs
            (run_at, engine, factor_model_version, unhealthy_sources, detail)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id
    """, (datetime.now(timezone.utc), engine, model_version,
          list(source_health.unhealthy_sources),
          json.dumps(dict(source_health.detail or {}))))

    run_id = cur.fetchone()[0]
    return ComputeRun(run_id, engine, model_version,
                      SourceHealth(
                          run_at=source_health.run_at,
                          unhealthy_sources=source_health.unhealthy_sources,
                          detail=source_health.detail,
                          factor_model_version=model_version,
                          run_id=run_id))


def finalise_run(cur, run: ComputeRun, rows_written: int) -> None:
    """Record the tally. The only post-insert mutation the trigger permits."""
    cur.execute("UPDATE screener.compute_runs SET rows_written = %s WHERE id = %s",
                (rows_written, run.run_id))


# ── Building the write ────────────────────────────────────────────────────────

def persisted_governed(model_version: str) -> dict[str, str]:
    """canonical metric -> storage column, for everything this version persists.

    The canonical SET list is derived from the governed registry, never
    hand-maintained. A hand-written list of 72 columns is a second declaration
    of what is governed, and the two would diverge on the first metric added to
    a model version -- silently, because a column missing from an UPDATE does
    not fail, it leaves yesterday's value in place.

    Two structural checks, both of which abort rather than degrade:
      * no two canonical metrics may claim one storage column, or a read-back
        has to guess which metric a value belongs to;
      * NOT_PERSISTED members are excluded, because they have no column at all.
    """
    governed = governed_for(model_version)

    mapping: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for metric in sorted(governed):
        if metric in NOT_PERSISTED:
            continue
        column = column_for(metric)
        if column in claimed:
            raise WriteRefused(
                f"{claimed[column]} and {metric} both map to column {column}; "
                f"one column cannot answer for two metrics")
        claimed[column] = metric
        mapping[metric] = column
    return mapping


def verify_storage(cur, model_version: str) -> None:
    """Every column this version promises must exist. Checked once per run.

    A promised column that is absent is an application defect and must stop the
    run. It must never be allowed to present as SOURCE_MISSING: that would
    report our own missing schema as the company having no value, which is the
    precise conflation this contract exists to remove.
    """
    mapping = persisted_governed(model_version)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = 'screener' AND table_name = 'universe';""")
    present = {r[0] for r in cur.fetchall()}

    absent = sorted({c for c in mapping.values() if c not in present})
    if absent:
        raise WriteRefused(
            f"{model_version} governs metrics whose storage columns do not "
            f"exist: {absent}. This is an application defect, not missing "
            f"data, and must not be written as a source failure.")


def build_update(asx_code: str, assessments: Mapping[str, Assessment],
                 run: ComputeRun) -> tuple[str, dict]:
    """One statement carrying numeric columns, the sidecar and the run.

    Returns ``(sql, params)`` and touches nothing, so the atomicity is a
    property of the statement rather than of the caller's discipline. A crash
    between two statements would leave exactly the contradictory state
    ``violations()`` exists to catch, on a row that was correct a moment
    earlier — so there is only ever one.
    """
    governed = governed_for(run.factor_model_version)

    unknown = sorted(m for m in assessments if normalise(m) not in governed)
    if unknown:
        raise WriteRefused(
            f"{asx_code}: {unknown} are not governed by "
            f"{run.factor_model_version}; a metric this contract does not "
            f"cover cannot be written under it")

    # Every governed metric must be assessed. A metric the canonical frame
    # cannot speak for is an application defect: it must abort, not arrive as
    # SOURCE_MISSING, which would blame the feed for our own gap.
    mapping = persisted_governed(run.factor_model_version)
    unassessed = sorted(m for m in mapping if normalise(m) not in
                        {normalise(k) for k in assessments})
    if unassessed:
        raise WriteRefused(
            f"{asx_code}: governed but not assessed by this run: {unassessed}. "
            f"Writing the row would leave those columns holding the previous "
            f"run's values while the sidecar describes this one.")

    values, states = persist_row(assessments)
    assert_complete(values, states)      # both contradiction directions

    params: dict = {"asx_code": asx_code,
                    "metric_states": json.dumps(states, separators=(",", ":"),
                                                sort_keys=True),
                    "compute_run_id": run.run_id}
    sets: list[str] = []

    # Driven by the registry, not by the keys of `values`. Every governed
    # column is assigned on every canonical row, explicit NULL included.
    #
    #     "no value this run" must overwrite the previous run's value with
    #     NULL and the current state. Omitting the column is forbidden.
    #
    # This is the writer-side half of the finding that 2,954 yearly_metrics
    # rows outlived the run that produced them. A column left out of an UPDATE
    # does not fail; it silently keeps yesterday's number, which then sits
    # beside today's sidecar and reads as current.
    for metric, column in sorted(mapping.items()):
        placeholder = f"m_{normalise(metric)}"
        sets.append(f"{column} = %({placeholder})s")
        params[placeholder] = values.get(metric)

    sets.append("metric_states = %(metric_states)s::jsonb")
    sets.append("compute_run_id = %(compute_run_id)s")

    sql = (f"UPDATE screener.universe SET {', '.join(sets)} "
           f"WHERE asx_code = %(asx_code)s")
    return sql, params


def write_row(cur, asx_code: str, assessments: Mapping[str, Assessment],
              run: ComputeRun) -> None:
    sql, params = build_update(asx_code, assessments, run)
    cur.execute(sql, params)


def write_all(cur, by_code: Mapping[str, Mapping[str, Assessment]],
              run: ComputeRun) -> int:
    """Write every company's governed state under one run."""
    written = 0
    for asx_code, assessments in by_code.items():
        write_row(cur, asx_code, assessments, run)
        written += 1
    return written


def commit_canonical(conn, run: ComputeRun,
                     by_code: Mapping[str, Mapping[str, Assessment]],
                     *, required_stages: Sequence[str],
                     readback_sample: int = 25,
                     snapshot_id: Optional[str] = None,
                     details: Optional[Mapping[str, object]] = None) -> int:
    """The canonical commit boundary. The transaction IS the publication unit.

    Everything the contract depends on happens inside one transaction, so the
    universe is never half-canonical:

        write every governed value, the sidecar and the attribution
        validate what was written, against this run
        insert the finalisation record
        COMMIT

    If validation fails the whole thing rolls back and no finalisation exists,
    so the resolver finds no eligible run rather than a partially-published
    one. The compute_runs row and the stage evidence are deliberately OUTSIDE
    this transaction and already committed: a failed attempt must stay
    visible as forensics. Losing the record of what was tried is how a
    recurring failure becomes invisible.

    Prerequisite stages are checked first. Attribution asserts that this run
    wrote the row after its required producer populations were proven
    complete, so writing it before that proof exists would make the claim
    false -- and a false attribution is worse than none, because everything
    downstream reads it as evidence of coherence.
    """
    from compute.engine.run_stages import finalise, require_stages

    cur = conn.cursor()
    try:
        # Before any row is touched: the prerequisites, and the schema this
        # version promises. Both abort rather than degrade.
        require_stages(cur, run.run_id, required_stages)
        verify_storage(cur, run.factor_model_version)

        rows_written = write_all(cur, by_code, run)

        # Validate what is actually in the table under this run, not what we
        # believe we sent. read_back is scoped to the run id, so a row written
        # by anything else cannot satisfy the check by accident.
        bad = 0
        sample = sorted(by_code)[:readback_sample]
        for asx_code in sample:
            restored = read_back(cur, asx_code, run)
            if restored is None:
                raise WriteRefused(
                    f"{asx_code} is not attributable to run {run.run_id} "
                    f"immediately after writing it")
            values = {m: a.value for m, a in restored.items()}
            states = encode(restored)
            bad += len(violations(values, states, run.factor_model_version))

        finalise_run(cur, run, rows_written)

        # Refuses unless the stages passed and nothing violates. The insert is
        # the publication boundary, and it is inside this transaction so it
        # cannot outlive a rollback of the rows it vouches for.
        finalise(cur, run.run_id,
                 rows_written=rows_written,
                 persistence_violations=bad,
                 required_stages=required_stages,
                 snapshot_id=snapshot_id,
                 details={**dict(details or {}),
                          "readback_sampled": len(sample)})

        conn.commit()
        return rows_written
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ── Reading it back ───────────────────────────────────────────────────────────

def read_back(cur, asx_code: str, run: ComputeRun,
              metrics: Optional[Sequence[str]] = None) -> dict:
    """Re-read one row and rebuild its assessments, from that exact run.

    Scoped to the run on purpose. Reading the current row and hoping it came
    from the write we just made is the timestamp-matching fallacy in another
    costume; a row rewritten by a later run must not be returned as
    verification of this one.
    """
    wanted = [normalise(m) for m in
              (metrics or sorted(governed_for(run.factor_model_version)))]
    columns = [column_for(m) for m in wanted]

    cur.execute(
        f"SELECT {', '.join(columns)}, metric_states, compute_run_id "
        f"FROM screener.universe WHERE asx_code = %s",
        (asx_code,))
    row = cur.fetchone()
    if row is None:
        raise WriteRefused(f"{asx_code}: row disappeared between write and read")

    *values, states, run_id = row
    if run_id != run.run_id:
        raise WriteRefused(
            f"{asx_code}: row now belongs to run {run_id}, not {run.run_id}; "
            f"a later run has overwritten it and this is not verification")

    from compute.engine.metric_states import decode_all, load_states
    return decode_all(dict(zip(wanted, values)), load_states(states))
