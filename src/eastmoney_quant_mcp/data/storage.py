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
from ..core.constants import INDICATOR_VERSION, PATTERN_ENGINE_VERSION, SCHEMA_VERSION


# ── Lazy initialization ──
# Paths are computed on first access (not at import time) to avoid
# triggering filesystem operations (mkdir) during module import.
# This ensures unit tests and lightweight imports don't create directories.

_db_paths_cache: dict[str, str] = {}

# 测试/临时库重定向: 非空时优先生效 (monkeypatch storage.STOCK_DB 等不再影响内部函数)
_path_overrides: dict[str, str | None] = {
    "STOCK_DIR": None, "SECTOR_DIR": None, "STOCK_DB": None, "SECTOR_DB": None,
}


def set_db_paths(stock_db: str | None = None, sector_db: str | None = None) -> None:
    """重定向数据库路径(测试用); 传 None 清除对应重定向。"""
    if stock_db is not None:
        _path_overrides["STOCK_DB"] = stock_db
        _path_overrides["STOCK_DIR"] = str(Path(stock_db).parent)
    else:
        _path_overrides["STOCK_DB"] = None
        _path_overrides["STOCK_DIR"] = None
    if sector_db is not None:
        _path_overrides["SECTOR_DB"] = sector_db
        _path_overrides["SECTOR_DIR"] = str(Path(sector_db).parent)
    else:
        _path_overrides["SECTOR_DB"] = None
        _path_overrides["SECTOR_DIR"] = None


def _resolve_path(name: str) -> str:
    """优先取重定向路径, 否则懒加载默认路径。"""
    override = _path_overrides.get(name)
    if override:
        return override
    _ensure_paths()
    return _db_paths_cache[name]


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
    return _resolve_path("STOCK_DB")


def get_sector_db() -> str:
    """Get sector database path (lazy-initialized)."""
    return _resolve_path("SECTOR_DB")


def __getattr__(name: str):
    """Module-level __getattr__ for backward-compatible lazy access to STOCK_DB/SECTOR_DB/etc."""
    if name in ("STOCK_DIR", "SECTOR_DIR", "STOCK_DB", "SECTOR_DB"):
        return _resolve_path(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_lock = threading.Lock()
_init_lock = threading.Lock()

# 已完成建表的库路径(进程内只建一次; DDL 全部 IF NOT EXISTS, 重复执行也安全)
_schema_ready: set = set()


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    # 跨进程/跨线程并发写时等待锁而不是立刻抛 "database is locked"
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    # 首次连接时幂等建表, 避免 init_full_data 之前调用只读工具时
    # 抛出 "no such table" (如新库上直接调 get_data_status/screen_stocks)
    if db_path not in _schema_ready:
        with _init_lock:
            if db_path not in _schema_ready:
                ddl = STOCK_DDL if db_path == get_stock_db() else SECTOR_DDL
                conn.executescript(ddl)
                if db_path == get_stock_db():
                    _migrate_stock_schema(conn)
                else:
                    _migrate_sector_schema(conn)
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
    adjust_type  TEXT NOT NULL DEFAULT 'qfq',
    source       TEXT,
    fetched_at   TEXT,
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
    PRIMARY KEY (symbol, date, adjust_type)
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
    adjust_type TEXT NOT NULL DEFAULT 'qfq',
    indicator_version TEXT,
    MA5       REAL, MA10 REAL, MA20 REAL, MA30 REAL, MA60 REAL, MA100 REAL, MA120 REAL, MA200 REAL, MA250 REAL,
    RSI6      REAL, RSI14 REAL, RSI24 REAL,
    DIF       REAL, DEA REAL, MACD REAL,
    BOLL_UPPER  REAL, BOLL_MIDDLE REAL, BOLL_LOWER REAL,
    KDJ_K     REAL, KDJ_D REAL, KDJ_J REAL,
    VOL_MA5   REAL, VOL_MA10 REAL, VOL_MA20 REAL, VOL_RATIO5 REAL, VOL_RATIO20 REAL,
    ATR14     REAL, ATR_PCT REAL,
    BIAS20 REAL, BIAS60 REAL, BIAS250 REAL,
    RETURN_5 REAL, RETURN_10 REAL, RETURN_20 REAL, RETURN_60 REAL,
    HIGH_20 REAL, HIGH_60 REAL, HIGH_120 REAL,
    LOW_20 REAL, LOW_60 REAL, LOW_120 REAL,
    PRIMARY KEY (symbol, date, adjust_type)
);
CREATE INDEX IF NOT EXISTS idx_ind_date ON stock_indicators(date);

