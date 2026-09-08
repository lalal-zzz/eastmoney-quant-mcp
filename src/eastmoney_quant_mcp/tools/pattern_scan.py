"""
形态选股工具: 技术形态筛选 (本地指标表驱动, 无网络依赖)
"""

from ..data.network import normalize_symbol
from ..data.storage import query_stock_db


async def screen_golden_cross(market_data: list[dict] = None, top_n: int = 30) -> list[dict]:
    """金叉扫描: MA5 上穿 MA20(前一日 MA5<=MA20, 当日 MA5>MA20) 且 RSI14 < 70。

    数据来自本地 stock_indicators 最近两个交易日的指标缓存, 需要
    init_full_data/update_daily_data 先行。
    """
    dates = [r["date"] for r in query_stock_db(
        "SELECT DISTINCT date FROM stock_indicators WHERE adjust_type='qfq' ORDER BY date DESC LIMIT 2")]
    if len(dates) < 2:
        return []

    rows = query_stock_db(
        "SELECT symbol, date, MA5, MA20, RSI14 FROM stock_indicators "
        "WHERE adjust_type='qfq' AND date IN (?, ?)",
        (dates[0], dates[1]),
    )
    by_symbol: dict[str, dict] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], {})[r["date"]] = r

    results = []
    for symbol, by_date in by_symbol.items():
        cur, prev = by_date.get(dates[0]), by_date.get(dates[1])
        if not cur or not prev:
            continue
        ma5, ma20 = cur.get("MA5"), cur.get("MA20")
        p_ma5, p_ma20 = prev.get("MA5"), prev.get("MA20")
        if None in (ma5, ma20, p_ma5, p_ma20):
            continue
        if ma5 > ma20 and p_ma5 <= p_ma20 and (cur.get("RSI14") or 70) < 70:
            results.append({"symbol": symbol, "date": cur["date"], "MA5": ma5, "MA20": ma20,
                            "RSI14": cur.get("RSI14")})
    return results[:top_n]


async def screen_oversold_reversal(market_data: list[dict] = None, top_n: int = 30) -> list[dict]:
    """超跌反弹扫描: RSI14 < 30 且 当日涨跌幅 > 0 (RSI 取本地指标缓存最新值)"""
    if market_data is None:
        from .stock_data import get_latest_indicators
        market_data = await get_latest_indicators()

    rsi_map: dict[str, float] = {}
    if market_data:
        latest = query_stock_db(
            "SELECT symbol, RSI14 FROM stock_indicators WHERE date = "
            "(SELECT MAX(date) FROM stock_indicators WHERE adjust_type='qfq') "
            "AND adjust_type='qfq' AND RSI14 IS NOT NULL")
        rsi_map = {r["symbol"]: r["RSI14"] for r in latest}

    results = []
    for item in market_data:
        change_pct = item.get("change_pct")
        rsi = rsi_map.get(normalize_symbol(item["symbol"])) if item.get("symbol") else None
        if change_pct is not None and float(change_pct) > 0 and rsi is not None and rsi < 30:
            results.append({**item, "RSI14": rsi})

    results.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)
    return results[:top_n]


async def screen_volume_surge(market_data: list[dict] = None, min_ratio: float = 2.0, top_n: int = 30) -> list[dict]:
    """放量突破扫描: 量比 >= min_ratio 且 涨跌幅 > 0"""
    if market_data is None:
        from .stock_data import get_latest_indicators
        market_data = await get_latest_indicators()

    results = []
    for item in market_data:
        vol_ratio = item.get("volume_ratio")
        change_pct = item.get("change_pct")
        if (
            vol_ratio is not None
            and float(vol_ratio) >= min_ratio
            and change_pct is not None
            and float(change_pct) > 0
        ):
            results.append(item)

    results.sort(key=lambda x: x.get("volume_ratio") or 0, reverse=True)
    return results[:top_n]


async def screen_strong_breakout(market_data: list[dict] = None, top_n: int = 30) -> list[dict]:
    """强势突破扫描: 涨跌幅 >= 5% 且 换手率 >= 5%"""
    if market_data is None:
        from .stock_data import get_latest_indicators
        market_data = await get_latest_indicators()

    results = []
    for item in market_data:
        change_pct = item.get("change_pct")
        turnover = item.get("turnover_rate")
        if (
            change_pct is not None
            and float(change_pct) >= 5.0
            and turnover is not None
            and float(turnover) >= 5.0
        ):
            results.append(item)

    results.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)
    return results[:top_n]


async def screen_low_pe_growth(market_data: list[dict] = None, max_pe: float = 20, top_n: int = 30) -> list[dict]:
    """低估值成长扫描: 市盈率 < max_pe 且 涨跌幅 > 0 且 量比 > 1"""
    if market_data is None:
        from .stock_data import get_latest_indicators
        market_data = await get_latest_indicators()

    results = []
    for item in market_data:
        pe = item.get("pe_dynamic")
        vol_ratio = item.get("volume_ratio")
        change_pct = item.get("change_pct")
        if (
            pe is not None
            and 0 < float(pe) < max_pe
            and vol_ratio is not None
            and float(vol_ratio) > 1
            and change_pct is not None
            and float(change_pct) > 0
        ):
            results.append(item)

    results.sort(key=lambda x: x.get("pe_dynamic") or 9999)
    return results[:top_n]


async def screen_ma_bullish(market_data: list[dict] = None, top_n: int = 30) -> list[dict]:
    """多头排列扫描: 涨跌幅 > 0, 量比 > 1, 60日涨跌幅 > 0"""
    if market_data is None:
        from .stock_data import get_latest_indicators
        market_data = await get_latest_indicators()

    results = []
    for item in market_data:
        change_pct = item.get("change_pct")
        vol_ratio = item.get("volume_ratio")
        sixty_day = item.get("sixty_day_change")
        if (
            change_pct is not None
            and float(change_pct) > 0
            and vol_ratio is not None
            and float(vol_ratio) > 1
            and sixty_day is not None
            and float(sixty_day) > 0
        ):
            results.append(item)

    results.sort(key=lambda x: x.get("sixty_day_change") or 0, reverse=True)
    return results[:top_n]


# ── 形态描述 ──

PATTERN_DESCRIPTIONS = {
    "golden_cross": "MA5上穿MA20金叉, RSI14 < 70 (本地指标缓存)",
    "oversold_reversal": "超跌反弹(RSI14<30 且当日涨跌幅>0)",
    "volume_surge": "放量突破(量比>=2且上涨)",
    "strong_breakout": "强势突破(涨跌幅>=5%且换手>=5%)",
    "low_pe_growth": "低估值成长(PE<20且量比>1且上涨)",
    "ma_bullish": "多头排列(涨跌幅>0且量比>1且60日涨跌幅>0)",
}

PATTERNS = {
    "golden_cross": screen_golden_cross,
    "oversold_reversal": screen_oversold_reversal,
    "volume_surge": screen_volume_surge,
    "strong_breakout": screen_strong_breakout,
    "low_pe_growth": screen_low_pe_growth,
    "ma_bullish": screen_ma_bullish,
}
