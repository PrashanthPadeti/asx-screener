-- Migration 021: Add half-yearly HoH growth columns to screener.universe
-- ========================================================================
-- Exposes the most recent half-over-half (HoH) growth from
-- market.halfyearly_metrics. YoY is already covered by yearly/quarterly
-- metrics; HoH is the unique insight from half-yearly reporting.
-- ========================================================================

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS revenue_growth_hoh      NUMERIC(18,6),   -- latest half HoH
    ADD COLUMN IF NOT EXISTS net_income_growth_hoh   NUMERIC(18,6),   -- latest half HoH
    ADD COLUMN IF NOT EXISTS eps_growth_hoh          NUMERIC(18,6);   -- latest half HoH

-- Recreate screener.fundamentals view to include new columns
DROP VIEW IF EXISTS screener.fundamentals;
CREATE OR REPLACE VIEW screener.fundamentals AS
SELECT
    asx_code, company_name, sector, industry, stock_type, status,
    market_cap, pe_ratio, forward_pe, peg_ratio, price_to_book,
    price_to_sales, price_to_cash_flow, price_to_fcf,
    ev, ev_to_ebitda, ev_to_ebit, ev_to_revenue, graham_number,
    dps_ttm, dividend_yield, franking_pct, grossed_up_yield,
    payout_ratio,
    dividend_cagr_3y, dividend_consecutive_yrs,
    revenue_ttm, gross_profit_ttm, ebitda_ttm, net_profit_ttm,
    gross_margin, ebitda_margin, net_margin, operating_margin,
    roe, roa, roce, avg_roe_3y,
    revenue_fy0, revenue_fy1, revenue_fy2,
    ebitda_fy0, ebitda_fy1,
    net_profit_fy0, net_profit_fy1,
    eps_fy0, eps_fy1, dps_fy0, dps_fy1,
    total_assets, total_equity, total_debt, net_debt, cash,
    book_value_per_share, debt_to_equity, current_ratio,
    cfo_fy0, capex_fy0, fcf_fy0, fcf_yield,
    revenue_growth_1y, revenue_growth_3y_cagr, revenue_cagr_5y,
    earnings_growth_1y, earnings_growth_3y_cagr, eps_growth_3y_cagr,
    revenue_growth_yoy_q, eps_growth_yoy_q, net_income_growth_yoy_q,
    revenue_growth_hoh, net_income_growth_hoh, eps_growth_hoh,
    piotroski_f_score, altman_z_score,
    return_1y, return_3y, return_5y, return_7y, return_10y, return_15y,
    analyst_rating, analyst_target_price, analyst_upside,
    shares_outstanding, percent_insiders, percent_institutions
FROM screener.universe;

GRANT SELECT ON screener.fundamentals TO asx_user;