-- Legacy multi-gigabyte databases keep their original (symbol,date) primary key.
-- Non-qfq variants are stored here, avoiding a full-table copy migration.
CREATE TABLE IF NOT EXISTS stock_kline_variants (
    symbol TEXT, date TEXT, adjust_type TEXT NOT NULL,
    source TEXT, fetched_at TEXT, open REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL, amplitude REAL, change_pct REAL,
    change_amount REAL, turnover_rate REAL,
    PRIMARY KEY(symbol,date,adjust_type)
);
CREATE TABLE IF NOT EXISTS stock_indicator_variants (
    symbol TEXT, date TEXT, adjust_type TEXT NOT NULL, indicator_version TEXT,
    MA5 REAL, MA10 REAL, MA20 REAL, MA30 REAL, MA60 REAL, MA100 REAL, MA120 REAL, MA200 REAL, MA250 REAL,
    RSI6 REAL, RSI14 REAL, RSI24 REAL, DIF REAL, DEA REAL, MACD REAL,
    BOLL_UPPER REAL, BOLL_MIDDLE REAL, BOLL_LOWER REAL,
    KDJ_K REAL, KDJ_D REAL, KDJ_J REAL, VOL_MA5 REAL, VOL_MA10 REAL,
    VOL_MA20 REAL, VOL_RATIO5 REAL, VOL_RATIO20 REAL, ATR14 REAL, ATR_PCT REAL,
    BIAS20 REAL, BIAS60 REAL, BIAS250 REAL,
    RETURN_5 REAL, RETURN_10 REAL, RETURN_20 REAL, RETURN_60 REAL,
    HIGH_20 REAL, HIGH_60 REAL, HIGH_120 REAL, LOW_20 REAL, LOW_60 REAL, LOW_120 REAL,
    PRIMARY KEY(symbol,date,adjust_type)
);

CREATE TABLE IF NOT EXISTS data_coverage (
    data_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    period TEXT NOT NULL DEFAULT 'daily',
    adjust_type TEXT NOT NULL DEFAULT '',
    first_date TEXT,
    last_date TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'partial',
    last_error TEXT,
    data_version TEXT,
    updated_at TEXT,
    PRIMARY KEY (data_type, symbol, period, adjust_type)
);
CREATE INDEX IF NOT EXISTS idx_coverage_status ON data_coverage(data_type, status);

