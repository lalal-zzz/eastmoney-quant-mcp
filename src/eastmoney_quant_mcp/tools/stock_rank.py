"""
人气榜单工具: 东方财富人气排名(早盘/尾盘)
"""

from urllib.parse import urlencode

from ..data.network import http_get, normalize_symbol

BASE_URL = "https://data.eastmoney.com/dataapi/xuangu/list"

FIELDS = [
    "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR",
    "NEW_PRICE", "CHANGE_RATE", "VOLUME_RATIO",
    "HIGH_PRICE", "LOW_PRICE", "PRE_CLOSE_PRICE",
    "VOLUME", "DEAL_AMOUNT", "TURNOVERRATE", "POPULARITY_RANK",
]


def _build_url(page: int, page_size: int = 100) -> str:
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


async def _fetch_all_rankings() -> list[dict]:
    """分页拉取全部人气排名数据"""
    all_rows = []
    page = 1
    while True:
        url = _build_url(page, 100)
        payload = http_get(url, retries=3, timeout=20)
        if not payload:
            break

        result = payload.get("result") or {}
        data = result.get("data") or payload.get("data")
        if not isinstance(data, list) or not data:
            break

        all_rows.extend(data)
        if len(data) < 100:
            break
        page += 1

    return all_rows


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
