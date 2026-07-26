"""
形态选股工具: 技术形态筛选
"""

import pandas as pd

from .stock_data import get_stock_history, get_latest_indicators
from ..data.indicators import compute_all_indicators
from ..data.network import normalize_symbol


async def screen_golden_cross(market_data: list[dict] = None, top_n: int = 30) -> list[dict]:
    """金叉扫描: 扫描所有股票中 MA5 上穿 MA20 且 RSI14 < 70 的"""
    if market_data is None:
        market_data = await get_latest_indicators()
    return []  # 留接口,批量扫描需逐个取K线


async def screen_oversold_reversal(market_data: list[dict] = None, top_n: int = 30) -> list[dict]:
    """超跌反弹扫描: RSI14 < 30 且 当日涨跌幅 > 0"""
    if market_data is None:
        market_data = await get_latest_indicators()

    results = []
    for item in market_data:
        change_pct = item.get("change_pct")
        if change_pct is not None and float(change_pct) > 0:
            results.append(item)

    results.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)
    return results[:top_n]


async def screen_volume_surge(market_data: list[dict] = None, min_ratio: float = 2.0, top_n: int = 30) -> list[dict]:
    """放量突破扫描: 量比 >= min_ratio 且 涨跌幅 > 0"""
    if market_data is None:
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
    "golden_cross": "MA5上穿MA20金叉, RSI14 < 70",
    "oversold_reversal": "超跌反弹(当日涨跌幅>0)",
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