CREATE TABLE IF NOT EXISTS pattern_signals (
    universe TEXT NOT NULL,
    symbol TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    pattern TEXT NOT NULL,
    stage TEXT NOT NULL,
    score REAL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    trend_state TEXT,
    entry_status TEXT,
    support REAL,
    resistance REAL,
    neckline REAL,
    invalid_level REAL,
    fib_levels_json TEXT,
    evidence_json TEXT,
    factors_json TEXT,
    engine_version TEXT,
    calculated_at TEXT,
    PRIMARY KEY (universe, symbol, signal_date, pattern)
);

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
    source TEXT,
    fetched_at TEXT,
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


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    return {row[1]: {"type": row[2], "pk": row[5]} for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_stock_schema(conn: sqlite3.Connection) -> None:
    """Idempotent, in-place migration safe for multi-gigabyte legacy databases."""
    kcols = _table_columns(conn, "stock_kline")
    kpk = [name for name, meta in sorted(kcols.items(), key=lambda x: x[1]["pk"]) if meta["pk"]]
    if kcols and kpk != ["symbol", "date", "adjust_type"]:
        for name, ddl in (("adjust_type", "TEXT NOT NULL DEFAULT 'qfq'"),
                          ("source", "TEXT DEFAULT 'legacy'"),
                          ("fetched_at", "TEXT")):
            if name not in kcols:
                conn.execute(f"ALTER TABLE stock_kline ADD COLUMN {name} {ddl}")

    icols = _table_columns(conn, "stock_indicators")
    ipk = [name for name, meta in sorted(icols.items(), key=lambda x: x[1]["pk"]) if meta["pk"]]
    if icols and ipk != ["symbol", "date", "adjust_type"]:
        if "adjust_type" not in icols:
            conn.execute("ALTER TABLE stock_indicators ADD COLUMN adjust_type TEXT NOT NULL DEFAULT 'qfq'")
    required = {
        # SQLite applies this metadata-only default to legacy rows without
        # rewriting the multi-gigabyte indicator table.  "legacy" deliberately
        # marks those cached values as stale so callers can recompute lazily.
        "indicator_version": "TEXT DEFAULT 'legacy'", "MA120": "REAL", "MA250": "REAL",
        "VOL_MA20": "REAL", "VOL_RATIO5": "REAL", "VOL_RATIO20": "REAL",
        "ATR_PCT": "REAL", "BIAS20": "REAL", "BIAS60": "REAL", "BIAS250": "REAL",
        "RETURN_5": "REAL", "RETURN_10": "REAL", "RETURN_20": "REAL", "RETURN_60": "REAL",
        "HIGH_20": "REAL", "HIGH_60": "REAL", "HIGH_120": "REAL",
        "LOW_20": "REAL", "LOW_60": "REAL", "LOW_120": "REAL",
    }
    icols = _table_columns(conn, "stock_indicators")
    for name, typ in required.items():
        if name not in icols:
            conn.execute(f"ALTER TABLE stock_indicators ADD COLUMN {name} {typ}")
    now = datetime.now().isoformat()
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("indicator_version", INDICATOR_VERSION),
                       ("pattern_engine_version", PATTERN_ENGINE_VERSION)):
        conn.execute("INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)", (key, value, now))
    # Backfill coverage for legacy databases so status reflects existing usable data.
    conn.execute("""
        INSERT OR REPLACE INTO data_coverage
            (data_type,symbol,period,adjust_type,first_date,last_date,row_count,source,
             status,data_version,updated_at)
        SELECT 'stock_kline',symbol,'daily',adjust_type,MIN(date),MAX(date),COUNT(*),
               COALESCE(MAX(source),'legacy'),
               CASE WHEN COUNT(*)>=260 THEN 'ready' ELSE 'partial' END,?,?
        FROM stock_kline GROUP BY symbol,adjust_type
    """, (SCHEMA_VERSION, now))


def _migrate_sector_schema(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "sector_kline")
    for name in ("source", "fetched_at"):
        if name not in cols:
            conn.execute(f"ALTER TABLE sector_kline ADD COLUMN {name} TEXT")
    conn.execute("INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
                 ("schema_version", SCHEMA_VERSION, datetime.now().isoformat()))


def init_stock_db():
    with _lock:
        conn = _get_conn(get_stock_db())
        try:
            conn.executescript(STOCK_DDL)
            conn.commit()
        finally:
            conn.close()


def init_sector_db():
    with _lock:
        conn = _get_conn(get_sector_db())
        try:
            conn.executescript(SECTOR_DDL)
            conn.commit()
        finally:
            conn.close()


def init_all():
    init_stock_db()
    init_sector_db()


# ════════════════════════════════════════
# Stock DB 写入
# ════════════════════════════════════════

def _save_rows(db_path_fn, table: str, cols: list[str], rows: list[dict]) -> int:
    """save_* 通用模板: 列补齐 -> INSERT OR REPLACE -> 提交 (锁内, 连接 finally 关闭)"""
    if not rows:
        return 0
    rows_padded = [{c: r.get(c) for c in cols} for r in rows]
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    with _lock:
        conn = _get_conn(db_path_fn())
        try:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
                rows_padded,
            )
            conn.commit()
        finally:
            conn.close()
    return len(rows)


def _table_has_adjust_pk(table: str) -> bool:
    conn = _get_conn(get_stock_db())
    try:
        pk = [r[1] for r in sorted(conn.execute(f"PRAGMA table_info({table})"), key=lambda r: r[5]) if r[5]]
        return pk == ["symbol", "date", "adjust_type"]
    finally:
        conn.close()


