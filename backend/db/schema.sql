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
