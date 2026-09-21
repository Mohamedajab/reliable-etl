SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS etl_run (
    run_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    rows_read INTEGER NOT NULL DEFAULT 0,
    rows_accepted INTEGER NOT NULL DEFAULT 0,
    rows_rejected INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS transaction_fact (
    transaction_id TEXT PRIMARY KEY,
    transaction_date TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price NUMERIC NOT NULL CHECK(unit_price >= 0),
    amount NUMERIC NOT NULL CHECK(amount >= 0),
    source_run_id TEXT NOT NULL REFERENCES etl_run(run_id),
    loaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected_record (
    reject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES etl_run(run_id),
    row_number INTEGER NOT NULL,
    raw_record TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    rejected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_date ON transaction_fact(transaction_date);
CREATE INDEX IF NOT EXISTS idx_reject_run ON rejected_record(run_id);
"""

