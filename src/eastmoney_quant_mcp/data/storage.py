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

from ..core.config import get_settings


# ── Lazy initialization ──
# Paths are computed on first access (not at import time) to avoid
# triggering filesystem operations (mkdir) during module import.
# This ensures unit tests and lightweight imports don't create directories.

_db_paths_cache: dict[str, str] = {}


def _ensure_paths() -> None:
    """Compute and cache DB paths on first access."""
    if _db_paths_cache:
        return
    settings = get_settings()
    stock_dir = settings.stock_dir
    sector_dir = settings.sector_dir
    stock_dir.mkdir(parents=True, exist_ok=True)
    sector_dir.mkdir(parents=True, exist_ok=True)
    _db_paths_cache["STOCK_DIR"] = str(stock_dir)
    _db_paths_cache["SECTOR_DIR"] = str(sector_dir)
    _db_paths_cache["STOCK_DB"] = os.path.join(str(stock_dir), "stock_data.db")
    _db_paths_cache["SECTOR_DB"] = os.path.join(str(sector_dir), "sector_data.db")


def get_stock_db() -> str:
    """Get stock database path (lazy-initialized)."""
    _ensure_paths()
    return _db_paths_cache["STOCK_DB"]


def get_sector_db() -> str:
    """Get sector database path (lazy-initialized)."""
    _ensure_paths()
    return _db_paths_cache["SECTOR_DB"]