def save_stock_basic(rows: list[dict]):
    return _save_rows(get_stock_db, "stock_basic", ["symbol", "name", "raw_symbol"], rows)


def save_stock_kline(rows: list[dict]):
    now = datetime.now().isoformat()
    payload = [{**r, "adjust_type": r.get("adjust_type") or "qfq",
                "source": r.get("source") or "unknown",
                "fetched_at": r.get("fetched_at") or now} for r in rows]
    cols = ["symbol", "date", "adjust_type", "source", "fetched_at",
        "open", "high", "low", "close", "volume", "amount", "amplitude", "change_pct",
        "change_amount", "turnover_rate"]
    if _table_has_adjust_pk("stock_kline"):
        return _save_rows(get_stock_db, "stock_kline", cols, payload)
    primary = [r for r in payload if r["adjust_type"] == "qfq"]
    variants = [r for r in payload if r["adjust_type"] != "qfq"]
    return (_save_rows(get_stock_db, "stock_kline", cols, primary)
            + _save_rows(get_stock_db, "stock_kline_variants", cols, variants))


def save_stock_spot(rows: list[dict]):
    return _save_rows(get_stock_db, "stock_spot", ["symbol", "name", "latest_price", "change_pct", "change_amount",
        "volume", "amount", "amplitude", "high", "low", "open", "pre_close",
        "volume_ratio", "turnover_rate", "pe_dynamic", "pb",
        "total_market_cap", "float_market_cap", "speed", "sixty_day_change",
        "ytd_change", "updated_date"], rows)


def save_stock_rank(rows: list[dict]):
    return _save_rows(get_stock_db, "stock_rank", ["symbol", "name", "rank_date", "latest_price", "change_pct",
        "volume_ratio", "high", "low", "pre_close",
        "volume", "amount", "turnover_rate", "popularity_rank"], rows)


def save_stock_indicators(rows: list[dict]):
    payload = [{**r, "adjust_type": r.get("adjust_type") or "qfq",
                "indicator_version": r.get("indicator_version") or INDICATOR_VERSION} for r in rows]
    cols = ["symbol", "date", "adjust_type", "indicator_version",
        "MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA120", "MA200", "MA250",
        "RSI6", "RSI14", "RSI24",
        "DIF", "DEA", "MACD",
        "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
        "KDJ_K", "KDJ_D", "KDJ_J",
        "VOL_MA5", "VOL_MA10", "VOL_MA20", "VOL_RATIO5", "VOL_RATIO20",
        "ATR14", "ATR_PCT", "BIAS20", "BIAS60", "BIAS250",
        "RETURN_5", "RETURN_10", "RETURN_20", "RETURN_60",
        "HIGH_20", "HIGH_60", "HIGH_120", "LOW_20", "LOW_60", "LOW_120"]
    if _table_has_adjust_pk("stock_indicators"):
        return _save_rows(get_stock_db, "stock_indicators", cols, payload)
    primary = [r for r in payload if r["adjust_type"] == "qfq"]
    variants = [r for r in payload if r["adjust_type"] != "qfq"]
    return (_save_rows(get_stock_db, "stock_indicators", cols, primary)
            + _save_rows(get_stock_db, "stock_indicator_variants", cols, variants))


def save_data_coverage(data_type: str, symbol: str, *, period: str = "daily",
                       adjust_type: str = "", first_date: str | None = None,
                       last_date: str | None = None, row_count: int = 0,
                       source: str | None = None, status: str = "partial",
                       last_error: str | None = None, data_version: str | None = None) -> None:
    _save_rows(get_stock_db, "data_coverage", [
        "data_type", "symbol", "period", "adjust_type", "first_date", "last_date",
        "row_count", "source", "status", "last_error", "data_version", "updated_at",
    ], [{"data_type": data_type, "symbol": symbol, "period": period,
         "adjust_type": adjust_type, "first_date": first_date, "last_date": last_date,
         "row_count": row_count, "source": source, "status": status,
         "last_error": last_error, "data_version": data_version,
         "updated_at": datetime.now().isoformat()}])


