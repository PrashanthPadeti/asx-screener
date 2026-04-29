-- ─────────────────────────────────────────────────────────────
--  Migration 005 — financials Schema
--  annual_pnl · annual_balance_sheet · annual_cashflow ·
--  half_year_pnl · mining_data · reit_data
-- ─────────────────────────────────────────────────────────────

-- ── financials.annual_pnl ─────────────────────────────────────

CREATE TABLE financials.annual_pnl (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    fiscal_year             INTEGER NOT NULL,      -- e.g. 2024 = FY ending June 2024
    period_end_date         DATE NOT NULL,
    report_date             DATE,                  -- Date ASX announcement filed

    -- Income Statement (AUD millions)
    revenue                 NUMERIC(18,2),
    cost_of_sales           NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    operating_expenses      NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    depreciation            NUMERIC(18,2),
    amortisation            NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    interest_income         NUMERIC(18,2),
    pbt                     NUMERIC(18,2),
    tax                     NUMERIC(18,2),
    pat                     NUMERIC(18,2),
    minority_interest       NUMERIC(18,2),
    net_profit              NUMERIC(18,2),
    extraordinary_items     NUMERIC(18,2),
    dividend_paid           NUMERIC(18,2),
    material_cost           NUMERIC(18,2),
    employee_cost           NUMERIC(18,2),

    -- Derived margins (stored for fast screener access)
    opm                     NUMERIC(18,6),
    npm                     NUMERIC(18,6),
    gpm                     NUMERIC(18,6),
    ebitda_margin           NUMERIC(18,6),

    -- Per share
    eps                     NUMERIC(18,4),
    eps_diluted             NUMERIC(18,4),
    shares_used             BIGINT,

    -- Dividend
    dps                     NUMERIC(12,4),
    dps_franking_pct        NUMERIC(6,2) DEFAULT 0,
    dps_grossed_up          NUMERIC(12,4),

    -- Metadata
    currency                VARCHAR(3) DEFAULT 'AUD',
    is_restated             BOOLEAN DEFAULT FALSE,
    data_source             VARCHAR(50),   -- claude_pdf | fmp | morningstar | manual

    UNIQUE (asx_code, fiscal_year)
);

CREATE INDEX idx_pnl_asx_year ON financials.annual_pnl(asx_code, fiscal_year DESC);

-- ── financials.annual_balance_sheet ───────────────────────────

CREATE TABLE financials.annual_balance_sheet (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    fiscal_year             INTEGER NOT NULL,
    period_end_date         DATE NOT NULL,

    -- Assets (AUD millions)
    cash_equivalents        NUMERIC(18,2),
    trade_receivables       NUMERIC(18,2),
    inventory               NUMERIC(18,2),
    other_current_assets    NUMERIC(18,2),
    total_current_assets    NUMERIC(18,2),
    gross_block             NUMERIC(18,2),
    accumulated_depreciation NUMERIC(18,2),
    net_block               NUMERIC(18,2),
    cwip                    NUMERIC(18,2),
    goodwill                NUMERIC(18,2),
    intangibles             NUMERIC(18,2),
    investments             NUMERIC(18,2),
    other_non_current       NUMERIC(18,2),
    total_assets            NUMERIC(18,2),

    -- Liabilities (AUD millions)
    trade_payables          NUMERIC(18,2),
    advance_from_customers  NUMERIC(18,2),
    short_term_debt         NUMERIC(18,2),
    other_current_liab      NUMERIC(18,2),
    total_current_liab      NUMERIC(18,2),
    long_term_debt          NUMERIC(18,2),
    lease_liabilities       NUMERIC(18,2),
    contingent_liabilities  NUMERIC(18,2),
    other_non_current_liab  NUMERIC(18,2),
    total_liabilities       NUMERIC(18,2),

    -- Equity (AUD millions)
    equity_capital          NUMERIC(18,2),
    preference_capital      NUMERIC(18,2),
    reserves                NUMERIC(18,2),
    retained_earnings       NUMERIC(18,2),
    minority_interest_bs    NUMERIC(18,2),
    total_equity            NUMERIC(18,2),

    -- Derived
    total_debt              NUMERIC(18,2),
    net_debt                NUMERIC(18,2),
    working_capital         NUMERIC(18,2),
    book_value_per_share    NUMERIC(12,4),
    face_value              NUMERIC(10,4),
    shares_outstanding      BIGINT,

    is_restated             BOOLEAN DEFAULT FALSE,
    data_source             VARCHAR(50),

    UNIQUE (asx_code, fiscal_year)
);

CREATE INDEX idx_bs_asx_year ON financials.annual_balance_sheet(asx_code, fiscal_year DESC);

-- ── financials.annual_cashflow ────────────────────────────────

CREATE TABLE financials.annual_cashflow (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    fiscal_year             INTEGER NOT NULL,
    period_end_date         DATE NOT NULL,

    -- Cash Flow Statement (AUD millions)
    net_income              NUMERIC(18,2),
    depreciation_amort      NUMERIC(18,2),
    working_capital_changes NUMERIC(18,2),
    other_operating         NUMERIC(18,2),
    cfo                     NUMERIC(18,2),   -- Cash From Operations

    capex                   NUMERIC(18,2),   -- Negative value
    acquisitions            NUMERIC(18,2),
    disposals               NUMERIC(18,2),
    investment_purchases    NUMERIC(18,2),
    other_investing         NUMERIC(18,2),
    cfi                     NUMERIC(18,2),   -- Cash From Investing

    dividends_paid          NUMERIC(18,2),
    debt_raised             NUMERIC(18,2),
    debt_repaid             NUMERIC(18,2),
    equity_raised           NUMERIC(18,2),
    buybacks                NUMERIC(18,2),
    other_financing         NUMERIC(18,2),
    cff                     NUMERIC(18,2),   -- Cash From Financing

    net_change_in_cash      NUMERIC(18,2),
    opening_cash            NUMERIC(18,2),
    closing_cash            NUMERIC(18,2),
    fcf                     NUMERIC(18,2),   -- FCF = CFO + Capex

    is_restated             BOOLEAN DEFAULT FALSE,
    data_source             VARCHAR(50),

    UNIQUE (asx_code, fiscal_year)
);

