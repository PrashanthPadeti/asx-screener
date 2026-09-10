"""
Applicability — is this metric valid for this company, and for this observation
===============================================================================
A metric must be valid for a company's economic model *before* it is
calculated, scored, flagged, or supplied to AI. Today nothing enforces that, so
the product tells users Commonwealth Bank is financially distressed:

    Altman Z-Score -0.15 — elevated financial distress risk
    High debt-to-equity 4.6x — elevated leverage
    Current ratio 0.1x below 1 — near-term liquidity risk

Every line is a category error. Altman removed financial institutions from his
original sample because their capital structure breaks the model. Leverage of
4.6x is a bank's business model — deposits are liabilities. A current ratio
presumes a working-capital cycle banks do not have. And the same bug runs from
the other end: ARU, a pre-revenue explorer with $7M of liabilities, is told its
Altman Z of 2853.0 indicates *safety*.

This is not a presentation filter. ``quality_score`` rewards "low D/E", so the
same off-domain metrics change rankings and screen membership across the
Financials sector. Applicability is therefore a shared scoring contract,
consumed by the calculation engine, factor scoring, screens, saved queries,
anomaly rules, the UI and the AI prompt alike. Suppressing a metric visually
while still ranking on it underneath is the failure mode to design against.

Two gates, not one:

    Domain validity       Is this metric meaningful for this economic model?
                          Altman Z on a bank                  -> not_meaningful

    Observation validity  Are the underlying values in a state where the ratio
                          has economic meaning?
                          ROE with equity <= 0  (QAN 206.30%) -> not_meaningful
                          5Y CAGR with 3 years of history     -> insufficient_data
                          Valid metric, provider field absent -> unavailable

``NM`` is not missing data. A suppressed current ratio for CBA and an absent
current ratio mean entirely different things, and collapsing them into one
em-dash is how the page reached its present state. The distinction has to
survive into the score and the prompt, not just the pixel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Optional


class Applicability(str, Enum):
    """The four states. Frozen — every consumer branches on exactly these."""

    APPLICABLE = "applicable"                # valid for this economic model
    NOT_MEANINGFUL = "not_meaningful"        # deliberately suppressed, out of domain
    UNAVAILABLE = "unavailable"              # applicable, but the source has no value
    INSUFFICIENT_DATA = "insufficient_data"  # applicable, too little history


class Cause(str, Enum):
    """*Why* a metric is not applicable — a different axis from *whether*.

    The four states are frozen and stay four. This is the discriminator the
    states cannot carry on their own, and it exists because of one rule:

        FEED_INCOMPLETE is not NOT_APPLICABLE.

    A REIT metric that does not apply to a bank is an applicability decision:
    the number would be meaningless, the model is working, and a composite may
    legitimately reweight around it. A dividend metric that cannot be computed
    because the exchange-wide feed stopped is a data-quality failure: the
    number is meaningful and simply missing, and reweighting around it would
    silently redefine the strategy rather than describe the company.

    Identical downstream behaviour for those two is the failure being designed
    against.
    """

    DOMAIN = "domain"                      # gate 1 — wrong economic model
    OBSERVATION = "observation"            # gate 2 — values without meaning
    SOURCE_MISSING = "source_missing"      # this company has no value
    SOURCE_UNHEALTHY = "source_unhealthy"  # the feed itself is broken
    INSUFFICIENT_HISTORY = "insufficient_history"


class PredicateResult(str, Enum):
    """How a predicate over an assessment resolves.

    ``NOT_ELIGIBLE`` and ``NO_DATA`` both mean "no comparison happened", and
    they are still different: an NM predicate must not exclude a security,
    because the metric is meaningless for it and penalising it would be the
    original bug. An unavailable predicate legitimately fails to match a
    positive filter, because the company does not demonstrate the property —
    we simply cannot show that it does.
    """

    EVALUATED = "evaluated"          # compare the value normally
    NOT_ELIGIBLE = "not_eligible"    # NM — cannot exclude, cannot include
    NO_DATA = "no_data"              # cannot match a positive filter


class Domain(str, Enum):
    """A company's economic model, which is not its sector or its security type.

    ``sector`` is insufficient: CBA and Netwealth are both *Financials*.
    ``company_type`` holds common_stock / etf / notes / fund — a *security*
    classification, the wrong abstraction for an issuer's economics.
    ``is_reit`` and ``is_miner`` solve two known cases only.
    """

    BANK = "bank"
    INSURER = "insurer"
    CAPITAL_MARKETS = "capital_markets"      # asset & wealth managers, exchanges
    OTHER_FINANCIAL = "other_financial"      # consumer finance, diversified
    REIT = "reit"
    MINING_PRODUCER = "mining_producer"
    MINING_EXPLORER = "mining_explorer"      # pre-revenue
    GENERAL_CORPORATE = "general_corporate"
    UNKNOWN = "unknown"


#: Domains whose balance sheets are funded by deposits, float or client money,
#: so industrial leverage and working-capital ratios do not describe them.
DEPOSIT_FUNDED = frozenset({Domain.BANK, Domain.INSURER})

#: Every domain whose accounts do not take an industrial P&L or balance-sheet
#: shape. Capital markets and consumer finance sit here because their gearing
#: and revenue recognition differ enough that industrial defaults mislead.
FINANCIAL = frozenset({Domain.BANK, Domain.INSURER,
                       Domain.CAPITAL_MARKETS, Domain.OTHER_FINANCIAL})


@dataclass(frozen=True)
class Assessment:
    """One metric's state, with the reason it reached it.

    ``value`` is None whenever the state is not APPLICABLE. That is the whole
    point: a suppressed metric must not be reachable by a caller that forgets
    to check the state, because a ranking built on ``assessment.value`` would
    otherwise silently keep using the number it was told not to use.

    ``observed`` remembers the input for debugging and evidence. It is
    deliberately *not* the same field: an assessment can remember what it was
    given without presenting it as an interpretable metric. Nothing that
    ranks, sorts, filters, alerts or displays may read it — see
    ``usable_values`` and ``to_payload`` for the supported ways out.
    """

    metric: str
    state: Applicability
    value: Optional[float] = None
    reason: str = ""
    domain: Optional[Domain] = None
    observed: Optional[float] = None
    cause: Optional[Cause] = None

    @property
    def ok(self) -> bool:
        return self.state is Applicability.APPLICABLE

    @property
    def suppressed(self) -> bool:
        """True when a value exists but must not be used or shown as a number."""
        return self.state is Applicability.NOT_MEANINGFUL

    @property
    def source_unhealthy(self) -> bool:
        """True when the *feed* failed, not the company and not the model.

        The one property a composite must consult before reweighting.
        """
        return self.cause is Cause.SOURCE_UNHEALTHY

    @property
    def reweightable(self) -> bool:
        """May a composite renormalise around this absence?

        Only when the absence is applicability-driven. A metric missing
        because the source broke is a gap in the data, not a statement about
        the company, and building a smaller composite on it changes what the
        composite means without saying so.
        """
        return not self.ok and not self.source_unhealthy

    def display(self) -> str:
        """What the UI renders. Never an em-dash for a suppressed metric, and
        never a bare em-dash for a broken feed either — those read as "this
        company has no dividend", which is a different and false claim."""
        if self.state is Applicability.APPLICABLE:
            return "" if self.value is None else f"{self.value:g}"
        if self.state is Applicability.NOT_MEANINGFUL:
            return "NM"
        if self.source_unhealthy:
            return "Data unavailable"
        return "—"


