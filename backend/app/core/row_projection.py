"""
One projection from a stored row to a served row
================================================
Filtering and ranking learned the applicability contract first; projection is
where it was still missing. A screen could correctly refuse to *rank* a bank on
EV/EBITDA and then hand that same bank's EV/EBITDA back in the row it returned,
because the row was assembled by selecting the numeric columns and nothing
else. ``/batch`` had the same shape with no filtering at all in front of it.

So this module is the single place a stored observation becomes a served one:

    raw stored value  ->  decode metric_states  ->  value only when APPLICABLE
                                                ->  otherwise null + state/cause

Four situations produce a null, and they are not the same fact:

    no contract            the applicability sidecar has not been provisioned,
                           so no governed value on this database is
                           interpretable yet
    outside the snapshot   the row carries a compute_run_id that is not in the
                           validated scope, so its sidecar was written under
                           semantics this response is not speaking
    suppressed             the sidecar has an entry: domain, observation,
                           source health or history said not to evaluate
    applicable             no entry, inside the contract — the value stands

The third is the only one the sidecar describes on its own. The first two are
properties of the *row's relationship to the contract*, and collapsing them
into "no data" would tell a user their bank has no leverage ratio when the
truth is that nobody has computed one under semantics we can read.

Non-evaluation is never evidence, so a null here must never be rendered as
zero, as "0%", or as a low rank. The state travels beside it for exactly that
reason.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from compute.engine.metric_registry import normalise
from compute.engine.metric_states import GOVERNED_METRICS
from compute.engine.universe_writer import column_for

#: Forensic keys that live in the stored sidecar and must not cross the API
#: boundary. ``observed`` is the suppressed raw number, kept so an operator can
#: audit why a metric was withheld. Serving it would hand the client back
#: precisely the value the contract suppressed, and a frontend that finds a
#: number in the payload will display it.
PRIVATE_ENTRY_KEYS = frozenset({"observed"})

NO_CONTRACT = "no validated applicability contract on this database"
OUTSIDE_SNAPSHOT = ("row was computed under a run outside the validated "
                    "snapshot, so its states cannot be read")


def _public(entry: Mapping) -> dict:
    """The client-facing part of a stored sidecar entry."""
    return {k: v for k, v in entry.items() if k not in PRIVATE_ENTRY_KEYS}


def _withheld(reason: str) -> dict:
    """A governed metric nulled because of the row's standing, not its value.

    UNAVAILABLE rather than NOT_MEANINGFUL: we are not claiming the metric is
    meaningless for this company, only that we cannot say. SOURCE_MISSING is
    the cause because what is missing is the contract, not the observation.
    """
    return {"state": "unavailable", "cause": "source_missing", "reason": reason}


def governed_columns(model_version: str) -> dict[str, str]:
    """canonical metric -> physical column, for one pinned model version.

    Canonical identity governs semantics; the column spelling is storage. The
    sidecar is keyed canonically and the row is keyed by column, so a
    projection that compared the two directly would silently skip every metric
    whose spellings differ — which is how ev_to_ebitda escaped assessment once
    already.
    """
    return {metric: column_for(metric)
            for metric in GOVERNED_METRICS[model_version]}


def project_row(row: Mapping[str, Any],
                *,
                model_version: str,
                run_ids: Optional[Iterable[int]] = None,
                states_key: str = "metric_states",
                run_key: str = "compute_run_id",
                ) -> tuple[dict[str, Any], dict[str, dict]]:
    """One stored row as (served values, sparse state map).

    ``run_ids`` None means no validated contract was resolved; an empty
    iterable means one was resolved and this row belongs to none of its runs.
    Both withhold, for different stated reasons, and neither is an error — a
    watchlist must still show a price when the contract is unavailable.

    The state map is sparse in the same way the sidecar is: a metric that is
    applicable has no entry. Absence means applicable *inside a contract*, and
    the caller is responsible for having established one.
    """
    values = dict(row)
    states: dict[str, dict] = {}
    columns = governed_columns(model_version)

    scope = None if run_ids is None else {int(r) for r in run_ids}
    in_scope = scope is not None and _run_of(row, run_key) in scope

    if scope is None or not in_scope:
        reason = NO_CONTRACT if scope is None else OUTSIDE_SNAPSHOT
        for metric, column in columns.items():
            if column in values:
                values[column] = None
                states[metric] = _withheld(reason)
        return _clean(values, states_key, run_key), states

    sidecar = row.get(states_key) or {}
    if isinstance(sidecar, str):                      # a driver that returns
        import json                                   # JSONB as text
        sidecar = json.loads(sidecar) or {}

    for raw_metric, entry in sidecar.items():
        metric = normalise(raw_metric)
        column = columns.get(metric)
        if column is None:
            # An entry for something this model version does not govern. It is
            # not ours to interpret, and guessing would be worse than ignoring
            # it, but it must not silently null an ungoverned column either.
            continue
        # Nulling unconditionally is deliberate. A stored row carrying both a
        # value and an entry is the contradictory state violations() exists to
        # catch; on the read path the safe reading of a contradiction is the
        # one that withholds.
        if column in values:
            values[column] = None
        states[metric] = _public(entry)

    return _clean(values, states_key, run_key), states


def _run_of(row: Mapping[str, Any], run_key: str) -> Optional[int]:
    raw = row.get(run_key)
    return int(raw) if raw is not None else None


def _clean(values: dict, states_key: str, run_key: str) -> dict:
    """Drop the machinery columns from the served row.

    The sidecar and the run id are how the projection was decided, not fields
    of the result. Leaving the raw sidecar in the payload would also re-expose
    the forensic ``observed`` values _public() just stripped.
    """
    values.pop(states_key, None)
    values.pop(run_key, None)
    return values
