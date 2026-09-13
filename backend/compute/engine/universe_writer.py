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

    values, states = persist_row(assessments)
    assert_complete(values, states)      # both contradiction directions

    params: dict = {"asx_code": asx_code,
                    "metric_states": json.dumps(states, separators=(",", ":"),
                                                sort_keys=True),
                    "compute_run_id": run.run_id}
    sets: list[str] = []

    for metric, value in sorted(values.items()):
        column = column_for(metric)
        # Parameter names use the canonical identity so a mapping mistake in
        # STORAGE_COLUMN shows up as a mismatch rather than a silent overwrite
        # of the wrong column.
        placeholder = f"m_{normalise(metric)}"
        sets.append(f"{column} = %({placeholder})s")
        params[placeholder] = value

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
