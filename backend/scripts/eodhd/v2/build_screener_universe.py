"""
Build Screener Universe — Golden Record
========================================
Builds screener.universe from all transform-layer and compute-layer tables.

One denormalised row per stock, covering:
  - Identity & classification  (market.companies_current)
  - Price & market cap         (market.daily_prices latest close +
                                market.valuation_snapshot)
  - Valuation ratios           (market.valuation_snapshot)
  - Dividends                  (market.dividends latest + valuation_snapshot)
  - Profitability / margins    (market.computed_metrics preferred,
                                market.valuation_snapshot fallback)
  - Financials FY0/FY1         (financials.annual_pnl + balance_sheet + cashflow)
  - Returns / momentum         (market.monthly_metrics — latest month)
  - Technicals                 (market.monthly_metrics — latest month)
  - Multi-year metrics         (market.yearly_metrics  — latest FY)
  - Latest-quarter growth      (market.quarterly_metrics — latest quarter)
  - Analyst ratings            (market.analyst_ratings)
  - Shares / ownership         (staging_au.shares_stats)

COALESCE priority for overlapping fields:
  market.computed_metrics  (daily, freshest)
  market.yearly_metrics    (annual compute, thorough)
  market.valuation_snapshot (EODHD snapshot, weekly refresh)

Run after all compute engines complete.

Usage:
    python scripts/eodhd/v2/build_screener_universe.py
    python scripts/eodhd/v2/build_screener_universe.py --codes BHP CBA
"""

import logging
import os
import argparse
from datetime import date

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _flush_screener_cache() -> None:
    """Flush all asx:screener:* keys from Redis after universe rebuild.
    Fault-tolerant — silently skips if Redis is unavailable."""
    try:
        import redis as sync_redis
        r = sync_redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        deleted = 0
        for key in r.scan_iter("asx:screener:*"):
            r.delete(key)
            deleted += 1
        if deleted:
            log.info(f"Cache invalidated: {deleted} asx:screener:* keys flushed")
        else:
            log.info("Cache invalidated: no asx:screener:* keys found (cache was cold)")
    except Exception as e:
        log.warning(f"Redis cache flush skipped (Redis unavailable): {e}")

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


