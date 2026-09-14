"""
patterns/universe.py — 标的宇宙定义与数据加载 (股票/板块双宇宙)

  "stocks"  → stock_kline + stock_indicators (symbol, date)      [本地库]
  "sectors" → sector_kline + sector_indicators (sector_code, trade_date) [本地库]
字段映射: 板块的 trade_date→date, turnover_rate→turnover; KDJ_K/D/J→K/D/J。
历史不足 MIN_BARS=260 的标的自动跳过 (历史短的板块自然过滤)。

注意: 内部统一经 `_current_universe_defs()` 取宇宙定义 —— 它穿透包门面查找,
使测试可以 monkeypatch `patterns._universe_defs` 重定向库路径。
"""

import sqlite3
import sys

import numpy as np
import pandas as pd

from .constants import BACKTEST_START

_KLINE_COLS = ("open", "high", "low", "close", "volume")
_IND_COLS = ("MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
             "RSI6", "RSI14", "DIF", "DEA", "VOL_MA5", "VOL_MA10",
             "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER")


def _universe_defs() -> dict:
    """Lazy universe definitions (paths computed on first access)."""
    from ...data.storage import get_sector_db, get_stock_db

    return {
        # universe: (库路径, K线表, 指标表, 基础表, K线日期列, 标的ID列)
        "stocks": (get_stock_db(), "stock_kline", "stock_indicators", "stock_basic",
                   "date", "symbol"),
        "sectors": (get_sector_db(), "sector_kline", "sector_indicators", "sector_basic",
                    "trade_date", "sector_code"),
    }


def _current_universe_defs() -> dict:
    """经包门面解析 _universe_defs, 兼容测试对 patterns._universe_defs 的重定向。"""
    pkg = sys.modules[__package__]
    return pkg._universe_defs()


def _connect(universe: str) -> sqlite3.Connection:
    defs = _current_universe_defs()
    if universe not in defs:
        raise ValueError(f"unknown universe: {universe} (stocks|sectors)")
    return sqlite3.connect(defs[universe][0], timeout=60)


def load_pattern_df(universe: str, symbol: str, start: str = BACKTEST_START,
                    end: str | None = None, tail: int | None = None) -> pd.DataFrame:
    """读取单标的K线 + 指标缓存, 补算 MA120/MA250, 返回按日期升序的 DataFrame。

    股票/板块字段映射统一输出: date/open/high/low/close/volume/change_rate/turnover
    + 指标列 (K/D/J 由 KDJ_K/KDJ_D/KDJ_J 映射)。
    tail: 只取 start~end 范围内最后 N 行 (scan 加速用)。
    """
    db_path, kt, it, _bt, kdate_col, id_col = _current_universe_defs()[universe]
    id_field = f"h.{id_col}"
    stock_join = " AND c.adjust_type = h.adjust_type" if universe == "stocks" else ""
    stock_where = " AND h.adjust_type = 'qfq'" if universe == "stocks" else ""

    select_common = f"""
        SELECT h.{kdate_col} AS date, h.open, h.high, h.low, h.close,
               h.volume,
               h.change_pct AS change_rate, h.turnover_rate AS turnover,
               c.MA5, c.MA10, c.MA20, c.MA30, c.MA60, c.MA100, c.MA200,
               c.RSI14, c.DIF, c.DEA, c.VOL_MA5, c.VOL_MA10,
               c.RSI6, c.KDJ_K AS K, c.KDJ_D AS D, c.KDJ_J AS J,
               c.BOLL_UPPER, c.BOLL_MIDDLE, c.BOLL_LOWER
        FROM {kt} h
        LEFT JOIN {it} c
            ON c.{kdate_col} = h.{kdate_col} AND c.{id_col} = {id_field}{stock_join}
    """
    where = f"WHERE h.{id_col} = ? AND h.{kdate_col} >= ?{stock_where}"
    params: list = [symbol, start]
    if end:
        where += f" AND h.{kdate_col} <= ?"
        params.append(end)
    if tail:
        sql = (f"SELECT * FROM ({select_common} {where} "
               f"ORDER BY h.{kdate_col} DESC LIMIT {int(tail)}) ORDER BY date")
    else:
        sql = f"{select_common} {where} ORDER BY h.{kdate_col}"

    with sqlite3.connect(db_path, timeout=60) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return df

    num_cols = [c for c in df.columns if c != "date"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    _backfill_missing_columns(df)
    return df


def _backfill_missing_columns(df: pd.DataFrame) -> None:
    """补算指标缓存里没有的均线 + 防御性补算 (缓存整列缺失时)。"""
    close = df["close"]
    for w in (120, 250):
        df[f"MA{w}"] = close.rolling(w, min_periods=w).mean()
    if df["VOL_MA5"].isna().all():
        df["VOL_MA5"] = df["volume"].rolling(5, min_periods=5).mean()
    if df["MA5"].isna().all():
        df["MA5"] = close.rolling(5, min_periods=5).mean()
    if df["RSI14"].isna().all():
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        rs = (gain.ewm(alpha=1 / 14, adjust=False).mean()
              / loss.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan))
        df["RSI14"] = 100 - 100 / (1 + rs)


