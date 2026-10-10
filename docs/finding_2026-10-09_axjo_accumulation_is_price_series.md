# Finding — "ASX 200 Accumulation" is served the price-only series

**Status: OPEN, unverified fix.** Found 9 Oct 2026 while keying producer
outcomes by entity code. Not caused by that work; exposed by it.

## The claim

`/indices` presents index code `AXJO` as:

> **S&P/ASX 200 Accumulation** — "The total return version of the S&P/ASX 200
> index, incorporating reinvestment of dividends. Provides a more accurate
> measure of total investor return than the price-only ASX 200. This is the
> standard benchmark used by Australian superannuation funds and managed
> equity funds."

(`app/api/v1/routes/indices_funds.py:137`)

## What it is actually served

```python
TICKER_MAP = {
    "ASX200": "^AXJO",
    "AXJO":   "^AXJO",   # accumulation — same price series as ASX200 on Yahoo
}
```

`^AXJO` **is** the S&P/ASX 200 price index. The comment states the problem
and was never treated as one. So the surface advertised as "more accurate
than the price-only ASX 200" is the price-only ASX 200.

## Nobody agrees what the series is

Three definitions coexist in the codebase:

| Where | Says it is |
|---|---|
| `index_prices.py` | "accumulation — same price series as ASX200" |
| `indices_funds.py` | "S&P/ASX 200 Accumulation", total return, ~200 constituents |
| three frontend files | "AXJO (All Ordinaries, ~500 stocks)" |

All Ordinaries is a different index from the S&P/ASX 200. So this is not
simply a wrong mapping — **the intended series is contested**, and the
correct replacement cannot be specified until that is settled. That is the
main reason containment is suppression rather than substitution.

## Why it matters

Every published figure for `AXJO` — `return_1y`, `return_ytd`, `return_1m` —
is a price-index observation presented as a total return, which is a
different quantity. A price series omits the dividend contribution by
construction.

**The size of that error is not stated here and must not be guessed.** An
earlier draft of this finding asserted "roughly 4% annually, compounding" by
applying a market dividend yield. That number was never measured against a
correct benchmark, and publishing an unmeasured figure is the exact practice
this work exists to end. The magnitude is unknown until a verified
accumulation series exists to difference against.

Aggravating factors:

- It is sold as **the superannuation benchmark**, which is the use where the
  price/accumulation distinction matters most.
- `/indices` is **Premium**. This is a paid-for number.
- The defect is visible without any tooling: `ASX200` and `AXJO` must render
  **identical** returns on that page, because they are the same series.

This is the governing rule of the correctness work, violated directly: *no
number may be served that the system cannot substantiate.*

## What is NOT yet established

- Whether the provider offers a genuine ASX 200 accumulation/total-return
  series, and under what symbol. Yahoo's `^AXJO` is price-only; EODHD may
  carry a total-return variant, but that must be **verified**, not assumed
  from a plausible-looking symbol.
- Whether any other index code in `TICKER_MAP` carries a definition its
  ticker does not satisfy. Only `AXJO` was examined. **Each index's
  definition must be checked against its provider mapping** before its output
  is declared usable — a mapping that merely returns data is not a mapping
  that returns the right data.

## Containment applied (9 Oct 2026)

Treated as release-blocking. The series is marked unavailable and its figures
withheld; **stored rows are preserved** for investigation, flagged as price-
index provenance and invalid for any accumulation calculation.

| Surface | Containment |
|---|---|
| `index_prices.py` | `AXJO` removed from `TICKER_MAP` — no new rows accrue under an unsupportable provenance |
| `GET /market-data/indices` | every numeric field withheld; `data_status = series_provenance_unverified` |
| `GET /market-data/indices/{code}` | same suppression on the price snapshot |
| `GET /market-data/indices/{code}/history` | returns an empty series — a chart would otherwise render exactly the points the other two withhold, and a chart is harder to caveat than a number |
| `INDEX_META` description | no longer claims total return, dividend reinvestment, or "the standard benchmark used by superannuation funds" |

`price_date` is retained: it says when the underlying rows stop, which an
investigator needs, and cannot be mistaken for a return. `data_status` is
published so a consumer can tell *withheld* from *missing* — without it,
suppression looks like an outage, and an outage invites a retry.

Logic lives in `app/core/series_provenance.py`, deliberately free of
framework imports so containment can be exercised without standing up the
app. `SUPPRESSED_FIELDS` is explicit rather than inferred from the response
model, so a numeric field added to `IndexPrice` defaults to **withheld**, not
served; a test asserts the two cannot drift.

## Before any replacement is mapped

Settle the intended index first — the three definitions above must be
reconciled to one. Then, for the candidate series, verify and record:

- **return type** — price, total return / accumulation, or net total return
- **currency** and whether it is hedged
- **dividend treatment** — gross or net of withholding; franking handling
- **date coverage** — history depth, and whether it spans the stored rows

Only then backfill and recalculate. Existing rows must not be silently
reinterpreted as accumulation observations; they are not.

## Rejected

**Relabelling `AXJO` as the price index.** It would be a duplicate of
`ASX200` under another name — a meaningless row that also quietly drops a
feature the Premium surface implies. Noted to rule it out.

## Related

The same code review confirmed that `index_prices` derives its expected
population from `TICKER_MAP` — the same defect as `fund_prices` with `FUNDS`.
That is **confirmed from code**; its connection to the index charts being
stale since 1 Oct is a **hypothesis** until runtime evidence establishes it.
It is tracked separately and is **not** addressed by this containment, which
withholds figures and changes no population logic.

Accounting and correctness are separate properties, and this finding is the
illustration: keying outcomes by entity code stops `ASX200` and `AXJO`
colliding in the tally. It does nothing about one of them being wrong.
