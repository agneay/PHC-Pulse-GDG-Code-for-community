"""SQLite storage. The schema mirrors the BigQuery warehouse tables in /bigquery/schema.sql so
the same rows can be streamed to BigQuery in production."""
import sqlite3
import threading
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS states (
    code TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS districts (
    code TEXT PRIMARY KEY, state_code TEXT NOT NULL, name TEXT NOT NULL, lat REAL, lon REAL
);
CREATE TABLE IF NOT EXISTS phcs (
    id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, block TEXT,
    district_code TEXT NOT NULL, state_code TEXT NOT NULL, lat REAL, lon REAL,
    beds_total INTEGER, staff_sanctioned INTEGER, is_24x7 INTEGER, language TEXT,
    supply_anchor TEXT,           -- a date on which the monthly indent is delivered
    nin TEXT                      -- National Identification Number (HMIS facility id)
);
CREATE TABLE IF NOT EXISTS drugs (
    code TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_daily (
    phc_id INTEGER NOT NULL, drug_code TEXT NOT NULL, day TEXT NOT NULL,
    opening REAL, received REAL, dispensed REAL, unmet REAL, adjustment REAL, closing REAL,
    source TEXT, PRIMARY KEY (phc_id, drug_code, day)
);
CREATE TABLE IF NOT EXISTS footfall_daily (
    phc_id INTEGER NOT NULL, day TEXT NOT NULL,
    opd INTEGER, fever INTEGER, diarrhoea INTEGER, respiratory INTEGER,
    beds_occupied INTEGER, staff_present INTEGER, source TEXT,
    PRIMARY KEY (phc_id, day)
);
CREATE TABLE IF NOT EXISTS workers (
    phone TEXT PRIMARY KEY, name TEXT, role TEXT, phc_id INTEGER, language TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, phc_id INTEGER NOT NULL, created_at TEXT NOT NULL,
    channel TEXT, language TEXT, transcript TEXT, parsed_json TEXT, confirmation TEXT,
    reporter TEXT, engine TEXT
);
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
    from_phc INTEGER NOT NULL, to_phc INTEGER NOT NULL,
    lines_json TEXT NOT NULL,     -- [{"drug_code":..,"qty":..,"needed_in_days":..}]
    distance_km REAL, cost_inr REAL, eta_hours REAL, status TEXT NOT NULL,
    reason TEXT, created_at TEXT, updated_at TEXT, approved_by TEXT, history_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_stock_day ON stock_daily(day);
CREATE INDEX IF NOT EXISTS idx_foot_day ON footfall_daily(day);
"""

_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def get_conn():
    """Serialised connection; SQLite is the single-instance prototype store."""
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
