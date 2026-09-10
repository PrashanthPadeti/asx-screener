"""
Metric dependency registry
==========================
A screen can be affected by a defect it never names. ``Quality Compounder``
filters on ``quality_score`` alone, and a matcher that only sees quoted field
names certifies it clean — while ``quality_score`` inherits ``debt_to_equity``,
``piotroski_f_score``, ``roe`` and ``roce`` underneath. The direct-reference
audit found 18 affected predefined screens and that number is a *lower bound*
for exactly this reason.

The fix is not a smarter regex:

    predicate
       -> normalise field / alias
       -> expand computed metric
       -> expand composite constituents recursively
       -> primitive metrics
       -> applicability + observation-validity rules

This module is that expansion, and it is the mechanism that makes the
composite-inheritance invariant enforceable rather than aspirational:

    A composite cannot be more applicable than the material constituents
    required to calculate it.

It audits **anomaly rules alongside screen definitions**. Both are predicates
over the same metrics, and auditing them by separate mechanisms is how
``HIGH_GROSSED_UP_YIELD`` came to fire on 199 ordinary semi-annual payers while
the screen audit reported clean.

Fail closed: a node that is neither a known primitive nor a declared composite
is reported ``unresolved`` and must never be treated as safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Sequence

from compute.engine.applicability import DOMAIN_RULES, POSITIVE_DENOMINATOR


class UnresolvedMetric(Exception):
    """Raised when strict resolution meets a node it cannot classify."""


class CircularDependency(Exception):
    """Raised when a composite transitively depends on itself."""


# ── Aliases ───────────────────────────────────────────────────────────────────
# The same concept is spelled differently in different layers: FACTOR_SIGNALS
# says ev_to_ebitda, the applicability rules and the screener columns say
# ev_ebitda. Normalising here is what stops an audit passing a screen clean
# because it looked for the other spelling.

ALIASES: dict[str, str] = {
    "ev_to_ebitda": "ev_ebitda",
    "ev_to_ebit": "ev_ebit",
    "return_on_equity": "roe",
    "return_on_capital_employed": "roce",
    "return_on_invested_capital": "roic",
    "pe": "pe_ratio",
    "p_e_ratio": "pe_ratio",
    "pb_ratio": "price_to_book",
    "p_b_ratio": "price_to_book",
    "ps_ratio": "price_to_sales",
    "de_ratio": "debt_to_equity",
    "piotroski": "piotroski_f_score",
    "piotroski_score": "piotroski_f_score",
    "altman_z": "altman_z_score",
    "altman": "altman_z_score",
    "franked_yield": "grossed_up_yield",
    "grossed_up_dividend_yield": "grossed_up_yield",
    "payout_ratio": "dividend_payout_ratio",
    "dps": "dividend_per_share",
}


def normalise(metric: str) -> str:
    """Canonical name for a metric, following alias chains."""
    seen: set[str] = set()
    m = metric.strip().lower()
    while m in ALIASES and m not in seen:
        seen.add(m)
        m = ALIASES[m]
    return m


# ── Level 2 · composites whose constituents live inside function bodies ───────
# FACTOR_SIGNALS and MB_WEIGHTS are data, so the factor layer can be generated.
# calc_piotroski(), piotroski_f_score() and altman_z_score() hold their
# constituents imperatively, so they are declared here instead. This is the
# largest variance driver in the P0-A estimate and the reason the registry is
# part of the runtime correctness mechanism rather than extra CI work.

COMPOSITES: dict[str, list[str]] = {
    # Piotroski's nine tests. Two of them — the leverage change and the
    # current-ratio change — are what make the whole score NM for a
    # deposit-funded balance sheet.
    "piotroski_f_score": [
        "net_profit", "operating_cash_flow", "return_on_assets",
        "leverage_change", "current_ratio_change", "shares_outstanding_change",
        "gross_margin_change", "asset_turnover_change", "accruals",
    ],
    # Altman's five weighted ratios, every one of which presumes an industrial
    # balance sheet and an operating revenue base.
    "altman_z_score": [
        "working_capital", "total_assets", "retained_earnings", "ebit",
        "market_cap", "total_liabilities", "revenue",
    ],
    "earnings_quality": ["operating_cash_flow", "net_profit"],
    "fcf_yield": ["free_cash_flow", "market_cap"],
    "fcf_conversion": ["free_cash_flow", "net_profit"],
    "free_cash_flow": ["operating_cash_flow", "capital_expenditure"],
    "net_debt_to_ebitda": ["total_debt", "cash_and_equivalents", "ebitda"],
    "interest_coverage": ["ebit", "interest_expense"],
    "working_capital": ["current_assets", "current_liabilities"],
    "current_ratio": ["current_assets", "current_liabilities"],
    "quick_ratio": ["current_assets", "inventory", "current_liabilities"],
    "debt_to_equity": ["total_debt", "total_equity"],
    "roe": ["net_profit", "total_equity"],
    "roce": ["ebit", "invested_capital"],
    "roic": ["nopat", "invested_capital"],
    "pe_ratio": ["price", "eps"],
    "price_to_book": ["price", "book_value_per_share"],
    "price_to_sales": ["price", "revenue_per_share"],
    "ev_ebitda": ["enterprise_value", "ebitda"],
    "ev_ebit": ["enterprise_value", "ebit"],
    "enterprise_value": ["market_cap", "total_debt", "cash_and_equivalents"],

    # The dividend chain. This is the path the TTM window defect travels:
    # market.dividends -> window -> gross-up -> yield -> income factor ->
    # composite -> rank -> screen membership -> anomaly predicate.
    "dividend_yield": ["dividend_per_share", "price"],
    "grossed_up_yield": ["grossed_up_dividend", "price"],
    "grossed_up_dividend": ["dividend_per_share", "franking_pct"],
    "dividend_payout_ratio": ["dividend_per_share", "eps"],
}

#: Columns that come straight from the database or a price series. Anything
#: that is neither one of these nor a declared composite is unresolved.
KNOWN_PRIMITIVES: frozenset[str] = frozenset({
    # prices and market data
    "price", "market_cap", "volume", "shares_outstanding", "beta",
    "return_1w", "return_1m", "return_3m", "return_6m", "return_1y", "return_ytd",
    "rsi_14", "adx_14", "atr_14", "sma_50", "sma_200", "week_52_high", "week_52_low",
    # income statement
    "revenue", "revenue_per_share", "ebit", "ebitda", "net_profit", "eps",
    "gross_profit", "operating_profit", "interest_expense", "nopat",
    "gross_margin", "operating_margin", "net_margin",
    # balance sheet
    "total_assets", "total_liabilities", "total_equity", "total_debt",
    "current_assets", "current_liabilities", "inventory", "retained_earnings",
    "cash_and_equivalents", "invested_capital", "book_value_per_share",
    # cash flow
    "operating_cash_flow", "capital_expenditure",
    # dividends
    "dividend_per_share", "franking_pct", "dividend_consecutive_yrs",
    "dividend_cagr_3y",
    # growth
    "revenue_growth_1y", "earnings_growth_1y", "revenue_growth_hoh",
    "eps_growth_hoh", "eps_growth_3y_cagr", "revenue_cagr_5y",
    "revenue_growth_3y_cagr", "earnings_growth_3y_cagr",
    # period-over-period deltas used by Piotroski
    "return_on_assets", "leverage_change", "current_ratio_change",
    "shares_outstanding_change", "gross_margin_change", "asset_turnover_change",
    "accruals", "asset_turnover", "inventory_turnover",
    # other engine outputs treated as inputs here
    "earnings_stability_score", "gross_margin_expansion",
    "operating_margin_expansion", "gross_margin_expanding",
    "operating_margin_expanding", "shares_dilution_3y", "percent_insiders",
    "short_pct", "multibagger_potential_score",
    # descriptive
    "asx_code", "company_name", "sector", "industry", "status",
    "is_asx200", "is_asx300", "is_reit", "is_miner",
})

#: Metrics whose validity depends on economic domain or on the observation.
#: Read from the applicability tables so the two cannot drift apart.
SENSITIVE: frozenset[str] = (
    frozenset(DOMAIN_RULES) | frozenset(POSITIVE_DENOMINATOR)
    # The dividend-methodology defect is not a domain question, but it makes
    # these fields sensitive in exactly the same operational sense: a predicate
    # over them was computed on a two-year window.
    | frozenset({"grossed_up_yield", "grossed_up_dividend", "dividend_yield",
                 "dividend_per_share", "franking_pct", "dividend_payout_ratio"})
)


def factor_composites() -> dict[str, list[str]]:
    """The five factor scores, generated from FACTOR_SIGNALS rather than copied.

    Falls back to nothing if the scoring engine cannot be imported (it pulls
    pandas); ``test_registry_matches_factor_signals`` asserts the two agree
    wherever the import does work, so CI cannot drift from runtime.
    """
    try:
        from compute.engine.composite_score import FACTOR_SIGNALS
    except Exception:
        return {}

    out = {f"{name}_score": [normalise(col) for col, _ in signals]
           for name, signals in FACTOR_SIGNALS.items()}
    out["composite_score"] = sorted(out)
    return out


def graph() -> dict[str, list[str]]:
    """The full dependency graph: declared composites plus generated factors."""
    g = dict(COMPOSITES)
    g.update(factor_composites())
    return g


# ── Resolution ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Resolution:
    """What a metric depends on, and how it got there."""

    metric: str
    primitives: frozenset[str]
    #: constituent -> the chain that reached it, e.g. quality_score -> roe
    paths: Mapping[str, tuple[str, ...]]
    unresolved: frozenset[str] = frozenset()

    @property
    def is_composite(self) -> bool:
        return bool(self.paths)


def resolve(metric: str, strict: bool = False,
            _graph: Optional[Mapping[str, Sequence[str]]] = None) -> Resolution:
    """Expand a metric to its primitive dependencies, transitively.

    ``strict`` raises on an unresolved node instead of reporting it. CI runs
    non-strict so it can list everything wrong in one pass; the runtime runs
    strict so an unknown node fails the request rather than being assumed safe.
    """
    g = _graph if _graph is not None else graph()
    root = normalise(metric)

    primitives: set[str] = set()
    unresolved: set[str] = set()
    paths: dict[str, tuple[str, ...]] = {}

    def walk(node: str, trail: tuple[str, ...]) -> None:
        # trail includes node as its final element, so a repeat anywhere
        # earlier in the trail is a cycle.
        if node in trail[:-1]:
            raise CircularDependency(" -> ".join(trail))

        children = g.get(node)
        if children is None:
            if node in KNOWN_PRIMITIVES:
                primitives.add(node)
            else:
                unresolved.add(node)
                if strict:
                    raise UnresolvedMetric(
                        f"{node} is neither a known primitive nor a declared "
                        f"composite (via {' -> '.join(trail)})")
            return

        for child in children:
            c = normalise(child)
            paths.setdefault(c, trail + (c,))
            walk(c, trail + (c,))

    walk(root, (root,))
    paths.pop(root, None)
    return Resolution(root, frozenset(primitives), paths, frozenset(unresolved))


def sensitive_dependencies(metric: str) -> dict[str, tuple[str, ...]]:
    """Every applicability-sensitive metric this one touches, with its path.

    Includes the metric itself when it is directly sensitive, so a caller
    never has to check two places.
    """
    res = resolve(metric)
    out: dict[str, tuple[str, ...]] = {}

    if res.metric in SENSITIVE:
        out[res.metric] = (res.metric,)
    for dep, path in res.paths.items():
        if dep in SENSITIVE:
            out[dep] = path
    return out


# ── The audit ─────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """One definition's blast radius, in the shape the roadmap requires."""

    name: str
    kind: str                              # "screen" | "anomaly"
    direct: list[str] = field(default_factory=list)
    inherited: dict[str, tuple[str, ...]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)

    @property
    def affected(self) -> bool:
        return bool(self.direct or self.inherited or self.unresolved)

    def render(self) -> str:
        lines = [self.name]
        if self.direct:
            lines.append(f"  direct:     {', '.join(sorted(self.direct))}")
        for dep, path in sorted(self.inherited.items()):
            lines.append(f"  inherited:  {' -> '.join(path)}")
        if self.unresolved:
            lines.append(f"  UNRESOLVED: {', '.join(sorted(self.unresolved))}")
        return "\n".join(lines)