# ── Gate 1 · domain validity ──────────────────────────────────────────────────

#: metric -> the domains for which it is *not* meaningful, and why.
#: Declarative so the dependency registry and the CI audit can read the same
#: table the runtime uses, rather than re-deriving it from scoring code.
DOMAIN_RULES: dict[str, tuple[frozenset[Domain], str]] = {
    # Altman excluded financial institutions from the original sample; the
    # model also has no meaning below a revenue base, which is how a debt-free
    # explorer scored 2853.
    "altman_z_score": (FINANCIAL | {Domain.MINING_EXPLORER},
                       "Altman's model excludes financial institutions and "
                       "presumes an operating revenue base"),

    "debt_to_equity": (DEPOSIT_FUNDED,
                       "deposits and policyholder funds are liabilities by "
                       "design, not leverage"),
    "current_ratio": (DEPOSIT_FUNDED,
                      "no working-capital cycle"),
    "quick_ratio": (DEPOSIT_FUNDED,
                    "no working-capital cycle"),
    "interest_coverage": (DEPOSIT_FUNDED,
                          "interest expense is a cost of goods, not a burden "
                          "on operating profit"),
    "working_capital": (DEPOSIT_FUNDED,
                        "no working-capital cycle"),

    "gross_margin": (FINANCIAL | {Domain.REIT},
                     "no cost of goods sold; an industrial P&L shape forced "
                     "onto interest or rental income"),
    "operating_margin": (FINANCIAL,
                         "no comparable operating revenue line"),
    # A change in a meaningless margin is equally meaningless, and these are
    # ranked cross-sectionally by the multibagger score — so leaving them
    # unmasked would let a bank's gross-margin trend move every industrial
    # company's capital-efficiency percentile.
    "gross_margin_expansion": (FINANCIAL | {Domain.REIT},
                               "change in a margin that has no meaning here"),
    "operating_margin_expansion": (FINANCIAL,
                                   "change in a margin that has no meaning here"),
    "gross_margin_expanding": (FINANCIAL | {Domain.REIT},
                               "change in a margin that has no meaning here"),
    "operating_margin_expanding": (FINANCIAL,
                                   "change in a margin that has no meaning here"),
    "inventory_turnover": (FINANCIAL | {Domain.REIT, Domain.MINING_EXPLORER},
                           "no inventory"),
    "asset_turnover": (FINANCIAL,
                       "assets are the earning base, not a throughput input"),

    "ev_ebitda": (FINANCIAL,
                  "enterprise value is not defined where debt is the operating "
                  "input"),
    "ev_ebit": (FINANCIAL, "enterprise value is not defined for these"),
    "net_debt_to_ebitda": (FINANCIAL, "debt is funding, not a burden ratio"),

    "free_cash_flow": (DEPOSIT_FUNDED,
                       "negative operating cash flow is what a growing loan "
                       "book looks like"),
    "fcf_conversion": (DEPOSIT_FUNDED, "operating cash flow is not comparable"),
    "earnings_quality": (DEPOSIT_FUNDED,
                         "accrual-to-cash comparison presumes an industrial "
                         "cash cycle"),

    "price_to_sales": ({Domain.MINING_EXPLORER} | DEPOSIT_FUNDED,
                       "no revenue base to price against"),

    # Piotroski's nine tests include a leverage change and a current-ratio
    # change, both meaningless for a deposit-funded balance sheet, and margin
    # and turnover tests that a pre-revenue explorer cannot satisfy. It is a
    # composite, so this is really composite inheritance stated up front — see
    # assess_composite for the general rule.
    "piotroski_f_score": (DEPOSIT_FUNDED | {Domain.MINING_EXPLORER},
                          "leverage-change and current-ratio subtests are out "
                          "of domain"),
}