CREATE INDEX idx_cf_asx_year ON financials.annual_cashflow(asx_code, fiscal_year DESC);

-- ── financials.half_year_pnl ──────────────────────────────────
-- ASX companies report half-yearly (not quarterly like USA/India)

CREATE TABLE financials.half_year_pnl (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    period_end_date         DATE NOT NULL,
    period_label            VARCHAR(20) NOT NULL,  -- e.g. '1H FY2024', '2H FY2024'
    report_date             DATE,

    revenue                 NUMERIC(18,2),
    gross_profit            NUMERIC(18,2),
    other_income            NUMERIC(18,2),
    ebitda                  NUMERIC(18,2),
    depreciation            NUMERIC(18,2),
    ebit                    NUMERIC(18,2),
    interest_expense        NUMERIC(18,2),
    pbt                     NUMERIC(18,2),
    tax                     NUMERIC(18,2),
    pat                     NUMERIC(18,2),
    net_profit              NUMERIC(18,2),
    extraordinary_items     NUMERIC(18,2),
    equity_capital          NUMERIC(18,2),
    eps                     NUMERIC(18,4),
    dps                     NUMERIC(12,4),
    dps_franking_pct        NUMERIC(6,2) DEFAULT 0,
    opm                     NUMERIC(18,6),
    npm                     NUMERIC(18,6),
    gpm                     NUMERIC(18,6),

    data_source             VARCHAR(50),

    UNIQUE (asx_code, period_end_date)
);

CREATE INDEX idx_halfyear_asx ON financials.half_year_pnl(asx_code, period_end_date DESC);

-- ── financials.mining_data ────────────────────────────────────

CREATE TABLE financials.mining_data (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    report_date             DATE NOT NULL,
    report_type             VARCHAR(30),   -- reserves | qar | annual

    primary_commodity       VARCHAR(100),
    secondary_commodity     VARCHAR(100),

    -- Ore Reserves
    reserves_proven_kt      NUMERIC(18,2),
    reserves_probable_kt    NUMERIC(18,2),
    total_reserves_kt       NUMERIC(18,2),
    reserves_grade          NUMERIC(10,4),
    reserves_contained_oz   NUMERIC(18,2),  -- Gold miners: contained ounces

    -- Resources
    resources_measured_kt   NUMERIC(18,2),
    resources_indicated_kt  NUMERIC(18,2),
    resources_inferred_kt   NUMERIC(18,2),
    total_resources_kt      NUMERIC(18,2),

    -- Production (quarterly)
    production_qty          NUMERIC(18,2),
    production_unit         VARCHAR(20),    -- koz | kt | bbl
    production_guidance_low NUMERIC(18,2),
    production_guidance_high NUMERIC(18,2),

    -- Costs
    aisc_per_oz             NUMERIC(12,2),  -- All-in sustaining cost (AUD)
    c1_cost_per_oz          NUMERIC(12,2),
    operating_cost_per_t    NUMERIC(12,2),

    -- Life of mine
    reserve_life_years      NUMERIC(8,2),
    mine_life_years         NUMERIC(8,2),

    -- Hedging
    hedged_oz               NUMERIC(18,2),
    hedging_pct             NUMERIC(8,4),
    hedge_price             NUMERIC(12,2),

    UNIQUE (asx_code, report_date, report_type)
);

CREATE INDEX idx_mining_asx ON financials.mining_data(asx_code, report_date DESC);

-- ── financials.reit_data ──────────────────────────────────────

CREATE TABLE financials.reit_data (
    id                      SERIAL PRIMARY KEY,
    asx_code                VARCHAR(10) NOT NULL,
    report_date             DATE NOT NULL,
    period_label            VARCHAR(20),

    -- FFO
    ffo                     NUMERIC(18,2),
    ffo_per_unit            NUMERIC(12,4),
    affo                    NUMERIC(18,2),
    affo_per_unit           NUMERIC(12,4),

    -- NTA
    nta_total               NUMERIC(18,2),
    nta_per_unit            NUMERIC(12,4),
    intangibles_written_off NUMERIC(18,2),

    -- Portfolio
    portfolio_value         NUMERIC(18,2),
    property_count          INTEGER,
    property_type           VARCHAR(50),   -- retail | office | industrial | mixed
    geographic_split        JSONB,         -- {"AU": 80, "NZ": 20}

    -- Leverage
    gearing_ratio           NUMERIC(8,4),
    look_through_gearing    NUMERIC(8,4),

    -- Leasing
    wale_years              NUMERIC(8,2),
    wale_by_income          NUMERIC(8,2),
    occupancy_pct           NUMERIC(8,4),
    cap_rate                NUMERIC(8,4),

    -- Interest rate risk
    fixed_rate_debt_pct     NUMERIC(8,4),
    weighted_avg_debt_cost  NUMERIC(8,4),
    weighted_avg_debt_term  NUMERIC(8,2),

    UNIQUE (asx_code, report_date)
);

CREATE INDEX idx_reit_asx ON financials.reit_data(asx_code, report_date DESC);
