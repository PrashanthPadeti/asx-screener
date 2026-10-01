"""
Which rows the serving surface can return
=========================================
One definition, imported by everyone who needs it, because three components
independently deciding what "the population" means is how a phantom defect
gets reported and a real one gets missed.

    every row the serving surface can return must either carry the current
    canonical contract, or be explicitly outside the serving population

Three components have to agree on the second half of that sentence:

    the API           filters what it will return
    the canonical writer  covers what the API can return
    the evidence bundle   measures the same set, or its numbers describe
                          a population nobody serves

They did not. The API filtered `price IS NOT NULL AND status = 'active'` in
three places, composite_score wrote exactly that set, and the evidence bundle
asked for `status = 'active'` alone -- so it saw 2,117 rows where the other
two saw 2,103, and reported 14 unexplained blanks on all 72 governed metrics.
Fourteen rows that are correctly outside the contract, reported as 1,005
violations of it.

That is the more dangerous direction for an instrument to fail in. A bundle
that under-reports hides defects; one that over-reports buries the real
findings in noise and trains the reader to skim past the column.

Why price is part of it: a row with no price has no market capitalisation, so
no P/E, no EV/EBITDA, no yield, no momentum. It is not a company the screener
can rank or filter, and the API has always excluded it. That is a product
decision rather than a correctness one, and it lives here where all three can
see it instead of being restated in four places that can drift apart.
"""

from __future__ import annotations

#: The SQL predicate, parameterless, for use with whatever alias the caller
#: has. Pass the alias so it reads naturally in the query it lands in.
def serving_predicate(alias: str = "") -> str:
    """`status = 'active' AND price IS NOT NULL`, qualified by `alias`."""
    prefix = f"{alias}." if alias else ""
    return f"{prefix}status = 'active' AND {prefix}price IS NOT NULL"


#: The same thing as a description, for evidence and logs. Kept beside the
#: predicate so a change to one is visibly a change to the other.
SERVING_POPULATION = "active companies with a price"


#: Price sources we no longer collect from.
#:
#: `yahoo` was a backfill job, deleted 30 Sep 2026 after the evidence showed
#: it was manufacturing ETF coverage from prices up to seven weeks old, on a
#: selector that only ever targeted codes with `price_date IS NULL` -- so once
#: an instrument had any price it was never refreshed again, by design.
#:
#: Deleting the job stopped acquisition. It did not stop SERVING: 1,849 rows
#: remain in market.daily_prices, and four instruments (DVDY, MTN, XASG,
#: HGODB) still had them as their NEWEST price 33 and 23 sessions after the
#: market moved on.
#:
#: This is not a staleness threshold and makes no claim about trading
#: activity. The distinction it draws is narrower and provable: a price from
#: a source we have retired can never become current, by any mechanism,
#: because nothing will ever write another one. Measured 1 Oct 2026, the
#: staleness tail is continuous (0,1,2,3,...,105 sessions) with no natural
#: cut-off, and this system has NO suspension signal -- `status` separates
#: only active from delisted, EODHD's General block carries nothing, and
#: announcements cover 216 of 2,155 codes and none of the affected ones. So
#: "has not traded" and "was not collected" are indistinguishable here, and a
#: session threshold would assert a feed failure that has not been
#: established.
#:
#: Storage is unaffected. The history stays; only eligibility changes.
RETIRED_PRICE_SOURCES = ("yahoo",)


def current_source_predicate(alias: str = "") -> str:
    """`data_source` is one we still collect from, qualified by `alias`.

    Spelled inline for the same reason excluded_types_predicate is: it lands
    in the middle of queries that carry their own parameters.
    """
    prefix = f"{alias}." if alias else ""
    retired = ", ".join(f"'{s}'" for s in RETIRED_PRICE_SOURCES)
    return f"COALESCE({prefix}data_source, '') NOT IN ({retired})"


#: Instrument types the screener does not carry.
#:
#: Hybrids, capital notes and preference shares are not ordinary equities. They
#: also distort the composite score: having no momentum or growth data, they
#: are averaged over their remaining factors only, which floats them to the top
#: of the ranking.
#:
#: Lives here, with the rest of the population definition, because
#: build_screener_universe and technical_compute must agree on it. They did
#: not: technical_compute's expected population included SUNPG, a note the
#: universe deletes, so the producer was held to covering a row the product
#: never serves.
EXCLUDED_COMPANY_TYPES = ("notes", "preferred_stock")


def excluded_types_predicate(alias: str = "") -> str:
    """`COALESCE(company_type,'') NOT IN (...)`, qualified by `alias`.

    Spelled out rather than parameterised: this lands in the middle of queries
    that already carry their own parameters, and threading two more through
    every call site is how the two copies of the list appear.
    """
    prefix = f"{alias}." if alias else ""
    types = ", ".join(f"'{t}'" for t in EXCLUDED_COMPANY_TYPES)
    return f"COALESCE({prefix}company_type, '') NOT IN ({types})"