def get_universe_list(universe: str, exclude_st: bool = True,
                      sector_type: str | None = None) -> pd.DataFrame:
    """标的清单 (symbol, name)。股票默认剔除 ST; 板块可按 sector_type 过滤。"""
    db_path, _kt, _it, bt, _kdate_col, id_col = _current_universe_defs()[universe]
    if universe == "stocks":
        sql = f"SELECT {id_col} AS symbol, name FROM {bt}"
        if exclude_st:
            sql += " WHERE name NOT LIKE '%ST%'"
        sql += " ORDER BY symbol"
    else:
        sql = f"SELECT {id_col} AS symbol, sector_name AS name FROM {bt}"
        if sector_type:
            sql += f" WHERE sector_type = ?"
        sql += " ORDER BY sector_code"
    with sqlite3.connect(db_path, timeout=60) as conn:
        params = (sector_type,) if (universe == "sectors" and sector_type) else ()
        return pd.read_sql_query(sql, conn, params=params)


def get_latest_trade_date(universe: str) -> str | None:
    db_path, kt, _it, _bt, kdate_col, _id_col = _current_universe_defs()[universe]
    with sqlite3.connect(db_path, timeout=60) as conn:
        suffix = " WHERE adjust_type='qfq'" if universe == "stocks" else ""
        row = conn.execute(f"SELECT MAX({kdate_col}) FROM {kt}{suffix}").fetchone()
    return row[0] if row else None


def resolve_universe_symbol(universe: str, query: str) -> tuple[str, str]:
    """按代码或名称解析标的 → (symbol, name)。未命中抛 ValueError。"""
    query = str(query).strip()
    db_path, _kt, _it, bt, _kdate_col, id_col = _current_universe_defs()[universe]
    name_col = "name" if universe == "stocks" else "sector_name"
    with sqlite3.connect(db_path, timeout=60) as conn:
        # 代码精确匹配优先 (兼容 'BK1090' / '1090' / 'sh600000' 等格式)
        candidates = [query]
        digits = "".join(ch for ch in query if ch.isdigit())
        if digits and digits != query:
            candidates.append(digits)
        for cand in candidates:
            row = conn.execute(
                f"SELECT {id_col}, {name_col} FROM {bt} WHERE {id_col} = ?", (cand,)).fetchone()
            if row:
                return row[0], row[1] or ""
        # 板块裸代码补 BK 前缀 (1090 → BK1090)
        if universe == "sectors" and digits and not query.upper().startswith("BK"):
            row = conn.execute(
                f"SELECT {id_col}, {name_col} FROM {bt} WHERE {id_col} = ?",
                (f"BK{digits}",)).fetchone()
            if row:
                return row[0], row[1] or ""
        # 名称模糊匹配
        rows = conn.execute(
            f"SELECT {id_col}, {name_col} FROM {bt} WHERE {name_col} LIKE ? "
            f"ORDER BY {id_col} LIMIT 1", (f"%{query}%",)).fetchall()
        if rows:
            return rows[0][0], rows[0][1] or ""
    raise ValueError(f"无法解析{('板块' if universe == 'sectors' else '股票')}: {query}")
