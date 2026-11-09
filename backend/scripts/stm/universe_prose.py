"""Authored prose for the Gold -> Universe mapping document.

What is written here, and what is not
-------------------------------------
Everything in this file is a claim a person is making. The formula, the
source table and column, the join rule and the writer list are NOT here --
they are derived from the statement by the evidence scripts and emitted by
universe_sidecars.py, because copying them by hand creates a second version
of the statement that is free to disagree with the first.

Prose sits at SECTION level, which is where it is actually true. The columns
inside one of the builder's own SELECT sections share a source, a grain, a
unit, a freshness rule and an adjustment basis. Writing that out per column
would present one reviewed claim as forty.

`applicability` is the column where a known defect is declared. A section
reading `market.computed_metrics` carries finding 7a whether or not anyone
has looked at that particular column, because the defect is in the source.

Fields
------
transformation_rule  what the statement does to the source value
business_rule        what the number means, and the rule it must obey
grain                one row per WHAT
unit                 the unit of the stored value, stated explicitly
applicability        when the value is absent, stale, or must not be trusted
"""

# ── Cross-cutting notes, written once and referenced ─────────────────────────

_PRICE_BASIS = (
    "Prices are UNADJUSTED close. `adjusted_close` exists on the source and "
    "is not used here: it is a total-return series (dividends reinvested) "
    "and is separately known to be stale, so a return computed from it would "
    "mix a price return with a total return. A corporate action inside the "
    "window therefore moves this value for a reason that is not a price "
    "move; the daily engine withholds across detected actions and the "
    "coverage of that detection is finding 1c."
)

_FRESH_DAILY = (
    "Freshness: `market.daily_prices` is the pipeline's anchor and is "
    "measured, not declared -- the window starts three days behind the "
    "table's own Sydney-date watermark, not behind the clock. A missing "
    "trading day is a continuity failure, not a fresh table with a hole."
)

_CM_DEFECT = (
    "Source carries finding 7a: `market.computed_metrics` is written by a "
    "dynamically built UPDATE whose SET list varies per run, so a column "
    "omitted on a run KEEPS the previous run's value rather than being set "
    "NULL. A value read from `cm.` may therefore predate the run that "
    "published this row, and nothing in the row says so."
)

_YM_DEFECT = (
    "Source carries finding 6: of 188 columns on `market.yearly_metrics`, "
    "27 are never written and 37 hold frozen values produced by the "
    "superseded `_avg` helper -- proven by window-length inversions, where "
    "avg_roe_10y exceeds avg_roe_7y on the same company. Check a column "
    "against that census before relying on it."
)

_LATEST_FY = (
    "Period: the latest fiscal year the company has reported (`pnl0`, "
    "chosen by ORDER BY fiscal_year DESC LIMIT 1), NOT a fixed calendar "
    "year. Two companies in the same row of a screen may be reporting "
    "periods up to eleven months apart, and the period itself is not "
    "published on the row."
)

_GOVERNED = (
    "Governed column: the builder's value is PROVISIONAL. "
    "`compute/engine/universe_writer.py` overwrites it last, driven by the "
    "governed registry, and assigns every governed column on every canonical "
    "row including an explicit NULL -- so 'no value this run' replaces the "
    "previous run's number instead of leaving it in place. Precedence is "
    "therefore: builder INSERT, then engine updaters, then the canonical "
    "writer. Until the canonical writer commits, `metric_states` and "
    "`compute_run_id` are NULL and `app/core/row_projection.py` fails the "
    "row closed as OUTSIDE_SNAPSHOT rather than serving it."
)

_ANNUAL_PINNED = (
    "The prior-year lateral pins `fiscal_year = <base>.fiscal_year - N` by "
    "name rather than taking OFFSET N. OFFSET returned the previous ROW, so "
    "a company missing a year had its 'prior year' taken from two or more "
    "years back and the comparison spanned an interval nobody declared. If "
    "year N is absent the value is NULL -- unknown, not zero."
)


