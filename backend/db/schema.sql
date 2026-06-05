-- Trade Review · SQLite Schema v1.0
-- 参见 DESIGN.md §4

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    market          TEXT NOT NULL CHECK (market IN ('A', 'HK', 'US')),
    name            TEXT,
    action          TEXT NOT NULL CHECK (action IN ('buy', 'sell')),
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    trade_time      TEXT NOT NULL,
    reason          TEXT,
    mood            TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    market          TEXT NOT NULL,
    name            TEXT,
    quantity        INTEGER NOT NULL,
    cost_price      REAL NOT NULL,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, market)
);

CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_type     TEXT NOT NULL CHECK (review_type IN ('flash', 'daily')),
    trade_id        INTEGER REFERENCES trades(id),
    review_date     TEXT NOT NULL,
    scores_json     TEXT,
    tags_json       TEXT,
    report_md       TEXT NOT NULL,
    scenarios_json  TEXT,
    lesson          TEXT,
    ai_engine       TEXT,
    ai_latency_ms   INTEGER,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mindset_tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id),
    tag             TEXT NOT NULL,
    severity        TEXT CHECK (severity IN ('light', 'medium', 'heavy')),
    evidence_json   TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weekly_mindset (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year_week       TEXT NOT NULL UNIQUE,
    week_start      TEXT NOT NULL,
    week_end        TEXT NOT NULL,
    radar_json      TEXT,
    tags_summary    TEXT,
    top_errors_json TEXT,
    ai_message      TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trade_outcomes (
    trade_id        INTEGER PRIMARY KEY REFERENCES trades(id),
    t_plus_1_pct    REAL,
    t_plus_3_pct    REAL,
    t_plus_5_pct    REAL,
    hindsight_tag   TEXT,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(symbol, trade_time DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_date ON reviews(review_date DESC);
CREATE INDEX IF NOT EXISTS idx_mindset_tags_trade ON mindset_tags(trade_id);

-- ─── Quant subsystem (v1.0) ────────────────────────────────────────────
-- 本地行情缓存。后复权价存 *_hfq 列；原始价用于真实成交对比。
CREATE TABLE IF NOT EXISTS daily_quotes (
    symbol      TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    turnover    REAL,
    pct_chg     REAL,
    adjust      TEXT NOT NULL DEFAULT 'hfq',
    PRIMARY KEY (symbol, trade_date, adjust)
);
CREATE INDEX IF NOT EXISTS idx_quotes_date ON daily_quotes(trade_date);

-- 基本面日频快照(来自百度估值,point-in-time)。pe_ttm/pb 可为负(亏损/负净资产)。
CREATE TABLE IF NOT EXISTS fundamental_quotes (
    symbol      TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    pe_ttm      REAL,
    pb          REAL,
    total_mv    REAL,
    PRIMARY KEY (symbol, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_fundq_date ON fundamental_quotes(trade_date);

-- 因子快照:每个交易日每只股票的因子值与综合打分。
CREATE TABLE IF NOT EXISTS factor_snapshots (
    snapshot_date TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    factors_json  TEXT NOT NULL,
    composite     REAL,
    rank          INTEGER,
    PRIMARY KEY (snapshot_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_rank ON factor_snapshots(snapshot_date, rank);

-- 策略当日信号:Top N 候选 + 入选理由。
CREATE TABLE IF NOT EXISTS strategy_signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy      TEXT NOT NULL,
    signal_date   TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    score         REAL,
    reason_json   TEXT,
    consumed      INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (strategy, signal_date, symbol, side)
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON strategy_signals(signal_date, strategy);

-- 策略归因绩效。closed trade 聚合;按 strategy 维度评估。
CREATE TABLE IF NOT EXISTS strategy_performance (
    strategy      TEXT NOT NULL,
    eval_date     TEXT NOT NULL,
    n_trades      INTEGER,
    win_rate      REAL,
    avg_return    REAL,
    sharpe        REAL,
    max_drawdown  REAL,
    metrics_json  TEXT,
    PRIMARY KEY (strategy, eval_date)
);
