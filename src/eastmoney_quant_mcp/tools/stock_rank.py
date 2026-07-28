"""
人气榜单工具: 东方财富人气排名(早盘/尾盘)

网络请求为同步实现(curl_cffi), 对外 async 接口用 asyncio.to_thread 包装,
使 asyncio.gather 能真正并发。
"""

import asyncio
from urllib.parse import urlencode

from ..data.network import http_get, normalize_symbol

BASE_URL = "https://data.eastmoney.com/dataapi/xuangu/list"

FIELDS = [
    "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR",
    "NEW_PRICE", "CHANGE_RATE", "VOLUME_RATIO",
    "HIGH_PRICE", "LOW_PRICE", "PRE_CLOSE_PRICE",
    "VOLUME", "DEAL_AMOUNT", "TURNOVERRATE", "POPULARITY_RANK",
]


_PAGE_SIZE = 500


def _build_url(page: int, page_size: int = _PAGE_SIZE) -> str:
    params = {
        "st": "CHANGE_RATE",
        "sr": "-1",
        "ps": str(page_size),
        "p": str(page),
        "sty": ",".join(FIELDS),
        "filter": "(POPULARITY_RANK>=0.00)(POPULARITY_RANK<=6000)",
        "source": "SELECT_SECURITIES",
        "client": "WEB",
        "hyversion": "v2",
    }
    return f"{BASE_URL}?{urlencode(params)}"


def _rank_page_sync(page: int) -> dict | None:
    """人气排名单页请求(同步, 供 to_thread 调用)"""
    return http_get(_build_url(page), retries=3, timeout=20)


def _extract_rank(payload: dict | None) -> tuple[list, int]:
    """提取排名记录列表和总条数(count 缺失时为 0)"""
    if not payload:
        return [], 0
    result = payload.get("result") or {}
    data = result.get("data") or payload.get("data")
    if not isinstance(data, list) or not data:
        return [], 0
    return data, result.get("count", 0) or 0


async def _fetch_all_rankings() -> list[dict]:
    """分页拉取全部人气排名: 第1页拿 count, 剩余页并发; count 缺失时回退串行"""
    rows, count = _extract_rank(await asyncio.to_thread(_rank_page_sync, 1))
    if not rows:
        return []

    if count > len(rows):
        import math
        pages = math.ceil(count / _PAGE_SIZE)
        sem = asyncio.Semaphore(16)

        async def _page(p: int) -> list:
            async with sem:
                chunk, _ = _extract_rank(await asyncio.to_thread(_rank_page_sync, p))
                return chunk

        for chunk in await asyncio.gather(*(_page(p) for p in range(2, pages + 1))):
            rows.extend(chunk)
        return rows

    # count 缺失: 串行翻页直至短页
    page = 2
    while len(rows) % _PAGE_SIZE == 0:
        chunk, _ = _extract_rank(await asyncio.to_thread(_rank_page_sync, page))
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < _PAGE_SIZE:
            break
        page += 1

    return rows


def _format_rank_item(item: dict) -> dict:
    return {
        "symbol": normalize_symbol(str(item.get("SECURITY_CODE", ""))),
        "name": item.get("SECURITY_NAME_ABBR", ""),
        "secu_code": item.get("SECUCODE", ""),
        "latest_price": _safe_float(item.get("NEW_PRICE")),
        "change_pct": _safe_float(item.get("CHANGE_RATE")),
        "volume_ratio": _safe_float(item.get("VOLUME_RATIO")),
        "high": _safe_float(item.get("HIGH_PRICE")),
        "low": _safe_float(item.get("LOW_PRICE")),
        "pre_close": _safe_float(item.get("PRE_CLOSE_PRICE")),
        "volume": _safe_float(item.get("VOLUME")),
        "amount": _safe_float(item.get("DEAL_AMOUNT")),
        "turnover_rate": _safe_float(item.get("TURNOVERRATE")),
        "popularity_rank": _safe_float(item.get("POPULARITY_RANK")),
    }


def _safe_float(val) -> float | None:
    if val is None or val == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def get_popularity_rankings(top_n: int = 50) -> list[dict]:
    """获取人气排名榜单(按涨跌幅排序)"""
    rows = await _fetch_all_rankings()
    if not rows:
        return []

    items = [_format_rank_item(r) for r in rows]
    items.sort(key=lambda x: x.get("popularity_rank") or 9999)
    return items[:top_n]


async def get_top_gainers_rank(top_n: int = 50) -> list[dict]:
    """获取涨幅最高人气排行"""
    rows = await _fetch_all_rankings()
    if not rows:
        return []

    items = [_format_rank_item(r) for r in rows]
    items.sort(key=lambda x: x.get("change_pct") or -999, reverse=True)
    return items[:top_n]


async def get_top_volume_rank(top_n: int = 50) -> list[dict]:
    """获取成交量最大人气排行"""
    rows = await _fetch_all_rankings()
    if not rows:
        return []

    items = [_format_rank_item(r) for r in rows]
    items.sort(key=lambda x: x.get("volume") or 0, reverse=True)
    return items[:top_n]


async def get_top_turnover_rank(top_n: int = 50) -> list[dict]:
    """获取换手率最高人气排行"""
    rows = await _fetch_all_rankings()
    if not rows:
        return []

    items = [_format_rank_item(r) for r in rows]
    items.sort(key=lambda x: x.get("turnover_rate") or 0, reverse=True)
    return items[:top_n]
