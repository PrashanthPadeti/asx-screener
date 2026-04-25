# ASX Screener — Compute Engine Design (LLD)

> Version 1.0 | April 2026
> Runs daily after price ingestion. Computes all 544+ metrics for 2,200 ASX stocks.

---

## 1. Compute Engine Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         COMPUTE ENGINE                                        │
│                                                                               │
│  INPUTS:                                                                      │
│  • market.daily_prices          (today's EOD prices)                         │
│  • market.short_interest        (today's ASIC short data)                    │
│  • financials.annual_pnl        (latest annual P&L)                          │
│  • financials.annual_balance_sheet                                           │
│  • financials.annual_cashflow                                                 │
│  • financials.half_year_pnl     (for TTM calculations)                       │
│  • market.dividends             (last 12 months)                             │
│  • market.technical_indicators  (computed in Stage 1)                        │
│                                                                               │
│  OUTPUTS:                                                                     │
│  • market.technical_indicators  (Stage 1)                                    │
│  • market.computed_metrics      (Stages 2–6)                                 │
│  • Redis cache invalidation     (Stage 7)                                    │
│  • Elasticsearch re-index       (Stage 7)                                    │
│                                                                               │
│  PERFORMANCE TARGETS:                                                         │
│  • 2,200 stocks × 544 metrics                                                │
│  • Target: < 20 minutes total                                                │
│  • Method: Pandas vectorized operations (no row-by-row loops)                │
│  • Parallelism: 16 worker processes × 140 stocks per worker                  │
│  • DB writes: single COPY statement per stage (bulk insert)                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Compute Pipeline — Stage Sequence

```
compute_engine.py
│
├── STAGE 0: Data Load (2 min)
│   Load all required data into memory as Pandas DataFrames
│   (one-time load at start, shared across all workers)
│
├── STAGE 1: Technical Indicators (4 min) — PARALLEL
│   Compute: DMA, RSI, MACD, ATR, Bollinger, OBV, Returns, 52W levels
│   Input:  daily_prices (last 200 trading days)
│   Output: technical_indicators table
│
├── STAGE 2: Valuation Ratios (3 min) — PARALLEL
│   Compute: PE, PB, PS, EV/EBITDA, FCF Yield, Graham Number, etc.
│   Input:  today's prices + latest financials + technical_indicators
│   Output: computed_metrics (valuation columns)
│
├── STAGE 3: Profitability & Efficiency (3 min) — PARALLEL
│   Compute: ROE, ROA, ROCE, ROIC, Margins, Turnover, CCC
│   Input:  annual P&L + balance sheet
│   Output: computed_metrics (profitability columns)
│
├── STAGE 4: Growth Metrics (3 min) — PARALLEL
│   Compute: 1Y/3Y/5Y/7Y/10Y CAGR for revenue, profit, EPS, FCF
│   Input:  annual_pnl history (10 years)
│   Output: computed_metrics (growth columns)
│
├── STAGE 5: Composite Scores & Risk (3 min) — PARALLEL
│   Compute: Piotroski, Altman Z, Beneish M, Beta, Sharpe
│   Input:  all financial data + price returns
│   Output: computed_metrics (score columns)
│
├── STAGE 6: ASX-Specific Metrics (2 min) — PARALLEL
│   Compute: Grossed-up yield, REIT metrics, mining NAV
│   Input:  dividends + mining_data + reit_data
│   Output: computed_metrics (asx-specific columns)
│
└── STAGE 7: Write & Cache Invalidation (2 min) — SEQUENTIAL
    Bulk write all computed_metrics to PostgreSQL
    Invalidate Redis keys for all stocks
    Sync Elasticsearch documents (async background)

TOTAL: ~20 minutes
```

---

## 3. Stage 0 — Data Load

```python
# compute_engine/data_loader.py

import pandas as pd
from sqlalchemy import create_engine
from datetime import date, timedelta


class DataLoader:
    """
    Loads all required data into memory at the start of the compute run.
    Uses efficient SQL queries with minimal data transfer.
    """

    def __init__(self, compute_date: date):
        self.compute_date = compute_date
        self.engine = create_engine(DATABASE_URL)

    def load_all(self) -> "ComputeContext":
        """Load all datasets in parallel using ThreadPoolExecutor."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                'prices_today':    executor.submit(self._load_prices_today),
                'prices_history':  executor.submit(self._load_prices_history),
                'annual_pnl':      executor.submit(self._load_annual_pnl),
                'balance_sheet':   executor.submit(self._load_balance_sheet),
                'cashflow':        executor.submit(self._load_cashflow),
                'half_year_pnl':   executor.submit(self._load_half_year_pnl),
                'dividends':       executor.submit(self._load_dividends),
                'short_interest':  executor.submit(self._load_short_interest),
                'companies':       executor.submit(self._load_companies),
                'mining_data':     executor.submit(self._load_mining_data),
                'reit_data':       executor.submit(self._load_reit_data),
            }
            return ComputeContext({k: f.result() for k, f in futures.items()})

    def _load_prices_today(self) -> pd.DataFrame:
        return pd.read_sql("""
            SELECT asx_code, open, high, low, close, adjusted_close, volume
            FROM market.daily_prices
            WHERE time = %(date)s
        """, self.engine, params={'date': self.compute_date},
            index_col='asx_code')

    def _load_prices_history(self) -> pd.DataFrame:
        """Load last 252 trading days for technical indicator computation."""
        return pd.read_sql("""
            SELECT time, asx_code, close, adjusted_close, volume, high, low
            FROM market.daily_prices
            WHERE time >= %(start)s AND time <= %(end)s
            ORDER BY asx_code, time
        """, self.engine, params={
            'start': self.compute_date - timedelta(days=400),
            'end': self.compute_date
        })

    def _load_annual_pnl(self) -> pd.DataFrame:
        """Load last 11 years of annual P&L (10 years + current for CAGR)."""
        return pd.read_sql("""
            SELECT asx_code, fiscal_year, revenue, gross_profit,
                   ebitda, ebit, interest_expense, pat, net_profit,
                   depreciation, eps, opm, npm, gpm, ebitda_margin,
                   dividend_paid, material_cost, employee_cost
            FROM financials.annual_pnl
            WHERE fiscal_year >= EXTRACT(YEAR FROM NOW()) - 11
            ORDER BY asx_code, fiscal_year DESC
        """, self.engine)

    def _load_balance_sheet(self) -> pd.DataFrame:
        """Load most recent balance sheet per company."""
        return pd.read_sql("""
            SELECT DISTINCT ON (asx_code)
                asx_code, total_assets, total_current_assets, total_current_liab,
                total_equity, total_debt, net_debt, cash_equivalents,
                working_capital, inventory, trade_receivables, trade_payables,
                net_block, goodwill, intangibles, book_value_per_share,
                shares_outstanding, contingent_liabilities, retained_earnings,
                fiscal_year
            FROM financials.annual_balance_sheet
            ORDER BY asx_code, fiscal_year DESC
        """, self.engine, index_col='asx_code')

    def _load_dividends(self) -> pd.DataFrame:
        """Load dividends paid in last 12 months."""
        return pd.read_sql("""
            SELECT asx_code, ex_date, amount_per_share, franking_pct,
                   grossed_up_amount, dividend_type
            FROM market.dividends
            WHERE ex_date >= %(start)s
              AND dividend_type != 'drp'
            ORDER BY asx_code, ex_date DESC
        """, self.engine, params={
            'start': self.compute_date - timedelta(days=366)
        })
```

---

## 4. Stage 1 — Technical Indicators

```python
# compute_engine/stages/technical.py

import pandas as pd
import numpy as np
from pandas_ta import rsi, macd, bbands, atr, obv


class TechnicalStage:
    """
    Computes all technical indicators using vectorized operations.
    Processes all stocks simultaneously using MultiIndex DataFrame.
    """

    def compute(self, ctx: ComputeContext) -> pd.DataFrame:
        prices = ctx.prices_history.copy()

        # Pivot to wide format: index=date, columns=asx_code, values=close
        close  = prices.pivot(index='time', columns='asx_code', values='adjusted_close')
        high   = prices.pivot(index='time', columns='asx_code', values='high')
        low    = prices.pivot(index='time', columns='asx_code', values='low')
        volume = prices.pivot(index='time', columns='asx_code', values='volume')

        results = {}
        today = ctx.compute_date

        # ── Moving Averages (vectorized across all stocks simultaneously) ──
        dma_50  = close.rolling(50).mean()
        dma_200 = close.rolling(200).mean()
        dma_20  = close.rolling(20).mean()
        ema_12  = close.ewm(span=12, adjust=False).mean()
        ema_26  = close.ewm(span=26, adjust=False).mean()

        results['dma_50']      = dma_50.loc[today]
        results['dma_200']     = dma_200.loc[today]
        results['dma_50_prev'] = dma_50.iloc[-2]
        results['dma_200_prev']= dma_200.iloc[-2]
        results['dma_50_ratio']= close.loc[today] / dma_50.loc[today]
        results['dma_200_ratio']= close.loc[today] / dma_200.loc[today]

        # ── Golden/Death Cross (crossover detection) ──
        prev_50_above_200 = dma_50.iloc[-2] > dma_200.iloc[-2]
        curr_50_above_200 = dma_50.loc[today] > dma_200.loc[today]
        results['golden_cross'] = (~prev_50_above_200) & curr_50_above_200
        results['death_cross']  = prev_50_above_200  & (~curr_50_above_200)
        results['above_dma_50'] = close.loc[today] > dma_50.loc[today]
        results['above_dma_200']= close.loc[today] > dma_200.loc[today]

        # ── MACD ──
        macd_line = ema_12 - ema_26
        macd_sig  = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_sig

        results['macd']             = macd_line.loc[today]
        results['macd_signal']      = macd_sig.loc[today]
        results['macd_histogram']   = macd_hist.loc[today]
        results['macd_prev']        = macd_line.iloc[-2]
        results['macd_signal_prev'] = macd_sig.iloc[-2]

        # ── RSI (14-period) ──
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, np.nan)
        results['rsi_14'] = (100 - 100 / (1 + rs)).loc[today]

        # ── ATR (14-period) ──
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ]).max(level=1)
        results['atr_14'] = tr.rolling(14).mean().loc[today]

        # ── Bollinger Bands (20-period, 2 std dev) ──
        bb_std = close.rolling(20).std()
        results['bollinger_upper'] = dma_20.loc[today] + 2 * bb_std.loc[today]
        results['bollinger_lower'] = dma_20.loc[today] - 2 * bb_std.loc[today]
        results['bollinger_mid']   = dma_20.loc[today]
        band_width = results['bollinger_upper'] - results['bollinger_lower']
        results['bollinger_pct'] = (
            (close.loc[today] - results['bollinger_lower']) / band_width
        ).clip(0, 1)

        # ── Volatility (20-day annualised) ──
        log_returns = np.log(close / close.shift(1))
        results['historical_volatility_20'] = (
            log_returns.rolling(20).std() * np.sqrt(252)
        ).loc[today]

        # ── Volume Metrics ──
        results['volume']         = volume.loc[today]
        results['volume_avg_5d']  = volume.rolling(5).mean().loc[today].astype(int)
        results['volume_avg_20d'] = volume.rolling(20).mean().loc[today].astype(int)
        results['volume_avg_60d'] = volume.rolling(60).mean().loc[today].astype(int)
        results['volume_ratio']   = volume.loc[today] / results['volume_avg_20d']

        # ── OBV (On-Balance Volume) ──
        price_direction = np.sign(close.diff())
        results['obv'] = (volume * price_direction).cumsum().loc[today].astype(int)

        # ── 52-Week Levels ──
        year_window = close.last('252B')  # Last 252 trading days
        results['high_52w'] = year_window.max()
        results['low_52w']  = year_window.min()
        results['pct_from_52w_high'] = (close.loc[today] / results['high_52w'] - 1)
        results['pct_from_52w_low']  = (close.loc[today] / results['low_52w']  - 1)

        range_size = results['high_52w'] - results['low_52w']
        results['range_52w_position'] = (
            (close.loc[today] - results['low_52w']) / range_size.replace(0, np.nan)
        ).clip(0, 1)

        results['new_52w_high'] = close.loc[today] >= results['high_52w']
        results['new_52w_low']  = close.loc[today] <= results['low_52w']

        # ── All-Time Levels ──
        # Loaded separately from pre-computed table
        results['high_all_time'] = ctx.all_time_levels['high_all_time']
        results['low_all_time']  = ctx.all_time_levels['low_all_time']
        results['pct_from_ath']  = (close.loc[today] / results['high_all_time'] - 1)
        results['pct_from_atl']  = (close.loc[today] / results['low_all_time']  - 1)

        # ── Returns ──
        def safe_return(n_days):
            try:
                past_close = close.iloc[-n_days - 1]
                return (close.loc[today] / past_close) - 1
            except IndexError:
                return pd.Series(np.nan, index=close.columns)

        results['return_1d']  = safe_return(1)
        results['return_1w']  = safe_return(5)
        results['return_1m']  = safe_return(21)
        results['return_3m']  = safe_return(63)
        results['return_6m']  = safe_return(126)

        # Annual/multi-year returns need longer price history
        results['return_1y']  = self._annual_return(close, 252)
        results['return_3y']  = self._cagr_return(close, 252 * 3)
        results['return_5y']  = self._cagr_return(close, 252 * 5)

        # ── Beta (1-year, vs XJO = ASX 200) ──
        results['beta_1y'] = self._compute_beta(close, ctx.index_prices['XJO'], 252)

        return pd.DataFrame(results)

    def _cagr_return(self, close: pd.DataFrame, n_days: int) -> pd.Series:
        """Annualised CAGR return over n_days."""
        if len(close) < n_days + 1:
            return pd.Series(np.nan, index=close.columns)
        years = n_days / 252
        total_return = close.iloc[-1] / close.iloc[-n_days - 1]
        return total_return ** (1 / years) - 1

    def _compute_beta(self, close: pd.DataFrame, index_series: pd.Series,
                      n_days: int) -> pd.Series:
        """Compute rolling beta vs index for all stocks simultaneously."""
        returns = close.pct_change().iloc[-n_days:]
        idx_ret = index_series.pct_change().iloc[-n_days:]
        idx_var = idx_ret.var()
        cov = returns.apply(lambda s: s.cov(idx_ret))
        return cov / idx_var
```

---

## 5. Stage 2 — Valuation Ratios

```python
# compute_engine/stages/valuation.py

class ValuationStage:

    def compute(self, ctx: ComputeContext, tech: pd.DataFrame) -> pd.DataFrame:
        prices   = ctx.prices_today['close']
        adj      = ctx.prices_today['adjusted_close']
        bs       = ctx.balance_sheet         # Latest balance sheet, indexed by asx_code
        pnl      = ctx.annual_pnl_latest     # Latest annual P&L, indexed by asx_code
        shares   = bs['shares_outstanding']
        divs     = ctx.dividends_ttm         # TTM dividends per share, indexed by asx_code

        # ── Market Cap ──
        market_cap = prices * shares / 1e6   # AUD millions

        # ── Enterprise Value ──
        # EV = Market Cap + Total Debt - Cash & Equivalents
        enterprise_value = (market_cap + bs['total_debt'] / 1e6
                            - bs['cash_equivalents'] / 1e6)

        # ── PE Ratio ──
        eps_ttm = ctx.eps_ttm    # Trailing 12-month EPS per share
        pe_ratio = prices / eps_ttm.replace(0, np.nan)
        pe_ratio = pe_ratio.where(eps_ttm > 0)  # Only positive earnings

        # ── PB Ratio ──
        pb_ratio = prices / bs['book_value_per_share'].replace(0, np.nan)

        # ── PS Ratio ──
        revenue_ttm = ctx.revenue_ttm / 1e6   # AUD millions
        ps_ratio = market_cap / revenue_ttm.replace(0, np.nan)

        # ── PCF Ratio ──
        ocf_per_share = ctx.ocf_ttm / shares.replace(0, np.nan) / 1e6
        pcf_ratio = prices / ocf_per_share.replace(0, np.nan)

        # ── PFCF Ratio ──
        fcf_per_share = ctx.fcf_ttm / shares.replace(0, np.nan) / 1e6
        pfcf_ratio = prices / fcf_per_share.replace(0, np.nan)

        # ── EV/EBITDA ──
        ebitda_ttm = ctx.ebitda_ttm / 1e6
        ev_ebitda = enterprise_value / ebitda_ttm.replace(0, np.nan)

        # ── EV/EBIT ──
        ebit_ttm = ctx.ebit_ttm / 1e6
        ev_ebit = enterprise_value / ebit_ttm.replace(0, np.nan)

        # ── EV/Sales ──
        ev_sales = enterprise_value / revenue_ttm.replace(0, np.nan)

        # ── EV/FCF ──
        fcf_ttm = ctx.fcf_ttm / 1e6
        ev_fcf = enterprise_value / fcf_ttm.replace(0, np.nan)

        # ── Earnings Yield ──
        earnings_yield = eps_ttm / prices.replace(0, np.nan)

        # ── FCF Yield ──
        fcf_yield = fcf_ttm / market_cap.replace(0, np.nan)

        # ── Dividend Yield ──
        dividend_yield = divs['dps_ttm'] / prices.replace(0, np.nan)

        # ── Franking Credit Yield (ASX-specific) ──
        franking_pct   = divs['weighted_franking_pct'] / 100  # 0–1
        corp_tax_rate  = 0.30                                   # Australian corporate rate
        franking_credit_per_share = (divs['dps_ttm'] * franking_pct
                                     * corp_tax_rate / (1 - corp_tax_rate))
        grossed_up_dividend = divs['dps_ttm'] + franking_credit_per_share
        grossed_up_yield    = grossed_up_dividend / prices.replace(0, np.nan)

        # ── Graham Number ──
        # = sqrt(22.5 × EPS × Book Value per Share)
        graham_number = np.sqrt(
            22.5 * eps_ttm.clip(lower=0) * bs['book_value_per_share'].clip(lower=0)
        )

        # ── NCAVPS (Net Current Asset Value per Share) ──
        # = (Current Assets - Total Liabilities) / Shares
        ncavps = ((bs['total_current_assets'] - bs['total_liabilities'])
                  / shares.replace(0, np.nan))

        # ── PB × PE ──
        pb_x_pe = pb_ratio * pe_ratio

        # ── PEG Ratio ──
        peg_ratio = pe_ratio / (ctx.eps_growth_1y * 100).replace(0, np.nan)

        return pd.DataFrame({
            'market_cap': market_cap,
            'enterprise_value': enterprise_value,
            'pe_ratio': pe_ratio.clip(-999, 9999),
            'pb_ratio': pb_ratio.clip(0, 999),
            'ps_ratio': ps_ratio.clip(0, 999),
            'pcf_ratio': pcf_ratio.clip(-999, 9999),
            'pfcf_ratio': pfcf_ratio.clip(-999, 9999),
            'ev_ebitda': ev_ebitda.clip(-99, 999),
            'ev_ebit': ev_ebit.clip(-99, 999),
            'ev_sales': ev_sales.clip(0, 999),
            'ev_fcf': ev_fcf.clip(-99, 9999),
            'peg_ratio': peg_ratio.clip(-99, 999),
            'earnings_yield': earnings_yield,
            'fcf_yield': fcf_yield,
            'dividend_yield': dividend_yield,
            'grossed_up_yield': grossed_up_yield,
            'dividend_per_share': divs['dps_ttm'],
            'franking_pct': divs['weighted_franking_pct'],
            'grossed_up_dividend': grossed_up_dividend,
            'graham_number': graham_number,
            'ncavps': ncavps,
            'pb_x_pe': pb_x_pe,
        })
```

---

## 6. Stage 3 — Profitability & Efficiency

```python
# compute_engine/stages/profitability.py

class ProfitabilityStage:

    def compute(self, ctx: ComputeContext) -> pd.DataFrame:
        pnl = ctx.annual_pnl_latest
        bs  = ctx.balance_sheet
        cf  = ctx.cashflow_latest

        # ── ROE ──
        roe = pnl['net_profit'] / bs['total_equity'].replace(0, np.nan)

        # ── ROA ──
        roa = pnl['net_profit'] / bs['total_assets'].replace(0, np.nan)

        # ── ROCE (Return on Capital Employed) ──
        # Capital Employed = Total Assets - Current Liabilities
        capital_employed = bs['total_assets'] - bs['total_current_liab']
        roce = pnl['ebit'] / capital_employed.replace(0, np.nan)

        # ── ROIC (Return on Invested Capital) ──
        # NOPAT = EBIT × (1 - tax_rate)
        tax_rate = (pnl['tax'] / pnl['pbt'].replace(0, np.nan)).clip(0, 0.50)
        nopat    = pnl['ebit'] * (1 - tax_rate)
        invested_capital = bs['total_equity'] + bs['total_debt'] - bs['cash_equivalents']
        roic = nopat / invested_capital.replace(0, np.nan)

        # ── CROIC (Cash Return on Invested Capital) ──
        croic = cf['fcf'] / invested_capital.replace(0, np.nan)

        # ── Margins ──
        revenue = pnl['revenue'].replace(0, np.nan)
        opm     = pnl['ebit'] / revenue
        npm     = pnl['net_profit'] / revenue
        gpm     = pnl['gross_profit'] / revenue
        ebitda_margin = pnl['ebitda'] / revenue
        ebit_margin   = pnl['ebit'] / revenue

        # ── Asset Turnover ──
        asset_turnover = pnl['revenue'] / bs['total_assets'].replace(0, np.nan)

        # ── Inventory Turnover ──
        inv_turnover = pnl['ebit'] / bs['inventory'].replace(0, np.nan)
        # More precisely: COGS / avg_inventory (use COGS if available)

        # ── Debtor Days (DSO) ──
        debtor_days = bs['trade_receivables'] / (pnl['revenue'] / 365)

        # ── DPO (Days Payable Outstanding) ──
        dpo = bs['trade_payables'] / (pnl['revenue'] / 365)

        # ── DIO (Days Inventory Outstanding) ──
        dio = bs['inventory'] / (pnl['revenue'] / 365)

        # ── Cash Conversion Cycle ──
        ccc = debtor_days + dio - dpo

        # ── Working Capital Days ──
        working_capital_days = bs['working_capital'] / (pnl['revenue'] / 365)

        # ── Interest Coverage ──
        interest_coverage = (pnl['ebit'] / pnl['interest_expense'].replace(0, np.nan))
        interest_coverage = interest_coverage.clip(-100, 1000)

        # ── Current Ratio ──
        current_ratio = (bs['total_current_assets']
                         / bs['total_current_liab'].replace(0, np.nan))

        # ── Quick Ratio ──
        quick_ratio = ((bs['total_current_assets'] - bs['inventory'])
                       / bs['total_current_liab'].replace(0, np.nan))

        # ── Cash Ratio ──
        cash_ratio = (bs['cash_equivalents']
                      / bs['total_current_liab'].replace(0, np.nan))

        # ── Debt/Equity ──
        debt_to_equity = bs['total_debt'] / bs['total_equity'].replace(0, np.nan)

        # ── Net Debt / EBITDA ──
        net_debt_to_ebitda = bs['net_debt'] / pnl['ebitda'].replace(0, np.nan)

        # ── Financial Leverage ──
        financial_leverage = bs['total_assets'] / bs['total_equity'].replace(0, np.nan)

        # ── Earning Power ──
        earning_power = pnl['ebit'] / bs['total_assets'].replace(0, np.nan)

        return pd.DataFrame({
            'roe': roe, 'roa': roa, 'roce': roce, 'roic': roic, 'croic': croic,
            'opm': opm, 'npm': npm, 'gpm': gpm,
            'ebitda_margin': ebitda_margin, 'ebit_margin': ebit_margin,
            'asset_turnover': asset_turnover, 'inventory_turnover': inv_turnover,
            'debtor_days': debtor_days, 'dpo': dpo, 'dio': dio,
            'cash_conversion_cycle': ccc, 'working_capital_days': working_capital_days,
            'interest_coverage': interest_coverage,
            'current_ratio': current_ratio, 'quick_ratio': quick_ratio,
            'cash_ratio': cash_ratio,
            'debt_to_equity': debt_to_equity,
            'net_debt_to_ebitda': net_debt_to_ebitda,
            'financial_leverage': financial_leverage,
            'earning_power': earning_power,
        })
```

---

## 7. Stage 4 — Growth Metrics

```python
# compute_engine/stages/growth.py

class GrowthStage:

    def compute(self, ctx: ComputeContext) -> pd.DataFrame:
        """
        CAGR calculations for revenue, profit, EPS, EBITDA, FCF.
        These use the full 10-year history of annual_pnl.
        """
        pnl_hist = ctx.annual_pnl  # Full history, pivoted by fiscal_year

        def cagr(series_latest, series_n_years_ago, n_years):
            """Compound Annual Growth Rate."""
            valid = (series_n_years_ago > 0) & (series_latest > 0)
            result = pd.Series(np.nan, index=series_latest.index)
            result[valid] = (
                (series_latest[valid] / series_n_years_ago[valid]) ** (1 / n_years)
            ) - 1
            return result

        def get_year_data(metric: str, years_ago: int) -> pd.Series:
            """Get a metric value from n years ago, indexed by asx_code."""
            target_year = ctx.current_fy - years_ago
            mask = pnl_hist['fiscal_year'] == target_year
            return (pnl_hist[mask]
                    .set_index('asx_code')[metric]
                    .reindex(ctx.all_asx_codes))

        curr_rev    = get_year_data('revenue', 0)
        curr_profit = get_year_data('net_profit', 0)
        curr_eps    = get_year_data('eps', 0)
        curr_ebitda = get_year_data('ebitda', 0)

        # YoY (1-year)
        rev_1y_ago    = get_year_data('revenue', 1)
        profit_1y_ago = get_year_data('net_profit', 1)
        eps_1y_ago    = get_year_data('eps', 1)

        # Growth rates
        results = {
            # Revenue CAGR
            'revenue_growth_1y':   cagr(curr_rev, rev_1y_ago, 1),
            'revenue_growth_3y':   cagr(curr_rev, get_year_data('revenue', 3), 3),
            'revenue_growth_5y':   cagr(curr_rev, get_year_data('revenue', 5), 5),
            'revenue_growth_7y':   cagr(curr_rev, get_year_data('revenue', 7), 7),
            'revenue_growth_10y':  cagr(curr_rev, get_year_data('revenue', 10), 10),

            # Profit CAGR
            'profit_growth_1y':    cagr(curr_profit, profit_1y_ago, 1),
            'profit_growth_3y':    cagr(curr_profit, get_year_data('net_profit', 3), 3),
            'profit_growth_5y':    cagr(curr_profit, get_year_data('net_profit', 5), 5),
            'profit_growth_7y':    cagr(curr_profit, get_year_data('net_profit', 7), 7),
            'profit_growth_10y':   cagr(curr_profit, get_year_data('net_profit', 10), 10),

            # EPS CAGR
            'eps_growth_1y':       cagr(curr_eps, eps_1y_ago, 1),
            'eps_growth_3y':       cagr(curr_eps, get_year_data('eps', 3), 3),
            'eps_growth_5y':       cagr(curr_eps, get_year_data('eps', 5), 5),
            'eps_growth_7y':       cagr(curr_eps, get_year_data('eps', 7), 7),
            'eps_growth_10y':      cagr(curr_eps, get_year_data('eps', 10), 10),

            # EBITDA CAGR
            'ebitda_growth_3y':    cagr(curr_ebitda, get_year_data('ebitda', 3), 3),
            'ebitda_growth_5y':    cagr(curr_ebitda, get_year_data('ebitda', 5), 5),

            # Rolling averages (ROE, ROCE)
            'roe_avg_3y':          self._rolling_avg(pnl_hist, 'roe', 3),
            'roe_avg_5y':          self._rolling_avg(pnl_hist, 'roe', 5),
            'roe_avg_7y':          self._rolling_avg(pnl_hist, 'roe', 7),
            'roe_avg_10y':         self._rolling_avg(pnl_hist, 'roe', 10),
            'opm_avg_5y':          self._rolling_avg(pnl_hist, 'opm', 5),
            'opm_avg_10y':         self._rolling_avg(pnl_hist, 'opm', 10),
        }

        # ── Quarterly Growth (YoY) ──
        half_yr = ctx.half_year_pnl
        results['rev_qoq_growth']    = self._yoy_half_year_growth(half_yr, 'revenue')
        results['profit_qoq_growth'] = self._yoy_half_year_growth(half_yr, 'net_profit')

        return pd.DataFrame(results)

    def _rolling_avg(self, pnl_hist, metric, n_years):
        """Average of a ratio over last n years."""
        recent = pnl_hist[pnl_hist['fiscal_year'] >= ctx.current_fy - n_years + 1]
        return recent.groupby('asx_code')[metric].mean()
```

---

## 8. Stage 5 — Composite Scores & Risk

```python
# compute_engine/stages/scores.py

class ScoresStage:

    def compute(self, ctx: ComputeContext,
                prof: pd.DataFrame, growth: pd.DataFrame) -> pd.DataFrame:
        results = {}

        # ── Piotroski F-Score (0–9) ──
        # 9 binary signals from profitability, leverage/liquidity, efficiency
        pnl   = ctx.annual_pnl_latest
        pnl_1 = ctx.annual_pnl_1y_ago
        bs    = ctx.balance_sheet
        bs_1  = ctx.balance_sheet_1y_ago
        cf    = ctx.cashflow_latest

        p_scores = pd.DataFrame({
            # PROFITABILITY SIGNALS
            'F1_roa_positive':      (pnl['net_profit'] / bs['total_assets'] > 0).astype(int),
            'F2_ocf_positive':      (cf['cfo'] > 0).astype(int),
            'F3_roa_improving':     ((pnl['net_profit'] / bs['total_assets'])
                                     > (pnl_1['net_profit'] / bs_1['total_assets'])).astype(int),
            'F4_accruals_low':      ((cf['cfo'] / bs['total_assets'])
                                     > (pnl['net_profit'] / bs['total_assets'])).astype(int),

            # LEVERAGE / LIQUIDITY SIGNALS
            'F5_leverage_down':     (bs['total_debt'] / bs['total_assets']
                                     < bs_1['total_debt'] / bs_1['total_assets']).astype(int),
            'F6_current_ratio_up':  ((bs['total_current_assets'] / bs['total_current_liab'])
                                     > (bs_1['total_current_assets'] / bs_1['total_current_liab'])).astype(int),
            'F7_no_dilution':       (bs['shares_outstanding'] <= bs_1['shares_outstanding']).astype(int),

            # EFFICIENCY SIGNALS
            'F8_gpm_improving':     (pnl['gross_profit'] / pnl['revenue']
                                     > pnl_1['gross_profit'] / pnl_1['revenue']).astype(int),
            'F9_asset_turnover_up': (pnl['revenue'] / bs['total_assets']
                                     > pnl_1['revenue'] / bs_1['total_assets']).astype(int),
        })
        results['piotroski_score'] = p_scores.sum(axis=1).astype('Int8')

        # ── Altman Z-Score ──
        # Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
        ta  = bs['total_assets'].replace(0, np.nan)
        wc  = bs['working_capital']
        re  = bs['retained_earnings']
        ebit = pnl['ebit']
        mve = ctx.market_cap_aud   # Market value of equity (AUD)
        tl  = bs['total_liabilities'].replace(0, np.nan)
        rev = pnl['revenue']

        x1 = wc / ta
        x2 = re / ta
        x3 = ebit / ta
        x4 = mve / tl
        x5 = rev / ta

        results['altman_z_score'] = (1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + x5).clip(-10, 20)

        # ── Beneish M-Score (earnings manipulation) ──
        # Higher than -1.78 = potential manipulation
        # Simplified version using 5 of 8 variables
        dsri = ((bs['trade_receivables'] / pnl['revenue'])
                / (bs_1['trade_receivables'] / pnl_1['revenue'])).replace([np.inf, -np.inf], np.nan)
        gmi  = (pnl_1['gross_profit'] / pnl_1['revenue']) / (pnl['gross_profit'] / pnl['revenue'])
        aqi  = (1 - (bs['total_current_assets'] + bs['net_block']) / bs['total_assets']) / \
               (1 - (bs_1['total_current_assets'] + bs_1['net_block']) / bs_1['total_assets'])
        sgi  = pnl['revenue'] / pnl_1['revenue']
        depi = ((pnl_1['depreciation'] / (pnl_1['net_block'] + pnl_1['depreciation']))
                / (pnl['depreciation'] / (pnl['net_block'] + pnl['depreciation'])))

        results['beneish_m_score'] = (
            -4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi + 0.115*depi
        ).clip(-10, 10)

        # ── Sharpe Ratio (1-year, risk-free = RBA cash rate ~4.35%) ──
        risk_free = 0.0435 / 252  # Daily risk-free rate
        daily_returns = ctx.daily_returns_1y  # Pre-computed Series indexed by asx_code
        excess_returns = daily_returns.mean() - risk_free
        std_returns    = daily_returns.std()
        results['sharpe_1y'] = (excess_returns / std_returns.replace(0, np.nan) * np.sqrt(252))

        # ── Sortino Ratio (only downside deviation) ──
        downside_returns = daily_returns.where(daily_returns < 0, 0)
        downside_std     = downside_returns.std()
        results['sortino_1y'] = (excess_returns / downside_std.replace(0, np.nan) * np.sqrt(252))

        # ── Max Drawdown ──
        def max_drawdown(price_series):
            rolling_max = price_series.expanding().max()
            drawdown    = (price_series - rolling_max) / rolling_max
            return drawdown.min()

        results['max_drawdown_1y'] = ctx.price_1y.apply(max_drawdown)

        # ── Beta (from TechnicalStage, pass through) ──
        results['beta_1y'] = ctx.technical['beta_1y']

        return pd.DataFrame(results)
```

---

## 9. Stage 6 — ASX-Specific Metrics

```python
# compute_engine/stages/asx_specific.py

class ASXSpecificStage:

    def compute(self, ctx: ComputeContext, val: pd.DataFrame) -> pd.DataFrame:
        results = {}

        # ── REIT-Specific Metrics ──
        reit_mask = ctx.companies['is_reit']
        reit_data = ctx.reit_data  # Latest snapshot

        reit_cols = {}
        reit_cols['ffo_per_unit']   = reit_data['ffo_per_unit']
        reit_cols['affo_per_unit']  = reit_data['affo_per_unit']
        reit_cols['nta_per_unit']   = reit_data['nta_per_unit']
        reit_cols['price_to_nta']   = ctx.prices_today['close'] / reit_data['nta_per_unit']
        reit_cols['gearing_ratio']  = reit_data['gearing_ratio']
        reit_cols['wale_years']     = reit_data['wale_years']
        reit_cols['occupancy_pct']  = reit_data['occupancy_pct']
        reit_cols['ffo_yield']      = (reit_data['ffo_per_unit']
                                       / ctx.prices_today['close'].replace(0, np.nan))

        for col, series in reit_cols.items():
            results[col] = series.reindex(ctx.all_asx_codes)

        # ── Mining-Specific Metrics ──
        mining_data = ctx.mining_data

        results['aisc_per_oz']    = mining_data['aisc_per_oz'].reindex(ctx.all_asx_codes)
        results['reserve_life_years'] = mining_data['reserve_life_years'].reindex(ctx.all_asx_codes)

        # NAV per share for miners (from reserves × commodity price - debt)
        # This is approximate; actual NAV requires detailed modelling
        results['nav_per_share']  = mining_data['nav_per_share'].reindex(ctx.all_asx_codes)

        # ── Franking Yield Adjustment ──
        # Already computed in Stage 2 — pass through
        results['grossed_up_yield'] = val['grossed_up_yield']

        # ── Dividend Payout Ratio ──
        pnl = ctx.annual_pnl_latest
        cf  = ctx.cashflow_latest
        results['dividend_payout_ratio'] = (
            cf['dividends_paid'].abs()
            / pnl['net_profit'].replace(0, np.nan)
        ).clip(0, 5)

        # ── Dividend Growth (3Y) ──
        results['dividend_growth_3y'] = ctx.dividend_growth_3y

        # ── Market Cap to Quarterly Profit ──
        q_profit = ctx.latest_quarter_profit
        results['mcap_to_quarterly_profit'] = (
            val['market_cap'] / (q_profit / 1e6).replace(0, np.nan)
        )

        # ── Intrinsic Value (Graham formula) ──
        # V = EPS × (8.5 + 2g) where g = EPS growth 5Y
        eps_ttm     = ctx.eps_ttm
        eps_growth  = ctx.growth_metrics['eps_growth_5y'] * 100  # Convert to %
        results['intrinsic_value'] = eps_ttm * (8.5 + 2 * eps_growth.clip(0, 25))

        return pd.DataFrame(results)
```

---

## 10. Stage 7 — Write & Cache Invalidation

```python
# compute_engine/stages/writer.py

class WriterStage:

    def write_all(self, compute_date: date, all_metrics: pd.DataFrame):
        """
        Bulk write all computed metrics to PostgreSQL using COPY.
        This is 10-100× faster than individual INSERTs.
        """
        all_metrics['time'] = compute_date
        all_metrics['compute_version'] = COMPUTE_ENGINE_VERSION
        all_metrics['computed_at'] = datetime.now(tz=timezone.utc)

        # Reset index so asx_code becomes a column
        df = all_metrics.reset_index()

        # Use COPY via psycopg2 for maximum speed
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Create temp table
            cur.execute("""
                CREATE TEMP TABLE computed_metrics_staging
                (LIKE market.computed_metrics INCLUDING ALL)
                ON COMMIT DROP;
            """)

            # Bulk copy from in-memory buffer
            buffer = df_to_csv_buffer(df)
            cur.copy_expert("""
                COPY computed_metrics_staging FROM STDIN
                WITH CSV HEADER NULL 'None'
            """, buffer)

            # Upsert from temp table
            cur.execute("""
                INSERT INTO market.computed_metrics
                SELECT * FROM computed_metrics_staging
                ON CONFLICT (time, asx_code) DO UPDATE
                SET
                    market_cap         = EXCLUDED.market_cap,
                    pe_ratio           = EXCLUDED.pe_ratio,
                    -- ... all columns ...
                    computed_at        = EXCLUDED.computed_at;
            """)

            conn.commit()

        # Estimated time: ~30 seconds for 2,200 rows

    def invalidate_redis_cache(self, asx_codes: list[str]):
        """Delete all cached data for all updated stocks."""
        redis = get_redis_client()
        pipeline = redis.pipeline()
        for code in asx_codes:
            pipeline.delete(f"ratios:{code}")
            pipeline.delete(f"company:{code}:overview")
            pipeline.delete(f"company:{code}:metrics")
        pipeline.execute()
        # Also invalidate screener result cache (all screens stale after recompute)
        redis.flushdb(1)  # Flush screen results DB

    def sync_elasticsearch(self, asx_codes: list[str], all_metrics: pd.DataFrame):
        """
        Re-index updated companies in Elasticsearch.
        Run asynchronously (non-blocking) after DB write completes.
        """
        from elasticsearch import Elasticsearch, helpers

        es = Elasticsearch([ES_URL])
        docs = []
        for code in asx_codes:
            row = all_metrics.loc[code]
            company = get_company_info(code)
            docs.append({
                '_index': 'stocks',
                '_id':    code,
                '_source': {
                    'asx_code':    code,
                    'name':        company.company_name,
                    'sector':      company.gics_sector,
                    'is_asx200':   company.is_asx200,
                    'market_cap':  row.market_cap,
                    'pe_ratio':    row.pe_ratio,
                    'roe':         row.roe,
                    'dividend_yield': row.dividend_yield,
                    'revenue_growth_3y': row.revenue_growth_3y,
                    # All screenable fields
                    **{col: row[col] for col in ELASTICSEARCH_FIELDS},
                }
            })

        helpers.bulk(es, docs)
```

---

## 11. Compute Engine Orchestration

```python
# compute_engine/__main__.py

import logging
from datetime import date
from concurrent.futures import ProcessPoolExecutor

log = logging.getLogger(__name__)

def run_compute_engine(compute_date: date):
    """
    Main entry point. Called by Airflow DAG at 5:30 PM AEST.
    """
    log.info(f"=== Compute Engine Started: {compute_date} ===")
    start_time = time.time()

    # STAGE 0: Load all data
    log.info("Stage 0: Loading data...")
    ctx = DataLoader(compute_date).load_all()
    log.info(f"  Loaded {len(ctx.all_asx_codes)} stocks in {elapsed(start_time):.1f}s")

    # STAGE 1: Technical Indicators (parallel by stock)
    log.info("Stage 1: Technical indicators...")
    tech = TechnicalStage().compute(ctx)
    write_technical_indicators(compute_date, tech)
    ctx.set('technical', tech)
    log.info(f"  Technical done in {elapsed(start_time):.1f}s")

    # STAGES 2–6: Run in parallel process pool
    # Each stage is independent of the others (except they share ctx)
    log.info("Stages 2–6: Computing all ratios (parallel)...")

    with ProcessPoolExecutor(max_workers=6) as executor:
        f_val   = executor.submit(ValuationStage().compute, ctx, tech)
        f_prof  = executor.submit(ProfitabilityStage().compute, ctx)
        f_growth= executor.submit(GrowthStage().compute, ctx)

    val    = f_val.result()
    prof   = f_prof.result()
    growth = f_growth.result()

    # Scores depends on profitability output
    scores = ScoresStage().compute(ctx, prof, growth)

    # ASX-specific depends on valuation output
    asx    = ASXSpecificStage().compute(ctx, val)

    log.info(f"  All ratios done in {elapsed(start_time):.1f}s")

    # Merge all stage outputs
    all_metrics = pd.concat([tech, val, prof, growth, scores, asx], axis=1)
    all_metrics.index = ctx.all_asx_codes

    # STAGE 7: Write
    log.info("Stage 7: Writing to database...")
    writer = WriterStage()
    writer.write_all(compute_date, all_metrics)
    writer.invalidate_redis_cache(ctx.all_asx_codes)

    # Async (non-blocking): sync Elasticsearch
    writer.sync_elasticsearch.apply_async(
        args=[ctx.all_asx_codes, all_metrics]
    )

    total_time = elapsed(start_time)
    log.info(f"=== Compute Engine Complete: {total_time:.0f}s for {len(ctx.all_asx_codes)} stocks ===")

    # Write pipeline status
    write_pipeline_status({
        'dag': 'compute_engine',
        'date': compute_date,
        'stocks_processed': len(ctx.all_asx_codes),
        'duration_seconds': total_time,
        'status': 'success'
    })

    return {'stocks': len(ctx.all_asx_codes), 'duration': total_time}
```

---

## 12. Performance Profile

```
STAGE BREAKDOWN (2,200 stocks):

Stage 0: Data Load          ~120s  ██████
Stage 1: Technical           ~60s  ███
Stage 2: Valuation           ~45s  ██
Stage 3: Profitability       ~40s  ██
Stage 4: Growth              ~45s  ██
Stage 5: Scores              ~50s  ██
Stage 6: ASX-specific        ~30s  █
Stage 7: Write + Cache       ~50s  ██
Stage 7b: Elasticsearch      ~90s  ████ (async, not blocking)
─────────────────────────────────────
TOTAL (blocking):           ~440s = ~7 minutes  ✅
(Target was < 20 minutes — well within SLA)

Memory usage: ~2–4 GB RAM for all DataFrames in parallel
CPU: 16 cores × 100% during computation stages
DB write: 2,200 rows via COPY = ~5 seconds
```

---

## 13. Error Recovery

```python
# If compute fails for some stocks (e.g. missing data):

class ComputeEngine:
    def compute_with_recovery(self, ctx):
        failed = []
        results = {}

        for asx_code in ctx.all_asx_codes:
            try:
                results[asx_code] = self._compute_single(asx_code, ctx)
            except InsufficientDataError:
                # Skip: new listing with < 1 year of data
                log.warning(f"{asx_code}: insufficient data, skipping")
            except Exception as e:
                log.error(f"{asx_code}: compute failed: {e}")
                failed.append(asx_code)
                # Use yesterday's computed metrics as fallback
                results[asx_code] = get_previous_metrics(asx_code)

        if len(failed) > 50:
            # More than 50 failures = systemic issue, abort and alert
            raise ComputeEngineFailure(f"{len(failed)} stocks failed")

        return results, failed
```

---

*Next: See `05_Frontend_Wireframes.md` for UI/UX design*