#: Metrics that are domain-sensitive at all. Under an unresolved domain these
#: are suppressed rather than defaulted — the absence of a rule is exactly how
#: CBA came to be treated as an industrial company.
DOMAIN_SENSITIVE = frozenset(DOMAIN_RULES)


def domain_gate(metric: str, domain: Domain) -> Optional[tuple[Applicability, str]]:
    """Gate 1. Returns None when the metric passes for this domain."""
    rule = DOMAIN_RULES.get(metric)
    if rule is None:
        return None

    not_meaningful_for, reason = rule

    if domain is Domain.UNKNOWN:
        # Conservative by contract: an unclassified issuer must not inherit
        # industrial defaults. Suppressing here costs a number; defaulting
        # costs a false distress warning on a bank.
        return (Applicability.NOT_MEANINGFUL,
                "economic model not resolved; metric is domain-sensitive")

    if domain in not_meaningful_for:
        return (Applicability.NOT_MEANINGFUL, reason)

    return None


# ── Gate 2 · observation validity ─────────────────────────────────────────────

@dataclass(frozen=True)
class Observation:
    """The underlying values gate 2 needs, beyond the metric's own value.

    Populated from whatever the caller already has. Anything left None simply
    means that particular check cannot run, not that it passed.
    """

    equity: Optional[float] = None
    earnings: Optional[float] = None
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    invested_capital: Optional[float] = None
    periods_available: Optional[int] = None
    periods_required: Optional[int] = None


