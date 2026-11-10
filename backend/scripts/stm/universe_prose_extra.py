"""Prose for the 60 columns the builder's INSERT does not write.

Three populations, and they fail in three different ways:

  25  written ONLY by an UPDATE-in-place engine module. The row exists
      before they do, so each is NULL between the builder's commit and that
      module's. If the module does not run, the column keeps the PREVIOUS
      run's value and nothing on the row says so.

  10  written by nothing at all (finding 11). Nine are NULL on every row.
      price_to_52w_high is not: it is frozen on 2,290 of 2,566 rows and
      served through a registered filter, a sort column and a response
      field, which is worse than empty because empty is visible.

  25  the compute-run lifecycle tables, which are not metrics. They are the
      evidence that decides whether a universe row may be served at all.

Everything here is authored because there is no expression to derive it
from. `derivation_formula` carries the module and statement that writes it,
which is the nearest thing to a formula these columns have.
"""

_UPDATE_ONLY = (
    "UPDATE-IN-PLACE. The builder's INSERT does not list this column, so a "
    "newly inserted row holds NULL until the module below commits. If that "
    "module does not run, an EXISTING row keeps the value from the last run "
    "that did -- an UPDATE that is never issued does not fail, it leaves "
    "yesterday's number in place beside today's."
)

_UNWRITTEN = (
    "FINDING 11. No statement in the codebase writes this column: not the "
    "builder's INSERT, not its ON CONFLICT SET list, not any engine "
    "UPDATE, and it is not in the governed registry. Measured 10 Nov 2026."
)

EXTRA_FILES: dict[str, str] = {
    "screener_universe_scores": "screener.universe",
    "screener_universe_unwritten": "screener.universe",
    "screener_universe_lifecycle": None,      # several tables, keyed per column
}


# ── 25 update-only ──────────────────────────────────────────────────────────

_SCORES = {
    "source_table": "screener.universe (reads the row it then updates)",
    "grain": "one row per asx_code",
    "writer_job": "compute/engine/composite_score.py (UPDATE @846)",
    "join_condition":
        "No join: a single UPDATE over screener.universe, ranking each "
        "company against the rest of the universe as it stands at that "
        "moment.",
}

_FACTOR_RULE = (
    "A percentile rank 0-100 within the universe, so it is a RELATIVE claim. "
    "The same company can move without its own inputs changing, because the "
    "population moved. Constituents are declared per model version in "
    "compute/engine/factor_model.py and are not editable at runtime; "
    "FACTOR_MODEL_V3 is deliberately bound to V2's specs, so V3 scores "
    "identically to V2 and exists only to widen the governed-metric set."
)

_FACTOR_APPLICABILITY = (
    "Under the strict weighting rule a constituent that is universally "
    "absent makes its factor universally unavailable. That is why V2 drops "
    "eps_growth_hoh from growth: the column is NULL for all 2,117 active "
    "companies and has no producer anywhere in the pipeline, and leaving it "
    "declared would have made growth unscoreable for every company for a "
    "reason that has nothing to do with the companies. " + _UPDATE_ONLY
)

