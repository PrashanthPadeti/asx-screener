"""
Structural company flags, derived from evidence or not at all
=============================================================
`is_reit` and `is_miner` answer questions about what a listed entity IS.
They are consumed as trustworthy booleans -- `domain_resolver` calls them
"explicit structural flags", `reit_metrics` and `mining_metrics` select
their whole populations with `WHERE is_reit = TRUE` / `is_miner = TRUE`.

They were derived like this:

    "reit" in (sn(row.get("gic_industry")) or "").lower()

When the industry is absent, `(None or "")` is the empty string and the
answer is **False**. A company nobody has assessed became a published,
confident non-REIT.

Measured on production, 24 Oct 2026: of 2,589 current companies, 884 have
no gics_industry; 805 carry NULL flags and ~80 had already been written as
definite negatives with nothing to justify them. In screener.universe,
768 of 2,552 rows -- 30% -- are unclassified, and the API renders each of
them as "Is REIT: No".

So the verdict is three-valued, because the world is:

    True / False   an industry was known, and it matched or it did not
    None           no industry was available          (failed to obtain)
    None           an ETF, note or fund               (cannot apply)

The last two read the same to a consumer but are different facts, and
neither is False. 439 of the 805 unclassified rows are ETFs: "is this ETF
a REIT" has no answer, and writing False invents one.

This module is deliberately free of database and environment imports so
the rules can be tested as what they are -- pure functions over a row --
without a driver, a connection or a .env file.
"""

#: Instrument types for which the structural questions have no answer.
NON_OPERATING_TYPES = {"etf", "notes", "fund", "preferred_stock"}

#: Industry substrings that identify a miner. Matched case-insensitively.
MINING_KEYWORDS = ("mining", "gold", "metals", "coal")


def sn(v):
    """Strip to a real value, or None for the many spellings of absent."""
    if v is None or str(v).strip() in ("", "None", "N/A"):
        return None
    return str(v).strip()


def _evidence(row) -> tuple:
    """(industry, type) as cleaned text, each None when not supplied.

    Keeping "no industry" distinct from "an industry that is not mining"
    is the whole point; collapsing them is the defect this module exists
    to prevent.
    """
    return sn(row.get("gic_industry")), sn(row.get("type"))


def classify_reit(row):
    """True, False, or None when the question cannot be answered."""
    industry, type_text = _evidence(row)

    # The instrument type can settle it on its own, in both directions.
    if type_text and "reit" in type_text.lower():
        return True
    if type_text and type_text.lower() in NON_OPERATING_TYPES:
        return None                      # not applicable, not negative
    if industry is None:
        return None                      # failed to obtain, not negative
    return "reit" in industry.lower()


def classify_miner(row):
    """True, False, or None when the question cannot be answered."""
    industry, type_text = _evidence(row)

    if type_text and type_text.lower() in NON_OPERATING_TYPES:
        return None
    if industry is None:
        return None
    return any(k in industry.lower() for k in MINING_KEYWORDS)
