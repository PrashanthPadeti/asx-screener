"""
Domain resolution — which economic model is this company?
=========================================================
The applicability contract decides what a metric means for a domain. This
decides which domain a company is in, and it is the input that determines how
much of the universe the contract suppresses. Get it wrong in one direction and
CBA is an industrial company again; wrong in the other and a quarter of the
market goes quiet for no reason.

Precedence, in order, first match wins:

    1. explicit structural flags      is_reit, is_miner — trustworthy booleans
    2. canonical industry mapping     from the observed production vocabulary
    3. defensible sector fallback     only where the sector alone settles it
    4. UNKNOWN                        and UNKNOWN is conservative, by contract

The rule that matters is the last one: **do not widen the mapping merely to
improve coverage.** An unmapped industry resolving to UNKNOWN costs some
suppressed metrics and is visible in the coverage report. An unmapped industry
guessed into GENERAL_CORPORATE costs a false distress warning on a bank, and is
visible to a customer.

``INDUSTRY_DOMAIN`` is deliberately empty until authored from the production
vocabulary — the roadmap's preflight (b) requires exemplar validation *before*
the mapping is written, not after. ``coverage()`` then answers the second
question the preflight asks, which is different from the first:

    data coverage      how many companies have an industry at all?
    resolver coverage  after the mapping runs, how many are still UNKNOWN?
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional

from compute.engine.applicability import Domain


class Source(str, Enum):
    """How a domain was established — recorded so coverage can be audited."""

    STRUCTURAL_FLAG = "structural_flag"
    INDUSTRY_MAPPING = "industry_mapping"
    SECTOR_FALLBACK = "sector_fallback"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class DomainResult:
    domain: Domain
    source: Source
    evidence: str = ""

    @property
    def resolved(self) -> bool:
        return self.domain is not Domain.UNKNOWN


# ── 1 · structural flags ──────────────────────────────────────────────────────
# is_reit and is_miner already back the AISC, reserve-life, NTA and WALE work,
# so they are the most trustworthy signal available. is_miner does not
# distinguish a producer from an explorer, and that distinction is the whole
# ARU case — a debt-free pre-revenue explorer scored Altman Z 2853 — so it is
# split on observed revenue rather than assumed.

#: Revenue at or below this is treated as pre-revenue for the producer/explorer
#: split. Not zero: a nominal interest or tenement-recharge line should not
#: promote an explorer to a producer.
PRE_REVENUE_CEILING = 1_000_000.0


# ── 2 · canonical industry mapping ────────────────────────────────────────────
# PENDING preflight B2/B3. Author from the observed vocabulary, lower-cased,
# after the exemplars confirm CBA/NAB/WBC/ANZ land as banks, QBE/IAG/MPL/SUN as
# insurers, and NWL/HUB/PNI as capital markets. Every entry here is a claim
# about an issuer's economics, so each one should be defensible on its own.

INDUSTRY_DOMAIN: dict[str, Domain] = {
    # e.g. "banks": Domain.BANK,
    #      "insurance": Domain.INSURER,
    #      "capital markets": Domain.CAPITAL_MARKETS,
}


# ── 3 · defensible sector fallback ────────────────────────────────────────────
# Only where the sector *alone* settles the question, and only where the
# fallback is at least as conservative as UNKNOWN.
#
# There is deliberately **no fallback for Financials**, and that is not an
# oversight. OTHER_FINANCIAL looks like the safe answer but is strictly weaker
# than UNKNOWN: it sits in FINANCIAL (so Altman is suppressed) but not in
# DEPOSIT_FUNDED, so debt_to_equity and current_ratio stay applicable. An
# unmapped Financials company that is actually a bank would therefore still be
# told its 4.6x leverage is elevated and its 0.1x current ratio is a liquidity
# risk — two of the three CBA lines, arriving through the fallback that was
# supposed to prevent them.
#
# It also hides the gap: with the fallback in place every unmapped financial
# lands quietly in OTHER_FINANCIAL, so the coverage report never lists "banks"
# as an industry worth authoring. Refusing to fall back makes the missing
# mapping visible, which is the point of measuring.
#
# Real Estate has no fallback for a related reason: the sector holds developers
# and agencies as well as trusts, and only is_reit is trustworthy.

SECTOR_FALLBACK: dict[str, Domain] = {}

#: Sectors where industrial metrics genuinely do apply, so GENERAL_CORPORATE is
#: a real answer rather than an assumed default. Kept explicit for the same
#: reason UNKNOWN is conservative: the absence of a rule must not be a rule.
INDUSTRIAL_SECTORS: frozenset[str] = frozenset({
    "consumer discretionary", "consumer staples", "energy", "health care",
    "healthcare", "industrials", "information technology", "technology",
    "communication services", "utilities", "materials",
})


def _clean(v: Optional[str]) -> str:
    return (v or "").strip().lower()


def resolve_domain(row: Mapping) -> DomainResult:
    """Resolve one company's economic model, first match wins.

    ``row`` needs whatever of ``is_reit``, ``is_miner``, ``industry``,
    ``sector`` and ``revenue`` the caller has. Anything absent simply means
    that step cannot fire.
    """
    # 1 · structural flags
    if row.get("is_reit"):
        return DomainResult(Domain.REIT, Source.STRUCTURAL_FLAG, "is_reit")

    if row.get("is_miner"):
        revenue = row.get("revenue")
        if revenue is None:
            # A miner whose revenue is unknown could be either, and the two
            # have opposite applicability. Refusing to guess is the contract.
            return DomainResult(Domain.UNKNOWN, Source.UNRESOLVED,
                                "is_miner, revenue unknown")
        if float(revenue) > PRE_REVENUE_CEILING:
            return DomainResult(Domain.MINING_PRODUCER, Source.STRUCTURAL_FLAG,
                                "is_miner, revenue above pre-revenue ceiling")
        return DomainResult(Domain.MINING_EXPLORER, Source.STRUCTURAL_FLAG,
                            "is_miner, pre-revenue")

    # 2 · canonical industry mapping
    industry = _clean(row.get("industry"))
    if industry and industry in INDUSTRY_DOMAIN:
        return DomainResult(INDUSTRY_DOMAIN[industry], Source.INDUSTRY_MAPPING,
                            f"industry={industry}")

    # 3 · defensible sector fallback
    sector = _clean(row.get("sector"))
    if sector in SECTOR_FALLBACK:
        return DomainResult(SECTOR_FALLBACK[sector], Source.SECTOR_FALLBACK,
                            f"sector={sector}")
    if sector in INDUSTRIAL_SECTORS:
        return DomainResult(Domain.GENERAL_CORPORATE, Source.SECTOR_FALLBACK,
                            f"sector={sector}")

    # 4 · unknown, conservatively
    if industry:
        return DomainResult(Domain.UNKNOWN, Source.UNRESOLVED,
                            f"industry={industry} unmapped")
    return DomainResult(Domain.UNKNOWN, Source.UNRESOLVED,
                        f"no industry, sector={sector or '(blank)'}")


# ── Resolver coverage ─────────────────────────────────────────────────────────

@dataclass
class Coverage:
    """What the resolver actually achieved over a set of companies."""

    total: int = 0
    by_domain: Counter = field(default_factory=Counter)
    by_source: Counter = field(default_factory=Counter)
    #: unmapped industry -> how many companies it accounts for, biggest first
    unmapped_industries: Counter = field(default_factory=Counter)

    @property
    def unknown(self) -> int:
        return self.by_domain[Domain.UNKNOWN]

    @property
    def unknown_pct(self) -> float:
        return 100.0 * self.unknown / self.total if self.total else 0.0

    def render(self, top_unmapped: int = 15) -> str:
        lines = [f"resolver coverage: {self.total} companies, "
                 f"{self.unknown} UNKNOWN ({self.unknown_pct:.1f}%)", "", "by domain:"]
        for domain, n in self.by_domain.most_common():
            lines.append(f"  {domain.value:20} {n:5}")
        lines += ["", "by source:"]
        for source, n in self.by_source.most_common():
            lines.append(f"  {source.value:20} {n:5}")
        if self.unmapped_industries:
            lines += ["", f"top unmapped industries (author these first):"]
            for industry, n in self.unmapped_industries.most_common(top_unmapped):
                lines.append(f"  {n:5}  {industry}")
        return "\n".join(lines)


def coverage(rows: Iterable[Mapping]) -> Coverage:
    """Measure resolver coverage — the question data coverage does not answer.

    A company can have an industry and still be UNKNOWN, because the mapping
    does not carry that industry yet. Run this before wiring so the real
    suppression percentage is known rather than estimated.
    """
    cov = Coverage()
    for row in rows:
        result = resolve_domain(row)
        cov.total += 1
        cov.by_domain[result.domain] += 1
        cov.by_source[result.source] += 1

        if result.domain is Domain.UNKNOWN:
            industry = _clean(row.get("industry"))
            cov.unmapped_industries[industry or "(no industry)"] += 1

    return cov
