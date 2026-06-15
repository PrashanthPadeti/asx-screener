-- Migration 057: Add ratio-framework signal columns to screener.universe
-- earning_power:            EBIT / Total Assets (pre-tax, pre-interest ROA)
-- financial_leverage:       Total Assets / Equity (DuPont leverage factor)
-- days_payable_outstanding: Trade Payables / COGS × 365
-- cash_conversion_cycle:    DIO + DSO − DPO (full working capital cycle in days)
-- roe_improving:            Current ROE > 3Y average ROE
-- roce_improving:           Current ROCE > 3Y average ROCE

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS earning_power             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS financial_leverage        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS days_payable_outstanding  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS cash_conversion_cycle     DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS roe_improving             BOOLEAN,
    ADD COLUMN IF NOT EXISTS roce_improving            BOOLEAN;
