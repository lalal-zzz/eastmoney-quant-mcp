"""
板块数据工具: 行业/概念板块列表、行情、成分股、K 线

网络请求为同步实现(curl_cffi), 对外 async 接口统一用 asyncio.to_thread 包装,
使 asyncio.gather 能真正并发(sync.py 的批量下载依赖这一点)。

push2 clist 接口单页上限 100 条(pz>100 会被截断), 分页采用
"第1页拿 total → 剩余页并发拉取"策略。
"""

import asyncio
import math

from ..data.network import http_get, normalize_sector_code, rotated

PUSH2_HOSTS = [
    "https://push2.eastmoney.com/webguest/api/qt/clist/get",
    "https://82.push2.eastmoney.com/webguest/api/qt/clist/get",
    "https://73.push2.eastmoney.com/webguest/api/qt/clist/get",
]

SECTOR_FS_MAP = {"concept": "m:90+t:3", "industry": "m:90+s:4"}
SECTOR_FIELDS = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205"

MEMBER_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f23"


def _try_push2(params: dict, timeout: int = 15) -> dict | None:
    for host in rotated(PUSH2_HOSTS):
        r = http_get(host, params=params, retries=2, timeout=timeout)
        if r and "data" in r:
            return r
    return None


def _safe_float(val) -> float | None:
    if val is None or val == "-" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── clist 并发分页 ──

_PAGE_SIZE = 100  # push2 clist 接口单页上限, pz>100 会被截断为 100
_PAGE_CONCURRENCY = 8  # 成分股场景外层还有一层并发, 避免嵌套并发乘积过大


def _extract_diff(payload: dict | None) -> tuple[list, int]:
    """从 clist 响应提取记录列表和总条数"""
    if not payload or "data" not in payload:
        return [], 0
    data = payload["data"] or {}
    diff = data.get("diff") or []
    recs = list(diff) if isinstance(diff, list) else list(diff.values())
    return recs, data.get("total", 0) or len(recs)


async def _fetch_all_pages(base_params: dict) -> list[dict]:
    """先取第 1 页拿 total, 再并发拉取剩余页(单页请求各自含多 host 重试)"""
    params = {**base_params, "pz": str(_PAGE_SIZE)}
    first = await asyncio.to_thread(_try_push2, {**params, "pn": "1"})
    recs, total = _extract_diff(first)
    if not recs:
        return []

    pages = math.ceil(total / _PAGE_SIZE)
    if pages <= 1:
        return recs

    sem = asyncio.Semaphore(_PAGE_CONCURRENCY)

    async def _page(pn: int) -> list:
        async with sem:
            r = await asyncio.to_thread(_try_push2, {**params, "pn": str(pn)})
            page_recs, _ = _extract_diff(r)
            return page_recs

    chunks = await asyncio.gather(*(_page(p) for p in range(2, pages + 1)))
    for chunk in chunks:
        recs.extend(chunk)
    return recs


# ── 板块列表 + 行情 ──


async def get_sector_list(sector_type: str = "concept") -> list[dict]:
    """获取概念/行业板块列表及其当日行情"""
    fs = SECTOR_FS_MAP.get(sector_type, SECTOR_FS_MAP["concept"])
    all_records = await _fetch_all_pages({
        "fid": "f62", "po": "1",
        "np": "1", "fltt": "2", "invt": "2",
        "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
        "fs": fs, "fields": SECTOR_FIELDS,
    })

    items = []
    for r in all_records:
        items.append({
            "sector_code": r.get("f12", ""),
            "sector_name": r.get("f14", ""),
            "sector_type": sector_type,
            "latest_index": _safe_float(r.get("f2")),
            "change_pct": _safe_float(r.get("f3")),
            "main_net_inflow": _safe_float(r.get("f62")),
            "main_net_pct": _safe_float(r.get("f184")),
            "super_large_net": _safe_float(r.get("f66")),
            "super_large_pct": _safe_float(r.get("f69")),
            "large_net": _safe_float(r.get("f72")),
            "large_pct": _safe_float(r.get("f75")),
            "medium_net": _safe_float(r.get("f78")),
            "medium_pct": _safe_float(r.get("f81")),
            "small_net": _safe_float(r.get("f84")),
            "small_pct": _safe_float(r.get("f87")),
            "lead_stock_name": r.get("f204", ""),
            "lead_stock_code": r.get("f205", ""),
        })

    return items