SECTION_PROSE: dict[str, dict] = {

    # ── Identity ────────────────────────────────────────────────────────────
    "Identity": {
        "transformation_rule":
            "Carried unchanged from the conformed company record. The only "
            "renames are GICS: gics_sector -> sector, gics_industry_group -> "
            "industry_group, gics_industry -> industry, gics_sub_industry -> "
            "sub_industry, company_type -> stock_type.",
        "business_rule":
            "Identity and classification as of the CURRENT company record. "
            "`market.companies` is SCD Type 2 and `companies_current` is the "
            "is_current slice, so this row describes the company as it is "
            "now, not as it was when a historical figure beside it was "
            "reported. A reclassification rewrites the sector on every "
            "historical metric's row without restating the metric.",
        "grain": "one row per asx_code",
        "unit": "n/a (identifiers and classification labels)",
        "applicability":
            "Uniqueness is enforced by a UNIQUE PARTIAL index on "
            "market.companies(asx_code) WHERE is_current = true, not by the "
            "view definition. The index is what makes one row per company "
            "true; without it the driving relation could return two current "
            "rows and every figure on this row would come from whichever the "
            "planner emitted last. The six index membership flags are "
            "refreshed afterwards by compute/engine/asx_indices.py, so the "
            "builder's value for them is provisional.",
    },

    # ── Market cap tiers ────────────────────────────────────────────────────
    "Market cap tier flags (derived from vs.market_cap, raw AUD)": {
        "transformation_rule":
            "Six disjoint half-open bands over vs.market_cap in raw AUD -- "
            "mega >= 50e9, large [10e9, 50e9), mid [2e9, 10e9), small "
            "[300e6, 2e9), micro [50e6, 300e6), nano (0, 50e6). "
            "market_cap_tier is the same cut as a label.",
        "business_rule":
            "Bands are on market capitalisation in AUD, taken from "
            "market.valuation_snapshot and NOT rescaled. The `_bn` columns on "
            "the snapshot aggregates are a different quantity and carry "
            "finding 4 -- do not reconcile these bands against them.",
        "grain": "one row per asx_code",
        "unit":
            "booleans; market_cap_tier is one of mega/large/mid/small/micro/"
            "nano or NULL",
        "applicability":
            "FINDING 12. The six flags are COALESCE(..., FALSE) on columns "
            "declared NOT NULL DEFAULT false, so an unknown market cap is "
            "written as a measured false on all six, while market_cap_tier "
            "beside them returns NULL. Measured 10 Nov 2026: 641 of 2,566 "
            "rows (25.0%) carry six falses and a NULL tier. All three "
            "consumers test `= TRUE`, so no company is reported in a tier it "
            "is not in -- instead a quarter of the universe is invisible to "
            "every tier filter and nothing says so. Read market_cap_tier, "
            "which carries the distinction; never write `NOT is_mega`.",
    },

    "Admin tags (from market.companies)": {
        "transformation_rule":
            "Carried unchanged from the current company record via its own "
            "lateral, which repeats the is_current predicate rather than "
            "reusing the driving alias.",
        "business_rule":
            "Hand-maintained editorial tags, not derived from any feed. They "
            "are as current as the last person to edit them and carry no "
            "computation date.",
        "grain": "one row per asx_code",
        "unit": "n/a (free-text tags)",
        "applicability":
            "NULL means no tag has been set, which is the same value an "
            "incorrect-but-unset tag would have. Absence here is not "
            "evidence about the company.",
    },

    # ── Price ───────────────────────────────────────────────────────────────
    "Price (latest close + 52w range)": {
        "transformation_rule":
            "Latest daily bar carried through unchanged; avg_volume_20d and "
            "the 52-week high/low come from their own laterals over the "
            "daily series; market_cap is carried from the valuation "
            "snapshot.",
        "business_rule":
            _PRICE_BASIS + " " + _FRESH_DAILY,
        "grain": "one row per asx_code, values as at the latest trading day",
        "unit": "AUD for prices; share count for volume; raw AUD for market_cap",
        "applicability":
            "price_date is the authority for how current the price is and is "
            "published on the row -- read it rather than assuming today. "
            "high_52w and low_52w are governed. " + _GOVERNED,
    },

    "Volatility & risk": {
        "transformation_rule":
            "Carried from the daily engine's own windows; no rescaling here.",
        "business_rule":
            "Realised volatility over trailing daily windows, and a Sharpe "
            "ratio over one year. " + _PRICE_BASIS,
        "grain": "one row per asx_code, as at the latest trading day",
        "unit": "decimal ratios, not percentages",
        "applicability":
            "NULL when the daily series is shorter than the window. The "
            "daily engine writes NULL rather than a value computed from a "
            "short series -- that is the behaviour finding 10 records "
            "market.weekly_metrics as NOT having.",
    },

    "Technicals: the daily source, or nothing": {
        "transformation_rule":
            "Carried from market.daily_metrics unchanged. The section name "
            "is the rule: there is no fallback to a slower cadence.",
        "business_rule":
            "Indicators are computed on DAILY bars and their periods mean "
            "days. The weekly/monthly fallback that once backed this section "
            "was removed: suppressing a stale daily row PROMOTED the weekly "
            "value past four source guards, and a 14-month rsi_14 was served "
            "as a 14-day one. Two INSERT-side comments in the builder "
            "(around lines 149 and 534) still advertise that removed "
            "fallback and are stale -- the statement is the authority.",
        "grain": "one row per asx_code, as at the latest trading day",
        "unit":
            "AUD for price-level indicators (SMA, EMA, Bollinger, ATR, "
            "MACD); index points 0-100 for RSI and ADX; share count for OBV",
        "applicability":
            "NULL when the daily series is too short for the window, and "
            "NULL is the honest answer -- do not read it as a neutral "
            "reading. " + _PRICE_BASIS,
    },

    "Volume signals (daily_metrics)": {
        "transformation_rule":
            "Carried from the daily engine unchanged.",
        "business_rule":
            "Turnover and accumulation measures over trailing daily windows.",
        "grain": "one row per asx_code, as at the latest trading day",
        "unit":
            "share counts for volumes; ratios for relative measures; "
            "dollar_volume_avg_20d is stated in AUD MILLIONS by its own "
            "column comment, unlike every other AUD figure in this table",
        "applicability":
            "`adl` is one of the ten columns NO statement writes (finding "
            "11) and is NULL on every row -- it is listed in this section by "
            "subject, not by the statement.",
    },

    "Tier 2: daily signals (from daily_metrics)": {
        "transformation_rule":
            "Boolean crossings and ratios carried from the daily engine, "
            "with two computed inline against the latest close.",
        "business_rule":
            "Crossing and threshold signals on daily bars. " + _PRICE_BASIS,
        "grain": "one row per asx_code, as at the latest trading day",
        "unit": "booleans and decimal ratios",
        "applicability":
            "A boolean here is NULL when it could not be computed, which is "
            "the behaviour market.weekly_metrics does not share -- finding "
            "10. Do not compare a daily signal's false against a weekly "
            "signal's false and treat them as the same claim.",
    },

    # ── Returns ─────────────────────────────────────────────────────────────
    "Returns (daily -> weekly/monthly fallback)": {
        "transformation_rule":
            "Carried from market.daily_metrics, which computes each horizon "
            "against a CALENDAR offset with a 14-day grace window, not "
            "against a bar count.",
        "business_rule":
            "Price return over the named horizon. The section's name is "
            "STALE: the weekly fallback it mentions was removed, and the "
            "monthly source still joined here supplies momentum_* rather "
            "than these columns. " + _PRICE_BASIS,
        "grain": "one row per asx_code, as at the latest trading day",
        "unit": "decimal ratios (0.05 = +5%), not percentages",
        "applicability":
            "NULL when no bar exists within the grace window of the offset "
            "date, and withheld across a detected corporate action. Most of "
            "these are governed. " + _GOVERNED,
    },

    "Multi-year returns, from daily_metrics as of v11.2.63": {
        "transformation_rule":
            "Carried from market.daily_metrics. Moved into this statement by "
            "v11.2.63, which is the edit that can shift an INSERT's "
            "positional alignment -- test_universe_insert_alignment exists "
            "for exactly that and asserts both list lengths.",
        "business_rule":
            "Price return over multi-year horizons, same calendar-offset "
            "rule as the short horizons. " + _PRICE_BASIS +
            " Over horizons this long the unadjusted basis matters more, not "
            "less: a split or consolidation anywhere in the window moves the "
            "number by its own factor.",
        "grain": "one row per asx_code, as at the latest trading day",
        "unit": "decimal ratios, not percentages",
        "applicability":
            "NULL when the series does not reach back to the offset date. A "
            "company listed three years ago has NULL for return_10y, which "
            "is unknown and must not be read as zero or as underperformance.",
    },

    # ── Valuation ───────────────────────────────────────────────────────────
    "Valuation ratios": {
        "transformation_rule":
            "Mostly carried from market.valuation_snapshot; several are "
            "computed inline against the latest close with a CASE guarding "
            "the denominator, and three use a COALESCE fallback chain whose "
            "ORDER is the precedence: the first non-NULL source wins and the "
            "row does not record which one answered.",
        "business_rule":
            "A market quantity over a statement quantity. Both sides must "
            "be in the same currency for the ratio to mean anything, which "
            "is what reporting_currency gates. " + _LATEST_FY,
        "grain": "one row per asx_code",
        "unit": "multiples (x), dimensionless",
        "applicability":
            "APPLICABILITY GATE 1b: when reporting_currency is set and is "
            "not AUD, pe_ratio, price_to_book, price_to_sales, peg_ratio, "
            "ev_to_ebitda, ev_to_ebit, altman_z_score and "
            "book_value_per_share are NOT_MEANINGFUL with cause "
            "unit_mismatch -- an AUD market price over a foreign-currency "
            "statement figure. Ratios of two statement figures are "
            "unaffected because their units cancel. " + _GOVERNED + " " +
            _CM_DEFECT,
    },

    "Dividends": {
        "transformation_rule":
            "Carried from market.computed_metrics, with the latest dividend "
            "event from its own lateral. grossed_up_yield is bounded by a "
            "CASE that discards values of 100 or more.",
        "business_rule":
            "Trailing-twelve-month dividends per share, the franking "
            "percentage, and the grossed-up yield that franking produces. "
            "The grossed-up figure is the reason this product exists and is "
            "the one a user compares across companies.",
        "grain":
            "one row per asx_code; the dividend event columns describe the "
            "LATEST event only, not the trailing year",
        "unit":
            "AUD per share for dps_ttm; decimal ratios for the yields; "
            "percent (0-100) for franking_pct",
        "applicability":
            "The ABS(...) < 100 bound on grossed_up_yield silently discards "
            "an out-of-range value rather than recording that it was "
            "rejected, so a discarded value and an absent one are "
            "indistinguishable. franking_credit_per_share is one of the ten "
            "columns no statement writes (finding 11) and is NULL on every "
            "row. " + _GOVERNED + " " + _CM_DEFECT,
    },

    "Per-share & working capital": {
        "transformation_rule":
            "Computed inline, each guarded by a CASE on its denominator. "
            "The per-share columns convert an AUD-millions statement figure "
            "to AUD per share: value * 1e6 / shares_outstanding.",
        "business_rule":
            "Per-share figures use the CURRENT share count against a "
            "fiscal-year flow. A capital raising between the balance date "
            "and today therefore dilutes a historical flow by a count that "
            "did not exist during it. " + _LATEST_FY,
        "grain": "one row per asx_code",
        "unit":
            "AUD per share for the per-share columns; AUD MILLIONS for "
            "working_capital, per its column comment",
        "applicability":
            "NULL when the share count is absent or not positive. "
            "price_to_52w_high belongs to this migration batch (052) and is "
            "FINDING 11: it is in neither the INSERT nor the ON CONFLICT SET "
            "list, so an existing row's value is never touched by any run. "
            "Measured 10 Nov 2026: frozen on 2,290 of 2,566 rows and served "
            "through a registered filter, a sort column and a response "
            "field. The other five columns of that batch are wired "
            "correctly.",
    },

    # ── Fundamentals ────────────────────────────────────────────────────────
    "Profitability TTM": {
        "transformation_rule":
            "Carried from market.valuation_snapshot and "
            "market.computed_metrics, with COALESCE chains falling back to "
            "market.yearly_metrics. The chain order IS the precedence and "
            "the row does not record which source answered.",
        "business_rule":
            "Trailing-twelve-month margins and returns on capital. A margin "
            "is a ratio of two statement figures, so it survives a non-AUD "
            "reporting currency where a price-based ratio does not.",
        "grain": "one row per asx_code, trailing twelve months",
        "unit":
            "decimal ratios for margins and returns; raw AUD for the "
            "absolute TTM figures",
        "applicability":
            _GOVERNED + " " + _CM_DEFECT + " " + _YM_DEFECT,
    },

    "EPS": {
        "transformation_rule":
            "COALESCE(pnl0.eps, ym.eps) for FY0 -- the reported statement "
            "first, the computed yearly metric second. FY1 reads the pinned "
            "prior-year lateral with no fallback.",
        "business_rule":
            "Earnings per share as reported for the fiscal year. " +
            _LATEST_FY,
        "grain": "one row per asx_code per fiscal year (FY0 and FY1 columns)",
        "unit": "AUD per share",
        "applicability":
            "The fallback means an FY0 value may come from either source "
            "and the row does not say which, so a reconciliation against the "
            "statements will not always match. " + _ANNUAL_PINNED,
    },

    "Income Statement FY0 / FY1": {
        "transformation_rule":
            "Carried from the annual profit-and-loss statement for the "
            "latest fiscal year and the pinned prior one.",
        "business_rule":
            "As-reported annual figures. " + _LATEST_FY,
        "grain": "one row per asx_code per fiscal year",
        "unit": "AUD millions",
        "applicability":
            _ANNUAL_PINNED + " A disclosed zero is a value and must not be "
            "written NULL -- that conflation was v11.2.74 and cost 357 "
            "companies their Piotroski score.",
    },

    "Balance Sheet": {
        "transformation_rule":
            "Carried from the annual balance sheet, with two computed "
            "inline under a CASE guarding the denominator.",
        "business_rule":
            "Position as at the fiscal-year balance date, not as at today. "
            + _LATEST_FY,
        "grain": "one row per asx_code as at the latest balance date",
        "unit":
            "AUD millions for levels; decimal ratios for debt_to_equity and "
            "current_ratio; AUD per share for book_value_per_share",
        "applicability": _GOVERNED + " " + _YM_DEFECT,
    },

    "Cash Flow": {
        "transformation_rule":
            "Carried from the annual cash flow statement for the latest "
            "fiscal year.",
        "business_rule":
            "Flows over the fiscal year, not trailing twelve months. " +
            _LATEST_FY,
        "grain": "one row per asx_code per fiscal year",
        "unit": "AUD millions",
        "applicability":
            "capex sign convention follows the source statement and is not "
            "normalised here, so fcf = cfo + capex rather than cfo - capex "
            "wherever capex is reported negative. " + _GOVERNED,
    },

    "Income statement history (annual levels, AUD millions)": {
        "transformation_rule":
            "One pinned lateral per historical year (FY1, FY3, FY5, FY7, "
            "FY10), each selecting by name rather than by row offset.",
        "business_rule":
            "A time series of as-reported annual levels, for the user to "
            "compute growth over any pair. " + _LATEST_FY,
        "grain": "one row per asx_code per named fiscal year",
        "unit": "AUD millions",
        "applicability":
            _ANNUAL_PINNED + " A company that did not report in a named year "
            "has NULL for that year and NULL for every growth rate derived "
            "from it. The gap does not shift the series.",
    },

    "Income-statement & balance-sheet line items (annual, AUD millions)": {
        "transformation_rule":
            "Carried from the three annual statements for the latest fiscal "
            "year.",
        "business_rule":
            "As-reported line items, the inputs the derived ratios below are "
            "built from. " + _LATEST_FY,
        "grain": "one row per asx_code as at the latest fiscal year",
        "unit": "AUD millions",
        "applicability":
            "A line item absent from a company's statement is NULL. For "
            "totalAssets specifically, a reported zero is real: it occurred "
            "19 times in 33,201 company-years, which is why the "
            "'providers send 0 for missing' defence was false.",
    },

    "Derived ratios (from the line items above)": {
        "transformation_rule":
            "Computed inline from the line items, every one guarded by a "
            "CASE on its denominator so a zero or absent denominator yields "
            "NULL rather than an error or an infinity.",
        "business_rule":
            "Ratios of two statement figures, so they are meaningful "
            "regardless of reporting currency -- the units cancel. " +
            _LATEST_FY,
        "grain": "one row per asx_code as at the latest fiscal year",
        "unit":
            "decimal ratios, except the turnover and days measures, which "
            "are times-per-year and days respectively",
        "applicability":
            "A guarded NULL and a genuinely absent input are "
            "indistinguishable in the stored value. " + _GOVERNED,
    },

    # ── Growth ──────────────────────────────────────────────────────────────
    "Growth rates": {
        "transformation_rule":
            "Carried from market.computed_metrics with a COALESCE fallback "
            "to market.yearly_metrics; the chain order is the precedence.",
        "business_rule":
            "Year-on-year and compound annual growth over the named window.",
        "grain": "one row per asx_code",
        "unit": "decimal ratios (0.05 = +5% per year), not percentages",
        "applicability":
            "A CAGR requires both endpoints positive -- a loss-making base "
            "year has no meaningful compound rate and yields NULL, which is "
            "unknown and not zero growth. " + _GOVERNED + " " + _CM_DEFECT,
    },

    "Growth rates (decimal ratios; YoY = (end-base)/|base|, CAGR needs both > 0)": {
        "transformation_rule":
            "Computed inline from the pinned historical laterals. YoY is "
            "(end - base) / ABS(base), which keeps the sign correct when "
            "the base is negative; CASE requires both endpoints positive "
            "before computing a CAGR.",
        "business_rule":
            "Growth between two NAMED fiscal years, so the interval is "
            "always the one the column name states.",
        "grain": "one row per asx_code over a named pair of fiscal years",
        "unit": "decimal ratios, not percentages",
        "applicability":
            "NULL when either endpoint is missing or a CAGR's endpoints are "
            "not both positive. " + _ANNUAL_PINNED,
    },

    "Multi-year quality & CAGR (from yearly_metrics - latest FY)": {
        "transformation_rule":
            "Carried from market.yearly_metrics at the latest fiscal year, "
            "unchanged.",
        "business_rule":
            "Multi-year averages and compound rates. The averaging contract "
            "is exact: an n-year average requires exactly n NAMED fiscal "
            "years and is NULL otherwise -- it does not average whatever "
            "years happen to be present. " + _LATEST_FY,
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "decimal ratios, not percentages",
        "applicability":
            "This is the section most exposed to finding 6. " + _YM_DEFECT +
            " Thirty of these thirty-three columns are governed, so the "
            "canonical writer's value is what a customer reads. " + _GOVERNED,
    },

    "Latest-quarter YoY growth (from quarterly_metrics)": {
        "transformation_rule":
            "Carried from the latest quarterly row.",
        "business_rule":
            "Growth against the SAME quarter one year earlier, which is the "
            "comparison that removes seasonality.",
        "grain": "one row per asx_code, latest reported quarter",
        "unit": "decimal ratios, not percentages",
        "applicability":
            "market.quarterly_metrics has overlapping writers and its "
            "insert ownership, update precedence and the meaning of each "
            "timestamp are not yet documented; `computed_at IS NULL` alone "
            "must not be read as invalidating a reported figure. Whether "
            "EODHD quarterly figures are standalone-period or cumulative "
            "year-to-date amounts is NOT established, and summing or "
            "differencing them depends on that answer.",
    },

    "Half-yearly HoH growth (from halfyearly_metrics - latest half)": {
        "transformation_rule":
            "Carried from the latest half-yearly row, chosen by ORDER BY "
            "period_end_date DESC LIMIT 1.",
        "business_rule":
            "Growth of a half against the preceding half.",
        "grain": "one row per asx_code, latest reported half",
        "unit": "decimal ratios, not percentages",
        "applicability":
            "FINDING 9. The half is assigned by ROW POSITION within a "
            "calendar-year grouping rather than derived from the quarter "
            "number or the period end date. Measured: 1,827 of 32,263 "
            "company-years (5.7%) are misassigned, the largest case being a "
            "single December period labelled H1 -- 1,110 company-years "
            "across 1,024 companies. For a misassigned row both lookups "
            "mis-pair, so 'half-on-half' spans twelve months and "
            "'year-on-year' eighteen. HoH is populated on 43,832 of 63,289 "
            "source rows, so these values are SERVED rather than withheld. "
            "Do not rely on this section for screening until the grouping "
            "is corrected and recomputed.",
    },

    # ── Signals ─────────────────────────────────────────────────────────────
    "Quick-win metrics (from yearly_metrics + daily_metrics)": {
        "transformation_rule":
            "Carried from market.yearly_metrics at the latest fiscal year "
            "and from the latest daily row.",
        "business_rule":
            "Cash-conversion and dilution measures that need no new source. "
            + _LATEST_FY,
        "grain":
            "one row per asx_code; MIXED as-at dates -- the yearly columns "
            "are as at the balance date, the daily ones as at the last "
            "trading day",
        "unit": "decimal ratios; counts for the year counters",
        "applicability": _YM_DEFECT,
    },

    "Partial metrics": {
        "transformation_rule":
            "Carried from the daily and yearly sources unchanged.",
        "business_rule":
            "Measures whose inputs are present for only part of the "
            "universe.",
        "grain": "one row per asx_code",
        "unit": "decimal ratios",
        "applicability":
            "`beta_1y` is sourced from ym.beta_1y and is dead end to end: "
            "measured at 0 of 33,864 rows in market.yearly_metrics, whose "
            "writer carries a `# TODO: compute in yearly_metrics`. It is "
            "nonetheless an EXPOSED screener filter labelled 'Beta (1Y)' "
            "under Technicals, so the filter is inert -- it matches nothing "
            "and reports no error. " + _YM_DEFECT,
    },

    "Quick wins": {
        "transformation_rule":
            "Computed inline from the annual statements and the valuation "
            "snapshot, guarded by a CASE.",
        "business_rule": "Simple derived measures. " + _LATEST_FY,
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "decimal ratios",
        "applicability": "NULL when a denominator is absent or not positive.",
    },

    "Profit-based signals": {
        "transformation_rule":
            "Boolean comparisons computed inline, each under a CASE that "
            "yields NULL when either side is missing.",
        "business_rule":
            "Directional claims about profit quality -- margins expanding, "
            "earnings beating revenue growth. " + _LATEST_FY,
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "booleans, and decimal ratios for the magnitudes",
        "applicability":
            "A NULL here is unknown, not false, and the CASE structure "
            "preserves that -- unlike market.weekly_metrics (finding 10), "
            "where the same situation is written FALSE. " + _GOVERNED + " " +
            _YM_DEFECT,
    },

    "Sales-based signals": {
        "transformation_rule":
            "Computed inline with COALESCE fallbacks across "
            "market.computed_metrics, market.yearly_metrics and the annual "
            "statements; the chain order is the precedence.",
        "business_rule":
            "Directional claims about revenue growth and its consistency.",
        "grain": "one row per asx_code",
        "unit": "booleans; counts for the consistency measures",
        "applicability": _CM_DEFECT + " " + _YM_DEFECT,
    },

    "Balance sheet signals": {
        "transformation_rule":
            "Computed inline from the annual statements, each guarded by a "
            "CASE, several with COALESCE fallbacks whose order is the "
            "precedence.",
        "business_rule":
            "Directional claims about solvency and working-capital "
            "discipline, several comparing a flow's growth against a "
            "balance's. " + _LATEST_FY,
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "booleans, and decimal ratios for the magnitudes",
        "applicability":
            "The growth comparisons use the PINNED prior year, so they "
            "always span one fiscal year. " + _ANNUAL_PINNED + " " +
            _CM_DEFECT,
    },

    "Tier-1 qualitative proxies": {
        "transformation_rule":
            "Carried from market.yearly_metrics unchanged.",
        "business_rule":
            "Ordinal 0-3 proxy scores for pricing power, scalability and "
            "earnings predictability. They are PROXIES: each is a count of "
            "satisfied conditions, not a measurement of the quality it is "
            "named for.",
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "ordinal score 0-3",
        "applicability":
            "A score of 0 means no condition was satisfied, which is not "
            "the same as the inputs being absent -- and the stored value "
            "does not distinguish them. " + _YM_DEFECT,
    },

    "Ratio framework signals": {
        "transformation_rule":
            "Computed inline from the annual statements under CASE guards, "
            "with COALESCE fallbacks to the computed and yearly sources.",
        "business_rule":
            "Composite ratio measures -- earning power, financial leverage, "
            "the cash conversion cycle. " + _LATEST_FY,
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "decimal ratios; days for the cycle measures",
        "applicability": _CM_DEFECT + " " + _YM_DEFECT,
    },

    "Cash flow signals": {
        "transformation_rule":
            "Computed inline from the annual cash flow statement against "
            "the pinned prior year, under CASE guards.",
        "business_rule":
            "Directional claims about operating cash flow and its "
            "relationship to reported earnings. " + _LATEST_FY,
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "booleans, and decimal ratios for the magnitudes",
        "applicability":
            "'OCF growing' means this fiscal year against the pinned prior "
            "one. If year-1 is absent the signal is NULL -- unknown, not "
            "false. " + _ANNUAL_PINNED,
    },

    "Quality proxy scores (from yearly_metrics)": {
        "transformation_rule":
            "Carried from market.yearly_metrics unchanged.",
        "business_rule":
            "Ordinal composite scores over multi-year quality inputs.",
        "grain": "one row per asx_code at the latest fiscal year",
        "unit": "ordinal scores",
        "applicability": _YM_DEFECT,
    },

    "Tier 3: EODHD data previously unused": {
        "transformation_rule":
            "Several sources joined by their own laterals, three computed "
            "inline under a CASE.",
        "business_rule":
            "Fields the feed already supplied and the product did not "
            "previously read -- earnings surprise history, listing age, "
            "reporting currency.",
        "grain": "one row per asx_code",
        "unit": "mixed; stated per column by the column comment where set",
        "applicability":
            "reporting_currency is the input to applicability gate 1b and "
            "therefore decides whether eight valuation ratios are "
            "NOT_MEANINGFUL. Its lateral takes LIMIT 1 with no ORDER BY, "
            "which is deterministic ONLY because staging_au.fundamentals "
            "carries UNIQUE (asx_code) -- that constraint is load-bearing "
            "for the gate.",
    },

    # ── Market structure ────────────────────────────────────────────────────
    "Analyst": {
        "transformation_rule":
            "Carried from market.analyst_ratings via a plain LEFT JOIN on "
            "its primary key.",
        "business_rule":
            "Consensus recommendation counts and target price as last "
            "supplied by the feed. These are opinions, not measurements, and "
            "carry no as-at date on this row.",
        "grain": "one row per asx_code",
        "unit": "counts; AUD for the target price; 1-5 scale for the rating",
        "applicability":
            "`analyst_upside` is one of the ten columns no statement writes "
            "(finding 11) and is NULL on every row; `analyst_upside_pct`, "
            "computed inline from ar.target_price and the latest close, is "
            "the one that carries a value. Absence of coverage and absence "
            "of a feed update are indistinguishable here.",
    },

    "Analyst-derived (computed from existing buy/sell/hold counts)": {
        "transformation_rule":
            "Computed inline from the five recommendation counts, with "
            "COALESCE(count, 0) on each so a missing count contributes zero "
            "to the total, and a CASE guarding division by a zero total.",
        "business_rule":
            "analyst_count is the sum of the five buckets; analyst_buy_pct "
            "is the buy and strong-buy share of it; analyst_consensus_score "
            "is (SB*2 + B - S - SS*2) / total, bounded -2 to +2.",
        "grain": "one row per asx_code",
        "unit":
            "count; fraction 0-1 for buy_pct; score -2 to +2 for consensus",
        "applicability":
            "COALESCE(count, 0) makes a company with NO analyst coverage "
            "indistinguishable from one whose five counts are genuinely "
            "zero: both give analyst_count = 0. The CASE on the total means "
            "the derived ratios are NULL rather than zero in that case, "
            "which IS the honest answer -- read analyst_buy_pct, not "
            "analyst_count, to tell coverage from consensus.",
    },

    "Short interest (ASIC - latest report date per stock)": {
        "transformation_rule":
            "Latest ASIC report per stock, by its own lateral ordered on "
            "the report date.",
        "business_rule":
            "Short positions as at the LATEST ASIC report date, which lags "
            "the trading day by several business days and is not the price "
            "date on the same row. The two as-at dates on this row differ.",
        "grain": "one row per asx_code at the latest ASIC report date",
        "unit": "percent of issued capital; share count for the position",
        "applicability":
            "short_pct and short_interest_chg_1w are refreshed afterwards by "
            "compute/engine/short_positions.py, so the builder's values are "
            "provisional. The report date itself is NOT carried onto this "
            "row, so a consumer cannot tell how old the figure is.",
    },

    "Shares & Ownership": {
        "transformation_rule":
            "Carried from staging_au.shares_stats via a lateral whose "
            "LIMIT 1 is determined by UNIQUE (asx_code) on that table.",
        "business_rule":
            "Current share count and ownership concentration as last "
            "supplied by the feed. shares_outstanding is the denominator "
            "every per-share figure on this row divides by.",
        "grain": "one row per asx_code",
        "unit": "share count; percent for the ownership shares",
        "applicability":
            "This is Bronze read directly by the Universe builder, "
            "bypassing Silver -- the only such read in the statement apart "
            "from company_profile and fundamentals. `shares_float` is one of "
            "the ten columns no statement writes (finding 11) and is NULL "
            "on every row. Dilution history is written afterwards by "
            "compute/engine/dilution_metrics.py.",
    },

    "Tier 2: ASX announcements signals (market.asx_announcements)": {
        "transformation_rule":
            "Aggregated inline by laterals with no GROUP BY, so each "
            "returns exactly one row per company -- including a zero count "
            "where there are no announcements.",
        "business_rule":
            "Counts of announcement types over the trailing year, and the "
            "age of the most recent announcement.",
        "grain": "one row per asx_code over a trailing one-year window",
        "unit": "counts; days for days_since_last_announcement",
        "applicability":
            "An aggregate with no GROUP BY returns 0, not NULL, for a "
            "company with no announcements -- so zero here means 'none "
            "found', which conflates a quiet company with one whose "
            "announcements were never ingested. market.capital_raises "
            "carries finding 3: its writer uses ON CONFLICT DO NOTHING, so "
            "a correction to an already-ingested raise never lands.",
    },
}