def audit_definition(name: str, fields: Iterable[str], kind: str = "screen") -> Finding:
    """Audit one screen or anomaly rule, reporting direct *and* inherited."""
    finding = Finding(name=name, kind=kind)

    for raw in fields:
        f = normalise(raw)
        if f in SENSITIVE:
            if f not in finding.direct:
                finding.direct.append(f)

        for dep, path in sensitive_dependencies(f).items():
            if dep == f:
                continue
            finding.inherited.setdefault(dep, path)

        res = resolve(f)
        for u in res.unresolved:
            if u not in finding.unresolved:
                finding.unresolved.append(u)

    return finding


def screen_fields(screen: Mapping) -> list[str]:
    """Every metric a predefined screen references — filters and sort alike.

    Sorting matters as much as filtering: a screen ordered by a defective
    metric returns the wrong stocks first even when its filters are clean.
    """
    out = [f["field"] for f in screen.get("filters", []) if f.get("field")]
    if screen.get("sort_by"):
        out.append(screen["sort_by"])
    return out


def audit(screens: Sequence[Mapping] = (),
          anomalies: Sequence[Mapping] = ()) -> list[Finding]:
    """Audit screens and anomaly rules together, affected first.

    Anomaly rules are enumerated alongside screen definitions because they are
    predicates over the same metrics. Auditing them separately is what let a
    rule threshold on a metric that had been doubled since the threshold was
    chosen.
    """
    findings = [audit_definition(s.get("name") or s.get("id", "?"),
                                 screen_fields(s), "screen")
                for s in screens]
    findings += [audit_definition(a.get("flag_type") or a.get("name", "?"),
                                  a.get("fields", []), "anomaly")
                 for a in anomalies]

    return sorted(findings, key=lambda f: (not f.affected, f.kind, f.name))


def render(findings: Sequence[Finding]) -> str:
    """The blast-radius report: why each definition is affected, not how many."""
    affected = [f for f in findings if f.affected]
    body = "\n\n".join(f.render() for f in affected)
    unresolved = sorted({u for f in findings for u in f.unresolved})

    summary = f"{len(affected)} of {len(findings)} definitions affected"
    if unresolved:
        summary += f"\nFAIL CLOSED — unresolved nodes: {', '.join(unresolved)}"
    return f"{body}\n\n{summary}" if body else summary