COLUMN_PROSE_EXTRA: dict[str, dict] = {

    "value_score": dict(_SCORES, **{
        "transformation_rule":
            "Percentile rank of the value factor: low pe_ratio, low "
            "price_to_book, low ev_ebitda, low price_to_sales, high "
            "fcf_yield. Signs are declared per constituent.",
        "business_rule": _FACTOR_RULE,
        "unit": "percentile 0-100",
        "applicability":
            "CHECK (value_score BETWEEN 0 AND 100) is enforced. " +
            _FACTOR_APPLICABILITY,
    }),

    "quality_score": dict(_SCORES, **{
        "transformation_rule":
            "Percentile rank of the quality factor. V1 included "
            "piotroski_f_score; V2 and V3 do NOT -- it was declared out, "
            "not dropped at runtime. V2/V3 constituents are roe, roce, "
            "altman_z_score, debt_to_equity (negative) and net_margin.",
        "business_rule": _FACTOR_RULE,
        "unit": "percentile 0-100",
        "applicability":
            "CHECK (quality_score BETWEEN 0 AND 100) is enforced. A score "
            "computed under V1 and one under V2 are not comparable and the "
            "row records which version produced it only through "
            "compute_run_id -> compute_runs.factor_model_version. " +
            _FACTOR_APPLICABILITY,
    }),

    "growth_score": dict(_SCORES, **{
        "transformation_rule":
            "Percentile rank of the growth factor: revenue_growth_1y, "
            "earnings_growth_1y, eps_growth_3y_cagr, revenue_growth_hoh, "
            "revenue_cagr_5y.",
        "business_rule":
            _FACTOR_RULE + " The spec names eps_growth_3y_cagr rather than "
            "eps_cagr_3y deliberately: the two are the same concept under "
            "two names, no STORAGE_COLUMN alias links them, and their "
            "canonical identity is genuinely unresolved -- the served "
            "sibling column is a COALESCE of two different computations.",
        "unit": "percentile 0-100",
        "applicability":
            "CHECK (growth_score BETWEEN 0 AND 100) is enforced. This "
            "factor reads revenue_growth_hoh, which carries FINDING 9: "
            "5.7% of company-years have their half assigned by row position "
            "and the resulting values are served, not withheld. A growth "
            "score for an affected company is computed from a mis-paired "
            "interval. " + _FACTOR_APPLICABILITY,
    }),

    "momentum_score": dict(_SCORES, **{
        "transformation_rule":
            "Percentile rank of the momentum factor: return_1m, return_3m, "
            "return_6m, rsi_14, adx_14.",
        "business_rule":
            _FACTOR_RULE + " The constituents are the return_* family only. "
            "No momentum_* column is a constituent of any factor in any "
            "model version, so the momentum_3m/return_3m alias pair is NOT "
            "double-counted here -- checked against factor_model.py, not "
            "inferred from the column comment.",
        "unit": "percentile 0-100",
        "applicability":
            "CHECK (momentum_score BETWEEN 0 AND 100) is enforced. Its "
            "return_* constituents are governed and computed on UNADJUSTED "
            "close, and are withheld across a detected corporate action -- "
            "so a company with a recent action contributes fewer valid "
            "constituents. " + _FACTOR_APPLICABILITY,
    }),

    "income_score": dict(_SCORES, **{
        "transformation_rule":
            "Percentile rank of the income factor: grossed_up_yield, "
            "dividend_yield, franking_pct, dividend_consecutive_yrs, "
            "dividend_cagr_3y, and dividend_payout_ratio with a negative "
            "sign.",
        "business_rule":
            _FACTOR_RULE + " Franking is weighted explicitly, which is what "
            "makes this an Australian income score rather than a yield "
            "ranking.",
        "unit": "percentile 0-100",
        "applicability":
            "CHECK (income_score BETWEEN 0 AND 100) is enforced. A company "
            "that pays no dividend is a genuine zero on several "
            "constituents, not an absent one, and the two must not be "
            "conflated. " + _FACTOR_APPLICABILITY,
    }),

    "composite_score": dict(_SCORES, **{
        "transformation_rule":
            "Equal-weight average of the five factor scores.",
        "business_rule":
            "Equal weighting is a declared choice, not a fitted one: no "
            "factor is evidenced as more predictive than another here, and "
            "equal weights say so rather than implying a model that was "
            "never estimated. " + _FACTOR_RULE,
        "unit": "score 0-100",
        "applicability":
            "CHECK (composite_score BETWEEN 0 AND 100) is enforced, and the "
            "column is GOVERNED -- so the canonical writer assigns it on "
            "every canonical row including an explicit NULL. A composite "
            "over fewer than five available factors is an average of what "
            "was available, and the row does not publish how many that was. "
            + _FACTOR_APPLICABILITY,
    }),

    "multibagger_potential_score": {
        "source_table": "screener.universe",
        "transformation_rule":
            "MULTIBAGGER_POTENTIAL_V1, a weighted composite over seven "
            "components, each stored beside it.",
        "business_rule":
            "Strength of compounding CHARACTERISTICS. It is explicitly NOT "
            "a prediction of returns, and its own column comment says so -- "
            "the name invites the opposite reading and the comment exists "
            "to refuse it.",
        "grain": "one row per asx_code",
        "unit": "score 0-100, one decimal",
        "applicability":
            "NULL when the eligibility rules are unmet, and the rules are "
            "conjunctive: the growth component is required, plus capital "
            "efficiency OR earnings stability, plus at least 70% of the "
            "component weight valid. mb_valid_weight_pct publishes how much "
            "weight actually had data, so a published score can be checked "
            "rather than trusted. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/composite_score.py (UPDATE @886)",
        "join_condition": "No join: a single UPDATE over screener.universe.",
    },

    "multibagger_version": {
        "source_table": "screener.universe",
        "transformation_rule":
            "The version string of the model that produced the score on "
            "this row.",
        "business_rule":
            "Published so a score can be attributed to a model. Two rows "
            "with different versions are not comparable, and without this "
            "column that would be undetectable.",
        "grain": "one row per asx_code",
        "unit": "n/a (version label)",
        "applicability":
            "NULL alongside a NULL score means not eligible; NULL alongside "
            "a non-NULL score would be a contract violation. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/composite_score.py (UPDATE @886)",
        "join_condition": "No join: a single UPDATE over screener.universe.",
    },

    "mb_valid_weight_pct": {
        "source_table": "screener.universe",
        "transformation_rule":
            "The percentage of the 100% component weight that had usable "
            "data on this row.",
        "business_rule":
            "The honesty column of the multibagger score. 100 means every "
            "component contributed; 70 is the minimum for a published "
            "score. It is what lets a reader distinguish a strong score "
            "from a score computed over thin evidence.",
        "grain": "one row per asx_code",
        "unit": "percent 0-100, one decimal",
        "applicability":
            "Always read this beside the score. A score at 70% valid weight "
            "and one at 100% are presented identically otherwise. " +
            _UPDATE_ONLY,
        "writer_job": "compute/engine/composite_score.py (UPDATE @886)",
        "join_condition": "No join: a single UPDATE over screener.universe.",
    },

    "pros": {
        "source_table": "screener.universe (reads the row it then updates)",
        "transformation_rule":
            "Pre-computed plain-English bullish signals, derived from the "
            "metric columns already on the row.",
        "business_rule":
            "A presentation layer over the metrics, not a new measurement. "
            "Every statement in it should be traceable to a column on the "
            "same row.",
        "grain": "one row per asx_code",
        "unit": "array of text",
        "applicability":
            "DEFAULT '{}', so an empty array means either 'no bullish "
            "signal fired' or 'the module has not run for this row'. The "
            "two are not distinguishable from the stored value. Because "
            "these are derived from metric columns, any finding affecting a "
            "source metric reaches the prose silently -- a stale input "
            "produces a confidently-worded sentence. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/pros_cons.py (UPDATE @354)",
        "join_condition": "No join: a single UPDATE over screener.universe.",
    },

    "cons": {
        "source_table": "screener.universe (reads the row it then updates)",
        "transformation_rule":
            "Pre-computed plain-English bearish signals, derived from the "
            "metric columns already on the row.",
        "business_rule":
            "As for pros: presentation over the metrics, not a measurement.",
        "grain": "one row per asx_code",
        "unit": "array of text",
        "applicability":
            "DEFAULT '{}' -- see pros. A signal built on a boolean that is "
            "FALSE-for-unknown rather than NULL (finding 10's shape) would "
            "produce a bearish sentence about a company with insufficient "
            "history. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/pros_cons.py (UPDATE @354)",
        "join_condition": "No join: a single UPDATE over screener.universe.",
    },

    "metric_states": {
        "source_table": "screener.universe, market.daily_metrics",
        "transformation_rule":
            "The canonical applicability sidecar, emitted by the canonical "
            "writer in the same statement as the governed values. The "
            "builder sets it to NULL explicitly and atomically with its own "
            "write.",
        "business_rule":
            "Sparse by contract: an ABSENT entry means the metric is "
            "applicable. A present entry carries {state, cause, reason}. "
            "The builder may REVOKE a canonical claim but may never make "
            "one, because it has assessed nothing -- writing this sidecar "
            "there would be claiming an attribution it did not compute.",
        "grain": "one row per asx_code",
        "unit": "jsonb: metric -> {state, cause, reason}",
        "applicability":
            "NULL means the row was never assessed, which is NOT the same "
            "as assessed-and-clean ('{}') and must fail closed. A NULL "
            "numeric column with no entry here is a contract violation. "
            "There is deliberately NO column default, so an ad-hoc INSERT "
            "cannot produce a valid-looking row by construction.",
        "writer_job":
            "compute/engine/metric_states.py (UPDATE @152); "
            "compute/engine/universe_writer.py (canonical, dynamic SET); "
            "build_screener_universe.py sets it NULL",
        "join_condition":
            "No join: assigned per row by the canonical writer, keyed on "
            "asx_code.",
    },

    "compute_run_id": {
        "source_table": "screener.compute_runs",
        "transformation_rule":
            "The run that produced this row, written by the canonical "
            "writer. The builder sets it NULL atomically with its own "
            "write, in the same statement as the values, so there is no "
            "window in which values and attribution disagree.",
        "business_rule":
            "Attribution. It joins to screener.compute_runs for the factor "
            "model version and the source-health evidence behind any "
            "SOURCE_UNHEALTHY state, which is how a consumer tells 'this "
            "company pays no dividend' from 'we could not compute a "
            "dividend'.",
        "grain": "one row per asx_code",
        "unit": "n/a (foreign key to screener.compute_runs.id)",
        "applicability":
            "NULL means the row is not attributed to a completed run. "
            "app/core/row_projection.py turns that into OUTSIDE_SNAPSHOT "
            "and nulls every governed value with a stated cause, so an "
            "un-attributed row fails closed at the API rather than being "
            "served as current. NULL on an old row may instead mean it "
            "predates run attribution -- never backfill it with a guess.",
        "writer_job":
            "compute/engine/metric_states.py (UPDATE @152); "
            "compute/engine/universe_writer.py (canonical); "
            "build_screener_universe.py sets it NULL",
        "join_condition":
            "FOREIGN KEY (compute_run_id) REFERENCES screener.compute_runs(id)",
    },
}

