"""
本地 SQLite 数据存储模块

股票数据库 → EASTMONEY_STOCK_DATA_DIR 或 Desktop/股票信息/stock_data.db
板块数据库 → EASTMONEY_SECTOR_DATA_DIR 或 Desktop/分析板块/sector_data.db
"""

import os
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path


def _desktop_path(sub_dir: str) -> str:
    desktop = Path.home() / "Desktop" / sub_dir
    desktop.mkdir(parents=True, exist_ok=True)
    return str(desktop)


STOCK_DIR = os.environ.get("EASTMONEY_STOCK_DATA_DIR", _desktop_path("股票信息"))
SECTOR_DIR = os.environ.get("EASTMONEY_SECTOR_DATA_DIR", _desktop_path("分析板块"))

STOCK_DB = os.path.join(STOCK_DIR, "stock_data.db")
SECTOR_DB = os.path.join(SECTOR_DIR, "sector_data.db")

_lock = threading.Lock()


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


# ════════════════════════════════════════
# 初始化建表
# ════════════════════════════════════════

STOCK_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS stock_basic (
    symbol    TEXT PRIMARY KEY,
    name      TEXT,
    raw_symbol TEXT
);

CREATE TABLE IF NOT EXISTS stock_kline (
    symbol       TEXT,
    date         TEXT,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       REAL,
    amount       REAL,
    amplitude    REAL,
    change_pct   REAL,
    change_amount REAL,
    turnover_rate REAL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_kline_date ON stock_kline(date);

CREATE TABLE IF NOT EXISTS stock_spot (
    symbol          TEXT PRIMARY KEY,
    name            TEXT,
    latest_price    REAL,
    change_pct      REAL,
    change_amount   REAL,
    volume          REAL,
    amount          REAL,
    amplitude       REAL,
    high            REAL,
    low             REAL,
    open            REAL,
    pre_close       REAL,
    volume_ratio    REAL,
    turnover_rate   REAL,
    pe_dynamic      REAL,
    pb              REAL,
    total_market_cap REAL,
    float_market_cap REAL,
    speed           REAL,
    sixty_day_change REAL,
    ytd_change      REAL,
    updated_date    TEXT
);

CREATE TABLE IF NOT EXISTS stock_rank (
    symbol         TEXT,
    name           TEXT,
    rank_date      TEXT,
    latest_price   REAL,
    change_pct     REAL,
    volume_ratio   REAL,
    high           REAL,
    low            REAL,
    pre_close      REAL,
    volume         REAL,
    amount         REAL,
    turnover_rate  REAL,
    popularity_rank REAL,
    PRIMARY KEY (rank_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_rank_date ON stock_rank(rank_date);
CREATE INDEX IF NOT EXISTS idx_rank_symbol ON stock_rank(symbol);

CREATE TABLE IF NOT EXISTS stock_indicators (
    symbol    TEXT,
    date      TEXT,
    MA5       REAL, MA10 REAL, MA20 REAL, MA30 REAL, MA60 REAL, MA100 REAL, MA200 REAL,
    RSI6      REAL, RSI14 REAL, RSI24 REAL,
    DIF       REAL, DEA REAL, MACD REAL,
    BOLL_UPPER  REAL, BOLL_MIDDLE REAL, BOLL_LOWER REAL,
    KDJ_K     REAL, KDJ_D REAL, KDJ_J REAL,
    VOL_MA5   REAL, VOL_MA10 REAL,
    ATR14     REAL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_ind_date ON stock_indicators(date);
"""

SECTOR_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sector_basic (
    sector_code     TEXT PRIMARY KEY,
    sector_name     TEXT,
    sector_type     TEXT,
    latest_index    REAL,
    change_pct      REAL,
    main_net_inflow REAL,
    main_net_pct    REAL,
    super_large_net REAL,
    super_large_pct REAL,
    large_net       REAL,
    large_pct       REAL,
    medium_net      REAL,
    medium_pct      REAL,
    small_net       REAL,
    small_pct       REAL,
    lead_stock_name TEXT,
    lead_stock_code TEXT,
    updated_date    TEXT
);

CREATE TABLE IF NOT EXISTS sector_kline (
    sector_code   TEXT,
    trade_date    TEXT,
    open          REAL,
    close         REAL,
    high          REAL,
    low           REAL,
    volume        REAL,
    turnover      REAL,
    amplitude     REAL,
    change_pct    REAL,
    change_amount REAL,
    turnover_rate REAL,
    PRIMARY KEY (sector_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_skline_date ON sector_kline(trade_date);

CREATE TABLE IF NOT EXISTS sector_member (
    sector_code    TEXT,
    stock_code     TEXT,
    stock_name     TEXT,
    latest_price   REAL,
    change_pct     REAL,
    change_amount  REAL,
    volume         REAL,
    turnover       REAL,
    amplitude      REAL,
    turnover_rate  REAL,
    volume_ratio   REAL,
    high           REAL,
    low            REAL,
    open_today     REAL,
    close_yesterday REAL,
    pb             REAL,
    pe_dynamic     REAL,
    updated_date   TEXT,
    PRIMARY KEY (sector_code, stock_code)
);
CREATE INDEX IF NOT EXISTS idx_sm_sector ON sector_member(sector_code);
CREATE INDEX IF NOT EXISTS idx_sm_stock ON sector_member(stock_code);
"""


def init_stock_db():
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executescript(STOCK_DDL)
        conn.commit()
        conn.close()


def init_sector_db():
    with _lock:
        conn = _get_conn(SECTOR_DB)
        conn.executescript(SECTOR_DDL)
        conn.commit()
        conn.close()


def init_all():
    init_stock_db()
    init_sector_db()


# ════════════════════════════════════════
# Stock DB 写入
# ════════════════════════════════════════

def save_stock_basic(rows: list[dict]):
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(
            "INSERT OR REPLACE INTO stock_basic(symbol,name,raw_symbol) VALUES(:symbol,:name,:raw_symbol)",
            rows,
        )
        conn.commit()
        conn.close()


def save_stock_kline(rows: list[dict]):
    cols = [
        "symbol", "date", "open", "high", "low", "close",
        "volume", "amount", "amplitude", "change_pct", "change_amount", "turnover_rate",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO stock_kline ({col_list}) VALUES ({placeholders})",
            rows_padded,
        )
        conn.commit()
        conn.close()


def save_stock_spot(rows: list[dict]):
    cols = [
        "symbol", "name", "latest_price", "change_pct", "change_amount",
        "volume", "amount", "amplitude", "high", "low", "open", "pre_close",
        "volume_ratio", "turnover_rate", "pe_dynamic", "pb",
        "total_market_cap", "float_market_cap", "speed", "sixty_day_change",
        "ytd_change", "updated_date",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO stock_spot ({col_list}) VALUES ({placeholders})",
            rows_padded,
        )
        conn.commit()
        conn.close()


def save_stock_rank(rows: list[dict]):
    cols = [
        "symbol", "name", "rank_date", "latest_price", "change_pct",
        "volume_ratio", "high", "low", "pre_close",
        "volume", "amount", "turnover_rate", "popularity_rank",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO stock_rank ({col_list}) VALUES ({placeholders})",
            rows_padded,
        )
        conn.commit()
        conn.close()


def save_stock_indicators(rows: list[dict]):
    cols = [
        "symbol", "date",
        "MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
        "RSI6", "RSI14", "RSI24",
        "DIF", "DEA", "MACD",
        "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
        "KDJ_K", "KDJ_D", "KDJ_J",
        "VOL_MA5", "VOL_MA10",
        "ATR14",
    ]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO stock_indicators ({col_list}) VALUES ({placeholders})",
            rows,
        )
        conn.commit()
        conn.close()


def set_meta_stock(key: str, value: str):
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
            (key, value, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()


# ════════════════════════════════════════
# Sector DB 写入
# ════════════════════════════════════════

def save_sector_basic(rows: list[dict]):
    cols = [
        "sector_code", "sector_name", "sector_type", "latest_index", "change_pct",
        "main_net_inflow", "main_net_pct",
        "super_large_net", "super_large_pct", "large_net", "large_pct",
        "medium_net", "medium_pct", "small_net", "small_pct",
        "lead_stock_name", "lead_stock_code", "updated_date",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(SECTOR_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO sector_basic ({col_list}) VALUES ({placeholders})",
            rows_padded,
        )
        conn.commit()
        conn.close()


def save_sector_kline(rows: list[dict]):
    cols = [
        "sector_code", "trade_date", "open", "close", "high", "low",
        "volume", "turnover", "amplitude", "change_pct", "change_amount", "turnover_rate",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(SECTOR_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO sector_kline ({col_list}) VALUES ({placeholders})",
            rows_padded,
        )
        conn.commit()
        conn.close()


def save_sector_member(rows: list[dict]):
    cols = [
        "sector_code", "stock_code", "stock_name",
        "latest_price", "change_pct", "change_amount",
        "volume", "turnover", "amplitude", "turnover_rate", "volume_ratio",
        "high", "low", "open_today", "close_yesterday", "pb", "pe_dynamic", "updated_date",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(SECTOR_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO sector_member ({col_list}) VALUES ({placeholders})",
            rows_padded,
        )
        conn.commit()
        conn.close()


def set_meta_sector(key: str, value: str):
    with _lock:
        conn = _get_conn(SECTOR_DB)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
            (key, value, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()


# ════════════════════════════════════════
# 查询接口
# ════════════════════════════════════════

def query_stock_db(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        conn = _get_conn(STOCK_DB)
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


def query_sector_db(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        conn = _get_conn(SECTOR_DB)
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


def get_meta_stock(key: str) -> str | None:
    rows = query_stock_db("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


def get_meta_sector(key: str) -> str | None:
    rows = query_sector_db("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


def get_db_paths() -> dict:
    return {"stock_db": STOCK_DB, "sector_db": SECTOR_DB, "stock_dir": STOCK_DIR, "sector_dir": SECTOR_DIR}