# ── Per-column additions, where a column differs from its section ───────────
#
# Only columns that genuinely carry their own rule appear here. A column
# absent from this dict is fully described by its section, and saying so
# once is the honest form.

COLUMN_PROSE: dict[str, dict] = {

    "asx_code": {
        "business_rule":
            "The ASX ticker, and the primary key of this table. One row per "
            "code is guaranteed structurally: the driving relation is unique "
            "on it, both plain joins are ON the other side's primary key, 25 "
            "laterals take LIMIT 1 and 5 aggregate without GROUP BY, so no "
            "source can fan the row out.",
        "applicability":
            "The only column in the INSERT that is NOT reassigned on "
            "conflict, because it is the conflict key.",
    },

    "price_date": {
        "business_rule":
            "The trading date the price columns are as at. This is the "
            "as-at date a consumer should read; the row carries several "
            "others implicitly -- the fiscal balance date for the statement "
            "columns, the ASIC report date for short interest -- and none of "
            "those is published.",
    },

    "market_cap": {
        "business_rule":
            "Market capitalisation in RAW AUD. The tier bands above are cut "
            "on this column in raw AUD. Do not reconcile it against the "
            "`_bn` columns on the snapshot aggregates: those carry finding "
            "4 and hold thousands, not billions.",
        "unit": "raw AUD",
    },

    "reporting_currency": {
        "business_rule":
            "Carried from staging_au.fundamentals. This column is not a "
            "metric -- it is the INPUT to applicability gate 1b, which marks "
            "eight valuation ratios NOT_MEANINGFUL with cause unit_mismatch "
            "when it is set and is not AUD.",
        "applicability":
            "NULL means the currency is unknown, and the gate does not fire "
            "on unknown -- so a company whose currency never arrived has its "
            "ratios published as if they were AUD-on-AUD. The gate is "
            "written to fire only on a KNOWN non-AUD currency.",
    },

    "annual_periods": {
        "business_rule":
            "Consecutive annual reporting periods ending at FY0, counted "
            "over the same row set the averaging series is drawn from. An "
            "observation for applicability gate 2, not a metric anyone "
            "screens on.",
        "unit": "count of fiscal years",
        "applicability":
            "NULL means unknown -- no FY0 anchor -- and is NOT zero. The "
            "distinction decides whether an n-year average is withheld for "
            "insufficient history or was never assessed.",
    },

    "window_states": {
        "business_rule":
            "Carried from market.daily_metrics.metric_states as PROVISIONAL "
            "input, with the same standing as return_1y beside it. It is "
            "deliberately NOT written to metric_states: the builder assesses "
            "nothing and may revoke a canonical claim but never make one. "
            "The canonical writer reads this column, rebuilds each window "
            "assessment from it, and emits the real sidecar.",
        "unit": "jsonb: metric -> {state, cause, reason}",
        "applicability":
            "NULL means never assessed; '{}' means assessed and clean. The "
            "two are different states and a consumer must not treat NULL as "
            "empty.",
    },

    "revenue_above_sector_median": {
        "transformation_rule":
            "NOT part of the INSERT's SELECT. Written by a second UPDATE in "
            "the same job and the same transaction, comparing each "
            "company's revenue_growth_3y_cagr against the median for its "
            "sector computed over this table.",
        "business_rule":
            "A relative claim, so it depends on which companies are in the "
            "universe at the moment it runs -- the same company can flip "
            "without its own numbers changing.",
        "applicability":
            "Inside the rebuild's transaction because it writes a governed "
            "column; committed separately it would be a governed mutation "
            "outside the atomic boundary. Companies with a NULL CAGR are "
            "excluded from the median and get NULL, not false.",
    },

    "dollar_volume_avg_20d": {
        "unit":
            "AUD MILLIONS, per its column comment -- unlike market_cap and "
            "the statement figures beside it. Check the unit before "
            "comparing it with any other AUD column on this row.",
    },

    "beta_1y": {
        "applicability":
            "DEAD END TO END, and exposed. Sourced from ym.beta_1y, which "
            "is measured at 0 of 33,864 rows; its writer carries a "
            "`# TODO: compute in yearly_metrics`. It is a registered "
            "screener filter labelled 'Beta (1Y)' under Technicals, so a "
            "user can select it and it matches nothing, with no error and "
            "no indication that the column is unpopulated.",
    },

    "momentum_3m": {
        "transformation_rule":
            "A literal copy of market.monthly_metrics.return_3m -- three "
            "monthly bars, with no grace window and no corporate-action "
            "withholding.",
        "business_rule":
            "ALIAS WARNING: this is not the same quantity as return_3m "
            "beside it, despite both being exposed screener fields over a "
            "three-month horizon. return_3m comes from the daily engine, "
            "uses a calendar offset with a 14-day grace window, and is "
            "withheld across a detected corporate action. momentum_3m "
            "counts bars. The two can disagree for the same company on the "
            "same day.",
        "applicability":
            "NOT double-counted, checked. The momentum factor is declared "
            "in compute/engine/factor_model.py as return_1m, return_3m, "
            "return_6m, rsi_14 and adx_14 -- the return_* family only. No "
            "momentum_* column is a constituent of any factor in V1, V2 or "
            "V3, so no score or ranking combines the two spellings and the "
            "alias is a presentation duplicate rather than a weighting "
            "defect. Both ARE exposed as screener fields, so a user can "
            "still filter on both and believe they have applied two "
            "independent conditions.",
    },

    "momentum_6m": {
        "business_rule":
            "ALIAS WARNING: see momentum_3m. Bar-counted from the monthly "
            "engine, against return_6m's calendar offset from the daily one.",
    },

    "momentum_12m": {
        "business_rule":
            "ALIAS WARNING: see momentum_3m. Bar-counted from the monthly "
            "engine, against return_1y's calendar offset from the daily one.",
    },
}