# The five index flags, the seven multibagger components, the five dilution
# columns and the two short-interest columns share their rule within each
# group, so each group is written once and applied.

# These seven are in the builder's INSERT *and* overwritten after it, so
# they already have a row in a section file. What is authored here is an
# OVERRIDE on that row -- chiefly that the builder's value is not the one
# a customer reads.
COLUMN_PROSE_OVERRIDES: dict[str, dict] = {}

for _col in ("is_asx20", "is_asx50", "is_asx100", "is_asx200", "is_asx300"):
    COLUMN_PROSE_OVERRIDES[_col] = {
        "source_table": "market.index_constituents (via asx_indices.py)",
        "transformation_rule":
            "Set from the index constituent lists after the builder has "
            "inserted the row. The builder also carries a value for these "
            "from market.companies_current, so this module OVERWRITES it -- "
            "the module's value is the one a customer reads.",
        "business_rule":
            "Membership of the named S&P/ASX index as at the latest "
            "constituent list. Membership changes on rebalance dates and "
            "the row does not publish which list it reflects.",
        "grain": "one row per asx_code",
        "unit": "boolean",
        "applicability":
            "FALSE means 'not in the list', which also covers 'the list was "
            "not loaded'. Finding 5 is open against the constituent counts: "
            "stock_count reads 189 and 277 against nominal 200 and 300, "
            "unexplained -- so a FALSE here may reflect an incomplete list "
            "rather than a non-member. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/asx_indices.py (UPDATE @139, @224)",
        "join_condition":
            "No join in the UPDATE: keyed on asx_code against the loaded "
            "constituent set.",
    }

