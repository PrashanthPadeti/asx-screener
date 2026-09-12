-- What does "every declared constituent" cost?
-- ============================================
-- compute_factor no longer averages whatever is non-null. A declared
-- constituent that is absent makes the factor unavailable, because a score
-- computed without it is a different model under the same name.
--
-- That rule is right and its cost is unmeasured, which makes it a V2
-- viability question rather than a coverage curiosity.
--
-- What this report will NOT settle: governing a constituent does not make its
-- holes reweightable. Governance supplies enough semantics to classify the
-- hole; the classification still has to be economically correct.
--
--     pe_ratio, non-positive earnings   legitimately NOT_MEANINGFUL, so the
--                                       declared reweight policy applies
--     fcf_yield NULL                    a negative FCF yield is meaningful,
--                                       so a NULL is missing input — the
--                                       factor should refuse, not reweight
--     rsi_14 / adx_14 / returns NULL    UNAVAILABLE / INSUFFICIENT_HISTORY.
--                                       Governing them names the reason and
--                                       restores no coverage at all
--
-- So each exclusion-heavy constituent resolves to exactly one of:
--
--     structurally not meaningful   govern it, reweight explicitly
--     observation unavailable       govern it, accept the factor going dark
--     genuinely optional signal     change the declared specification and
--                                   version it — an explicit minimum-coverage
--                                   policy in factor_model.py, never
--                                   optionality smuggled back through NaN
--
--     sudo -u postgres psql -d asx_screener -f scripts/factor_strictness_sizing.sql
--
-- Read-only. It proposes nothing.

\pset format aligned
\pset null '—'

CREATE TEMP VIEW factor_presence AS
WITH active AS (
    SELECT * FROM screener.universe WHERE status = 'active'
)
SELECT asx_code, 'value' AS factor,
       ARRAY['pe_ratio', 'price_to_book', 'ev_to_ebitda', 'fcf_yield',
             'price_to_sales']                                   AS names,
       ARRAY[TRUE, TRUE, TRUE, FALSE, TRUE]                      AS governed,
       ARRAY[pe_ratio IS NOT NULL, price_to_book IS NOT NULL,
             ev_to_ebitda IS NOT NULL, fcf_yield IS NOT NULL,
             price_to_sales IS NOT NULL]                         AS present,
       value_score                                               AS scored
  FROM active
UNION ALL
SELECT asx_code, 'quality (V2)',
       ARRAY['roe', 'roce', 'altman_z_score', 'debt_to_equity', 'net_margin'],
       ARRAY[TRUE, TRUE, TRUE, TRUE, TRUE],
       ARRAY[roe IS NOT NULL, roce IS NOT NULL, altman_z_score IS NOT NULL,
             debt_to_equity IS NOT NULL, net_margin IS NOT NULL],
       quality_score
  FROM active
UNION ALL
SELECT asx_code, 'growth',
       ARRAY['revenue_growth_1y', 'earnings_growth_1y', 'eps_growth_3y_cagr',
             'revenue_growth_hoh', 'eps_growth_hoh', 'revenue_cagr_5y'],
       ARRAY[FALSE, FALSE, FALSE, FALSE, FALSE, FALSE],
       ARRAY[revenue_growth_1y IS NOT NULL, earnings_growth_1y IS NOT NULL,
             eps_growth_3y_cagr IS NOT NULL, revenue_growth_hoh IS NOT NULL,
             eps_growth_hoh IS NOT NULL, revenue_cagr_5y IS NOT NULL],
       growth_score
  FROM active
UNION ALL
SELECT asx_code, 'momentum',
       ARRAY['return_1m', 'return_3m', 'return_6m', 'rsi_14', 'adx_14'],
       ARRAY[FALSE, FALSE, FALSE, FALSE, FALSE],
       ARRAY[return_1m IS NOT NULL, return_3m IS NOT NULL,
             return_6m IS NOT NULL, rsi_14 IS NOT NULL, adx_14 IS NOT NULL],
       momentum_score
  FROM active
UNION ALL
SELECT asx_code, 'income',
       ARRAY['grossed_up_yield', 'dividend_yield', 'franking_pct',
             'dividend_consecutive_yrs', 'dividend_cagr_3y', 'payout_ratio'],
       ARRAY[TRUE, TRUE, TRUE, FALSE, FALSE, TRUE],
       ARRAY[grossed_up_yield IS NOT NULL, dividend_yield IS NOT NULL,
             franking_pct IS NOT NULL, dividend_consecutive_yrs IS NOT NULL,
             dividend_cagr_3y IS NOT NULL, payout_ratio IS NOT NULL],
       income_score
  FROM active;

CREATE TEMP VIEW factor_counts AS
SELECT *,
       cardinality(present) AS declared,
       (SELECT count(*) FROM unnest(present) AS p WHERE p) AS n_present
  FROM factor_presence;

-- ── Complete coverage, against what is scored today ─────────────────────────

SELECT factor,
       count(*)                                        AS active_rows,
       count(*) FILTER (WHERE n_present = declared)     AS all_present,
       count(scored)                                    AS scored_today,
       count(scored) - count(*) FILTER (WHERE n_present = declared)
                                                        AS rows_lost,
       round(100.0 * count(*) FILTER (WHERE n_present = declared)
             / nullif(count(*), 0), 1)                  AS pct_complete
  FROM factor_counts
 GROUP BY factor
 ORDER BY rows_lost DESC;

-- ── The incremental cliff, per constituent ──────────────────────────────────
-- null_rows is how often a constituent is absent. sole_blocker is the number
-- of companies that have EVERY OTHER declared constituent and are excluded by
-- this one alone — the rows that would return if only this were resolved.
--
-- A constituent with a large null_rows and a small sole_blocker costs
-- nothing: those companies were already excluded by something else. The
-- opposite is where a decision is worth making.

SELECT f.factor,
       f.names[i]                                            AS constituent,
       f.governed[i]                                         AS governed,
       count(*) FILTER (WHERE NOT f.present[i])              AS null_rows,
       count(*) FILTER (WHERE NOT f.present[i]
                          AND f.n_present = f.declared - 1)  AS sole_blocker
  FROM factor_counts f, generate_subscripts(f.present, 1) AS i
 GROUP BY 1, 2, 3
 ORDER BY sole_blocker DESC, null_rows DESC;

-- ── How sharp is the cliff? ─────────────────────────────────────────────────
-- If most companies sit at declared-1, a minimum-coverage policy would be a
-- large change in outcome. If they sit far below, strictness is not what is
-- excluding them and the coverage problem is elsewhere.

SELECT factor, n_present || ' of ' || declared AS constituents_present,
       count(*) AS companies
  FROM factor_counts
 GROUP BY factor, n_present, declared
 ORDER BY factor, n_present DESC;