def save_pattern_signals(rows: list[dict], universe: str = "stocks") -> int:
    import json
    now = datetime.now().isoformat()
    payload = []
    for row in rows:
        payload.append({
            "universe": row.get("universe") or universe, "symbol": row["symbol"],
            "signal_date": row.get("signal_date") or row.get("date"), "pattern": row["pattern"],
            "stage": row.get("stage") or "candidate", "score": row.get("score"),
            "confirmed": int(bool(row.get("confirmed"))), "trend_state": row.get("trend_state"),
            "entry_status": row.get("entry_status"), "support": row.get("support"),
            "resistance": row.get("resistance"), "neckline": row.get("neckline"),
            "invalid_level": row.get("invalid_level"),
            "fib_levels_json": json.dumps(row.get("fib_levels") or {}, ensure_ascii=False),
            "evidence_json": json.dumps(row.get("evidence") or [], ensure_ascii=False),
            "factors_json": json.dumps(row.get("factors") or {}, ensure_ascii=False),
            "engine_version": PATTERN_ENGINE_VERSION, "calculated_at": now,
        })
    return _save_rows(get_stock_db, "pattern_signals", [
        "universe", "symbol", "signal_date", "pattern", "stage", "score", "confirmed",
        "trend_state", "entry_status", "support", "resistance", "neckline", "invalid_level",
        "fib_levels_json", "evidence_json", "factors_json", "engine_version", "calculated_at",
    ], payload)


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
        conn = _get_conn(get_stock_db())
        try:
            conn.executemany(
            f"INSERT OR REPLACE INTO daily_stock_info ({col_list}) VALUES ({placeholders})",
            payload,
            )
            conn.commit()
        finally:
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
        conn = _get_conn(get_stock_db())
        try:
            conn.executemany(sql, payload)
            conn.commit()
        finally:
            conn.close()
    return len(payload)


def build_combined_from_history() -> int:
    """K线 INNER JOIN 排名 -> stock_daily_combined (只生成有K线的交易日行)"""
    with _lock:
        conn = _get_conn(get_stock_db())
        try:
            # ON CONFLICT 只更新排名/K线列, 不用 REPLACE —— REPLACE 会整行覆盖,
            # 把 upsert_combined_spot 先填好的 spot 列抹成 NULL
            cur = conn.execute("""
            INSERT INTO stock_daily_combined
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
                AND h.adjust_type = 'qfq'
            LEFT JOIN stock_basic l ON l.symbol = r.symbol
            WHERE true
            ON CONFLICT(trade_date, symbol) DO UPDATE SET
            name=excluded.name,
            open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
            latest_price=excluded.latest_price, change_pct=excluded.change_pct,
            change_amount=excluded.change_amount, volume=excluded.volume,
            amount=excluded.amount, amplitude=excluded.amplitude,
            turnover_rate=excluded.turnover_rate,
            popularity_rank=excluded.popularity_rank, rank_time=excluded.rank_time,
            rank_source=excluded.rank_source
            """)
            n = cur.rowcount
            conn.commit()
        finally:
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
        conn = _get_conn(get_stock_db())
        try:
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
        finally:
            conn.close()
    return n


def upsert_combined_rank(trade_date: str) -> int:
    """某交易日的排名 -> stock_daily_combined 排名列 (不清除已有 spot 列)"""
    with _lock:
        conn = _get_conn(get_stock_db())
        try:
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
        finally:
            conn.close()
    return n


