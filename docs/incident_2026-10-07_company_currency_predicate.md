# 7 October 2026 — the company list counted history as companies

`market.companies` is SCD Type 2. Every read that joined it on `asx_code`
alone received the historical rows too.

    4,459 rows        2,579 distinct codes        1,878 codes with history

## Found by accident

Immediately after deploying v11.2.9, the alert worker logged `0/8 fired` while
four alerts were active. The 2× was the join, not the alerts. Chasing it found
a unique index that makes the design explicit —
`idx_companies_current_code ON market.companies (asx_code) WHERE is_current` —
and a view, `market.companies_current`, that already existed and was already
used by the universe builder, `technical_compute` and `daily_compute`'s
selection.

So the correct pattern was in the codebase. The serving layer did not use it:
`is_current` appeared in twelve files, none of them under `app/`.

## Measured, before the fix

    /companies list      3,737 entries served     2,147 companies exist
    alert_worker         8 rows fetched for 4 active alerts
    announcement sweep   LIMIT 200 over a fanned join -> ~115 distinct codes
    CBA announcements    52 join rows for 26 announcements

The list is the customer-visible one: a third of the entries on the companies
page were superseded records, and the pagination total counted them.

## Three failure modes, not one

**Fan-out.** `/companies` and its `COUNT(*)`, `predictions` and its `COUNT(*)`,
the alert worker, the watchlist digest. Duplicate rows and inflated totals.

**Budget consumed by duplicates.** `announcement_worker` takes the top 200 by
market cap with `LIMIT 200` — rows, not codes — and keys them into a dict. The
top-200 sweep has been covering roughly 115 companies. Nothing failed; the
population was simply smaller than intended, which is the
derived-population-completeness failure again.

**Arbitrary row.** `/companies/{code}` does `SELECT *` then `.first()`;
`daily_compute.fetch_company` does `fetchone()` for `shares_outstanding`.
Narrow: only **4 codes** have a superseded row differing in a served column.
DUI's superseded row says `gics_sector = 'Other'`, its current row says
`'Financials'`, so that page returned whichever the planner happened to give.

## What was already known, and handled wrongly

Three sites were individually defended — two `DISTINCT ON` wrappers in
`announcements.py` and `companies.py`, a `SELECT DISTINCT` in
`announcement_worker` — and one carries the comment *"companies that have
multiple rows in market.companies (normalised + raw names)"*. The condition
had been met, diagnosed, and patched at the call site. The join stayed wrong
everywhere else, and the diagnosis in that comment is wrong about the cause:
it is history, not name normalisation.

A claim made during this investigation and withdrawn: that announcements were
rendered twice on the site. The raw join does double, but the `DISTINCT ON`
collapses it before the response. What survives there is an arbitrary
`company_name`, not duplication.

## The view had drifted

`market.companies_current` enumerates its columns and was created before
`business_model_tag` and `commodity_exposure` were added. It served 50 of 52
columns, silently, for as long as those columns existed — a missing column in
a view is not an error until something selects it, and the only consumer that
wanted them read the base table with its own predicate.

It mattered here because `/companies/{code}` does `SELECT *`.
`migrations/refresh_companies_current_view.sql` appends them.

Drift will recur the next time a column is added. No view definition can
prevent that, so it is caught by a test rather than designed away.

## The fix

Identity and classification are read from `market.companies_current`. The base
table is for writers. 17 sites across `app/` and `compute/`.
`asx_companies.py` keeps the base table — it maintains the history — with an
explicit `is_current = TRUE`.

`tests/test_company_reads_are_current.py` enforces this on `app/` and
`compute/` by parsing each module and examining **string constants only**: the
property is "a SQL literal names this table", and a text scan would read this
document's own prose and the test's docstring. That has happened four times
here. `scripts/` is held at a frozen set of 13 legacy worklist queries whose
duplicates cost repeated downloads rather than wrong answers; a new offender
there fails the test.

## Not in scope

- the 13 legacy ingestion scripts, which re-download duplicated codes
- `DISTINCT ON (a.asx_code, a.title, a.released_at)` in `announcements.py`
  also collapses genuinely distinct announcements sharing a title and
  timestamp — a separate question from this one
- removing the three now-redundant `DISTINCT` wrappers; they are harmless
  once the joins are correct, and taking them out is a second change