#: metric -> (Observation field that must be positive, why it matters)
#: A ratio whose denominator is zero or negative does not become a large
#: number, it stops having a sign that means anything: QAN's negative equity
#: produced ROE 206.30%, which a percentile rank reads as exceptional quality.
POSITIVE_DENOMINATOR: dict[str, tuple[str, str]] = {
    # Keyed by canonical identity only. `return_on_equity` used to appear here
    # beside `roe`, which meant the same rule existed twice under two names
    # and SENSITIVE carried a spelling rather than an identity. Consumers
    # canonicalise before calling assess(), so the alias needs no entry.
    "roe": ("equity", "negative or zero equity inverts the ratio's meaning"),
    "book_value_per_share": ("equity", "negative book value is not a per-share base"),
    "price_to_book": ("equity", "negative book value inverts the multiple"),
    "pe_ratio": ("earnings", "a negative P/E is not a cheap P/E"),
    "peg_ratio": ("earnings", "a negative P/E is not a cheap P/E"),
    "roce": ("invested_capital", "negative capital employed inverts the ratio"),
    "roic": ("invested_capital", "negative invested capital inverts the ratio"),
    "price_to_sales": ("revenue", "no revenue to price against"),
    "ev_ebitda": ("ebitda", "negative EBITDA inverts the multiple"),
}


def observation_gate(metric: str, value: Optional[float],
                     obs: Optional[Observation]) -> Optional[tuple[Applicability, str]]:
    """Gate 2. Returns None when the observation passes."""
    if obs is not None:
        need = POSITIVE_DENOMINATOR.get(metric)
        if need is not None:
            field, reason = need
            denom = getattr(obs, field)
            if denom is not None and denom <= 0:
                return (Applicability.NOT_MEANINGFUL, reason)

        if obs.periods_required is not None and obs.periods_available is not None:
            if obs.periods_available < obs.periods_required:
                return (Applicability.INSUFFICIENT_DATA,
                        f"{obs.periods_available} of {obs.periods_required} "
                        f"periods available")

    if value is None:
        return (Applicability.UNAVAILABLE, "no value from source")

    return None


# ── The assessment ────────────────────────────────────────────────────────────

def assess(metric: str, value: Optional[float], domain: Domain,
           obs: Optional[Observation] = None) -> Assessment:
    """Run both gates, in order, before the value reaches anything downstream.

    Domain runs first and deliberately outranks availability: a metric that is
    meaningless for a bank is ``NM`` whether or not the provider happened to
    send a number, because the number is what causes the harm.
    """
    gate1 = domain_gate(metric, domain)
    if gate1 is not None:
        state, reason = gate1
        return Assessment(metric, state, None, reason, domain, observed=value,
                          cause=Cause.DOMAIN)

    gate2 = observation_gate(metric, value, obs)
    if gate2 is not None:
        state, reason = gate2
        cause = (Cause.INSUFFICIENT_HISTORY
                 if state is Applicability.INSUFFICIENT_DATA
                 else Cause.SOURCE_MISSING if state is Applicability.UNAVAILABLE
                 else Cause.OBSERVATION)
        return Assessment(metric, state, None, reason, domain, observed=value,
                          cause=cause)

    return Assessment(metric, Applicability.APPLICABLE, value, "", domain,
                      observed=value)


def unhealthy(metric: str, reason: str, domain: Optional[Domain] = None) -> Assessment:
    """An assessment for a metric whose *source* has failed.

    Constructed rather than assessed, because the failure is not about this
    company: the dividend feed stopping is an exchange-wide event, and every
    issuer's income metrics are equally uncomputable regardless of domain or
    observation. State is UNAVAILABLE — the metric is applicable and simply
    has no value — with the cause that stops consumers treating it as an
    applicability decision.
    """
    return Assessment(metric, Applicability.UNAVAILABLE, None, reason, domain,
                      cause=Cause.SOURCE_UNHEALTHY)


def assess_all(values: Mapping[str, Optional[float]], domain: Domain,
               obs: Optional[Observation] = None) -> dict[str, Assessment]:
    """Assess a whole row at once. The shape the compute engines want."""
    return {m: assess(m, v, domain, obs) for m, v in values.items()}


