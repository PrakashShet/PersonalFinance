-- Personal Finance Manager — SQLite Schema
-- Run at startup via db.apply_schema(). Idempotent (uses IF NOT EXISTS).

-- =========================================================================
-- ACCOUNTS  (bank, cash, wallet, credit card)
-- =========================================================================
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    account_type    TEXT NOT NULL,
    institution     TEXT,
    account_number  TEXT,
    opening_balance REAL NOT NULL DEFAULT 0,
    current_balance REAL NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'INR',
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    -- Contact & KYC details
    phone              TEXT,
    email              TEXT,
    ifsc_code          TEXT,
    bank_address       TEXT,
    personal_address   TEXT,   -- address on record with the bank
    -- Linked-account flags
    demat_enabled      INTEGER NOT NULL DEFAULT 0,
    investment_enabled INTEGER NOT NULL DEFAULT 0,
    -- Demat account details
    depository             TEXT,
    dp_id                  TEXT,
    demat_client_id        TEXT,
    demat_bo_id            TEXT,
    demat_broker           TEXT,
    -- Investment account details
    trading_account_number TEXT,
    investment_broker      TEXT,
    investment_segments    TEXT,
    -- Credit card details
    cc_network             TEXT,
    cc_last4               TEXT,
    cc_credit_limit        REAL NOT NULL DEFAULT 0,
    cc_outstanding         REAL NOT NULL DEFAULT 0,
    cc_billing_day         INTEGER NOT NULL DEFAULT 0,
    cc_due_day             INTEGER NOT NULL DEFAULT 0,
    -- Loan details
    loan_type              TEXT,
    loan_account_number    TEXT,
    loan_principal         REAL NOT NULL DEFAULT 0,
    loan_outstanding       REAL NOT NULL DEFAULT 0,
    loan_interest_rate     REAL NOT NULL DEFAULT 0,
    loan_emi               REAL NOT NULL DEFAULT 0,
    loan_tenure_months     INTEGER NOT NULL DEFAULT 0,
    loan_start_date        TEXT,
    -- Bond details
    bond_issuer            TEXT,
    bond_isin              TEXT,
    bond_face_value        REAL NOT NULL DEFAULT 0,
    bond_coupon_rate       REAL NOT NULL DEFAULT 0,
    bond_units             INTEGER NOT NULL DEFAULT 0,
    bond_maturity_date     TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- CATEGORIES  (for income/expense tagging)
-- =========================================================================
CREATE TABLE IF NOT EXISTS categories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    kind      TEXT NOT NULL,    -- income | expense
    parent_id INTEGER,
    icon      TEXT,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
);

-- =========================================================================
-- TRANSACTIONS  (universal ledger)
-- =========================================================================
CREATE TABLE IF NOT EXISTS transactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date       TEXT NOT NULL,
    txn_type       TEXT NOT NULL,    -- income | expense | transfer | investment_buy | investment_sell | adjustment
    amount         REAL NOT NULL,    -- always > 0, except `adjustment` which is signed (+ adds, - removes)
    account_id     INTEGER NOT NULL,
    counter_account_id INTEGER,      -- for transfers
    category_id    INTEGER,
    holding_id     INTEGER,          -- if linked to an investment
    income_source_id INTEGER,        -- if income
    description    TEXT,
    reference_no   TEXT,
    tags           TEXT,             -- comma-separated
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (counter_account_id) REFERENCES accounts(id) ON DELETE SET NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (holding_id) REFERENCES holdings(id) ON DELETE SET NULL,
    FOREIGN KEY (income_source_id) REFERENCES income_sources(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions(account_id);

-- =========================================================================
-- INCOME SOURCES  (salary, web apps, trading, freelance, dividends, ...)
-- =========================================================================
CREATE TABLE IF NOT EXISTS income_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL,        -- salary | web_app | trading | freelance | ...
    is_recurring    INTEGER NOT NULL DEFAULT 1,
    expected_amount REAL,
    frequency       TEXT,                 -- monthly | quarterly | yearly | irregular
    employer        TEXT,
    -- Salary breakdown (nullable for non-salary)
    basic           REAL,
    hra             REAL,
    special_allow   REAL,
    pf_employee     REAL,
    pf_employer     REAL,
    professional_tax REAL,
    tds             REAL,
    notes           TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    -- Account this income is deposited into (nullable)
    deposit_account_id INTEGER,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deposit_account_id) REFERENCES accounts(id) ON DELETE SET NULL
);

-- =========================================================================
-- INCOME ENTRIES  (per-month actuals logged against an income source)
-- =========================================================================
CREATE TABLE IF NOT EXISTS income_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    income_source_id  INTEGER NOT NULL,
    period_month      TEXT NOT NULL,        -- 'YYYY-MM'
    expected_amount   REAL,                 -- snapshot of expected/net at record time
    actual_amount     REAL NOT NULL,        -- actually received
    received_date     TEXT,                 -- 'YYYY-MM-DD'
    account_id        INTEGER,              -- account it landed in
    transaction_id    INTEGER,              -- linked ledger transaction (if posted)
    notes             TEXT,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (income_source_id) REFERENCES income_sources(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE SET NULL,
    UNIQUE (income_source_id, period_month)
);
CREATE INDEX IF NOT EXISTS idx_income_entries_source ON income_entries(income_source_id);
CREATE INDEX IF NOT EXISTS idx_income_entries_period ON income_entries(period_month);

