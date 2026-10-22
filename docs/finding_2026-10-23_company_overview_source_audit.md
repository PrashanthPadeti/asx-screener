# What a Company Overview can be sourced from today

**Measured:** 23 October 2026, read-only, 5 EODHD fundamentals requests
**Probe:** `backend/scripts/probe_company_overview_sources.py`
**Status:** audit complete; document sourcing unresolved and gating

## The request

Thirteen sections: profile, history and listing, core business, business
model and revenue sources, locations and markets, customers and pipeline,
order book, investments and growth projects, employees, competitors and
industry position, management and governance, vision and strategy, future
perspective.

## Method

Five companies chosen for spread rather than convenience — a lithium miner
(PLS), a diversified major (BHP), a bank (CBA), healthcare (CSL) and a
71-employee small cap (BRN). Coverage that holds for BHP and fails for a
small explorer cannot carry a page across ~2,100 companies, and probing
three large caps would have hidden that.

The section-to-field mapping was written in source **before** the data was
fetched, so the result is read against the request rather than against
whatever came back.

## Two different verdicts, and they are not the same

**Coverage** — does the provider return this field for every company?
**Sufficiency** — does that field answer the section's question?

Four sections have full coverage and do not answer their question. The
first version of this audit reported them as served, which would have
understated the work by roughly a third.

| # | Section | Coverage | Sufficient | Gap |
|---|---|---|---|---|
| 1 | Profile | 5/5 | **yes** | — |
| 2 | History & listing | **2/5** | no | no founding date at all; `IPODate` absent for CBA, CSL, BRN |
| 3 | Core business | 5/5 | no | one paragraph + a classification; no products, no specialisation |
| 4 | Business model | 5/5 | **no** | **no segment revenue anywhere.** The income statement gives totals, not which activities earn the money |
| 5 | Locations & markets | 5/5 | **no** | **head office only.** Not operating locations, not countries served |
| 6 | Customers & pipeline | 0/5 | no | nothing |
| 7 | Order book | 0/5 | no | nothing |
| 8 | Investments & projects | 0/5 | no | nothing |
| 9 | Employees | 5/5 | **yes** | a count, which is what the section asks for |
| 10 | Competitors & position | 5/5 | **no** | **a classification, not competitors.** No market position, no named rivals |
| 11 | Management & governance | 5/5 | **yes** | officers present for all five, including the 71-person company |
| 12 | Vision & strategy | 0/5 | no | nothing |
| 13 | Future perspective | 0/5 | no | nothing |

## What this means for the build

**Three sections need no documents:** profile, employees, management.

**Ten sections touch the document pipeline** — five entirely (6, 7, 8, 12,
13) and five for the part the provider does not serve (2, 3, 4, 5, 10).

So the annual-report pipeline is not a supplement to a mostly-provider
page. It is most of the feature. And because five sections must *merge*
provider data with document data, **the citation contract has to work at
field level, not section level**: "head office from the provider, operating
locations from the 2026 annual report page 14" has to be expressible and
renderable within one section.

## Two provider problems that affect every section

**The provider contradicts itself.** For PLS, `General.Name` is "Pilbara
Minerals Ltd" while `General.Description` opens "PLS Group Limited engages
in…". Two fields from one payload disagreeing about the company's name. One
is stale; which is not established. This is the description already visible
on the live company page, so it is ours to display whether or not it is
ours to fix.

**Currency is payload-level, not field-level.** `General.UpdatedAt` exists,
but if `Description` can be stale while `Name` is current, a single
timestamp cannot date individual fields. Every provider-sourced section
will be dated by a timestamp that does not actually apply to it. Unresolved.

## Also available, not yet considered

`Holders` and `InsiderTransactions` are returned in the same payload and may
bear on section 11. `LogoURL`, `WebURL`, `ISIN`, `LEI`, `Listings`,
`PrimaryTicker` and the four-level GIC hierarchy are present and unused.

## The gating question

Annual reports are PDFs on the ASX announcements platform.
`market.asx_announcements` holds EODHD **news items** — headlines, not
documents. Whether those PDFs can be obtained at scale, technically and
within ASX's terms, decides whether ten of the thirteen sections are
buildable at all.

That is unestablished, and no further design should proceed until it is.
Designing an extraction and citation contract for documents we may not be
able to obtain would be work spent on an assumption.