def __getattr__(name: str):
    """Module-level __getattr__ for backward-compatible lazy access to STOCK_DB/SECTOR_DB/etc."""
    if name in ("STOCK_DIR", "SECTOR_DIR", "STOCK_DB", "SECTOR_DB"):
        _ensure_paths()
        return _db_paths_cache[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_lock = threading.Lock()

# 已完成建表的库路径(进程内只建一次; DDL 全部 IF NOT EXISTS, 重复执行也安全)
_schema_ready: set = set()


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    # 首次连接时幂等建表, 避免 init_full_data 之前调用只读工具时
    # 抛出 "no such table" (如新库上直接调 get_data_status/screen_stocks)
    if db_path not in _schema_ready:
        ddl = STOCK_DDL if db_path == STOCK_DB else SECTOR_DDL
        conn.executescript(ddl)
        conn.commit()
        _schema_ready.add(db_path)
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

CREATE TABLE IF NOT EXISTS daily_stock_info (
    trade_date   TEXT NOT NULL,
    capture_time TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    name         TEXT,
    latest_price REAL, change_pct REAL, change_amount REAL,
    volume REAL, amount REAL, amplitude REAL, turnover_rate REAL,
    high REAL, low REAL, open REAL, pre_close REAL,
    volume_ratio REAL, volume_ratio_5d REAL, amplitude_5d REAL,
    pe_dynamic REAL, pe_ttm REAL, pb REAL,
    total_market_cap REAL, float_market_cap REAL,
    speed REAL, five_min_change REAL, sixty_day_change REAL, ytd_change REAL,
    main_net_inflow REAL, sector_name TEXT,
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_daily_info_sym ON daily_stock_info(symbol, trade_date);

CREATE TABLE IF NOT EXISTS stock_popularity_rank (
    trade_date          TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    rank                INTEGER,
    rank_time           TEXT,
    rank_change         INTEGER,
    hour_rank_change    INTEGER,
    his_rank_change     INTEGER,
    his_rank_change_rank INTEGER,
    hot_rank_score      REAL,
    market_all_count    INTEGER,
    source              TEXT NOT NULL DEFAULT 'guba',
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_pop_rank_sym ON stock_popularity_rank(symbol, trade_date);

CREATE TABLE IF NOT EXISTS stock_daily_combined (
    trade_date   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    name         TEXT,
    capture_time TEXT,
    open REAL, high REAL, low REAL, close REAL, pre_close REAL,
    latest_price REAL, change_pct REAL, change_amount REAL,
    volume REAL, amount REAL, amplitude REAL, turnover_rate REAL,
    volume_ratio REAL, volume_ratio_5d REAL, amplitude_5d REAL,
    pe_dynamic REAL, pe_ttm REAL, pb REAL,
    total_market_cap REAL, float_market_cap REAL,
    speed REAL, five_min_change REAL, sixty_day_change REAL, ytd_change REAL,
    main_net_inflow REAL, sector_name TEXT,
    popularity_rank INTEGER, rank_time TEXT, rank_source TEXT,
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_combined_sym ON stock_daily_combined(symbol, trade_date);

CREATE TABLE IF NOT EXISTS rebuild_progress (
    step       TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    rows       INTEGER,
    updated_at TEXT,
    PRIMARY KEY (step, symbol)
);
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

CREATE TABLE IF NOT EXISTS sector_indicators (
    sector_code TEXT,
    trade_date  TEXT,
    MA5 REAL, MA10 REAL, MA20 REAL, MA30 REAL, MA60 REAL, MA100 REAL, MA200 REAL,
    RSI6 REAL, RSI14 REAL, RSI24 REAL,
    DIF REAL, DEA REAL, MACD REAL,
    BOLL_UPPER REAL, BOLL_MIDDLE REAL, BOLL_LOWER REAL,
    KDJ_K REAL, KDJ_D REAL, KDJ_J REAL,
    VOL_MA5 REAL, VOL_MA10 REAL,
    ATR14 REAL,
    PRIMARY KEY (sector_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_sind_date ON sector_indicators(trade_date);
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


# ════════════════════════════════════════
# 历史快照 / 人气排名 / 合并表 (移植自"股票信息"项目)
# ════════════════════════════════════════

# 与"股票信息"项目 stock_db.py 的 SPOT_COLUMNS 对齐
SPOT_COLUMNS = [
    "name", "latest_price", "change_pct", "change_amount",
    "volume", "amount", "amplitude", "turnover_rate",
    "high", "low", "open", "pre_close",
    "volume_ratio", "volume_ratio_5d", "amplitude_5d",
    "pe_dynamic", "pe_ttm", "pb",
    "total_market_cap", "float_market_cap",
    "speed", "five_min_change", "sixty_day_change", "ytd_change",
    "main_net_inflow", "sector_name",
]

RANK_COLUMNS = [
    "rank", "rank_time", "rank_change", "hour_rank_change",
    "his_rank_change", "his_rank_change_rank",
    "hot_rank_score", "market_all_count",
]

# stock_daily_combined 中来自 spot 的列 (close 由 latest_price 填充)
COMBINED_SPOT_COLUMNS = [
    "open", "high", "low", "close", "pre_close",
    "latest_price", "change_pct", "change_amount",
    "volume", "amount", "amplitude", "turnover_rate",
    "volume_ratio", "volume_ratio_5d", "amplitude_5d",
    "pe_dynamic", "pe_ttm", "pb",
    "total_market_cap", "float_market_cap",
    "speed", "five_min_change", "sixty_day_change", "ytd_change",
    "main_net_inflow", "sector_name",
]


def save_daily_stock_info(trade_date: str, capture_time: str, rows: list[dict]) -> int:
    """全市场 spot 快照 -> daily_stock_info (INSERT OR REPLACE, 返回写入行数)"""
    if not rows:
        return 0
    cols = ["trade_date", "capture_time", "symbol"] + SPOT_COLUMNS
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    payload = [
        {**{"trade_date": trade_date, "capture_time": capture_time, "symbol": r["symbol"]},
         **{c: r.get(c) for c in SPOT_COLUMNS}}
        for r in rows
    ]
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO daily_stock_info ({col_list}) VALUES ({placeholders})",
            payload,
        )
        conn.commit()
        conn.close()
    return len(payload)


def save_popularity_rank(rows: list[dict], replace: bool = True) -> int:
    """人气排名 -> stock_popularity_rank

    replace=True  (xuangu 快照): ON CONFLICT DO UPDATE, 覆盖已有值(当日权威值)
    replace=False (guba 年文件): INSERT OR IGNORE, 不覆盖 xuangu 已写日期
    """
    if not rows:
        return 0
    cols = ["trade_date", "symbol"] + RANK_COLUMNS + ["source"]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    payload = [
        {**{"trade_date": r["trade_date"], "symbol": r["symbol"]},
         **{c: r.get(c) for c in RANK_COLUMNS},
         "source": r.get("source") or "guba"}
        for r in rows
    ]
    if replace:
        update_sql = ", ".join(
            f"{c} = COALESCE(excluded.{c}, stock_popularity_rank.{c})"
            for c in RANK_COLUMNS + ["source"]
        )
        sql = (f"INSERT INTO stock_popularity_rank ({col_list}) VALUES ({placeholders}) "
               f"ON CONFLICT(trade_date, symbol) DO UPDATE SET {update_sql}")
    else:
        sql = f"INSERT OR IGNORE INTO stock_popularity_rank ({col_list}) VALUES ({placeholders})"
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.executemany(sql, payload)
        conn.commit()
        conn.close()
    return len(payload)


def build_combined_from_history() -> int:
    """K线 INNER JOIN 排名 -> stock_daily_combined (只生成有K线的交易日行)"""
    with _lock:
        conn = _get_conn(STOCK_DB)
        cur = conn.execute("""
            INSERT OR REPLACE INTO stock_daily_combined
                (trade_date, symbol, name,
                 open, high, low, close, latest_price, change_pct, change_amount,
                 volume, amount, amplitude, turnover_rate,
                 popularity_rank, rank_time, rank_source)
            SELECT r.trade_date, r.symbol, l.name,
                   h.open, h.high, h.low, h.close,
                   h.close, h.change_pct, h.change_amount,
                   h.volume, h.amount, h.amplitude, h.turnover_rate,
                   r.rank, r.rank_time, r.source
            FROM stock_popularity_rank r
            INNER JOIN stock_kline h ON h.symbol = r.symbol AND h.date = r.trade_date
            LEFT JOIN stock_basic l ON l.symbol = r.symbol
        """)
        n = cur.rowcount
        conn.commit()
        conn.close()
    return n


def upsert_combined_spot() -> int:
    """daily_stock_info 全部行 -> stock_daily_combined (spot 列, 不清除已有排名)"""
    spot_cols_sql = ", ".join(COMBINED_SPOT_COLUMNS)
    # daily_stock_info 无 close 列, 用 latest_price 作为 combined.close
    spot_select_sql = ", ".join(
        "d.latest_price AS close" if c == "close" else f"d.{c}"
        for c in COMBINED_SPOT_COLUMNS
    )
    set_parts = (
        ["name = COALESCE(excluded.name, stock_daily_combined.name)",
         "capture_time = excluded.capture_time"]
        + [f"{c} = COALESCE(excluded.{c}, stock_daily_combined.{c})" for c in COMBINED_SPOT_COLUMNS]
        + ["popularity_rank = COALESCE(excluded.popularity_rank, stock_daily_combined.popularity_rank)",
           "rank_time = COALESCE(excluded.rank_time, stock_daily_combined.rank_time)",
           "rank_source = COALESCE(excluded.rank_source, stock_daily_combined.rank_source)"]
    )
    with _lock:
        conn = _get_conn(STOCK_DB)
        cur = conn.execute(f"""
            INSERT INTO stock_daily_combined
                (trade_date, symbol, name, capture_time, {spot_cols_sql},
                 popularity_rank, rank_time, rank_source)
            SELECT d.trade_date, d.symbol, d.name, d.capture_time, {spot_select_sql},
                   r.rank, r.rank_time, r.source
            FROM daily_stock_info d
            LEFT JOIN stock_popularity_rank r
                   ON r.trade_date = d.trade_date AND r.symbol = d.symbol
            ON CONFLICT(trade_date, symbol) DO UPDATE SET {', '.join(set_parts)}
        """)
        n = cur.rowcount
        conn.commit()
        conn.close()
    return n


def upsert_combined_rank(trade_date: str) -> int:
    """某交易日的排名 -> stock_daily_combined 排名列 (不清除已有 spot 列)"""
    with _lock:
        conn = _get_conn(STOCK_DB)
        cur = conn.execute("""
            INSERT INTO stock_daily_combined
                (trade_date, symbol, popularity_rank, rank_time, rank_source)
            SELECT trade_date, symbol, rank, rank_time, source
            FROM stock_popularity_rank
            WHERE trade_date = ?
            ON CONFLICT(trade_date, symbol) DO UPDATE SET
                popularity_rank = excluded.popularity_rank,
                rank_time = excluded.rank_time,
                rank_source = excluded.rank_source
        """, (trade_date,))
        n = cur.rowcount
        conn.commit()
        conn.close()
    return n


def record_rebuild_progress(step: str, symbol: str, rows: int) -> None:
    """记录重建断点续传进度"""
    with _lock:
        conn = _get_conn(STOCK_DB)
        conn.execute(
            "INSERT OR REPLACE INTO rebuild_progress(step, symbol, rows, updated_at) "
            "VALUES(?,?,?,?)",
            (step, symbol, rows, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()


def get_rebuild_done(step: str) -> set[str]:
    """某步骤已完成的 symbol 集合(断点续传)"""
    rows = query_stock_db("SELECT symbol FROM rebuild_progress WHERE step=?", (step,))
    return {r["symbol"] for r in rows}


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


def save_sector_indicators(rows: list[dict]):
    """板块技术指标缓存 -> sector_indicators (列与 stock_indicators 一致)"""
    cols = [
        "sector_code", "trade_date",
        "MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
        "RSI6", "RSI14", "RSI24",
        "DIF", "DEA", "MACD",
        "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
        "KDJ_K", "KDJ_D", "KDJ_J",
        "VOL_MA5", "VOL_MA10",
        "ATR14",
    ]
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list = ", ".join(cols)
    with _lock:
        conn = _get_conn(SECTOR_DB)
        conn.executemany(
            f"INSERT OR REPLACE INTO sector_indicators ({col_list}) VALUES ({placeholders})",
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