-- =========================================================================
-- HOLDINGS  (polymorphic: SIP, FD, stocks, gold, insurance, ...)
-- =========================================================================
CREATE TABLE IF NOT EXISTS holdings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    holding_type    TEXT NOT NULL,        -- see HoldingType enum
    institution     TEXT,
    folio_or_account TEXT,
    purchase_date   TEXT,
    -- Universal value fields
    invested_amount REAL NOT NULL DEFAULT 0,
    current_value   REAL NOT NULL DEFAULT 0,
    quantity        REAL,                 -- units / grams / shares
    avg_price       REAL,
    current_price   REAL,
    -- Stock-specific
    symbol          TEXT,
    exchange        TEXT,                 -- NSE | BSE
    market_cap      TEXT,                 -- sme | small_cap | mid_cap | large_cap
    sector          TEXT,
    -- FD-specific
    interest_rate   REAL,
    maturity_date   TEXT,
    payout_frequency TEXT,
    auto_renew      INTEGER DEFAULT 0,
    -- Insurance-specific
    sum_assured     REAL,
    premium_amount  REAL,
    premium_due_date TEXT,
    policy_term_years INTEGER,
    -- Gold-specific
    weight_grams    REAL,
    purity          TEXT,                 -- 24K | 22K | 18K
    making_charges  REAL,
    -- SIP-specific
    sip_amount      REAL,
    sip_day_of_month INTEGER,
    -- Linkage
    linked_account_id INTEGER,
    notes           TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (linked_account_id) REFERENCES accounts(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_holdings_type ON holdings(holding_type);

-- Daily/periodic valuations for charting
CREATE TABLE IF NOT EXISTS holding_valuations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id  INTEGER NOT NULL,
    as_of_date  TEXT NOT NULL,
    market_value REAL NOT NULL,
    unit_price  REAL,
    FOREIGN KEY (holding_id) REFERENCES holdings(id) ON DELETE CASCADE,
    UNIQUE (holding_id, as_of_date)
);

-- =========================================================================
-- LIABILITIES  (loans, credit-card outstanding, BNPL)
-- =========================================================================
CREATE TABLE IF NOT EXISTS liabilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    liability_type  TEXT NOT NULL,
    lender          TEXT,
    principal       REAL NOT NULL,
    outstanding     REAL NOT NULL,
    interest_rate   REAL,
    emi_amount      REAL,
    tenure_months   INTEGER,
    remaining_months INTEGER,
    start_date      TEXT,
    next_due_date   TEXT,
    account_id      INTEGER,                   -- account this debt is paid from
    notes           TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
);

-- =========================================================================
-- GOALS  (future targets)
-- =========================================================================
CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    target_amount   REAL NOT NULL,
    current_amount  REAL NOT NULL DEFAULT 0,
    target_date     TEXT,
    priority        INTEGER DEFAULT 3,        -- 1=high, 5=low
    expected_return REAL DEFAULT 0.10,        -- annual, decimal
    inflation_rate  REAL DEFAULT 0.06,
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goal_holdings (
    goal_id    INTEGER NOT NULL,
    holding_id INTEGER NOT NULL,
    allocation_pct REAL DEFAULT 100.0,
    PRIMARY KEY (goal_id, holding_id),
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE,
    FOREIGN KEY (holding_id) REFERENCES holdings(id) ON DELETE CASCADE
);

-- =========================================================================
-- BUDGETS  (spending limit for one expense category, per month or per year)
-- Spending = `expense` transactions in that category during the period,
-- converted to rupees with fx_rates. A yearly period starts in the month set
-- by the `budget_year_start` preference (1 = January, 4 = April / Indian FY).
-- =========================================================================
CREATE TABLE IF NOT EXISTS budgets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL,
    period       TEXT NOT NULL DEFAULT 'monthly',   -- monthly | yearly
    amount       REAL NOT NULL,                     -- the limit, in rupees per period
    notes        TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    UNIQUE (category_id, period)
);

-- =========================================================================
-- NET WORTH SNAPSHOTS  (monthly, for trend charts)
-- =========================================================================
CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date   TEXT NOT NULL UNIQUE,
    total_assets    REAL NOT NULL,
    total_liabilities REAL NOT NULL,
    net_worth       REAL NOT NULL,
    breakdown_json  TEXT                       -- per-bucket detail
);

-- =========================================================================
-- REMINDERS  (SIP due, FD maturity, premiums, EMI)
-- =========================================================================
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    amount      REAL,
    holding_id  INTEGER,
    liability_id INTEGER,
    is_done     INTEGER DEFAULT 0,
    notes       TEXT,
    FOREIGN KEY (holding_id) REFERENCES holdings(id) ON DELETE CASCADE,
    FOREIGN KEY (liability_id) REFERENCES liabilities(id) ON DELETE CASCADE
);

-- =========================================================================
-- REFERENCE  (loaded from data/reference/*.json — tax slabs, inflation)
-- =========================================================================
CREATE TABLE IF NOT EXISTS reference_data (
    key       TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- FX RATES  (user-maintained; converts non-INR account balances into INR)
-- Stored in data/store/fx_rates.json like any other user record.
-- =========================================================================
CREATE TABLE IF NOT EXISTS fx_rates (
    currency    TEXT PRIMARY KEY,          -- ISO code, e.g. USD
    rate_to_inr REAL NOT NULL,             -- 1 unit of `currency` = this many rupees
    as_of       TEXT,                      -- YYYY-MM-DD the rate was entered
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- STOCK MASTER  (reference: shipped in data/seed/stock_master.csv)
-- Used to auto-fill market cap / sector when a stock symbol is entered.
-- =========================================================================
CREATE TABLE IF NOT EXISTS stock_master (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,
    exchange    TEXT,
    market_cap  TEXT,                      -- sme | small_cap | mid_cap | large_cap
    sector      TEXT
);

-- ==========================================================