for _col, _what in (
    ("mb_growth_component", "growth"),
    ("mb_capital_efficiency_component", "capital efficiency"),
    ("mb_earnings_stability_component", "earnings stability"),
    ("mb_margin_expansion_component", "margin expansion"),
    ("mb_dilution_component", "dilution"),
    ("mb_momentum_component", "momentum"),
    ("mb_insider_alignment_component", "insider alignment"),
):
    COLUMN_PROSE_EXTRA[_col] = {
        "source_table": "screener.universe (reads the row it then updates)",
        "transformation_rule":
            f"The {_what} component of MULTIBAGGER_POTENTIAL_V1, published "
            f"separately so the composite can be decomposed.",
        "business_rule":
            f"Published so a reader can see WHY a multibagger score is what "
            f"it is. The {_what} component carries its own weight in the "
            f"composite; growth is REQUIRED for any score to be published, "
            f"and capital efficiency or earnings stability must also be "
            f"present.",
        "grain": "one row per asx_code",
        "unit": "score 0-100, one decimal",
        "applicability":
            "NULL means this component had no usable data, which reduces "
            "mb_valid_weight_pct rather than being scored as zero. A "
            "component scored 0 and a component absent are different "
            "claims and are stored differently. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/composite_score.py (UPDATE @886)",
        "join_condition": "No join: a single UPDATE over screener.universe.",
    }