# ── Composite inheritance ─────────────────────────────────────────────────────

def assess_composite(metric: str, value: Optional[float],
                     constituents: Iterable[Assessment],
                     domain: Domain,
                     material: Optional[Iterable[str]] = None) -> Assessment:
    """A composite cannot be more applicable than the constituents it needs.

    "Disable Piotroski for banks" is the wrong rule — it fixes one model for
    one sector and teaches nothing. The durable rule generalises: a composite
    is itself ``NM`` whenever material constituent tests are out of domain. So
    CBA's 3/9 is an artifact, and so are the 5/9, 3/9 and 2/9 shown for its
    peers, without anyone having to remember this case for the next sector.

    ``material`` names the constituents that must be applicable; by default
    every constituent is material. An immaterial constituent that is
    unavailable degrades the composite to a smaller basis rather than
    invalidating it — but that basis must then be *declared*, not left implicit
    the way ``composite_score``'s equal-weight average of non-null factors
    currently is.
    """
    by_metric = {a.metric: a for a in constituents}
    required = set(material) if material is not None else set(by_metric)

    # Source failure is checked before anything else and never renormalised
    # around. A composite built on the remaining factors would be a different
    # composite wearing the same name.
    broken = [a for m, a in by_metric.items()
              if m in required and a.source_unhealthy]
    if broken:
        names = ", ".join(sorted(a.metric for a in broken))
        return Assessment(metric, Applicability.UNAVAILABLE, None,
                          f"source unhealthy: {names}", domain,
                          observed=value, cause=Cause.SOURCE_UNHEALTHY)

    out_of_domain = [a for m, a in by_metric.items()
                     if m in required and a.suppressed]
    if out_of_domain:
        names = ", ".join(sorted(a.metric for a in out_of_domain))
        return Assessment(metric, Applicability.NOT_MEANINGFUL, None,
                          f"material constituents out of domain: {names}", domain,
                          observed=value)

    missing = [a for m, a in by_metric.items()
               if m in required and a.state is Applicability.INSUFFICIENT_DATA]
    if missing:
        names = ", ".join(sorted(a.metric for a in missing))
        return Assessment(metric, Applicability.INSUFFICIENT_DATA, None,
                          f"constituents lack history: {names}", domain,
                          observed=value)

    unavailable = [a for m, a in by_metric.items()
                   if m in required and a.state is Applicability.UNAVAILABLE]
    if unavailable:
        names = ", ".join(sorted(a.metric for a in unavailable))
        return Assessment(metric, Applicability.UNAVAILABLE, None,
                          f"constituents unavailable: {names}", domain,
                          observed=value)

    if value is None:
        return Assessment(metric, Applicability.UNAVAILABLE, None,
                          "no value from source", domain, observed=value)

    return Assessment(metric, Applicability.APPLICABLE, value, "", domain,
                      observed=value)


# ── Effective weighting ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Weighting:
    """What a composite was actually built from, so the denominator is visible.

    ``composite_score`` is documented as an "equal-weight average of all 5
    non-null factors", which means a stock missing income already competes on a
    four-factor mean against five-factor stocks — and nothing on the card says
    so. Applicability makes that re-weighting more frequent, so it has to make
    it visible at the same time rather than after.
    """

    nominal: Mapping[str, float]
    applicable: frozenset[str]
    #: Factors absent because their source failed, not because they do not
    #: apply. Renormalising around these is prohibited.
    unhealthy: frozenset[str] = frozenset()

    @property
    def may_reweight(self) -> bool:
        """False when any absence is a data-quality failure.

        An applicability-driven reweight describes the company: a bank has no
        meaningful Piotroski, so quality is built from what remains. A
        source-driven reweight describes nothing — it silently converts a
        five-factor strategy into a four-factor one and keeps the name.
        """
        return not self.unhealthy

    @property
    def effective(self) -> dict[str, float]:
        """Nominal weights renormalised over the applicable factors.

        Empty when reweighting is prohibited: there is no defensible weighting
        of a composite whose input is missing for reasons that have nothing to
        do with the company.
        """
        if not self.may_reweight:
            return {}
        total = sum(w for k, w in self.nominal.items() if k in self.applicable)
        if total <= 0:
            return {}
        return {k: w / total for k, w in self.nominal.items() if k in self.applicable}

    @property
    def coverage(self) -> str:
        """``4/5 applicable`` — the string the card and the drawer show."""
        return f"{len(self.applicable)}/{len(self.nominal)} applicable"

    @property
    def is_reweighted(self) -> bool:
        return len(self.applicable) < len(self.nominal)