UPSERT_SQL = """
INSERT INTO screener.universe (
    -- ── Identity ─────────────────────────────────────────────────────────────
    asx_code, company_name, sector, industry_group, industry, sub_industry,
    stock_type, status, fiscal_year_end_month,
    is_reit, is_miner,
    is_asx20, is_asx50, is_asx100, is_asx200, is_asx300, is_all_ords,
    is_mega, is_large, is_mid, is_small, is_micro, is_nano,
    market_cap_tier,
    isin, website, description,

    -- ── Price ────────────────────────────────────────────────────────────────
    price, price_date, open, volume, avg_volume_20d, market_cap,
    high_52w, low_52w,

    -- ── Valuation ratios (from valuation_snapshot + yearly_metrics) ──────────
    pe_ratio, forward_pe, peg_ratio, price_to_book, price_to_sales,
    ev, ev_to_ebitda, ev_to_revenue,
    ev_to_ebit, price_to_fcf, graham_number,

    -- ── Dividends ────────────────────────────────────────────────────────────
    dividend_yield, dps_ttm, ex_div_date, franking_pct, payout_ratio,

    -- ── Profitability (computed_metrics → yearly_metrics → valuation_snapshot)
    revenue_ttm, gross_profit_ttm, ebitda_ttm,
    gross_margin, ebitda_margin, net_margin, operating_margin,
    roe, roa, roce, roic,
    asset_turnover,
    ocf_margin, fcf_margin, capex_intensity,
    grossed_up_yield, fcf_yield,

    -- ── EPS ──────────────────────────────────────────────────────────────────
    eps_fy0, eps_fy1,

    -- ── Income Statement FY0 / FY1 ───────────────────────────────────────────
    revenue_fy0, revenue_fy1,
    ebitda_fy0, ebitda_fy1,
    net_profit_fy0, net_profit_fy1,

    -- ── Balance Sheet (latest FY) ─────────────────────────────────────────────
    total_assets, total_equity, total_debt, net_debt, cash,
    book_value_per_share,          -- COALESCE(bs0, ym.bvps)
    debt_to_equity, current_ratio,
    net_debt_to_ebitda, interest_coverage,
    debt_to_assets, lt_debt_to_capital,

    -- ── Cash Flow (latest FY) ────────────────────────────────────────────────
    cfo_fy0, capex_fy0, fcf_fy0,

    -- ── Growth rates (computed_metrics → yearly_metrics) ─────────────────────
    revenue_growth_1y, revenue_growth_3y_cagr,
    earnings_growth_1y, earnings_growth_3y_cagr,
    ebitda_growth_1y, fcf_growth_1y, eps_growth_1y,

    -- ── Returns (weekly + monthly) ───────────────────────────────────────────
    return_1w,
    return_1m, return_3m, return_6m, return_1y, return_ytd,
    momentum_3m, momentum_6m, momentum_12m,

    -- ── Volatility & risk ────────────────────────────────────────────────────
    volatility_20d, volatility_60d,
    sharpe_1y, drawdown_from_ath,
    beta_1y,

    -- ── Technicals (daily preferred; weekly/monthly fallback) ────────────────
    rsi_14, macd, macd_signal,
    sma_20, sma_50, sma_200, ema_20,
    bb_upper, bb_lower, atr_14, adx_14, obv,

    -- ── Multi-year quality & CAGR (from yearly_metrics — latest FY) ──────────
    piotroski_f_score, altman_z_score,
    revenue_cagr_5y, eps_growth_3y_cagr,
    revenue_cagr_7y, revenue_cagr_10y, net_income_cagr_5y, eps_cagr_5y,
    ebitda_cagr_3y, ebitda_cagr_5y, fcf_cagr_3y, fcf_cagr_5y,
    avg_roe_3y,
    avg_roe_5y, avg_roa_3y, avg_roa_5y, avg_roce_3y, avg_roce_5y,
    avg_gross_margin_3y, avg_gross_margin_5y,
    avg_ebitda_margin_3y, avg_ebitda_margin_5y,
    avg_operating_margin_3y, avg_operating_margin_5y,
    avg_net_margin_3y, avg_net_margin_5y,
    avg_eps_growth_3y, avg_eps_growth_5y,
    dividend_cagr_3y, dividend_consecutive_yrs,
    dividend_cagr_5y, bvps_cagr_3y, bvps_cagr_5y,
    return_3y, return_5y, return_7y, return_10y, return_15y,

    -- ── Latest-quarter YoY growth (from quarterly_metrics) ───────────────────
    revenue_growth_yoy_q, eps_growth_yoy_q, net_income_growth_yoy_q,

    -- ── Half-yearly HoH growth (from halfyearly_metrics — latest half) ───────
    revenue_growth_hoh, net_income_growth_hoh, eps_growth_hoh,

    -- ── Analyst ──────────────────────────────────────────────────────────────
    analyst_rating, analyst_target_price,
    analyst_strong_buy, analyst_buy, analyst_hold, analyst_sell, analyst_strong_sell,

    -- ── Short interest (ASIC) ────────────────────────────────────────────────
    short_pct, short_position_shares, short_interest_chg_1w,

    -- ── Shares & Ownership ───────────────────────────────────────────────────
    shares_outstanding,
    percent_insiders, percent_institutions,

    -- ── Quick-win metrics ────────────────────────────────────────────────────
    ocf_to_net_profit, fcf_payout_ratio, shares_dilution_3y,
    eps_volatility_5y, fcf_positive_years,
    above_vwap,

    -- ── Partial metrics ──────────────────────────────────────────────────────
    dollar_volume_avg_20d,
    avg_roic_3y, avg_roic_5y, asset_light_score,

    -- ── Volume signals (daily_metrics) ───────────────────────────────────────
    avg_volume_50d,
    cmf_20, up_down_vol_ratio_20d,
    obv_rising, volume_breakout,

    -- ── Analyst-derived (from existing buy/sell/hold counts) ─────────────────
    analyst_count, analyst_buy_pct, analyst_consensus_score,

    -- ── Quality proxy scores (from yearly_metrics) ───────────────────────────
    brand_proxy_score, capital_efficiency_score, earnings_stability_score,

    -- ── Admin tags (from market.companies) ───────────────────────────────────
    business_model_tag, commodity_exposure,

    -- ── Tier 2: daily signals (from daily_metrics) ────────────────────────────
    dma50_ratio, dma200_ratio,
    above_sma50, above_sma200,
    golden_cross, death_cross,
    new_52w_high, new_52w_low,
    relative_volume,
    bb_pct, rsi_21, stoch_k, stoch_d,
    rsi_overbought, rsi_oversold,
    macd_bullish_cross, macd_bearish_cross,

    -- ── Per-share & working capital ──────────────────────────────────────────
    ocf_per_share, fcf_per_share, revenue_per_share,
    working_capital, price_to_52w_low,

    -- ── Income statement history (annual levels, AUD millions) ───────────────
    gross_profit_fy0, gross_profit_fy1, gross_profit_fy3, gross_profit_fy5, gross_profit_fy7, gross_profit_fy10,
    pbt_fy0, pbt_fy1, pbt_fy3, pbt_fy5, pbt_fy7, pbt_fy10,
    revenue_fy3, revenue_fy5, revenue_fy7, revenue_fy10,
    net_profit_fy3, net_profit_fy5, net_profit_fy7, net_profit_fy10,

    -- ── Growth rates (Sales prev-yr + Pre-tax Profit YoY/CAGR) ───────────────
    sales_growth_prev_y, pbt_growth_1y, pbt_growth_prev_y,
    pbt_cagr_3y, pbt_cagr_5y, pbt_cagr_7y, pbt_cagr_10y,

    -- ── Income-statement & balance-sheet line items (annual, AUD millions) ───
    cogs, ebit, income_tax_expense, interest_expense, depreciation,
    trade_receivables, inventory, goodwill, intangibles, ppe_net,
    total_current_assets, total_current_liabilities, total_liabilities,
    long_term_debt, retained_earnings, cfi, dividends_paid,

    -- ── Derived ratios ──────────────────────────────────────────────────────
    quick_ratio, cash_ratio, debt_to_ebitda, days_sales_outstanding,
    days_inventory_outstanding, inventory_turnover, receivables_turnover,
    pretax_margin, nopat, ebitda_interest_coverage, equity_ratio,
    liabilities_to_assets, fixed_asset_turnover, capex_to_revenue,
    tangible_book_value_per_share, cash_per_share,

    -- ── Quick wins (existing columns, previously unwritten) ──────────────────
    revenue_fy2, net_profit_ttm, price_to_cash_flow,

    -- ── Profit-based signals ─────────────────────────────────────────────────
    operating_margin_expanding, gross_margin_expanding, fcf_conversion,
    eps_beats_revenue_growth, operating_leverage,

    -- ── Sales-based signals ──────────────────────────────────────────────────
    revenue_growth_accelerating, revenue_growth_delta, revenue_growth_consistency,

    universe_built_at
)
SELECT
    -- ── Identity ─────────────────────────────────────────────────────────────
    c.asx_code,
    c.company_name,
    c.gics_sector,
    c.gics_industry_group,
    c.gics_industry,
    c.gics_sub_industry,
    c.company_type,
    c.status,
    c.fiscal_year_end_month,
    c.is_reit,
    c.is_miner,
    c.is_asx20,  c.is_asx50,  c.is_asx100,
    c.is_asx200, c.is_asx300, c.is_all_ords,

    -- ── Market cap tier flags (derived from vs.market_cap, raw AUD) ───────────
    -- COALESCE(..., FALSE) prevents NOT NULL violation when market_cap is NULL
    -- (e.g. delisted stocks or stocks not yet in valuation_snapshot)
    COALESCE(vs.market_cap >= 50000000000, FALSE)                                           AS is_mega,
    COALESCE(vs.market_cap >= 10000000000 AND vs.market_cap < 50000000000, FALSE)          AS is_large,
    COALESCE(vs.market_cap >= 2000000000  AND vs.market_cap < 10000000000, FALSE)          AS is_mid,
    COALESCE(vs.market_cap >= 300000000   AND vs.market_cap < 2000000000, FALSE)           AS is_small,
    COALESCE(vs.market_cap >= 50000000    AND vs.market_cap < 300000000, FALSE)            AS is_micro,
    COALESCE(vs.market_cap > 0            AND vs.market_cap < 50000000, FALSE)             AS is_nano,
    CASE
        WHEN vs.market_cap >= 50000000000                              THEN 'mega'
        WHEN vs.market_cap >= 10000000000 AND vs.market_cap < 50000000000 THEN 'large'
        WHEN vs.market_cap >= 2000000000  AND vs.market_cap < 10000000000 THEN 'mid'
        WHEN vs.market_cap >= 300000000   AND vs.market_cap < 2000000000  THEN 'small'
        WHEN vs.market_cap >= 50000000    AND vs.market_cap < 300000000   THEN 'micro'
        WHEN vs.market_cap > 0                                            THEN 'nano'
        ELSE NULL
    END                                                                      AS market_cap_tier,

    c.isin,
    c.website,
    c.description,

    -- ── Price (latest close + 52w range) ─────────────────────────────────────
    dp.close          AS price,
    dp.price_date     AS price_date,
    dp.open           AS open,
    dp.volume         AS volume,
    dp20.avg_volume_20d,
    vs.market_cap,
    dp52.high_52w,
    dp52.low_52w,

    -- ── Valuation ratios ─────────────────────────────────────────────────────
    -- P/E: prefer valuation_snapshot; fall back to price / derived EPS (eps_fy0)
    -- when snapshot is null. Guard < 9999 so a tiny-EPS garbage P/E is dropped.
    COALESCE(vs.pe_ratio,
             CASE WHEN COALESCE(pnl0.eps, ym.eps) > 0
                       AND dp.close / COALESCE(pnl0.eps, ym.eps) < 9999
                  THEN ROUND((dp.close / COALESCE(pnl0.eps, ym.eps))::numeric, 4) END) AS pe_ratio,
    vs.forward_pe,
    -- PEG: prefer snapshot; else derived P/E over 3Y earnings growth pct, growth > 0
    COALESCE(vs.peg_ratio,
             CASE WHEN COALESCE(cm.profit_growth_3y, ym.net_income_cagr_3y) > 0
                       AND COALESCE(pnl0.eps, ym.eps) > 0
                       AND dp.close / COALESCE(pnl0.eps, ym.eps) < 9999
                  THEN ROUND(((dp.close / COALESCE(pnl0.eps, ym.eps))
                              / (COALESCE(cm.profit_growth_3y, ym.net_income_cagr_3y) * 100))::numeric, 4) END) AS peg_ratio,
    vs.price_to_book,
    vs.price_to_sales,
    vs.enterprise_value     AS ev,
    vs.ev_to_ebitda,
    vs.ev_to_revenue,
    -- ev_to_ebit: from yearly_metrics (computed by yearly_compute)
    ym.ev_ebit              AS ev_to_ebit,
    -- price_to_fcf: use yearly_compute's pre-computed p_fcf_ratio (reliable,
    -- already guards against negative/zero FCF and extreme values)
    ym.p_fcf_ratio          AS price_to_fcf,
    -- graham_number: sqrt(22.5 * EPS * BVPS), both > 0. BVPS computed fresh from
    -- total_equity / shares (ym.bvps was unreliable — mostly <= 0).
    CASE WHEN COALESCE(pnl0.eps, ym.eps) > 0
              AND (bs0.total_equity * 1000000.0 / NULLIF(ss.shares_outstanding, 0)) > 0
         THEN ROUND(sqrt(22.5 * COALESCE(pnl0.eps, ym.eps)
                         * (bs0.total_equity * 1000000.0 / NULLIF(ss.shares_outstanding, 0)))::numeric, 4)
    END AS graham_number,

    -- ── Dividends ────────────────────────────────────────────────────────────
    vs.dividend_yield,
    vs.dividend_per_share   AS dps_ttm,
    div_latest.ex_date,
    div_latest.franking_pct,
    -- payout_ratio: prefer direct eps; fall back to yearly_metrics derived eps
    -- Guard: only compute when |ratio| < 10^7 to avoid NUMERIC(12,4) overflow
    -- (tiny eps near zero would produce an astronomically large ratio)
    CASE WHEN COALESCE(pnl0.eps, ym.eps) IS NOT NULL
              AND COALESCE(pnl0.eps, ym.eps) > 0
              AND vs.dividend_per_share IS NOT NULL
              -- guard must match the NUMERIC(8,4) column range (max 9999.9999):
              -- a payout ratio above ~9999x means near-zero EPS, i.e. garbage → NULL
              AND ABS(vs.dividend_per_share / COALESCE(pnl0.eps, ym.eps)) < 9999
         THEN ROUND((vs.dividend_per_share / COALESCE(pnl0.eps, ym.eps))::numeric, 4)
    END AS payout_ratio,

    -- ── Profitability TTM ─────────────────────────────────────────────────────
    -- Priority: computed_metrics (daily) → valuation_snapshot (weekly)
    vs.revenue_ttm,
    vs.gross_profit_ttm,
    vs.ebitda_ttm,
    COALESCE(cm.gpm,           NULL)                         AS gross_margin,
    COALESCE(cm.ebitda_margin, NULL)                         AS ebitda_margin,
    COALESCE(cm.npm,           vs.profit_margin)             AS net_margin,
    COALESCE(cm.opm,           vs.operating_margin)          AS operating_margin,
    COALESCE(cm.roe,  ym.roe,  vs.roe_ttm)                  AS roe,
    COALESCE(cm.roa,  ym.roa,  vs.roa_ttm)                  AS roa,
    COALESCE(cm.roce, ym.roce)                               AS roce,
    ym.roic                                                  AS roic,
    ym.asset_turnover                                        AS asset_turnover,
    ym.ocf_margin                                            AS ocf_margin,
    ym.fcf_margin                                            AS fcf_margin,
    ym.capex_intensity                                       AS capex_intensity,
    COALESCE(cm.grossed_up_yield, ym.franked_yield)          AS grossed_up_yield,
    COALESCE(cm.fcf_yield,        ym.fcf_yield)              AS fcf_yield,

    -- ── EPS ──────────────────────────────────────────────────────────────────
    -- COALESCE: pnl0.eps is usually NULL (EODHD doesn't supply per-share data
    -- for ASX income statements); yearly_compute derives EPS from net_profit /
    -- shares and stores in market.yearly_metrics.eps — use that as fallback.
    COALESCE(pnl0.eps, ym.eps)  AS eps_fy0,
    pnl1.eps                    AS eps_fy1,

    -- ── Income Statement FY0 / FY1 ───────────────────────────────────────────
    pnl0.revenue    AS revenue_fy0,
    pnl1.revenue    AS revenue_fy1,
    pnl0.ebitda     AS ebitda_fy0,
    pnl1.ebitda     AS ebitda_fy1,
    pnl0.net_profit AS net_profit_fy0,
    pnl1.net_profit AS net_profit_fy1,

    -- ── Balance Sheet ────────────────────────────────────────────────────────
    bs0.total_assets,
    bs0.total_equity,
    bs0.total_debt,
    bs0.net_debt,
    bs0.cash_equivalents    AS cash,
    -- BVPS computed fresh from total_equity / shares (bs0.bvps is None and ym.bvps
    -- was unreliable — mostly <= 0). total_equity is AUD millions, shares is a raw count.
    ROUND((bs0.total_equity * 1000000.0 / NULLIF(ss.shares_outstanding, 0))::numeric, 4) AS book_value_per_share,
    CASE WHEN bs0.total_equity <> 0 AND bs0.total_equity IS NOT NULL
         THEN ROUND(bs0.total_debt / bs0.total_equity, 4) END AS debt_to_equity,
    CASE WHEN bs0.total_current_liab <> 0 AND bs0.total_current_liab IS NOT NULL
         THEN ROUND(bs0.total_current_assets / bs0.total_current_liab, 4) END AS current_ratio,
    ym.net_debt_to_ebitda                                    AS net_debt_to_ebitda,
    ym.interest_coverage                                     AS interest_coverage,
    ym.debt_to_assets                                        AS debt_to_assets,
    ym.lt_debt_to_capital                                    AS lt_debt_to_capital,

    -- ── Cash Flow ────────────────────────────────────────────────────────────
    cf0.cfo         AS cfo_fy0,
    cf0.capex       AS capex_fy0,
    cf0.fcf         AS fcf_fy0,

    -- ── Growth rates ─────────────────────────────────────────────────────────
    -- Priority: computed_metrics (uses latest price + last 5 annual rows)
    --           yearly_metrics  (more thorough historical CAGR)
    COALESCE(cm.revenue_growth_1y,  ym.revenue_growth_1y)        AS revenue_growth_1y,
    COALESCE(cm.revenue_growth_3y,  ym.revenue_cagr_3y)          AS revenue_growth_3y_cagr,
    COALESCE(cm.profit_growth_1y,   ym.net_income_growth_1y)     AS earnings_growth_1y,
    COALESCE(cm.profit_growth_3y,   ym.net_income_cagr_3y)       AS earnings_growth_3y_cagr,
    ym.ebitda_growth_1y                                          AS ebitda_growth_1y,
    ym.fcf_growth_1y                                             AS fcf_growth_1y,
    ym.eps_growth_1y                                             AS eps_growth_1y,

    -- ── Returns (daily → weekly/monthly fallback) ─────────────────────────────
    COALESCE(dm.return_1w,  wm.weekly_return)  AS return_1w,
    COALESCE(dm.return_1m,  mm.monthly_return) AS return_1m,
    COALESCE(dm.return_3m,  mm.return_3m)      AS return_3m,
    COALESCE(dm.return_6m,  mm.return_6m)      AS return_6m,
    COALESCE(dm.return_1y,  mm.return_12m)     AS return_1y,
    COALESCE(dm.return_ytd, mm.return_ytd)     AS return_ytd,
    mm.momentum_3m      AS momentum_3m,
    mm.momentum_6m      AS momentum_6m,
    mm.momentum_12m     AS momentum_12m,

    -- ── Volatility & risk ────────────────────────────────────────────────────
    COALESCE(dm.hv_20d, mm.volatility_1m)      AS volatility_20d,
    COALESCE(dm.hv_60d, mm.volatility_3m)      AS volatility_60d,
    ym.sharpe_1y        AS sharpe_1y,
    COALESCE(dm.pct_from_ath, mm.drawdown_from_ath, ym.max_drawdown_1y) AS drawdown_from_ath,
    ym.beta_1y          AS beta_1y,

    -- ── Technicals: daily metrics preferred; weekly/monthly as fallback ───────
    COALESCE(dm.rsi_14,     mm.rsi_14)         AS rsi_14,
    COALESCE(dm.macd_line,  mm.macd_line)      AS macd,
    COALESCE(dm.macd_signal,mm.macd_signal)    AS macd_signal,
    -- SMAs: exact daily values preferred over weekly approximations
    COALESCE(dm.sma_20,  wm.sma_20w)           AS sma_20,
    COALESCE(dm.sma_50,  wm.sma_10w)           AS sma_50,
    COALESCE(dm.sma_200, wm.sma_40w)           AS sma_200,
    COALESCE(dm.ema_20,  wm.ema_13w)           AS ema_20,
    COALESCE(dm.bb_upper,wm.bb_upper)          AS bb_upper,
    COALESCE(dm.bb_lower,wm.bb_lower)          AS bb_lower,
    COALESCE(dm.atr_14,  wm.atr_14)            AS atr_14,
    dm.adx_14,
    COALESCE(dm.obv,     wm.obv)               AS obv,

    -- ── Multi-year quality & CAGR (from yearly_metrics — latest FY) ──────────
    ym.piotroski_f_score,
    ym.altman_z_score,
    ym.revenue_cagr_5y,
    ym.eps_cagr_3y          AS eps_growth_3y_cagr,
    ym.revenue_cagr_7y,
    ym.revenue_cagr_10y,
    ym.net_income_cagr_5y,
    ym.eps_cagr_5y,
    ym.ebitda_cagr_3y,
    ym.ebitda_cagr_5y,
    ym.fcf_cagr_3y,
    ym.fcf_cagr_5y,
    ym.avg_roe_3y,
    ym.avg_roe_5y,
    ym.avg_roa_3y,
    ym.avg_roa_5y,
    ym.avg_roce_3y,
    ym.avg_roce_5y,
    ym.avg_gross_margin_3y,
    ym.avg_gross_margin_5y,
    ym.avg_ebitda_margin_3y,
    ym.avg_ebitda_margin_5y,
    ym.avg_operating_margin_3y,
    ym.avg_operating_margin_5y,
    ym.avg_net_margin_3y,
    ym.avg_net_margin_5y,
    ym.avg_eps_growth_3y,
    ym.avg_eps_growth_5y,
    ym.dividend_cagr_3y,
    ym.dividend_consecutive_yrs,
    ym.dividend_cagr_5y,
    ym.bvps_cagr_3y,
    ym.bvps_cagr_5y,
    ym.return_3y,
    ym.return_5y,
    ym.return_7y,
    ym.return_10y,
    ym.return_15y,

    -- ── Latest-quarter YoY growth (from quarterly_metrics) ───────────────────
    qm.revenue_growth_yoy    AS revenue_growth_yoy_q,
    qm.eps_growth_yoy        AS eps_growth_yoy_q,
    qm.net_income_growth_yoy AS net_income_growth_yoy_q,

    -- ── Half-yearly HoH growth (from halfyearly_metrics — latest half) ────────
    hym.revenue_growth_hoh,
    hym.net_income_growth_hoh,
    hym.eps_growth_hoh,

    -- ── Analyst ──────────────────────────────────────────────────────────────
    ar.rating           AS analyst_rating,
    ar.target_price     AS analyst_target_price,
    ar.strong_buy, ar.buy, ar.hold, ar.sell, ar.strong_sell,

    -- ── Short interest (ASIC — latest report date per stock) ─────────────────
    si.short_pct,
    si.short_shares            AS short_position_shares,
    si.short_pct_chg_1w        AS short_interest_chg_1w,

    -- ── Shares & Ownership ───────────────────────────────────────────────────
    ss.shares_outstanding,
    ss.percent_insiders,
    ss.percent_institutions,

    -- ── Quick-win metrics (from yearly_metrics + daily_metrics) ──────────────
    ym.ocf_to_net_profit,
    ym.fcf_payout_ratio,
    ym.shares_dilution_3y,
    ym.eps_volatility_5y,
    ym.fcf_positive_years,
    dm.above_vwap,

    -- ── Partial metrics ──────────────────────────────────────────────────────
    dm.dollar_volume_avg_20d,
    ym.avg_roic_3y,
    ym.avg_roic_5y,
    ym.asset_light_score,

    -- ── Volume signals (daily_metrics) ───────────────────────────────────────
    dm.volume_avg_50d         AS avg_volume_50d,
    dm.cmf_20,
    dm.up_down_vol_ratio_20d,
    dm.obv_rising,
    dm.volume_breakout,

    -- ── Analyst-derived (computed from existing buy/sell/hold counts) ─────────
    NULLIF(
        COALESCE(ar.strong_buy,0) + COALESCE(ar.buy,0) + COALESCE(ar.hold,0)
        + COALESCE(ar.sell,0) + COALESCE(ar.strong_sell,0), 0
    )::SMALLINT                                                             AS analyst_count,

    CASE WHEN (COALESCE(ar.strong_buy,0) + COALESCE(ar.buy,0) + COALESCE(ar.hold,0)
               + COALESCE(ar.sell,0) + COALESCE(ar.strong_sell,0)) > 0
         THEN ROUND(
             (COALESCE(ar.strong_buy,0) + COALESCE(ar.buy,0))::NUMERIC
             / (COALESCE(ar.strong_buy,0) + COALESCE(ar.buy,0) + COALESCE(ar.hold,0)
                + COALESCE(ar.sell,0) + COALESCE(ar.strong_sell,0)), 4)
    END                                                                     AS analyst_buy_pct,

    CASE WHEN (COALESCE(ar.strong_buy,0) + COALESCE(ar.buy,0) + COALESCE(ar.hold,0)
               + COALESCE(ar.sell,0) + COALESCE(ar.strong_sell,0)) > 0
         THEN ROUND(
             (COALESCE(ar.strong_buy,0)*2 + COALESCE(ar.buy,0)
              - COALESCE(ar.sell,0) - COALESCE(ar.strong_sell,0)*2)::NUMERIC
             / (COALESCE(ar.strong_buy,0) + COALESCE(ar.buy,0) + COALESCE(ar.hold,0)
                + COALESCE(ar.sell,0) + COALESCE(ar.strong_sell,0)), 4)
    END                                                                     AS analyst_consensus_score,

    -- ── Quality proxy scores (from yearly_metrics) ────────────────────────────
    ym.brand_proxy_score,
    ym.capital_efficiency_score,
    ym.earnings_stability_score,

    -- ── Admin tags (from market.companies) ───────────────────────────────────
    mc.business_model_tag,
    mc.commodity_exposure,

    -- ── Tier 2: daily signals (from daily_metrics) ────────────────────────────
    dm.dma50_ratio,
    dm.dma200_ratio,
    dm.above_sma50,
    dm.above_sma200,
    dm.golden_cross,
    dm.death_cross,
    CASE WHEN dp.close IS NOT NULL AND dp52.high_52w IS NOT NULL
         AND dp.close >= dp52.high_52w THEN TRUE ELSE FALSE END AS new_52w_high,
    CASE WHEN dp.close IS NOT NULL AND dp52.low_52w IS NOT NULL
         AND dp.close <= dp52.low_52w THEN TRUE ELSE FALSE END  AS new_52w_low,
    dm.relative_volume,
    dm.bb_pct,
    dm.rsi_21,
    dm.stoch_k,
    dm.stoch_d,
    dm.rsi_overbought,
    dm.rsi_oversold,
    dm.macd_bullish_cross,
    dm.macd_bearish_cross,

    -- ── Per-share & working capital ──────────────────────────────────────────
    -- cfo/fcf are AUD millions, shares_outstanding is a raw count → ×1e6 = AUD/share
    CASE WHEN ss.shares_outstanding > 0
         THEN ROUND((cf0.cfo * 1000000.0 / ss.shares_outstanding)::numeric, 4) END AS ocf_per_share,
    CASE WHEN ss.shares_outstanding > 0
         THEN ROUND((cf0.fcf * 1000000.0 / ss.shares_outstanding)::numeric, 4) END AS fcf_per_share,
    -- vs.revenue_ttm is already raw AUD → divide directly
    CASE WHEN ss.shares_outstanding > 0
         THEN ROUND((vs.revenue_ttm / ss.shares_outstanding)::numeric, 4) END AS revenue_per_share,
    -- working capital: current assets − current liabilities (already AUD millions)
    (bs0.total_current_assets - bs0.total_current_liab) AS working_capital,
    -- price position vs 52w low (1.0 = sitting at the low)
    CASE WHEN dp52.low_52w > 0
         THEN ROUND((dp.close / dp52.low_52w)::numeric, 4) END AS price_to_52w_low,

    -- ── Income statement history (annual levels, AUD millions) ───────────────
    pnl0.gross_profit  AS gross_profit_fy0,
    pnl1.gross_profit  AS gross_profit_fy1,
    pnl3.gross_profit  AS gross_profit_fy3,
    pnl5.gross_profit  AS gross_profit_fy5,
    pnl7.gross_profit  AS gross_profit_fy7,
    pnl10.gross_profit AS gross_profit_fy10,
    pnl0.pbt           AS pbt_fy0,
    pnl1.pbt           AS pbt_fy1,
    pnl3.pbt           AS pbt_fy3,
    pnl5.pbt           AS pbt_fy5,
    pnl7.pbt           AS pbt_fy7,
    pnl10.pbt          AS pbt_fy10,
    pnl3.revenue       AS revenue_fy3,
    pnl5.revenue       AS revenue_fy5,
    pnl7.revenue       AS revenue_fy7,
    pnl10.revenue      AS revenue_fy10,
    pnl3.net_profit    AS net_profit_fy3,
    pnl5.net_profit    AS net_profit_fy5,
    pnl7.net_profit    AS net_profit_fy7,
    pnl10.net_profit   AS net_profit_fy10,

    -- ── Growth rates (decimal ratios; YoY = (end-base)/|base|, CAGR needs both > 0)
    CASE WHEN pnl2.revenue IS NOT NULL AND pnl2.revenue <> 0
         THEN ROUND(((pnl1.revenue - pnl2.revenue) / ABS(pnl2.revenue))::numeric, 4) END AS sales_growth_prev_y,
    CASE WHEN pnl1.pbt IS NOT NULL AND pnl1.pbt <> 0
         THEN ROUND(((pnl0.pbt - pnl1.pbt) / ABS(pnl1.pbt))::numeric, 4) END AS pbt_growth_1y,
    CASE WHEN pnl2.pbt IS NOT NULL AND pnl2.pbt <> 0
         THEN ROUND(((pnl1.pbt - pnl2.pbt) / ABS(pnl2.pbt))::numeric, 4) END AS pbt_growth_prev_y,
    CASE WHEN pnl0.pbt > 0 AND pnl3.pbt > 0
         THEN ROUND((power(pnl0.pbt / pnl3.pbt, 1.0/3) - 1)::numeric, 4) END AS pbt_cagr_3y,
    CASE WHEN pnl0.pbt > 0 AND pnl5.pbt > 0
         THEN ROUND((power(pnl0.pbt / pnl5.pbt, 1.0/5) - 1)::numeric, 4) END AS pbt_cagr_5y,
    CASE WHEN pnl0.pbt > 0 AND pnl7.pbt > 0
         THEN ROUND((power(pnl0.pbt / pnl7.pbt, 1.0/7) - 1)::numeric, 4) END AS pbt_cagr_7y,
    CASE WHEN pnl0.pbt > 0 AND pnl10.pbt > 0
         THEN ROUND((power(pnl0.pbt / pnl10.pbt, 1.0/10) - 1)::numeric, 4) END AS pbt_cagr_10y,

    -- ── Income-statement & balance-sheet line items (annual, AUD millions) ───
    pnl0.cost_of_sales      AS cogs,
    pnl0.ebit               AS ebit,
    pnl0.tax                AS income_tax_expense,
    pnl0.interest_expense   AS interest_expense,
    pnl0.depreciation       AS depreciation,
    bs0.trade_receivables   AS trade_receivables,
    bs0.inventory           AS inventory,
    bs0.goodwill            AS goodwill,
    bs0.intangibles         AS intangibles,
    bs0.gross_block         AS ppe_net,
    bs0.total_current_assets   AS total_current_assets,
    bs0.total_current_liab     AS total_current_liabilities,
    bs0.total_liabilities      AS total_liabilities,
    bs0.long_term_debt      AS long_term_debt,
    bs0.retained_earnings   AS retained_earnings,
    cf0.cfi                 AS cfi,
    cf0.dividends_paid      AS dividends_paid,

    -- ── Derived ratios (from the line items above) ───────────────────────────
    CASE WHEN bs0.total_current_liab > 0
         THEN ROUND(((bs0.total_current_assets - COALESCE(bs0.inventory,0)) / bs0.total_current_liab)::numeric, 4) END AS quick_ratio,
    CASE WHEN bs0.total_current_liab > 0
         THEN ROUND((bs0.cash_equivalents / bs0.total_current_liab)::numeric, 4) END AS cash_ratio,
    CASE WHEN pnl0.ebitda > 0
         THEN ROUND((bs0.total_debt / pnl0.ebitda)::numeric, 4) END AS debt_to_ebitda,
    CASE WHEN pnl0.revenue > 0
         THEN ROUND((bs0.trade_receivables / pnl0.revenue * 365)::numeric, 2) END AS days_sales_outstanding,
    CASE WHEN pnl0.cost_of_sales > 0
         THEN ROUND((bs0.inventory / pnl0.cost_of_sales * 365)::numeric, 2) END AS days_inventory_outstanding,
    CASE WHEN bs0.inventory > 0
         THEN ROUND((pnl0.cost_of_sales / bs0.inventory)::numeric, 4) END AS inventory_turnover,
    CASE WHEN bs0.trade_receivables > 0
         THEN ROUND((pnl0.revenue / bs0.trade_receivables)::numeric, 4) END AS receivables_turnover,
    CASE WHEN pnl0.revenue > 0
         THEN ROUND((pnl0.pbt / pnl0.revenue)::numeric, 4) END AS pretax_margin,
    CASE WHEN pnl0.pbt <> 0 AND pnl0.pbt IS NOT NULL
         THEN ROUND((pnl0.ebit * (1 - pnl0.tax / pnl0.pbt))::numeric, 2) END AS nopat,
    CASE WHEN ABS(pnl0.interest_expense) > 0
         THEN ROUND((pnl0.ebitda / ABS(pnl0.interest_expense))::numeric, 4) END AS ebitda_interest_coverage,
    CASE WHEN bs0.total_assets > 0
         THEN ROUND((bs0.total_equity / bs0.total_assets)::numeric, 4) END AS equity_ratio,
    CASE WHEN bs0.total_assets > 0
         THEN ROUND((bs0.total_liabilities / bs0.total_assets)::numeric, 4) END AS liabilities_to_assets,
    CASE WHEN bs0.gross_block > 0
         THEN ROUND((pnl0.revenue / bs0.gross_block)::numeric, 4) END AS fixed_asset_turnover,
    CASE WHEN pnl0.revenue > 0
         THEN ROUND((ABS(cf0.capex) / pnl0.revenue)::numeric, 4) END AS capex_to_revenue,
    CASE WHEN ss.shares_outstanding > 0
         THEN ROUND(((bs0.total_equity - COALESCE(bs0.goodwill,0) - COALESCE(bs0.intangibles,0)) * 1000000.0 / ss.shares_outstanding)::numeric, 4) END AS tangible_book_value_per_share,
    CASE WHEN ss.shares_outstanding > 0
         THEN ROUND((bs0.cash_equivalents * 1000000.0 / ss.shares_outstanding)::numeric, 4) END AS cash_per_share,

    -- ── Quick wins ───────────────────────────────────────────────────────────
    pnl2.revenue    AS revenue_fy2,
    pnl0.net_profit AS net_profit_ttm,
    CASE WHEN cf0.cfo > 0
         THEN ROUND((vs.market_cap / (cf0.cfo * 1000000.0))::numeric, 4) END AS price_to_cash_flow,

    -- ── Profit-based signals ─────────────────────────────────────────────────
    -- Margin expansion: current margin above 3Y average?
    CASE WHEN COALESCE(cm.opm, vs.operating_margin) IS NOT NULL
          AND ym.avg_operating_margin_3y IS NOT NULL
         THEN COALESCE(cm.opm, vs.operating_margin) > ym.avg_operating_margin_3y
         END AS operating_margin_expanding,
    CASE WHEN cm.gpm IS NOT NULL AND ym.avg_gross_margin_3y IS NOT NULL
         THEN cm.gpm > ym.avg_gross_margin_3y
         END AS gross_margin_expanding,
    -- FCF Conversion: how much of net profit turns into free cash flow (ratio)?
    CASE WHEN pnl0.net_profit IS NOT NULL AND pnl0.net_profit > 0 AND cf0.fcf IS NOT NULL
         THEN ROUND((cf0.fcf / pnl0.net_profit)::numeric, 4)
         END AS fcf_conversion,
    -- EPS beats revenue growth: true when EPS growth > revenue growth (operating leverage)
    CASE WHEN ym.eps_growth_1y IS NOT NULL
          AND COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y) IS NOT NULL
         THEN ym.eps_growth_1y > COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y)
         END AS eps_beats_revenue_growth,
    -- Operating leverage: EBITDA growth minus revenue growth in decimal pp
    CASE WHEN ym.ebitda_growth_1y IS NOT NULL
          AND COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y) IS NOT NULL
         THEN ROUND((ym.ebitda_growth_1y
                     - COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y))::numeric, 4)
         END AS operating_leverage,

    -- ── Sales-based signals ──────────────────────────────────────────────────
    -- Acceleration: is this year's revenue growth faster than last year's?
    CASE WHEN COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y) IS NOT NULL
          AND pnl1.revenue IS NOT NULL AND pnl2.revenue IS NOT NULL AND pnl2.revenue <> 0
         THEN COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y)
              > ((pnl1.revenue - pnl2.revenue) / ABS(pnl2.revenue))
         END AS revenue_growth_accelerating,
    -- Delta: magnitude of acceleration in pp (positive = speeding up, negative = slowing)
    CASE WHEN COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y) IS NOT NULL
          AND pnl1.revenue IS NOT NULL AND pnl2.revenue IS NOT NULL AND pnl2.revenue <> 0
         THEN ROUND((COALESCE(cm.revenue_growth_1y, ym.revenue_growth_1y)
                     - (pnl1.revenue - pnl2.revenue) / ABS(pnl2.revenue))::numeric, 4)
         END AS revenue_growth_delta,
    -- Consistency: count of last 3 years with positive revenue growth (0-3)
    CASE WHEN pnl0.revenue IS NOT NULL AND pnl1.revenue IS NOT NULL
         THEN (
             CASE WHEN pnl0.revenue > pnl1.revenue THEN 1 ELSE 0 END
           + CASE WHEN pnl1.revenue IS NOT NULL AND pnl2.revenue IS NOT NULL
                       AND pnl1.revenue > pnl2.revenue THEN 1 ELSE 0 END
           + CASE WHEN pnl2.revenue IS NOT NULL AND pnl3.revenue IS NOT NULL
                       AND pnl2.revenue > pnl3.revenue THEN 1 ELSE 0 END
         )::smallint END AS revenue_growth_consistency,

    NOW()

FROM market.companies_current c

-- ── Latest close price + open/volume ────────────────────────────────────────
-- Separated from range aggregates to avoid slow window-function scan.
LEFT JOIN LATERAL (
    SELECT close, open, volume,
           DATE(time AT TIME ZONE 'Australia/Sydney') AS price_date
    FROM market.daily_prices
    WHERE asx_code = c.asx_code
    ORDER BY time DESC
    LIMIT 1
) dp ON TRUE

-- ── 52-week high/low (simple MAX/MIN aggregate — much faster than window fn) ─
LEFT JOIN LATERAL (
    SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
    FROM market.daily_prices
    WHERE asx_code = c.asx_code
      AND time >= NOW() - INTERVAL '365 days'
) dp52 ON TRUE

-- ── 20-day avg volume (LIMIT 20 aggregate — scans only 20 rows per stock) ────
LEFT JOIN LATERAL (
    SELECT AVG(volume) AS avg_volume_20d
    FROM (
        SELECT volume
        FROM market.daily_prices
        WHERE asx_code = c.asx_code
        ORDER BY time DESC
        LIMIT 20
    ) v20
) dp20 ON TRUE

-- ── Valuation snapshot (EODHD weekly refresh) ─────────────────────────────────
LEFT JOIN market.valuation_snapshot vs ON vs.asx_code = c.asx_code

-- ── Latest ex-dividend date ───────────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT ex_date, franking_pct FROM market.dividends
    WHERE asx_code = c.asx_code
    ORDER BY ex_date DESC
    LIMIT 1
) div_latest ON TRUE

-- ── Annual P&L FY0 (most recent) ─────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT fiscal_year, revenue, cost_of_sales, gross_profit, ebit, ebitda,
           depreciation, interest_expense, pbt, tax, net_profit, eps
    FROM financials.annual_pnl
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) pnl0 ON TRUE

-- ── Annual P&L FY1 (second most recent) ──────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT fiscal_year, revenue, gross_profit, ebitda, pbt, net_profit, eps
    FROM financials.annual_pnl
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1 OFFSET 1
) pnl1 ON TRUE

-- ── Annual P&L history (2/3/5/7/10 fiscal years back, for level + growth screening)
LEFT JOIN LATERAL (
    SELECT revenue, pbt FROM financials.annual_pnl
    WHERE asx_code = c.asx_code ORDER BY fiscal_year DESC LIMIT 1 OFFSET 2
) pnl2 ON TRUE
LEFT JOIN LATERAL (
    SELECT revenue, gross_profit, pbt, net_profit FROM financials.annual_pnl
    WHERE asx_code = c.asx_code ORDER BY fiscal_year DESC LIMIT 1 OFFSET 3
) pnl3 ON TRUE
LEFT JOIN LATERAL (
    SELECT revenue, gross_profit, pbt, net_profit FROM financials.annual_pnl
    WHERE asx_code = c.asx_code ORDER BY fiscal_year DESC LIMIT 1 OFFSET 5
) pnl5 ON TRUE
LEFT JOIN LATERAL (
    SELECT revenue, gross_profit, pbt, net_profit FROM financials.annual_pnl
    WHERE asx_code = c.asx_code ORDER BY fiscal_year DESC LIMIT 1 OFFSET 7
) pnl7 ON TRUE
LEFT JOIN LATERAL (
    SELECT revenue, gross_profit, pbt, net_profit FROM financials.annual_pnl
    WHERE asx_code = c.asx_code ORDER BY fiscal_year DESC LIMIT 1 OFFSET 10
) pnl10 ON TRUE

-- ── Balance Sheet (latest FY) ─────────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT total_assets, total_equity, total_debt, net_debt,
           cash_equivalents, book_value_per_share,
           total_current_assets, total_current_liab,
           trade_receivables, inventory, goodwill, intangibles, gross_block,
           total_liabilities, long_term_debt, retained_earnings
    FROM financials.annual_balance_sheet
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) bs0 ON TRUE

-- ── Cash Flow (latest FY) ─────────────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT cfo, capex, fcf, cfi, dividends_paid
    FROM financials.annual_cashflow
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) cf0 ON TRUE

-- ── Computed metrics (daily compute — freshest ratios & margins) ──────────────
LEFT JOIN LATERAL (
    SELECT roe, roa, roce, opm, npm, gpm, ebitda_margin,
           grossed_up_yield, fcf_yield,
           revenue_growth_1y, revenue_growth_3y,
           profit_growth_1y,  profit_growth_3y
    FROM market.computed_metrics
    WHERE asx_code = c.asx_code
    ORDER BY time DESC
    LIMIT 1
) cm ON TRUE

-- ── Weekly metrics (latest week — return_1w, SMAs, BB, ATR, OBV) ─────────────
LEFT JOIN LATERAL (
    SELECT weekly_return,
           sma_10w, sma_20w, sma_40w, ema_13w,
           bb_upper, bb_lower, atr_14, obv,
           above_sma10w, above_sma40w, golden_cross, death_cross
    FROM market.weekly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY week_date DESC
    LIMIT 1
) wm ON TRUE

-- ── Monthly metrics (latest month — returns, momentum, volatility, technicals)
LEFT JOIN LATERAL (
    SELECT monthly_return, return_3m, return_6m, return_12m, return_ytd,
           momentum_3m, momentum_6m, momentum_12m,
           volatility_1m, volatility_3m,
           drawdown_from_ath,
           rsi_14, macd_line, macd_signal
    FROM market.monthly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY month_date DESC
    LIMIT 1
) mm ON TRUE

-- ── Daily metrics (latest date — exact technical indicators) ──────────────────
LEFT JOIN LATERAL (
    SELECT rsi_14, macd_line, macd_signal,
           sma_20, sma_50, sma_200, ema_20,
           bb_upper, bb_lower, atr_14, adx_14, obv,
           hv_20d, hv_60d, pct_from_ath,
           return_1w, return_1m, return_3m, return_6m, return_ytd, return_1y,
           above_vwap, dollar_volume_avg_20d,
           -- Tier 2 signals
           dma50_ratio, dma200_ratio,
           above_sma50, above_sma200,
           golden_cross, death_cross,
           relative_volume,
           bb_pct, rsi_21, stoch_k, stoch_d,
           rsi_overbought, rsi_oversold,
           macd_bullish_cross, macd_bearish_cross,
           -- Volume signals
           volume_avg_50d, cmf_20,
           up_down_vol_ratio_20d, obv_rising, volume_breakout
    FROM market.daily_metrics
    WHERE asx_code = c.asx_code
    ORDER BY date DESC
    LIMIT 1
) dm ON TRUE

-- ── Yearly metrics (latest FY — CAGRs, quality scores, risk) ─────────────────
LEFT JOIN LATERAL (
    SELECT roe, roa, roce,
           fcf_yield, franked_yield,
           revenue_growth_1y, revenue_cagr_3y, revenue_cagr_5y,
           net_income_growth_1y, net_income_cagr_3y,
           eps_cagr_3y,
           avg_roe_3y,
           piotroski_f_score, altman_z_score,
           sharpe_1y, max_drawdown_1y,
           beta_1y,
           dividend_cagr_3y, dividend_consecutive_yrs,
           return_3y, return_5y, return_7y, return_10y, return_15y,
           -- Quick-win metrics
           ocf_to_net_profit, fcf_payout_ratio, shares_dilution_3y,
           eps_volatility_5y, fcf_positive_years,
           -- Partial metrics
           avg_roic_3y, avg_roic_5y, asset_light_score,
           -- Quality proxy scores
           brand_proxy_score, capital_efficiency_score, earnings_stability_score,
           -- Per-share & valuation derived (used for COALESCE + payout_ratio)
           eps, bvps, graham_number, ev_ebit, p_fcf_ratio,
           -- Efficiency & leverage (Group 3 columns)
           roic, asset_turnover, interest_coverage, net_debt_to_ebitda,
           -- Margins / efficiency (new columns)
           ocf_margin, fcf_margin, capex_intensity, receivables_days,
           -- Leverage (new columns)
           debt_to_assets, lt_debt_to_capital,
           -- 1-year growth (new columns)
           ebitda_growth_1y, fcf_growth_1y, eps_growth_1y,
           -- Multi-year CAGRs (new columns)
           revenue_cagr_7y, revenue_cagr_10y, net_income_cagr_5y, eps_cagr_5y,
           ebitda_cagr_3y, ebitda_cagr_5y, fcf_cagr_3y, fcf_cagr_5y,
           dividend_cagr_5y, bvps_cagr_3y, bvps_cagr_5y,
           -- Rolling averages (new columns)
           avg_roe_5y, avg_roa_3y, avg_roa_5y, avg_roce_3y, avg_roce_5y,
           avg_gross_margin_3y, avg_gross_margin_5y,
           avg_ebitda_margin_3y, avg_ebitda_margin_5y,
           avg_operating_margin_3y, avg_operating_margin_5y,
           avg_net_margin_3y, avg_net_margin_5y,
           avg_eps_growth_3y, avg_eps_growth_5y
    FROM market.yearly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) ym ON TRUE

-- ── Quarterly metrics (latest quarter — QoQ and YoY growth) ──────────────────
LEFT JOIN LATERAL (
    SELECT revenue_growth_yoy, eps_growth_yoy, net_income_growth_yoy
    FROM market.quarterly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC, quarter DESC
    LIMIT 1
) qm ON TRUE

-- ── Half-yearly metrics (latest half — HoH growth) ───────────────────────────
LEFT JOIN LATERAL (
    SELECT revenue_growth_hoh, net_income_growth_hoh, eps_growth_hoh
    FROM market.halfyearly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY period_end_date DESC
    LIMIT 1
) hym ON TRUE

-- ── Analyst ratings ───────────────────────────────────────────────────────────
LEFT JOIN market.analyst_ratings ar ON ar.asx_code = c.asx_code

-- ── Shares outstanding + ownership (staging — most recently loaded) ──────────
LEFT JOIN LATERAL (
    SELECT
        shares_outstanding::BIGINT,
        percent_insiders,
        percent_institutions
    FROM staging_au.shares_stats
    WHERE asx_code = c.asx_code
    LIMIT 1
) ss ON TRUE

-- ── market.companies (admin-maintained tags) ─────────────────────────────────
LEFT JOIN LATERAL (
    SELECT business_model_tag, commodity_exposure
    FROM market.companies
    WHERE asx_code = c.asx_code
      AND is_current = TRUE
    LIMIT 1
) mc ON TRUE

-- ── ASIC short interest (latest report date per stock) ──────────────────────
-- Prefer market.short_positions (has WoW change); fall back to short_interest.
LEFT JOIN LATERAL (
    SELECT
        short_pct,
        short_shares,
        short_pct_chg_1w
    FROM market.short_positions
    WHERE asx_code = c.asx_code
    ORDER BY report_date DESC
    LIMIT 1
) si ON TRUE

{code_filter}

ON CONFLICT (asx_code) DO UPDATE SET
    -- Identity
    company_name            = EXCLUDED.company_name,
    sector                  = EXCLUDED.sector,
    industry_group          = EXCLUDED.industry_group,
    industry                = EXCLUDED.industry,
    sub_industry            = EXCLUDED.sub_industry,
    stock_type              = EXCLUDED.stock_type,
    status                  = EXCLUDED.status,
    fiscal_year_end_month   = EXCLUDED.fiscal_year_end_month,
    is_reit                 = EXCLUDED.is_reit,
    is_miner                = EXCLUDED.is_miner,
    is_mega                 = EXCLUDED.is_mega,
    is_large                = EXCLUDED.is_large,
    is_mid                  = EXCLUDED.is_mid,
    is_small                = EXCLUDED.is_small,
    is_micro                = EXCLUDED.is_micro,
    is_nano                 = EXCLUDED.is_nano,
    market_cap_tier         = EXCLUDED.market_cap_tier,
    is_asx20                = EXCLUDED.is_asx20,
    is_asx50                = EXCLUDED.is_asx50,
    is_asx100               = EXCLUDED.is_asx100,
    is_asx200               = EXCLUDED.is_asx200,
    is_asx300               = EXCLUDED.is_asx300,
    is_all_ords             = EXCLUDED.is_all_ords,
    isin                    = EXCLUDED.isin,
    website                 = EXCLUDED.website,
    description             = EXCLUDED.description,
    -- Price
    price                   = EXCLUDED.price,
    price_date              = EXCLUDED.price_date,
    open                    = EXCLUDED.open,
    volume                  = EXCLUDED.volume,
    avg_volume_20d          = EXCLUDED.avg_volume_20d,
    market_cap              = EXCLUDED.market_cap,
    high_52w                = EXCLUDED.high_52w,
    low_52w                 = EXCLUDED.low_52w,
    -- Valuation
    pe_ratio                = EXCLUDED.pe_ratio,
    forward_pe              = EXCLUDED.forward_pe,
    peg_ratio               = EXCLUDED.peg_ratio,
    price_to_book           = EXCLUDED.price_to_book,
    price_to_sales          = EXCLUDED.price_to_sales,
    ev                      = EXCLUDED.ev,
    ev_to_ebitda            = EXCLUDED.ev_to_ebitda,
    ev_to_revenue           = EXCLUDED.ev_to_revenue,
    ev_to_ebit              = EXCLUDED.ev_to_ebit,
    price_to_fcf            = EXCLUDED.price_to_fcf,
    graham_number           = EXCLUDED.graham_number,
    -- Dividends
    dividend_yield          = EXCLUDED.dividend_yield,
    dps_ttm                 = EXCLUDED.dps_ttm,
    ex_div_date             = EXCLUDED.ex_div_date,
    franking_pct            = EXCLUDED.franking_pct,
    payout_ratio            = EXCLUDED.payout_ratio,
    -- Profitability
    revenue_ttm             = EXCLUDED.revenue_ttm,
    gross_profit_ttm        = EXCLUDED.gross_profit_ttm,
    ebitda_ttm              = EXCLUDED.ebitda_ttm,
    gross_margin            = EXCLUDED.gross_margin,
    ebitda_margin           = EXCLUDED.ebitda_margin,
    net_margin              = EXCLUDED.net_margin,
    operating_margin        = EXCLUDED.operating_margin,
    roe                     = EXCLUDED.roe,
    roa                     = EXCLUDED.roa,
    roce                    = EXCLUDED.roce,
    roic                    = EXCLUDED.roic,
    asset_turnover          = EXCLUDED.asset_turnover,
    ocf_margin              = EXCLUDED.ocf_margin,
    fcf_margin              = EXCLUDED.fcf_margin,
    capex_intensity         = EXCLUDED.capex_intensity,
    grossed_up_yield        = EXCLUDED.grossed_up_yield,
    fcf_yield               = EXCLUDED.fcf_yield,
    -- EPS
    eps_fy0                 = EXCLUDED.eps_fy0,
    eps_fy1                 = EXCLUDED.eps_fy1,
    -- Income Statement
    revenue_fy0             = EXCLUDED.revenue_fy0,
    revenue_fy1             = EXCLUDED.revenue_fy1,
    ebitda_fy0              = EXCLUDED.ebitda_fy0,
    ebitda_fy1              = EXCLUDED.ebitda_fy1,
    net_profit_fy0          = EXCLUDED.net_profit_fy0,
    net_profit_fy1          = EXCLUDED.net_profit_fy1,
    -- Balance Sheet
    total_assets            = EXCLUDED.total_assets,
    total_equity            = EXCLUDED.total_equity,
    total_debt              = EXCLUDED.total_debt,
    net_debt                = EXCLUDED.net_debt,
    cash                    = EXCLUDED.cash,
    book_value_per_share    = EXCLUDED.book_value_per_share,
    debt_to_equity          = EXCLUDED.debt_to_equity,
    current_ratio           = EXCLUDED.current_ratio,
    net_debt_to_ebitda      = EXCLUDED.net_debt_to_ebitda,
    interest_coverage       = EXCLUDED.interest_coverage,
    debt_to_assets          = EXCLUDED.debt_to_assets,
    lt_debt_to_capital      = EXCLUDED.lt_debt_to_capital,
    -- Cash Flow
    cfo_fy0                 = EXCLUDED.cfo_fy0,
    capex_fy0               = EXCLUDED.capex_fy0,
    fcf_fy0                 = EXCLUDED.fcf_fy0,
    -- Growth rates
    revenue_growth_1y       = EXCLUDED.revenue_growth_1y,
    revenue_growth_3y_cagr  = EXCLUDED.revenue_growth_3y_cagr,
    earnings_growth_1y      = EXCLUDED.earnings_growth_1y,
    earnings_growth_3y_cagr = EXCLUDED.earnings_growth_3y_cagr,
    ebitda_growth_1y        = EXCLUDED.ebitda_growth_1y,
    fcf_growth_1y           = EXCLUDED.fcf_growth_1y,
    eps_growth_1y           = EXCLUDED.eps_growth_1y,
    -- Returns & momentum
    return_1w               = EXCLUDED.return_1w,
    return_1m               = EXCLUDED.return_1m,
    return_3m               = EXCLUDED.return_3m,
    return_6m               = EXCLUDED.return_6m,
    return_1y               = EXCLUDED.return_1y,
    return_ytd              = EXCLUDED.return_ytd,
    momentum_3m             = EXCLUDED.momentum_3m,
    momentum_6m             = EXCLUDED.momentum_6m,
    momentum_12m            = EXCLUDED.momentum_12m,
    -- Volatility & risk
    volatility_20d          = EXCLUDED.volatility_20d,
    volatility_60d          = EXCLUDED.volatility_60d,
    sharpe_1y               = EXCLUDED.sharpe_1y,
    drawdown_from_ath       = EXCLUDED.drawdown_from_ath,
    beta_1y                 = EXCLUDED.beta_1y,
    -- Technicals
    rsi_14                  = EXCLUDED.rsi_14,
    macd                    = EXCLUDED.macd,
    macd_signal             = EXCLUDED.macd_signal,
    sma_20                  = EXCLUDED.sma_20,
    sma_50                  = EXCLUDED.sma_50,
    sma_200                 = EXCLUDED.sma_200,
    ema_20                  = EXCLUDED.ema_20,
    bb_upper                = EXCLUDED.bb_upper,
    bb_lower                = EXCLUDED.bb_lower,
    atr_14                  = EXCLUDED.atr_14,
    adx_14                  = EXCLUDED.adx_14,
    obv                     = EXCLUDED.obv,
    -- Multi-year quality & CAGR
    piotroski_f_score       = EXCLUDED.piotroski_f_score,
    altman_z_score          = EXCLUDED.altman_z_score,
    revenue_cagr_5y         = EXCLUDED.revenue_cagr_5y,
    eps_growth_3y_cagr      = EXCLUDED.eps_growth_3y_cagr,
    revenue_cagr_7y         = EXCLUDED.revenue_cagr_7y,
    revenue_cagr_10y        = EXCLUDED.revenue_cagr_10y,
    net_income_cagr_5y      = EXCLUDED.net_income_cagr_5y,
    eps_cagr_5y             = EXCLUDED.eps_cagr_5y,
    ebitda_cagr_3y          = EXCLUDED.ebitda_cagr_3y,
    ebitda_cagr_5y          = EXCLUDED.ebitda_cagr_5y,
    fcf_cagr_3y             = EXCLUDED.fcf_cagr_3y,
    fcf_cagr_5y             = EXCLUDED.fcf_cagr_5y,
    avg_roe_3y              = EXCLUDED.avg_roe_3y,
    avg_roe_5y              = EXCLUDED.avg_roe_5y,
    avg_roa_3y              = EXCLUDED.avg_roa_3y,
    avg_roa_5y              = EXCLUDED.avg_roa_5y,
    avg_roce_3y             = EXCLUDED.avg_roce_3y,
    avg_roce_5y             = EXCLUDED.avg_roce_5y,
    avg_gross_margin_3y     = EXCLUDED.avg_gross_margin_3y,
    avg_gross_margin_5y     = EXCLUDED.avg_gross_margin_5y,
    avg_ebitda_margin_3y    = EXCLUDED.avg_ebitda_margin_3y,
    avg_ebitda_margin_5y    = EXCLUDED.avg_ebitda_margin_5y,
    avg_operating_margin_3y = EXCLUDED.avg_operating_margin_3y,
    avg_operating_margin_5y = EXCLUDED.avg_operating_margin_5y,
    avg_net_margin_3y       = EXCLUDED.avg_net_margin_3y,
    avg_net_margin_5y       = EXCLUDED.avg_net_margin_5y,
    avg_eps_growth_3y       = EXCLUDED.avg_eps_growth_3y,
    avg_eps_growth_5y       = EXCLUDED.avg_eps_growth_5y,
    dividend_cagr_3y        = EXCLUDED.dividend_cagr_3y,
    dividend_consecutive_yrs = EXCLUDED.dividend_consecutive_yrs,
    dividend_cagr_5y        = EXCLUDED.dividend_cagr_5y,
    bvps_cagr_3y            = EXCLUDED.bvps_cagr_3y,
    bvps_cagr_5y            = EXCLUDED.bvps_cagr_5y,
    return_3y               = EXCLUDED.return_3y,
    return_5y               = EXCLUDED.return_5y,
    return_7y               = EXCLUDED.return_7y,
    return_10y              = EXCLUDED.return_10y,
    return_15y              = EXCLUDED.return_15y,
    -- Latest-quarter growth
    revenue_growth_yoy_q    = EXCLUDED.revenue_growth_yoy_q,
    eps_growth_yoy_q        = EXCLUDED.eps_growth_yoy_q,
    net_income_growth_yoy_q = EXCLUDED.net_income_growth_yoy_q,
    -- Half-yearly HoH growth
    revenue_growth_hoh      = EXCLUDED.revenue_growth_hoh,
    net_income_growth_hoh   = EXCLUDED.net_income_growth_hoh,
    eps_growth_hoh          = EXCLUDED.eps_growth_hoh,
    -- Analyst
    analyst_rating          = EXCLUDED.analyst_rating,
    analyst_target_price    = EXCLUDED.analyst_target_price,
    analyst_strong_buy      = EXCLUDED.analyst_strong_buy,
    analyst_buy             = EXCLUDED.analyst_buy,
    analyst_hold            = EXCLUDED.analyst_hold,
    analyst_sell            = EXCLUDED.analyst_sell,
    analyst_strong_sell     = EXCLUDED.analyst_strong_sell,
    -- Short interest (ASIC)
    short_pct               = EXCLUDED.short_pct,
    short_position_shares   = EXCLUDED.short_position_shares,
    short_interest_chg_1w   = EXCLUDED.short_interest_chg_1w,
    -- Shares & Ownership
    shares_outstanding      = EXCLUDED.shares_outstanding,
    percent_insiders        = EXCLUDED.percent_insiders,
    percent_institutions    = EXCLUDED.percent_institutions,
    -- Quick-win metrics
    ocf_to_net_profit       = EXCLUDED.ocf_to_net_profit,
    fcf_payout_ratio        = EXCLUDED.fcf_payout_ratio,
    shares_dilution_3y      = EXCLUDED.shares_dilution_3y,
    eps_volatility_5y       = EXCLUDED.eps_volatility_5y,
    fcf_positive_years      = EXCLUDED.fcf_positive_years,
    above_vwap              = EXCLUDED.above_vwap,
    -- Partial metrics
    dollar_volume_avg_20d   = EXCLUDED.dollar_volume_avg_20d,
    avg_roic_3y             = EXCLUDED.avg_roic_3y,
    -- Volume signals
    avg_volume_50d          = EXCLUDED.avg_volume_50d,
    cmf_20                  = EXCLUDED.cmf_20,
    up_down_vol_ratio_20d   = EXCLUDED.up_down_vol_ratio_20d,
    obv_rising              = EXCLUDED.obv_rising,
    volume_breakout         = EXCLUDED.volume_breakout,
    avg_roic_5y             = EXCLUDED.avg_roic_5y,
    asset_light_score       = EXCLUDED.asset_light_score,
    -- Analyst-derived
    analyst_count           = EXCLUDED.analyst_count,
    analyst_buy_pct         = EXCLUDED.analyst_buy_pct,
    analyst_consensus_score = EXCLUDED.analyst_consensus_score,
    -- Quality proxy scores
    brand_proxy_score       = EXCLUDED.brand_proxy_score,
    capital_efficiency_score = EXCLUDED.capital_efficiency_score,
    earnings_stability_score = EXCLUDED.earnings_stability_score,
    -- Admin tags
    business_model_tag      = EXCLUDED.business_model_tag,
    commodity_exposure      = EXCLUDED.commodity_exposure,
    -- Tier 2 daily signals
    dma50_ratio             = EXCLUDED.dma50_ratio,
    dma200_ratio            = EXCLUDED.dma200_ratio,
    above_sma50             = EXCLUDED.above_sma50,
    above_sma200            = EXCLUDED.above_sma200,
    golden_cross            = EXCLUDED.golden_cross,
    death_cross             = EXCLUDED.death_cross,
    new_52w_high            = EXCLUDED.new_52w_high,
    new_52w_low             = EXCLUDED.new_52w_low,
    relative_volume         = EXCLUDED.relative_volume,
    bb_pct                  = EXCLUDED.bb_pct,
    rsi_21                  = EXCLUDED.rsi_21,
    stoch_k                 = EXCLUDED.stoch_k,
    stoch_d                 = EXCLUDED.stoch_d,
    rsi_overbought          = EXCLUDED.rsi_overbought,
    rsi_oversold            = EXCLUDED.rsi_oversold,
    macd_bullish_cross      = EXCLUDED.macd_bullish_cross,
    macd_bearish_cross      = EXCLUDED.macd_bearish_cross,
    -- Per-share & working capital
    ocf_per_share           = EXCLUDED.ocf_per_share,
    fcf_per_share           = EXCLUDED.fcf_per_share,
    revenue_per_share       = EXCLUDED.revenue_per_share,
    working_capital         = EXCLUDED.working_capital,
    price_to_52w_low        = EXCLUDED.price_to_52w_low,
    -- Income statement history (annual levels)
    gross_profit_fy0        = EXCLUDED.gross_profit_fy0,
    gross_profit_fy1        = EXCLUDED.gross_profit_fy1,
    gross_profit_fy3        = EXCLUDED.gross_profit_fy3,
    gross_profit_fy5        = EXCLUDED.gross_profit_fy5,
    gross_profit_fy7        = EXCLUDED.gross_profit_fy7,
    gross_profit_fy10       = EXCLUDED.gross_profit_fy10,
    pbt_fy0                 = EXCLUDED.pbt_fy0,
    pbt_fy1                 = EXCLUDED.pbt_fy1,
    pbt_fy3                 = EXCLUDED.pbt_fy3,
    pbt_fy5                 = EXCLUDED.pbt_fy5,
    pbt_fy7                 = EXCLUDED.pbt_fy7,
    pbt_fy10                = EXCLUDED.pbt_fy10,
    revenue_fy3             = EXCLUDED.revenue_fy3,
    revenue_fy5             = EXCLUDED.revenue_fy5,
    revenue_fy7             = EXCLUDED.revenue_fy7,
    revenue_fy10            = EXCLUDED.revenue_fy10,
    net_profit_fy3          = EXCLUDED.net_profit_fy3,
    net_profit_fy5          = EXCLUDED.net_profit_fy5,
    net_profit_fy7          = EXCLUDED.net_profit_fy7,
    net_profit_fy10         = EXCLUDED.net_profit_fy10,
    -- Growth rates
    sales_growth_prev_y     = EXCLUDED.sales_growth_prev_y,
    pbt_growth_1y           = EXCLUDED.pbt_growth_1y,
    pbt_growth_prev_y       = EXCLUDED.pbt_growth_prev_y,
    pbt_cagr_3y             = EXCLUDED.pbt_cagr_3y,
    pbt_cagr_5y             = EXCLUDED.pbt_cagr_5y,
    pbt_cagr_7y             = EXCLUDED.pbt_cagr_7y,
    pbt_cagr_10y            = EXCLUDED.pbt_cagr_10y,
    -- Income-statement & balance-sheet line items
    cogs                    = EXCLUDED.cogs,
    ebit                    = EXCLUDED.ebit,
    income_tax_expense      = EXCLUDED.income_tax_expense,
    interest_expense        = EXCLUDED.interest_expense,
    depreciation            = EXCLUDED.depreciation,
    trade_receivables       = EXCLUDED.trade_receivables,
    inventory               = EXCLUDED.inventory,
    goodwill                = EXCLUDED.goodwill,
    intangibles             = EXCLUDED.intangibles,
    ppe_net                 = EXCLUDED.ppe_net,
    total_current_assets    = EXCLUDED.total_current_assets,
    total_current_liabilities = EXCLUDED.total_current_liabilities,
    total_liabilities       = EXCLUDED.total_liabilities,
    long_term_debt          = EXCLUDED.long_term_debt,
    retained_earnings       = EXCLUDED.retained_earnings,
    cfi                     = EXCLUDED.cfi,
    dividends_paid          = EXCLUDED.dividends_paid,
    -- Derived ratios
    quick_ratio             = EXCLUDED.quick_ratio,
    cash_ratio              = EXCLUDED.cash_ratio,
    debt_to_ebitda          = EXCLUDED.debt_to_ebitda,
    days_sales_outstanding  = EXCLUDED.days_sales_outstanding,
    days_inventory_outstanding = EXCLUDED.days_inventory_outstanding,
    inventory_turnover      = EXCLUDED.inventory_turnover,
    receivables_turnover    = EXCLUDED.receivables_turnover,
    pretax_margin           = EXCLUDED.pretax_margin,
    nopat                   = EXCLUDED.nopat,
    ebitda_interest_coverage = EXCLUDED.ebitda_interest_coverage,
    equity_ratio            = EXCLUDED.equity_ratio,
    liabilities_to_assets   = EXCLUDED.liabilities_to_assets,
    fixed_asset_turnover    = EXCLUDED.fixed_asset_turnover,
    capex_to_revenue        = EXCLUDED.capex_to_revenue,
    tangible_book_value_per_share = EXCLUDED.tangible_book_value_per_share,
    cash_per_share          = EXCLUDED.cash_per_share,
    revenue_fy2             = EXCLUDED.revenue_fy2,
    net_profit_ttm          = EXCLUDED.net_profit_ttm,
    price_to_cash_flow      = EXCLUDED.price_to_cash_flow,
    -- Profit-based signals
    operating_margin_expanding  = EXCLUDED.operating_margin_expanding,
    gross_margin_expanding      = EXCLUDED.gross_margin_expanding,
    fcf_conversion              = EXCLUDED.fcf_conversion,
    eps_beats_revenue_growth    = EXCLUDED.eps_beats_revenue_growth,
    operating_leverage          = EXCLUDED.operating_leverage,
    -- Sales-based signals
    revenue_growth_accelerating = EXCLUDED.revenue_growth_accelerating,
    revenue_growth_delta        = EXCLUDED.revenue_growth_delta,
    revenue_growth_consistency  = EXCLUDED.revenue_growth_consistency,
    universe_built_at       = NOW()
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        code_filter = f"WHERE c.asx_code IN ({placeholders})"
        params = [c.upper() for c in args.codes]
    else:
        code_filter = ""
        params = []

    sql = UPSERT_SQL.format(code_filter=code_filter)

    log.info(f"Building screener.universe {'for ' + str(args.codes) if args.codes else '(all stocks)'}…")
    cur.execute(sql, params)
    n = cur.rowcount
    conn.commit()

    cur.close()
    conn.close()
    log.info(f"DONE — {n:,} rows upserted into screener.universe")

    # Flush Redis screener cache so next request gets fresh data
    _flush_screener_cache()


if __name__ == "__main__":
    main()