_DILUTION = {
    "source_table": "market.shares_history",
    "grain": "one row per asx_code",
    "writer_job": "compute/engine/dilution_metrics.py (UPDATE @127)",
    "join_condition":
        "No join in the UPDATE: computed per company from the annual share "
        "count series and assigned by asx_code.",
    "business_rule":
        "Dilution history. Annual share counts were only ingested as of "
        "v11.2.73 (1 Nov 2026), which took both_yr_shares from 0 to 1,529 "
        "companies with 45 named exceptions -- so this family is young and "
        "its coverage is not universal.",
}

COLUMN_PROSE_EXTRA["shares_outstanding_cagr_3y"] = dict(_DILUTION, **{
    "transformation_rule":
        "Annualised share-count change over the window, as a ratio.",
    "unit":
        "decimal ratio per year (0.05 = 5% per year of dilution); NEGATIVE "
        "means the count shrank, i.e. a buyback",
    "applicability":
        "NULL when any year-on-year step in the window is implausible, "
        "which usually indicates an unrecorded consolidation rather than "
        "genuine issuance -- the refusal is deliberate and is not missing "
        "data. Also NULL when shares_history_years is under 3. " +
        _UPDATE_ONLY,
})

COLUMN_PROSE_EXTRA["shares_change_1y"] = dict(_DILUTION, **{
    "transformation_rule":
        "Share-count change over the latest year.",
    "unit": "decimal ratio",
    "applicability":
        "Subject to the same implausibility refusal as the CAGR. " +
        _UPDATE_ONLY,
})

COLUMN_PROSE_EXTRA["dilution_years_3y"] = dict(_DILUTION, **{
    "transformation_rule":
        "Count of years in the window where the share count grew more than "
        "2 percent.",
    "unit": "count of years, 0-3",
    "applicability":
        "This is what distinguishes a serial issuer from a single capital "
        "event, which the CAGR alone cannot. Zero means no year crossed the "
        "threshold, not that the data is absent -- read shares_history_years "
        "to tell those apart. " + _UPDATE_ONLY,
})

COLUMN_PROSE_EXTRA["max_annual_dilution_3y"] = dict(_DILUTION, **{
    "transformation_rule":
        "The largest single-year share-count increase in the window.",
    "unit": "decimal ratio",
    "applicability":
        "Read beside dilution_years_3y: a large max with a count of 1 is "
        "one raising, the same max with a count of 3 is a pattern. " +
        _UPDATE_ONLY,
})

