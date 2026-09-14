"""
data/storage/snapshot.py — 历史快照表写入 (移植自"股票信息"项目)

daily_stock_info   全市场 spot 快照
stock_popularity_rank  人气排名 (xuangu 快照覆盖 / guba 年文件不覆盖)
stock_daily_combined   spot + 排名 + K线合并视图表
"""

from .paths import get_stock_db
from .schema import _write_conn

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
    with _write_conn(get_stock_db()) as conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO daily_stock_info ({col_list}) VALUES ({placeholders})",
            payload,
        )
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
    with _write_conn(get_stock_db()) as conn:
        conn.executemany(sql, payload)
    return len(payload)


def build_combined_from_history() -> int:
    """K线 INNER JOIN 排名 -> stock_daily_combined (只生成有K线的交易日行)"""
    with _write_conn(get_stock_db()) as conn:
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
    with _write_conn(get_stock_db()) as conn:
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
    return n


def upsert_combined_rank(trade_date: str) -> int:
    """某交易日的排名 -> stock_daily_combined 排名列 (不清除已有 spot 列)"""
    with _write_conn(get_stock_db()) as conn:
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
    return n