async def get_sector_members(sector_code: str, sector_name: str = None) -> list[dict]:
    """获取板块成分股列表

    降级链: 新浪 getHQNodeData(按板块名映射 node) → 东财 clist →
    搜狐 HTML 名单+腾讯批量行情补充。主库键始终为东财 BK 代码。
    """
    from ..data.providers import boardmap, sina, sohu, tencent

    code = normalize_sector_code(sector_code)

    # 1. 新浪(字段全, 一次分页请求量小)
    node, name = boardmap.resolve_sina_node(code, sector_name)
    if node:
        try:
            items = sina.fetch_sector_members(node, sector_code=code)
            if items:
                return items
        except Exception:
            pass

    # 2. 东财 clist(原有实现, 含四档相关字段)
    try:
        items = await _sector_members_em(code)
        if items:
            return items
    except Exception:
        pass

    # 3. 搜狐 HTML 名单(仅代码+名称), 用腾讯批量行情补实时字段
    bk = boardmap.resolve_sohu_bk(code, sector_name)
    if bk:
        try:
            return sohu.fetch_sector_members(
                bk, sector_code=code, quote_fetcher=tencent.fetch_quote_batch,
            )
        except Exception:
            pass
    return []


async def _sector_members_em(sector_code: str) -> list[dict]:
    """东财 clist 成分股(原实现)"""
    code = normalize_sector_code(sector_code)
    all_records = await _fetch_all_pages({
        "fid": "f3", "po": "1",
        "np": "1", "fltt": "2", "invt": "2",
        "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
        "fs": f"b:{code}", "fields": MEMBER_FIELDS,
    })

    items = []
    for rec in all_records:
        item = {"sector_code": code}
        item["stock_code"] = rec.get("f12", "")
        item["stock_name"] = rec.get("f14", "")

        # fltt=2 时接口返回的已是真实量纲的浮点数, 无需除以 100
        for api_f, db_c in [
            ("f2", "latest_price"), ("f3", "change_pct"), ("f4", "change_amount"),
            ("f5", "volume"), ("f6", "turnover"), ("f7", "amplitude"),
            ("f8", "turnover_rate"), ("f10", "volume_ratio"),
            ("f15", "high"), ("f16", "low"), ("f17", "open_today"),
            ("f18", "close_yesterday"), ("f23", "pb"),
        ]:
            item[db_c] = _safe_float(rec.get(api_f))

        item["pe_dynamic"] = _safe_float(rec.get("f9"))
        items.append(item)

    return items


async def get_sector_kline(sector_code: str, limit: int = 120) -> list[dict]:
    """获取板块历史 K 线(本地优先, 无数据回退网络)"""
    code = normalize_sector_code(sector_code)
    # 尝试本地
    try:
        from ..data.search import get_sector_kline_local
        local = get_sector_kline_local(code, limit)
        if local:
            return local
    except Exception:
        pass
    return await get_sector_kline_net(code, limit)


async def get_sector_kline_net(sector_code: str, limit: int = 120, klt: int = 101,
                               sector_name: str = None) -> list[dict]:
    """获取板块历史 K 线(纯网络, 供数据同步使用, 避免同步时读到本地旧数据)

    klt: 1/5/15/30/60(分钟), 101(日), 102(周), 103(月)
    板块K线历史仅东财提供(腾讯只有当日1根且口径不同), 带熔断保护:
    push2his 被封时快速返回 [] 由本地库兜底。
    """
    return await asyncio.to_thread(
        _sector_kline_net_sync, sector_code, limit, klt, sector_name,
    )


def _sector_kline_net_sync(sector_code: str, limit: int = 120, klt: int = 101,
                           sector_name: str = None) -> list[dict]:
    """板块 K 线网络下载同步实现(供 to_thread 调用)

    实测结论(2026-08): 腾讯 ifzq 全部形态对板块代码只返回最新 1 根
    (count/日期区间均被忽略), 且其板块成分集合与东财不同导致聚合口径
    有 ±20% 级差异 — 板块K线历史只有东财一个可靠来源, 跨源混写会引入
    系统性断层。故本实现保持东财单源 + 熔断保护(fetch_em_kline):
    push2his 被封时快速失败, 由调用方(sqlite 本地数据)兜底。
    """
    from ..data.network import fetch_em_kline

    code = normalize_sector_code(sector_code)
    params = {
        "secid": f"90.{code}",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": str(klt), "fqt": "1", "end": "20500101", "lmt": str(limit),
    }

    result = fetch_em_kline(params, timeout=15)
    if not result:
        return []

    box = result.get("data") or {}
    klines_list = box.get("klines")
    if not klines_list:
        return []

    cols = ["trade_date", "open", "close", "high", "low", "volume", "turnover",
            "amplitude", "change_pct", "change_amount", "turnover_rate"]

    items = []
    for row_str in klines_list:
        parts = row_str.split(",")
        if len(parts) >= len(cols):
            item = {"sector_code": code, "sector_name": sector_name or box.get("name", code)}
            for i, c in enumerate(cols):
                v = parts[i].strip()
                try:
                    item[c] = float(v) if v not in ("-", "") else None
                except ValueError:
                    item[c] = v
            items.append(item)

    return items

