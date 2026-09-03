"""
Market semantic taxonomy
========================
Central definitions for the vague terms investors use — "small cap", "micro
cap" and so on — so they live in one place rather than inside a prompt string.

Kept per market because the bands are not universal: A$500M is a mid-tier
company on the ASX and a micro cap in the US. When the screener covers more
than Australia, add a market here rather than branching in the prompt.

All bounds are in millions of the local currency. None means unbounded.
"""
from typing import Optional

# ── Market capitalisation bands ───────────────────────────────────────────────
# ASX: the S&P/ASX Small Ordinaries covers roughly the 100th to 300th largest
# names, which is about A$100M–A$1.5B. Capping "small cap" at A$300M pushes the
# result set into micro-cap territory — illiquid, frequently pre-profit, and
# heavily diluted — which is rarely what someone means by the phrase.
CAP_BANDS: dict[str, dict[str, tuple[Optional[float], Optional[float]]]] = {
    "AU": {
        "nano":   (None,      50),
        "micro":  (50,        100),
        "small":  (100,       1_500),
        "mid":    (1_500,     10_000),
        "large":  (10_000,    50_000),
        "mega":   (50_000,    None),
    },
}

DEFAULT_MARKET = "AU"

# Phrases that map onto a band, so "tiny companies" and "microcaps" land in the
# same place without the model inventing its own thresholds.
CAP_SYNONYMS: dict[str, str] = {
    "nano cap": "nano",   "nanocap": "nano",
    "micro cap": "micro", "microcap": "micro", "tiny": "micro",
    "small cap": "small", "smallcap": "small", "small companies": "small",
    "mid cap": "mid",     "midcap": "mid",
    "large cap": "large", "largecap": "large", "blue chip": "large",
    "mega cap": "mega",   "megacap": "mega",
}


def cap_band(name: str, market: str = DEFAULT_MARKET) -> tuple[Optional[float], Optional[float]]:
    """Bounds in millions for a named band, e.g. ('small') -> (100, 1500)."""
    return CAP_BANDS.get(market, CAP_BANDS[DEFAULT_MARKET]).get(name, (None, None))


def describe_bands(market: str = DEFAULT_MARKET) -> str:
    """Render the bands for inclusion in an LLM prompt."""
    bands = CAP_BANDS.get(market, CAP_BANDS[DEFAULT_MARKET])
    lines = []
    for label, (lo, hi) in bands.items():
        if lo is None:
            rng = f"market_cap lte {hi:.0f}"
        elif hi is None:
            rng = f"market_cap gte {lo:.0f}"
        else:
            rng = f"market_cap gte {lo:.0f} AND market_cap lte {hi:.0f}"
        lines.append(f'  "{label} cap": {rng}   (values in AUD millions)')
    return "\n".join(lines)