def predicate_excludes(assessment: Assessment) -> bool:
    """Whether a screen or anomaly predicate may exclude on this metric.

    An ``NM`` predicate does not evaluate FALSE, it fails to evaluate — so it
    cannot exclude a security. This is what stops "Top 25 stocks to buy and
    hold forever" from structurally excluding every major bank because
    ``debt_to_equity gt 1.5``, ``piotroski lt 5`` and ``altman lt 1.5`` all
    "fail" for a deposit-funded balance sheet.
    """
    return assessment.ok


def predicate_result(assessment: Assessment) -> PredicateResult:
    """How a filter over this assessment resolves — three outcomes, not two."""
    if assessment.ok:
        return PredicateResult.EVALUATED
    if assessment.suppressed:
        return PredicateResult.NOT_ELIGIBLE
    return PredicateResult.NO_DATA


# ── The canonical-strategy refresh gate ───────────────────────────────────────

@dataclass(frozen=True)
class RefreshGate:
    """Whether a canonical, published strategy may mint a new cohort."""

    permitted: bool
    blocked_by: tuple[str, ...] = ()
    message: str = ""


def refresh_gate(assessments: Iterable[Assessment],
                 required_families: Iterable[str],
                 last_published: Optional[str] = None) -> RefreshGate:
    """Fail closed at the refresh boundary when a required family has no source.

    AlphaFive is a *canonical* five-factor ranking. If Income disappears
    because the dividend feed stopped, recomputing it over the remaining four
    would publish a different strategy under the same name — even with the
    effective 25/25/25/25 weighting shown. The honest move is to decline to
    mint the cohort and say why.

    ``last_published`` is deliberately not called "last valid": if earlier
    cohorts were themselves computed on already-incomplete inputs, calling
    them valid manufactures a continuity that was never there.
    """
    required = set(required_families)
    broken = sorted({a.metric for a in assessments
                     if a.source_unhealthy and a.metric in required})

    if not broken:
        return RefreshGate(True)

    tail = (f"; last published computation: {last_published}"
            if last_published else "")
    return RefreshGate(
        False, tuple(broken),
        f"Refresh unavailable — source incomplete for {', '.join(broken)}{tail}")


# ── The consumer boundary ─────────────────────────────────────────────────────
# Everything above decides. These two decide *how the decision leaves*, and
# they exist because the dangerous failure is not a missing check — it is
# ``a.value or 0``, which turns a suppressed metric into a real number that
# sorts last, scores zero, and reads on a page as a fact.

def usable_values(assessments: Mapping[str, Assessment] | Iterable[Assessment]
                  ) -> dict[str, float]:
    """The only supported way to get numbers out for ranking or scoring.

    Applicable metrics only, with no placeholder for the rest — a suppressed
    metric is *absent* from the mapping rather than present as zero. A caller
    that iterates this cannot accidentally rank on something it was told not
    to use, because there is nothing there to rank on.
    """
    items = assessments.values() if isinstance(assessments, Mapping) else assessments
    return {a.metric: a.value for a in items if a.ok and a.value is not None}


def to_payload(assessment: Assessment, include_observed: bool = False) -> dict:
    """Serialise one assessment for an API response.

    ``value`` stays None for anything not applicable, all the way through
    serialisation — the invariant must survive the boundary, or the frontend
    re-acquires exactly the freedom this module removed. ``observed`` is
    emitted only when explicitly asked for, under its own key, and is for
    debugging and evidence rather than display.
    """
    out = {
        "metric": assessment.metric,
        "state": assessment.state.value,
        # The cause crosses the boundary too: a client that renders "—" for a
        # broken feed tells the user this company pays no dividend, which is a
        # different and false claim.
        "cause": assessment.cause.value if assessment.cause else None,
        "value": assessment.value if assessment.ok else None,
        "display": assessment.display(),
        "reason": assessment.reason,
    }
    if include_observed:
        out["observed_value"] = assessment.observed
    return out
