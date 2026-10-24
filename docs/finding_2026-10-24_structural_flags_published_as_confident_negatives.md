# A missing industry was published as a confident "not a REIT"

**Found** 24 October 2026, after the user asked why REIT and miner counts
looked low.
**Fixed in** v11.2.32 (producer) with the data repaired the same day.
**Blast radius** 805 companies published as confirmed non-REITs and
non-miners without any producer ever having assessed them; a further ~80
given a definite `False` from absent evidence; 10 miners whose industry
names the metal they mine recorded as not mining.

## What was served

`screener.universe` held 2,552 rows, **768 of them unclassified** — 30% of
the population. The API rendered every one as `Is REIT: No`.

Counts on the site read as totals over the whole universe:

```
Is REIT  = Yes  ->  37        over 1,784 assessed, shown as if over 2,552
Is Miner = Yes  -> 685
```

A random sample of the unclassified: Altitude Minerals, Gorilla Gold Mines,
Linq Minerals, Verity Resources — sector Materials, every one displayed as
"not a miner".

## Three defects, compounding

**1. Absence became a negative.** `transform_companies` derived the flags as

```python
"reit" in (sn(row.get("gic_industry")) or "").lower()
```

`sn()` returns `None` for a missing industry, `(None or "")` is the empty
string, and the answer is `False`. Not unknown — `False`.

**2. The producer read the thinner of two sources.** It took industry from
`staging_au.company_profile.gic_industry`, populated for 36 of the 327
unclassified operating companies. `staging_au.fundamentals.general_industry`
had it for 200. The data was present the whole time.

**3. The keyword list missed every metal-named industry.** `("mining",
"gold", "metals", "coal")` matches the activity and the category but not
`Copper` (6 companies), `Uranium` (3) or `Aluminum` (1).

Defects 1 and 2 compound: the producer looked in the thin source, then
turned the resulting absence into a confident negative. That is how ~80
rows came to hold `False` with no industry to justify it — and 24 of those
were miners.

**And a fourth, mine.** v11.2.27 made NULL booleans render as `False` to
stop a 500 on `/search`. That fixed the crash and entrenched the wrong
answer, turning "we never looked" into "we checked, and no".

## The verdict is three-valued, because the world is

```
True / False   an industry was known, and it matched or it did not
None           no industry was available          (failed to obtain)
None           an ETF, note or fund               (cannot apply)
```

439 of the 805 unclassified rows are ETFs. "Is this ETF a REIT" has no
answer; writing `False` invents one exactly as writing `True` would.

## What was repaired

Population taken from the source, not the target:

| | |
|---|---|
| operating, industry recoverable | **205** — classified |
| already classified, rule disagrees | **24** — corrected (23 miners, 1 REIT) |
| operating, sector only | 111 — left unknown |
| operating, nothing at all | 11 — left unknown |
| non-operating (ETF/note/fund) | 478 — not applicable |

The 111 were left alone deliberately. GICS `Materials` covers chemicals,
packaging and steel; `Real Estate` covers non-REIT developers. Classifying
from sector would manufacture a different set of wrong answers with more
confidence than the evidence carries.

Applied in one transaction, then propagated to `screener.universe` (229
rows) in a second, each verified against a measurement taken from the
source beforehand:

```
market.companies   unclassified 805 -> 600   miners 685 -> 821   reits 37 -> 40
screener.universe  unclassified 768 -> 563   miners 685 -> 821   reits 37 -> 40
```

No new SCD2 version was written. `is_reit` and `is_miner` are SCD2-tracked,
so changing one normally opens a version — but that is for a company that
*changed*. These rows were NULL because nobody classified them. A version
would assert that Gorilla Gold Mines became a miner on 24 October 2026,
which is false history written to make a repair look routine.

## What caught it

Not a test. The dry run printed the **evidence beside the verdict**, and one
row read `AMU  None -> False  Uranium`. A summary saying "205 classifiable"
would have passed review; the keyword gap was visible only because the plan
showed its reasoning.

The 24 confidently-wrong rows were found by re-deriving every
already-classified row and reporting disagreements — a check that exists
because filling NULLs cannot correct a row that is wrong with confidence.

## Still open

~563 universe rows remain genuinely unknown and **still render as "No"**.
Presentation is a separate release: unknown shown as unknown, filters
matching only known values, counts stating their coverage.

`mining_metrics` selects `WHERE is_miner = TRUE` at 10 EODHD calls per
company and now sees ~136 more.

## Rule

A guard, a producer or a repair that cannot say "I don't know" will say
something false instead, and it will say it with the same confidence as the
truth. Absence of evidence has to survive all the way to the customer:
through the producer that derives it, the table that stores it, the API that
serves it and the page that renders it. It was destroyed at every one of
those four layers here, and each layer looked correct on its own.
