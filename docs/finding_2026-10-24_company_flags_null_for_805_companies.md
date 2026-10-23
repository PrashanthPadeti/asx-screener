# `is_reit` and `is_miner` are unknown for 805 companies, and shown as "no"

**Measured:** 23 October 2026, read-only, across all current companies
**Status:** OPEN — the 500 it caused is fixed; the data gap is not

## What was measured

```
2589 current companies
  is_reit    1784 / 2589   68.9%
  is_miner   1784 / 2589   68.9%
  gics_sector 1981 / 2589  76.5%
  description 1818 / 2589  70.2%
```

**805 companies have NULL for both flags**, 598 of them `active` and therefore reachable through the search box. Not false — unknown. Nothing
has ever determined whether they are REITs or miners.

## Two consequences, one fixed and one not

**The 500 (fixed in this release).** `CompanySearchResult` and
`CompanyDetail` declare these fields `bool`. A Pydantic default covers a
missing key but rejects an explicit `None`, so searching any of those 805
companies produced "2 validation errors" and a 500 — 136 times, the most
frequent error on the site. `/companies/{code}` failed the same way for the
same companies.

**The silent negative (not fixed).** The screener `COALESCE`s these to
false, so `Is REIT = Yes` returns 35 and `Is Miner = Yes` returns 560.
Those are lower bounds presented as counts. A company whose status was
never determined is counted as "not a REIT" and excluded from the result,
with nothing on the page saying so.

The fix shipped in this release does the same thing — NULL renders as
false. That is consistent with what the schema's own default already
declares, and it is what unblocks the endpoint, but it is still an
assertion the data does not support. It is recorded here rather than
buried in a helper function.

## Why the gap exists

`asx_companies.py` writes only `asx_code`, `company_name`, `company_type`
and `status`. Everything else in `market.companies` — these flags,
`description`, `website`, `gics_*`, `employee_count` — comes from manual
scripts under `scripts/eodhd/v2/` that are not scheduled. `updated_at`
spans 23 June to 22 October with no pattern. Whatever those scripts last
covered is what the table holds.

That is the same root cause as the empty `employee_count` and
`listing_date` columns behind the Company Overview work, and the company
profile producer parked at `079ba23` is the intended repair for it.

## What would resolve this properly

1. **Determine the flags for all 2,589 companies**, from a source rather
   than by assumption. GICS sub-industry already distinguishes REITs; the
   mining classification is in `commodity_exposure` (96.1% populated) and
   `is_miner`'s own derivation rules in `domain_resolver`.
2. **Or distinguish unknown from false in the contract** — `Optional[bool]`
   on the schema, and a UI that says "not determined" rather than "no". The
   helper added in this release deliberately leaves `Optional[bool]` alone
   precisely so this remains possible without fighting it.

Until one of those happens, every REIT and miner count on the site is a
lower bound rendered as a total.

## Related

- `engineering_rule_absence_of_failure` — unknown states must be explicit
- commit `9c50b4c` (23 Jun) — the same defect, fixed in the screener only,
  by listing columns. A list covers what someone remembered; this
  release's fix derives the fields from the schema instead.