COLUMN_PROSE_EXTRA["shares_history_years"] = dict(_DILUTION, **{
    "transformation_rule":
        "The number of annual observations actually used.",
    "unit": "count of years",
    "applicability":
        "The coverage column for this family. Fewer than 3 means no CAGR is "
        "published. It is the only way to tell an absent dilution metric "
        "from a company with a stable share count. " + _UPDATE_ONLY,
})

for _col, _rule, _unit in (
    ("short_pct",
     "Short positions as a percentage of issued capital, as at the latest "
     "ASIC report date.",
     "percent of issued capital"),
    ("short_interest_chg_1w",
     "Week-over-week change in short interest, in PERCENTAGE POINTS -- not "
     "a percentage change of the percentage.",
     "percentage points"),
):
    COLUMN_PROSE_OVERRIDES[_col] = {
        "source_table": "market.short_positions",
        "transformation_rule": _rule,
        "business_rule":
            "ASIC publishes short positions with a lag of several business "
            "days, so this figure's as-at date is NOT the price_date on the "
            "same row. The report date is not carried onto the row, so a "
            "consumer cannot tell how old it is.",
        "grain": "one row per asx_code at the latest ASIC report date",
        "unit": _unit,
        "applicability":
            "short_pct is also written by the builder's INSERT, so this "
            "module OVERWRITES it and the module's value is what a customer "
            "reads. Finding 2 is open against market.short_interest, a "
            "different table for which no backend reader has been found -- "
            "that finding is not about this column. " + _UPDATE_ONLY,
        "writer_job": "compute/engine/short_positions.py (UPDATE @233)",
        "join_condition":
            "No join in the UPDATE: assigned by asx_code from the latest "
            "report.",
    }


# ── 10 that nothing writes ──────────────────────────────────────────────────

#: price_to_52w_high was the tenth entry here until 10 Nov 2026. It is now
#: written by the statement, so its prose lives with the section that
#: contains it. Nine remain.
_SIBLINGS = {
    "short_name": "company_name, carried from c.company_name",
    "listing_date": "years_listed, computed inline from cp.ipo_date",
    "franking_credit_per_share": "franking_pct and grossed_up_yield",
    "pay_date": "ex_div_date, carried from div_latest.ex_date",
    "dps_fy0": "eps_fy0 = COALESCE(pnl0.eps, ym.eps)",
    "dps_fy1": "eps_fy1 = pnl1.eps",
    "analyst_upside": "analyst_upside_pct, computed from ar.target_price",
    "shares_float": "shares_outstanding, carried from ss.shares_outstanding",
    "adl": "obv and cmf_20, both carried from dm.*",
}

for _col, _sib in _SIBLINGS.items():
    COLUMN_PROSE_EXTRA[_col] = {
        "source_table": "(none -- no statement writes this column)",
        "source_column": "(none)",
        "derivation_formula": "(none)",
        "transformation_rule":
            "There is none. The column exists in the table and in no "
            "statement.",
        "business_rule":
            f"What it was intended to hold is legible from its name and "
            f"from the sibling that IS written beside it: {_sib}. That "
            f"sibling is why the gap was invisible -- a reader checking "
            f"whether the subject is covered sees a populated column next "
            f"to this one.",
        "grain": "one row per asx_code",
        "unit": "n/a (never populated)",
        "applicability":
            _UNWRITTEN + " NULL on all 2,566 rows. It is not a screener "
            "field in ALLOWED_FIELDS, so no filter can select on it. Either "
            "wire a writer or drop the column; leaving it is a promise the "
            "schema makes and the pipeline does not keep.",
        "writer_job": "(none)",
        "join_condition": "(none)",
    }

# ── 25 lifecycle columns ────────────────────────────────────────────────────

_RUNS = {
    "source_table": "screener.compute_runs",
    "grain": "one row per compute run",
    "writer_job":
        "compute/engine/universe_writer.py; scripts/gate_seed_run.py; "
        "scripts/p0a_adversarial_assertions.py",
    "join_condition":
        "PRIMARY KEY (id); screener.universe.compute_run_id references it.",
}

