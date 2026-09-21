"""
新浪财经数据源

- 行业板块节点: vip.stock.finance.sina.com.cn/q/view/newSinaHy.php (GBK, ~49 个)
- 概念板块节点: vip.stock.finance.sina.com.cn/q/view/newFLJK.php?param=class (GBK, ~175 个)
- 板块成分股:   vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/
                Market_Center.getHQNodeData?node=<node> (JSON, 100 条/页)

新浪接口必须携带 Referer: https://finance.sina.com.cn。
单位约定: 成分股 volume 为股(÷100 转手), amount 为元; mktcap/nmc 为万元。
新浪无板块指数 K 线, 无当日四档资金流(历史资金流接口另行处理, 暂不接入)。
"""

import json
import re
import threading

from ..util import TtlCache
import time

from ..network import (
    http_get,
    http_get_text,
    mark_provider_fail,
    mark_provider_ok,
)

PROVIDER = "sina"

HY_URL = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
GN_URL = "https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php?param=class"
MEMBER_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)

_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

_PAGE_SIZE = 100
_NODE_INDEX_TTL = 24 * 3600



def _f(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── 板块节点(名称 → node 代码) ──


def fetch_node_maps() -> dict[str, dict[str, str]]:
    """返回 {"industry": {名: node}, "concept": {名: node}}"""
    maps: dict[str, dict[str, str]] = {"industry": {}, "concept": {}}
    for label, url in (("industry", HY_URL), ("concept", GN_URL)):
        text = http_get_text(url, retries=2, timeout=15, encoding="gbk",
                             extra_headers=_SINA_HEADERS)
        if text is None:
            mark_provider_fail(PROVIDER)
            continue
        mark_provider_ok(PROVIDER)
        m = re.search(r"=\s*(\{.*\})", text, re.S)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for node, val in data.items():
            # val 形如 "new_blhy,玻璃行业,19,..." — 取第 2 段为名称
            name = str(val).split(",")[1].strip() if "," in str(val) else ""
            if name:
                maps[label].setdefault(name, node)
    return maps


def _fetch_node_index() -> dict[str, dict[str, str]] | None:
    maps = fetch_node_maps()
    return maps if maps["industry"] or maps["concept"] else None


_node_index_cache = TtlCache(_NODE_INDEX_TTL)


def get_name_node_index(refresh: bool = False) -> dict[str, dict[str, str]]:
    """进程内缓存 24h 的 {板块类型: {名: node}}"""
    return _node_index_cache.get(_fetch_node_index, refresh=refresh) or fetch_node_maps()


# ── 板块成分股 ──


def fetch_sector_members(node: str, sector_code: str = "",
                         max_members: int = 1000) -> list[dict]:
    """
    按新浪 node 拉取板块成分股, 归一化为 sector_member 表字段。
    失败(网络)返回 []。
    """
    from ..network import provider_available

    if not provider_available(PROVIDER):
        return []

    items: list[dict] = []
    page = 1
    while len(items) < max_members:
        params = {
            "node": node, "num": str(_PAGE_SIZE), "page": str(page),
            "sort": "symbol", "asc": "1",
        }
        rows = http_get(MEMBER_URL, params=params, retries=2, timeout=15,
                        extra_headers=_SINA_HEADERS)
        if rows is None:
            mark_provider_fail(PROVIDER)
            return items if items else []
        mark_provider_ok(PROVIDER)
        if not isinstance(rows, list) or not rows:
            break
        for r in rows:
            item = _normalize_member(r, sector_code)
            if item:
                items.append(item)
        if len(rows) < _PAGE_SIZE:
            break
        page += 1
    return items


def _normalize_member(r: dict, sector_code: str) -> dict | None:
    code = str(r.get("code", "")).strip()
    if not code.isdigit() or len(code) != 6:
        return None
    settlement = _f(r.get("settlement"))
    high = _f(r.get("high"))
    low = _f(r.get("low"))
    volume = _f(r.get("volume"))
    amount = _f(r.get("amount"))
    item = {
        "sector_code": sector_code,
        "stock_code": code,
        "stock_name": str(r.get("name", "")).strip(),
        "latest_price": _f(r.get("trade")),
        "change_pct": _f(r.get("changepercent")),
        "change_amount": _f(r.get("pricechange")),
        "volume": volume / 100 if volume is not None else None,  # 股 → 手
        "turnover": amount,
        "turnover_rate": _f(r.get("turnoverratio")),
        "volume_ratio": None,  # 新浪无量比
        "high": high,
        "low": low,
        "open_today": _f(r.get("open")),
        "close_yesterday": settlement,
        "pb": _f(r.get("pb")),
        "pe_dynamic": _f(r.get("per")),
    }
    if None not in (high, low, settlement) and settlement:
        item["amplitude"] = round((high - low) / settlement * 100, 4)
    else:
        item["amplitude"] = None
    return item
