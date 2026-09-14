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
