"""
Carrying applicability across the persistence boundary
=====================================================
Serialisation preserves the contract; persistence is where it was going to be
lost. ``daily_compute`` reduces an assessment to a nullable numeric column in
``screener.universe``, and a route reading that column back gets ``NULL`` with
no way to know whether it means:

    DOMAIN                out of domain for this economic model
    OBSERVATION           the ratio has no meaning for these values
    SOURCE_MISSING        this company has no value
    SOURCE_UNHEALTHY      the feed itself is broken
    INSUFFICIENT_HISTORY  not enough periods

Those five have different downstream behaviour — one of them forbids composite
reweighting and blocks a canonical refresh — so collapsing them into ``NULL``
undoes the work upstream of it. The invariant has to survive the whole chain:

    source -> assessment -> compute -> persistence -> API -> UI / AI / anomaly

The mechanism is a sparse sidecar rather than a status column per metric.
``screener.universe`` already carries 225 columns; doubling that to shadow each
one is not a design, it is a tax. Instead:

  * the numeric column keeps holding the number, and holds NULL for every
    state other than APPLICABLE — unchanged, so every existing reader keeps
    working and none of them can read a suppressed number by accident;
  * ``metric_states`` (JSONB) records an entry for **every metric whose state
    is not APPLICABLE**, and nothing else, so it stays small;
  * run-level source health is recorded once per compute run, not per company,
    because a broken feed is an exchange-wide fact and repeating it 2,117 times
    would invite it to disagree with itself.

"Not APPLICABLE" rather than "not applicable" is deliberate and is not
pedantry: ``UNAVAILABLE`` with ``SOURCE_UNHEALTHY`` describes a metric that
*is* economically applicable and merely uncomputable right now. Calling that
"not applicable" is the exact conflation this module exists to prevent.

Two rules make the sparse encoding safe, and both directions matter:

    **A NULL numeric column must never be the only signal**, and
    **a populated numeric column must never sit beside a state entry.**

Absent from ``metric_states`` means APPLICABLE. So a NULL with no entry is a
contract violation rather than a default — and a stale entry left beside a
newly populated value is just as dangerous, because a contract-aware reader
suppresses a number that is now perfectly good. ``violations()`` reports both.

The observed input, where one existed, lives inside the sidecar entry rather
than in the numeric column. That keeps forensics available to a contract-aware
reader without a legacy ``SELECT`` picking up a suppressed value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional

from compute.engine.applicability import (
    ROLLING_AVERAGE_BASES,
    ROLLING_AVERAGE_WINDOWS,
    Applicability,
    Assessment,
    Cause,
    Domain,
)


# ── Run-level source health ───────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceHealth:
    """One compute run's view of its inputs, recorded once.

    Per run rather than per company: the dividend feed being 38 days behind is
    a fact about the exchange, and writing it onto every row would let it
    disagree with itself halfway through a run.
    """

    run_at: datetime
    unhealthy_sources: tuple[str, ...] = ()      # e.g. ("dividends",)
    detail: Mapping[str, str] = None             # source -> human reason
    factor_model_version: Optional[str] = None
    #: screener.compute_runs.id. Written onto every row the run produces, so
    #: the chain is a join rather than a timestamp guess:
    #:     value + state -> compute_run_id -> model version + source health
    #: Without it a row can say SOURCE_UNHEALTHY while the run that decided
    #: that has been overwritten by two later runs, and nothing recovers which
    #: feed observation produced the decision.
    run_id: Optional[int] = None

    def to_payload(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_at": self.run_at.isoformat(),
            "unhealthy_sources": list(self.unhealthy_sources),
            "detail": dict(self.detail or {}),
            "factor_model_version": self.factor_model_version,
        }

    @classmethod
    def from_payload(cls, payload: Optional[Mapping]) -> Optional["SourceHealth"]:
        if not payload:
            return None
        raw = payload.get("run_at")
        return cls(
            run_at=datetime.fromisoformat(raw) if raw else datetime.min,
            unhealthy_sources=tuple(payload.get("unhealthy_sources") or ()),
            detail=payload.get("detail") or {},
            factor_model_version=payload.get("factor_model_version"),
            run_id=payload.get("run_id"),
        )

    @property
    def healthy(self) -> bool:
        return not self.unhealthy_sources


# ── Encoding ──────────────────────────────────────────────────────────────────

def encode(assessments: Mapping[str, Assessment] | Iterable[Assessment]) -> dict:
    """The sparse sidecar: an entry for every metric that is not applicable.

    Applicable metrics are omitted deliberately. The absence *is* the signal,
    which is what keeps the payload proportional to the problem rather than to
    the column count.
    """
    items = (assessments.values() if isinstance(assessments, Mapping)
             else assessments)
    out: dict[str, dict] = {}
    for a in items:
        if a.ok:
            continue
        entry: dict[str, Any] = {"state": a.state.value}
        if a.cause is not None:
            entry["cause"] = a.cause.value
        if a.reason:
            entry["reason"] = a.reason
        if a.observed is not None:
            # Forensics live here, not in the numeric column, so a legacy
            # SELECT cannot pick up a suppressed value.
            entry["observed"] = a.observed
        out[a.metric] = entry
    return out


def persist_row(assessments: Mapping[str, Assessment] | Iterable[Assessment]
                ) -> tuple[dict[str, Optional[float]], dict]:
    """The numeric columns and the sidecar, produced together.

    Transitions are the risk this closes. Going suppressed -> applicable must
    populate the number *and* drop the entry; going applicable -> suppressed
    must null the number *and* add one. Two statements can half-apply; one
    function returning both cannot, because the pair is derived from a single
    set of assessments rather than assembled by a caller who might update one
    and forget the other.

    Application-level coherence is necessary and **not sufficient**: the write
    itself must not tear. The numeric columns, ``metric_states`` and
    ``compute_run_id`` go in one statement, so no reader can observe a row
    whose number has been updated and whose state has not:

        UPDATE screener.universe SET
            grossed_up_yield = %(grossed_up_yield)s,
            ...,
            metric_states  = %(metric_states)s::jsonb,
            compute_run_id = %(compute_run_id)s
        WHERE asx_code = %(asx_code)s

    Never as separate statements, and never with the sidecar updated in a
    second pass — a crash between them leaves exactly the contradictory state
    ``violations()`` exists to catch, on a row that was correct a moment ago.
    """
    items = list(assessments.values() if isinstance(assessments, Mapping)
                 else assessments)
    values = {a.metric: (a.value if a.ok else None) for a in items}
    return values, encode(items)


def encode_json(assessments) -> str:
    """The same payload as a JSON string, for a psycopg2 ``::jsonb`` parameter."""
    return json.dumps(encode(assessments), separators=(",", ":"), sort_keys=True)


# ── Decoding ──────────────────────────────────────────────────────────────────

def decode(metric: str, value: Optional[float],
           states: Optional[Mapping[str, Mapping]] = None,
           domain: Optional[Domain] = None) -> Assessment:
    """Rebuild one assessment from a persisted value plus its sidecar entry.

    The reconstructed assessment carries ``value=None`` for anything not
    applicable, exactly as the original did — the invariant is re-established
    on the read side rather than trusted to have survived.
    """
    entry = (states or {}).get(metric)

    if entry is None:
        if value is None:
            # Absent from the sidecar means applicable, so a NULL here is a
            # row written by something that does not know about the contract.
            # Fail closed and say so, rather than inventing a cause.
            return Assessment(metric, Applicability.UNAVAILABLE, None,
                              "no state recorded for a null value "
                              "(sidecar contract violation)", domain,
                              cause=Cause.SOURCE_MISSING)
        return Assessment(metric, Applicability.APPLICABLE, value, "", domain,
                          observed=value)

    state = Applicability(entry["state"])
    cause = Cause(entry["cause"]) if entry.get("cause") else None
    return Assessment(metric, state, None, entry.get("reason", ""), domain,
                      observed=value, cause=cause)


def decode_all(values: Mapping[str, Optional[float]],
               states: Optional[Mapping[str, Mapping]] = None,
               domain: Optional[Domain] = None) -> dict[str, Assessment]:
    """Rebuild a whole row's assessments from the numeric columns + sidecar."""
    return {m: decode(m, v, states, domain) for m, v in values.items()}


