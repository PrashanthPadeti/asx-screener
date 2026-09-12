"""
What each factor is made of, declared
=====================================
A factor model is a claim about which signals compose a score and in what
proportion. Until now that claim lived only in ``composite_score.FACTOR_SIGNALS``
and was enforced by ``stacked.mean(axis=1, skipna=True)`` — which means it was
not enforced at all. A constituent that was NaN for any reason simply left the
average, and the remaining signals silently absorbed its weight.

Two very different things produced that NaN and neither was distinguishable
from the other at the point it mattered:

    NOT_MEANINGFUL      the signal does not apply to this company's economics.
                        A bank has no meaningful debt-to-equity, and a quality
                        model that reweights around it is arguably describing
                        the bank correctly — but only if that is the declared
                        policy, stated and inspectable.

    UNAVAILABLE         the signal applies and we do not have it. Reweighting
                        here publishes a different model under the same name:
                        a five-signal quality score for a company that should
                        have had six, with nothing in the payload to say so.

This module separates the declaration from the execution so both can be read,
tested and versioned without a database driver. ``composite_score`` imports
``psycopg2`` at module scope, so the previous table was unreachable in any
environment lacking the driver — including every test run and
``metric_registry.graph_health()``, which reports it as an import failure.

FACTOR_MODEL_V2 and Piotroski
-----------------------------
V1's quality model declared six constituents including ``piotroski_f_score``.
That metric is withheld under ``COMPUTATION_UNSUPPORTED``: its implementation
awards two of nine criteria unconditionally, compares two years of ratios
against a single balance sheet, and scores a missing prior year as a failure.

Measured on production, a faithful nine-criterion score cannot be computed for
any company. Of the 1,599 active companies carrying annual statements, 1,596
have the exact ``Y-1`` pair — period coverage is not the constraint — but
prior-year ``shares_outstanding`` is NULL for all 1,596, so F7 is unevaluable
universally, and prior ``long_term_debt`` is NULL for 915, capping F5 at 594.
``all_nine`` is zero in every segment including the ASX 200.

So V2 removes Piotroski from the quality model rather than leaving it in and
failing to compute it. The distinction from the defect this replaces is the
whole point: V1 claimed six signals and silently delivered five for banks; V2
claims five and delivers five. Piotroski carries zero weight because it is not
a V2 constituent, not because its value happened to be missing.

Restoring a faithfully computed Piotroski to quality would be a further model
version, contingent on coverage and methodology validation. It is a candidate,
not a commitment, and it should not become one merely because a data source is
repaired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from compute.engine.applicability import Applicability, Assessment, Cause


@dataclass(frozen=True)
class Constituent:
    """One declared signal, its nominal weight, and its direction."""

    metric: str
    weight: float
    #: +1 when a higher raw value is better, -1 when lower is better.
    direction: int


@dataclass(frozen=True)
class FactorSpec:
    """The declared composition of one factor under one model version."""

    name: str
    constituents: tuple[Constituent, ...]

    #: Whether a constituent that is NOT_MEANINGFUL for this company's domain
    #: may be dropped and the remaining weights renormalised.
    #:
    #: True is a policy, not a convenience: a bank genuinely has no meaningful
    #: leverage ratio, and scoring it against one would be the original defect.
    #: What makes it legitimate rather than a silent reweight is that the
    #: decision is declared here and the effective weights are returned for
    #: the caller to expose.
    domain_reweight: bool = True

    def __post_init__(self) -> None:
        total = sum(c.weight for c in self.constituents)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"{self.name}: declared weights sum to {total}, not 1.0 — a "
                f"model whose weights do not sum to one has no defined scale")
        names = [c.metric for c in self.constituents]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.name}: duplicate constituent in {names}")


@dataclass(frozen=True)
class EffectiveWeights:
    """What the factor was actually computed from, for this company.

    Returned rather than applied silently, because the difference between the
    declared model and the effective one is exactly what a consumer needs in
    order to know whether the number means what its name says.
    """

    factor: str
    weights: Mapping[str, float]
    #: Constituents dropped because they are out of domain, with the model's
    #: permission. Named so a surface can say which five of six ran.
    dropped_for_domain: tuple[str, ...] = ()
    state: Applicability = Applicability.APPLICABLE
    cause: Optional[Cause] = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.state is Applicability.APPLICABLE

    @property
    def reweighted(self) -> bool:
        return bool(self.dropped_for_domain)


def effective_weights(spec: FactorSpec,
                      assessments: Mapping[str, Assessment]) -> EffectiveWeights:
    """Resolve a declared factor against one company's assessments.

    The order matters and encodes the policy:

        1. A declared constituent with no assessment at all is a wiring fault,
           not a company fault, and fails closed.
        2. Any constituent that is UNAVAILABLE or INSUFFICIENT_DATA makes the
           factor unavailable. No renormalisation — the signal applies to this
           company and we simply do not have it, so a score computed without
           it is a different model wearing this one's name.
        3. Constituents that are NOT_MEANINGFUL are dropped and the remainder
           renormalised, but only when the spec declares that policy, and the
           drop is reported.
        4. If every constituent is out of domain the factor is itself
           NOT_MEANINGFUL. A quality score for a company none of whose quality
           signals apply is not a low score, it is no score.
    """
    missing = [c.metric for c in spec.constituents
               if c.metric not in assessments]
    if missing:
        return EffectiveWeights(
            spec.name, {}, state=Applicability.UNAVAILABLE,
            cause=Cause.SOURCE_MISSING,
            reason=f"declared constituents never assessed: "
                   f"{', '.join(sorted(missing))}")

    # Source failure and absent observations before anything else. A factor
    # that renormalises around these publishes a model nobody declared.
    unusable = [a for c in spec.constituents
                for a in (assessments[c.metric],)
                if a.state in (Applicability.UNAVAILABLE,
                               Applicability.INSUFFICIENT_DATA)]
    if unusable:
        names = ", ".join(sorted(a.metric for a in unusable))
        # The first cause is carried rather than flattened: an operator needs
        # to know whether waiting will help.
        return EffectiveWeights(
            spec.name, {}, state=Applicability.UNAVAILABLE,
            cause=unusable[0].cause,
            reason=f"required constituents unavailable: {names}")

    out_of_domain = tuple(sorted(c.metric for c in spec.constituents
                                 if assessments[c.metric].state
                                 is Applicability.NOT_MEANINGFUL))

    if out_of_domain and not spec.domain_reweight:
        return EffectiveWeights(
            spec.name, {}, state=Applicability.NOT_MEANINGFUL,
            reason=f"constituents out of domain and this model does not "
                   f"reweight: {', '.join(out_of_domain)}")

    keep = [c for c in spec.constituents if c.metric not in out_of_domain]
    if not keep:
        return EffectiveWeights(
            spec.name, {}, dropped_for_domain=out_of_domain,
            state=Applicability.NOT_MEANINGFUL,
            reason="every declared constituent is out of domain")

    total = sum(c.weight for c in keep)
    return EffectiveWeights(
        spec.name,
        {c.metric: c.weight / total for c in keep},
        dropped_for_domain=out_of_domain,
        reason=(f"reweighted around {', '.join(out_of_domain)}"
                if out_of_domain else ""))


def _spec(name: str, signals: list[tuple[str, int]], **kw) -> FactorSpec:
    """Equal nominal weights, which is what the previous mean() implied.

    Stated explicitly so that changing it later is a visible decision rather
    than a side effect of adding a signal to a list.
    """
    weight = 1.0 / len(signals)
    return FactorSpec(name, tuple(Constituent(m, weight, d)
                                  for m, d in signals), **kw)


#: V1, recorded as it was. Never used in production — no row has referenced it
#: — and kept so that "what did V1 claim" has an answer that is not a guess.
FACTOR_MODEL_V1: dict[str, FactorSpec] = {
    "value": _spec("value", [
        ("pe_ratio", -1), ("price_to_book", -1), ("ev_ebitda", -1),
        ("fcf_yield", +1), ("price_to_sales", -1)]),
    "quality": _spec("quality", [
        ("piotroski_f_score", +1), ("roe", +1), ("roce", +1),
        ("altman_z_score", +1), ("debt_to_equity", -1), ("net_margin", +1)]),
    "growth": _spec("growth", [
        ("revenue_growth_1y", +1), ("earnings_growth_1y", +1),
        ("eps_cagr_3y", +1), ("revenue_growth_hoh", +1),
        ("eps_growth_hoh", +1), ("revenue_cagr_5y", +1)]),
    "momentum": _spec("momentum", [
        ("return_1m", +1), ("return_3m", +1), ("return_6m", +1),
        ("rsi_14", +1), ("adx_14", +1)]),
    "income": _spec("income", [
        ("grossed_up_yield", +1), ("dividend_yield", +1),
        ("franking_pct", +1), ("dividend_consecutive_yrs", +1),
        ("dividend_cagr_3y", +1), ("dividend_payout_ratio", -1)]),
}

#: V2. Quality loses Piotroski — declared, not dropped at runtime. Everything
#: else carries forward unchanged.
FACTOR_MODEL_V2: dict[str, FactorSpec] = dict(FACTOR_MODEL_V1)
FACTOR_MODEL_V2["quality"] = _spec("quality", [
    ("roe", +1), ("roce", +1), ("altman_z_score", +1),
    ("debt_to_equity", -1), ("net_margin", +1)])

FACTOR_MODELS: dict[str, dict[str, FactorSpec]] = {
    "FACTOR_MODEL_V1": FACTOR_MODEL_V1,
    "FACTOR_MODEL_V2": FACTOR_MODEL_V2,
}


def model_for(version: str) -> dict[str, FactorSpec]:
    """Fail closed on an unknown version, as governed_for() does.

    An unrecognised model must not fall back to a default: silently scoring
    under semantics the caller did not ask for is the failure this whole
    versioning scheme exists to prevent.
    """
    try:
        return FACTOR_MODELS[version]
    except KeyError:
        raise ValueError(
            f"unknown factor model version {version!r}; known versions are "
            f"{', '.join(sorted(FACTOR_MODELS))}") from None