_STAGES = {
    "source_table": "screener.compute_run_stages",
    "grain": "one terminal row per (run_id, stage_name)",
    "writer_job": "compute/engine/run_stages.py; scripts/gate_seed_run.py",
    "join_condition":
        "PRIMARY KEY (run_id, stage_name); FOREIGN KEY (run_id) REFERENCES "
        "screener.compute_runs(id) ON DELETE RESTRICT.",
}

_FINAL = {
    "source_table": "screener.compute_run_finalizations",
    "grain": "one row per PUBLISHED run",
    "writer_job": "compute/engine/run_stages.py; scripts/gate_seed_run.py",
    "join_condition":
        "PRIMARY KEY (run_id); FOREIGN KEY (run_id) REFERENCES "
        "screener.compute_runs(id) ON DELETE RESTRICT.",
}

_LIFECYCLE_NOTE = (
    "These tables are not metrics. They are the evidence that decides "
    "whether a universe row may be served at all: a resolver requires a "
    "finalization row plus a success row for every stage the run's plan "
    "declares. Append-only -- a retry is a NEW run, and an unpublishable "
    "run stays unfinalised rather than being downgraded."
)

_LIFECYCLE: dict[str, tuple[dict, str, str, str]] = {
    "screener.compute_runs.id": (
        _RUNS, "Surrogate key from a sequence.",
        "The identity a universe row is attributed to.",
        "n/a (identifier)"),
    "screener.compute_runs.run_at": (
        _RUNS, "Set to now() when the run opens.",
        "When the run STARTED, not when it published. Finalisation carries "
        "the publication time.",
        "timestamptz"),
    "screener.compute_runs.engine": (
        _RUNS, "The engine that opened the run.",
        "Which producer this run belongs to.", "n/a (label)"),
    "screener.compute_runs.factor_model_version": (
        _RUNS, "The factor model the run scored under.",
        "Scores from two versions are not comparable, and this column is "
        "the only thing on a universe row that says which produced it.",
        "n/a (version label)"),
    "screener.compute_runs.unhealthy_sources": (
        _RUNS, "The feeds that were not usable during the run.",
        "This is what lets a consumer tell 'this company pays no dividend' "
        "from 'we could not compute a dividend' without inspecting every "
        "metric. DEFAULT '{}' -- an empty array means no feed was reported "
        "unhealthy.",
        "array of text"),
    "screener.compute_runs.detail": (
        _RUNS, "Free-form run detail.",
        "Diagnostic payload; not a contract surface.", "jsonb"),
    "screener.compute_runs.rows_written": (
        _RUNS, "Rows the run wrote.",
        "Nullable, unlike the finalisation's own count -- a run that never "
        "reached a write has no number here, which is not zero.",
        "count of rows"),
    "screener.compute_runs.plan_name": (
        _RUNS, "The run plan the run was opened under. Immutable.",
        "Decides which stage evidence the run's publication requires and "
        "which the resolver validates. LEGACY_CANONICAL marks runs "
        "published before plans existed, under the historical three-stage "
        "contract -- so a legacy run is not missing evidence, it is held to "
        "a different declared contract.",
        "n/a (plan label)"),

    "screener.compute_run_stages.run_id": (
        _STAGES, "The run this stage belongs to.",
        "ON DELETE RESTRICT: a run cannot be deleted while its evidence "
        "exists, so evidence cannot be orphaned or quietly removed.",
        "n/a (foreign key)"),
    "screener.compute_run_stages.stage_name": (
        _STAGES, "The stage.",
        "One terminal row per (run_id, stage_name). A retry is a new run, "
        "not a second row, so a stage's outcome cannot be overwritten.",
        "n/a (stage label)"),
    "screener.compute_run_stages.status": (
        _STAGES, "success or failed, enforced by CHECK.",
        "status = 'success' REQUIRES expected_set_hash = written_set_hash. "
        "A stage that ran without covering its source population is not a "
        "success, and the hash is what makes that checkable rather than "
        "asserted.",
        "n/a; CHECK (status IN ('success','failed'))"),
    "screener.compute_run_stages.expected_count": (
        _STAGES, "Entities the stage was required to cover.",
        "Drawn from the SOURCE population, not from the target -- a "
        "selector reading the target cannot see an entity with zero target "
        "rows.",
        "count of entities"),
    "screener.compute_run_stages.written_count": (
        _STAGES, "Entities the stage actually wrote.",
        "Counts ENTITIES, not rows.", "count of entities"),
    "screener.compute_run_stages.missing_count": (
        _STAGES, "Expected and not written.",
        "Non-zero with status success would be a contradiction the hash "
        "equality already forbids.",
        "count of entities"),
    "screener.compute_run_stages.extra_count": (
        _STAGES, "Written and not expected.",
        "Non-zero means the stage covered something outside its declared "
        "population, which is as much a contract breach as missing one.",
        "count of entities"),
    "screener.compute_run_stages.expected_set_hash": (
        _STAGES, "Hash of the expected entity SET.",
        "A hash rather than a count because two sets of equal size can "
        "differ. Comparing counts alone would admit a stage that wrote the "
        "right NUMBER of the wrong entities.",
        "n/a (hash)"),
    "screener.compute_run_stages.written_set_hash": (
        _STAGES, "Hash of the written entity set.",
        "Equality with expected_set_hash is the success condition.",
        "n/a (hash)"),
    "screener.compute_run_stages.details": (
        _STAGES, "Per-stage detail. DEFAULT '{}'.",
        "Diagnostic payload; not a contract surface.", "jsonb"),
    "screener.compute_run_stages.completed_at": (
        _STAGES, "Set to now() when the terminal row is written.",
        "When the stage ENDED. Note this is the stage's own time, not the "
        "run's publication time.",
        "timestamptz"),

    "screener.compute_run_finalizations.run_id": (
        _FINAL, "The run being published.",
        "The PRESENCE of this row is the publication boundary. Nothing "
        "else marks a run as published, and there is no status column to "
        "set wrongly.",
        "n/a (primary and foreign key)"),
    "screener.compute_run_finalizations.validated_at": (
        _FINAL, "Set to now() at finalisation.",
        "When the run was PUBLISHED, as distinct from compute_runs.run_at, "
        "which is when it started.",
        "timestamptz"),
    "screener.compute_run_finalizations.rows_written": (
        _FINAL, "Rows in the published universe.",
        "NOT NULL here, unlike compute_runs.rows_written -- a run that "
        "finalises has necessarily written.",
        "count of rows"),
    "screener.compute_run_finalizations.persistence_violations": (
        _FINAL, "Violations detected at finalisation.",
        "NOT NULL. A non-zero value on a finalised run is a published run "
        "that knew about its own violations, which is a state worth being "
        "able to find.",
        "count"),
    "screener.compute_run_finalizations.snapshot_id": (
        _FINAL, "The snapshot this finalisation published.",
        "Nullable -- not every finalisation carries one.",
        "n/a (identifier)"),
    "screener.compute_run_finalizations.details": (
        _FINAL, "Finalisation detail. DEFAULT '{}'.",
        "Diagnostic payload; not a contract surface.", "jsonb"),
}

LIFECYCLE_PROSE: dict[str, dict] = {}
for _fq, (_base, _trans, _rule, _unit) in _LIFECYCLE.items():
    _table, _, _col = _fq.rpartition(".")
    LIFECYCLE_PROSE.setdefault(_table, {})[_col] = dict(_base, **{
        "transformation_rule": _trans,
        "business_rule": _rule + " " + _LIFECYCLE_NOTE,
        "unit": _unit,
        "source_column": _fq,
        "derivation_formula":
            "Written by the orchestration, not derived from a source "
            "column.",
        "applicability":
            "Append-only. An absent row is not a failed run -- it is a run "
            "that did not reach this point, and the distinction is the "
            "whole contract.",
    })