def load_states(raw: Any) -> dict:
    """Accept whatever the driver hands back for a JSONB column."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw) or {}
    return dict(raw)


# ── The rule that makes sparseness safe ───────────────────────────────────────

#: The metrics the contract governs, pinned per factor-model version.
#:
#: Pinned literally, and deliberately not derived from whatever
#: ``metric_registry.SENSITIVE`` happens to hold today. If the governed set
#: were computed live, adding a metric next quarter would retroactively make
#: every existing row incomplete — a row written correctly under V1 would
#: start failing validation because it lacks a state for something that did
#: not exist when it was written. New metrics join a *new* version.
#:
#: The pin protects *persisted* rows, so V1 may still be amended until the
#: first production write under it. After that it freezes and additions go to
#: V2. Nothing has been written under V1 yet — the recompute has not run.
GOVERNED_METRICS: dict[str, frozenset[str]] = {
    "FACTOR_MODEL_V1": frozenset({
        # domain-sensitive
        "altman_z_score", "debt_to_equity", "current_ratio", "quick_ratio",
        "interest_coverage", "working_capital", "gross_margin",
        "operating_margin", "inventory_turnover", "asset_turnover",
        "net_margin",
        "ev_ebitda", "ev_ebit", "net_debt_to_ebitda", "free_cash_flow",
        "fcf_conversion", "earnings_quality", "price_to_sales",
        "piotroski_f_score",
        # Margin *changes* inherit the domain of the margin they measure, and
        # the multibagger score ranks them cross-sectionally.
        "gross_margin_expansion", "operating_margin_expansion",
        "gross_margin_expanding", "operating_margin_expanding",
        # observation-sensitive
        "roe", "book_value_per_share", "price_to_book",
        "pe_ratio", "peg_ratio", "roce", "roic",
        # dividend methodology
        "dividend_yield", "grossed_up_yield", "franking_pct",
        "dividend_per_share", "grossed_up_dividend", "dividend_payout_ratio",
        # factor layer
        "value_score", "quality_score", "growth_score", "momentum_score",
        "income_score", "composite_score",
    }),
}

#: Every horizon-labelled CAGR produced by yearly_compute.cn(). Governed from
#: V2 onward, because their absence now carries a meaning that must survive the
#: persistence boundary: no observation exists at the exact horizon the field
#: name claims.
HORIZON_CAGRS: frozenset[str] = frozenset({
    "revenue_cagr_3y", "revenue_cagr_5y", "revenue_cagr_7y",
    "revenue_cagr_10y",
    "net_income_cagr_3y", "net_income_cagr_5y",
    "eps_cagr_3y", "eps_cagr_5y",
    "ebitda_cagr_3y", "ebitda_cagr_5y",
    "fcf_cagr_3y", "fcf_cagr_5y",
    "gross_profit_cagr_3y", "gross_profit_cagr_5y",
    "bvps_cagr_3y", "bvps_cagr_5y",
})

#: The fiscal-year rolling averages ScreenerRow advertises. Governed from V2
#: because the strict window rule makes them NULL more often, and a newly
#: introduced NULL on a promised field must not become an unexplained blank —
#: which is the condition Gate A exists to catch.
#:
#: The boundary is semantic, not mechanical. These eighteen are exposed on the
#: response model; avg_assets, avg_equity and avg_franking_pct are internal
#: intermediates with no governed surface and stay ungoverned, because
#: enlarging the registry is not the same as governing something.
#: avg_volume_20d is a twenty-day trading average, not a fiscal-year one, and
#: does not belong to this family at all.
#: Built from the same declaration the domain inheritance and
#: PERIOD_REQUIREMENT use, so the governed set, the domain rules and the
#: window requirements cannot disagree about which averages exist. A metric
#: governed here but absent from PERIOD_REQUIREMENT would withhold with
#: SOURCE_MISSING universally and look entirely normal doing it.
ROLLING_AVERAGES: frozenset[str] = frozenset(
    f"avg_{metric}_{n}y"
    for n in ROLLING_AVERAGE_WINDOWS
    for metric in ROLLING_AVERAGE_BASES
)

# FACTOR_MODEL_V2 = V1 plus period-exact CAGR semantics.
#
# V1 is left untouched and unpublished. It could still have been amended — no
# production row has ever referenced it — but that exception stops being used
# here. V1 was treated as complete, a freeze discipline was built around
# versioned semantics, and this defect was found after that point. Amending it
# now would mean the first production contract had already been rewritten once
# to hide something, which is precisely what a pinned version exists to prevent.
#
# What changed: an n-year CAGR requires an observation at fiscal year Y - n.
# Under V1 the window was positional — n rows back — so a company with a gap
# in its reported years had its growth annualised over too few years and came
# out inflated, plausibly and invisibly. The fix is not to divide by the real
# span: `revenue_cagr_5y` claims five years, and a correct nine-year rate is
# not that claim. The horizon is either available or it is not.
#
# These metrics are therefore governed from V2, so a missing horizon persists
# as UNAVAILABLE / INSUFFICIENT_HISTORY rather than as an unexplained null —
# and cannot be ranked, filtered, ordered or averaged into a peer statistic
# while unavailable.
GOVERNED_METRICS["FACTOR_MODEL_V2"] = (
    GOVERNED_METRICS["FACTOR_MODEL_V1"] | HORIZON_CAGRS | ROLLING_AVERAGES
)

LATEST_MODEL_VERSION = "FACTOR_MODEL_V1"

#: Sentinel for "this caller is not validating a version at all" — the
#: in-memory, pre-write check, where no version has been assigned yet.
#: Distinct from ``None``, which means the *row* claims no version.
UNSPECIFIED = object()


class UnsupportedModelVersion(Exception):
    """The row was written under a contract this build cannot interpret."""


class RunMismatch(Exception):
    """Two artefacts from different compute runs were about to be shown together."""


def assert_same_run(**run_ids) -> None:
    """Every artefact displayed together must come from one run.

    A company factor score and the sector benchmark shown beside it are only
    comparable if they were assessed under the same applicability rules,
    against the same source health, under the same model version. An overnight
    partial failure can leave each of them individually valid and jointly
    meaningless — the score computed while the dividend feed was healthy, the
    benchmark rebuilt after it broke, and nothing on the page saying so.

    Fails closed. There is no "use the newest benchmark" branch, because the
    newest one is exactly what makes the pair inconsistent.
    """
    present = {name: rid for name, rid in run_ids.items() if rid is not None}
    if len(set(present.values())) > 1:
        detail = ", ".join(f"{n}={r}" for n, r in sorted(present.items()))
        raise RunMismatch(
            f"artefacts from different compute runs cannot be shown together: "
            f"{detail}")

    missing = [name for name, rid in run_ids.items() if rid is None]
    if missing and present:
        raise RunMismatch(
            f"{', '.join(sorted(missing))} has no run attribution, so it "
            f"cannot be shown beside {', '.join(sorted(present))}")


def supported_version(version: Optional[str]) -> bool:
    return version in GOVERNED_METRICS


def governed_for(version: Optional[str]) -> frozenset[str]:
    """The governed metric set for a row's model version.

    Raises on anything this build does not know, and that is the point.

    An earlier *known* version legitimately governs a smaller set — a row
    written under V1 promised V1's metrics and nothing more. An *unknown*
    version is a different situation entirely: the build cannot say what the
    row promised, so it cannot say the row kept its promise.

        Unknown model version means unknown contract, not no contract.

    Returning an empty set here would have made the second case look like the
    first, and a row from a future model would validate clean precisely
    because nothing could check it.
    """
    if version is None:
        raise UnsupportedModelVersion(
            "row claims no factor-model version; it predates version "
            "attribution and cannot be validated against any contract")
    if version not in GOVERNED_METRICS:
        raise UnsupportedModelVersion(
            f"{version!r} is not a contract this build knows "
            f"(known: {', '.join(sorted(GOVERNED_METRICS))})")
    return GOVERNED_METRICS[version]


@dataclass(frozen=True)
class Violation:
    """One way a persisted row contradicts the contract."""

    metric: str
    kind: str        # unexplained_null | contradictory_state | missing_governed
    detail: str

    def __str__(self) -> str:
        return f"{self.metric} [{self.kind}]: {self.detail}"


#: Used as the metric name on a violation that is about the row, not a column.
ROW = "<row>"


def violations(values: Mapping[str, Optional[float]],
               states: Optional[Mapping[str, Mapping]] = None,
               model_version: Any = UNSPECIFIED) -> list[Violation]:
    """Every way this row's columns and sidecar disagree.

    Three kinds, and the second matters as much as the first:

      unexplained_null    NULL with no entry — absent means APPLICABLE, so the
                          row claims a value it does not have.
      contradictory_state an entry beside a populated value — a stale key left
                          behind by a suppressed -> applicable transition. A
                          contract-aware reader suppresses a number that is
                          now perfectly good, which is a silent regression in
                          the opposite direction.
      missing_governed    a governed metric absent from the row entirely.

    Plus two row-level kinds when a version is being checked at all. Pass
    ``UNSPECIFIED`` (the default) for the in-memory pre-write check, where no
    version has been assigned yet; pass the row's actual version — including
    ``None`` — when validating something persisted.
    """
    states = states or {}
    out: list[Violation] = []

    governed: frozenset[str] = frozenset()
    if model_version is not UNSPECIFIED:
        try:
            governed = governed_for(model_version)
        except UnsupportedModelVersion as e:
            kind = ("unversioned" if model_version is None
                    else "unsupported_model_version")
            out.append(Violation(ROW, kind, str(e)))

    for metric, value in values.items():
        entry = states.get(metric)
        if value is None and entry is None:
            out.append(Violation(metric, "unexplained_null",
                                 "null value with no recorded state"))
        elif value is not None and entry is not None:
            out.append(Violation(
                metric, "contradictory_state",
                f"value {value!r} present beside state "
                f"{entry.get('state')!r} — stale sidecar entry"))

    for metric in sorted(governed - set(values)):
        out.append(Violation(metric, "missing_governed",
                             f"governed by {model_version} but absent from the row"))

    return sorted(out, key=lambda v: (v.kind, v.metric))


def assert_complete(values: Mapping[str, Optional[float]],
                    states: Optional[Mapping[str, Mapping]] = None,
                    model_version: Any = UNSPECIFIED) -> None:
    """Raise on any violation. For the write path, before the row is committed."""
    bad = violations(values, states, model_version)
    if bad:
        raise ValueError("persistence contract violated: "
                         + "; ".join(str(v) for v in bad))


# ── The API shape ─────────────────────────────────────────────────────────────

def row_payload(values: Mapping[str, Optional[float]],
                states: Optional[Mapping[str, Mapping]] = None,
                source_health: Optional[SourceHealth] = None,
                domain: Optional[Domain] = None,
                compute_run_id: Optional[int] = None,
                model_version: Any = UNSPECIFIED) -> dict:
    """What a route returns: numbers, plus why any of them are missing.

    The client never has to infer a cause from a null. ``source_health`` rides
    at the row level rather than being repeated per metric, and is what lets a
    page render "Data unavailable — dividend feed incomplete" instead of an
    em-dash that reads as "this company pays no dividend".

    Refuses outright when ``model_version`` names a contract this build cannot
    interpret. A row whose semantics are unknown must not be served *as if*
    they were known: the numbers might be fine, and there is no way to say so.
    """
    if model_version is not UNSPECIFIED:
        governed_for(model_version)      # raises UnsupportedModelVersion

    assessments = decode_all(values, states, domain)
    out: dict[str, Any] = {
        "metrics": {m: a.value for m, a in assessments.items()},
        "states": {m: {"state": a.state.value,
                       "cause": a.cause.value if a.cause else None,
                       "display": a.display(),
                       "reason": a.reason}
                   for m, a in assessments.items() if not a.ok},
    }
    if compute_run_id is not None:
        out["compute_run_id"] = compute_run_id
    if source_health is not None:
        out["source_health"] = source_health.to_payload()
        if compute_run_id is not None and source_health.run_id is not None \
                and compute_run_id != source_health.run_id:
            raise ValueError(
                f"row claims compute_run_id {compute_run_id} but the supplied "
                f"source health belongs to run {source_health.run_id}")
    return out