def record_rebuild_progress(step: str, symbol: str, rows: int) -> None:
    """记录重建断点续传进度"""
    with _lock:
        conn = _get_conn(get_stock_db())
        try:
            conn.execute(
            "INSERT OR REPLACE INTO rebuild_progress(step, symbol, rows, updated_at) "
            "VALUES(?,?,?,?)",
            (step, symbol, rows, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
        finally:
            conn.close()


# 各步骤进度与实际数据表的对应关系(用于交叉校验)
_STEP_VERIFY_TABLE = {
    "kline": "stock_kline",
    "guba": "stock_popularity_rank",
}


def get_rebuild_done(step: str) -> set[str]:
    """某步骤已完成的 symbol 集合(断点续传)

    不能盲信 rebuild_progress: 若真实数据表被清空/重建而进度表残留
    (如外部删表、旧库迁移), 这些 symbol 会被永久跳过不再下载。
    故对有数据表映射的步骤做交叉校验, 并清除失效的进度记录。
    """
    rows = query_stock_db("SELECT symbol FROM rebuild_progress WHERE step=?", (step,))
    done = {r["symbol"] for r in rows}
    verify_table = _STEP_VERIFY_TABLE.get(step)
    if verify_table and done:
        present = {
            r["symbol"]
            for r in query_stock_db(f"SELECT DISTINCT symbol FROM {verify_table}")
        }
        stale = done - present
        if stale:
            with _lock:
                conn = _get_conn(get_stock_db())
                try:
                    conn.execute(
                    f"DELETE FROM rebuild_progress WHERE step=? "
                    f"AND symbol NOT IN (SELECT DISTINCT symbol FROM {verify_table})",
                    (step,),
                    )
                    conn.commit()
                finally:
                    conn.close()
            done = done & present
    return done


def set_meta_stock(key: str, value: str):
    with _lock:
        conn = _get_conn(get_stock_db())
        try:
            conn.execute(
            "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
            (key, value, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()


# ════════════════════════════════════════
# Sector DB 写入
# ════════════════════════════════════════

def save_sector_basic(rows: list[dict]):
    return _save_rows(get_sector_db, "sector_basic", ["sector_code", "sector_name", "sector_type", "latest_index", "change_pct",
        "main_net_inflow", "main_net_pct",
        "super_large_net", "super_large_pct", "large_net", "large_pct",
        "medium_net", "medium_pct", "small_net", "small_pct",
        "lead_stock_name", "lead_stock_code", "updated_date"], rows)


def save_sector_kline(rows: list[dict]):
    now = datetime.now().isoformat()
    payload = [{**r, "source": r.get("source") or "eastmoney",
                "fetched_at": r.get("fetched_at") or now} for r in rows]
    return _save_rows(get_sector_db, "sector_kline", ["sector_code", "trade_date", "open", "close", "high", "low",
        "volume", "turnover", "amplitude", "change_pct", "change_amount", "turnover_rate",
        "source", "fetched_at"], payload)


def save_sector_member(rows: list[dict]):
    return _save_rows(get_sector_db, "sector_member", ["sector_code", "stock_code", "stock_name",
        "latest_price", "change_pct", "change_amount",
        "volume", "turnover", "amplitude", "turnover_rate", "volume_ratio",
        "high", "low", "open_today", "close_yesterday", "pb", "pe_dynamic", "updated_date"], rows)


def save_sector_indicators(rows: list[dict]):
    return _save_rows(get_sector_db, "sector_indicators", ["sector_code", "trade_date",
        "MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
        "RSI6", "RSI14", "RSI24",
        "DIF", "DEA", "MACD",
        "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
        "KDJ_K", "KDJ_D", "KDJ_J",
        "VOL_MA5", "VOL_MA10",
        "ATR14"], rows)


def set_meta_sector(key: str, value: str):
    with _lock:
        conn = _get_conn(get_sector_db())
        try:
            conn.execute(
            "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
            (key, value, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()


# ════════════════════════════════════════
# 查询接口
# ════════════════════════════════════════

def query_stock_db(sql: str, params: tuple = ()) -> list[dict]:
    conn = _get_conn(get_stock_db())
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_sector_db(sql: str, params: tuple = ()) -> list[dict]:
    conn = _get_conn(get_sector_db())
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_meta_stock(key: str) -> str | None:
    rows = query_stock_db("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


def get_meta_sector(key: str) -> str | None:
    rows = query_sector_db("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


def get_db_paths() -> dict:
    return {
        "stock_db": _resolve_path("STOCK_DB"),
        "sector_db": _resolve_path("SECTOR_DB"),
        "stock_dir": _resolve_path("STOCK_DIR"),
        "sector_dir": _resolve_path("SECTOR_DIR"),
    }
