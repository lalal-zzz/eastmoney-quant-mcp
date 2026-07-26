"""
板块数据工具: 行业/概念板块列表、行情、成分股、K 线
"""

import time

from ..data.network import http_get, normalize_sector_code

PUSH2_HOSTS = [
    "https://push2.eastmoney.com/webguest/api/qt/clist/get",
    "https://82.push2.eastmoney.com/webguest/api/qt/clist/get",
    "https://73.push2.eastmoney.com/webguest/api/qt/clist/get",
]

KLINE_HOSTS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://82.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://73.push2his.eastmoney.com/api/qt/stock/kline/get",
]

SECTOR_FS_MAP = {"concept": "m:90+t:3", "industry": "m:90+s:4"}
SECTOR_FIELDS = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205"

MEMBER_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f10,f15,f16,f17,f18,f23"

DIVIDE_100_MEMBER = {"f2", "f3", "f4", "f7", "f8", "f9", "f10", "f15", "f16", "f17", "f18", "f23"}


def _try_push2(params: dict, timeout: int = 15) -> dict | None:
    for host in PUSH2_HOSTS:
        r = http_get(host, params=params, retries=2, timeout=timeout)
        if r and "data" in r:
            return r
    return None


def _try_kline(params: dict, timeout: int = 15) -> dict | None:
    for host in KLINE_HOSTS:
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


# ── 板块列表 + 行情 ──


async def get_sector_list(sector_type: str = "concept") -> list[dict]:
    """获取概念/行业板块列表及其当日行情"""
    fs = SECTOR_FS_MAP.get(sector_type, SECTOR_FS_MAP["concept"])
    all_records = []
    page = 1
    psz = 100

    while True:
        params = {
            "fid": "f62", "po": "1", "pz": str(psz), "pn": str(page),
            "np": "1", "fltt": "2", "invt": "2",
            "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
            "fs": fs, "fields": SECTOR_FIELDS,
        }
        result = _try_push2(params)
        if not result:
            break

        data = result["data"]
        diff = data.get("diff")
        if not diff:
            break

        recs = list(diff) if isinstance(diff, list) else list(diff.values())
        all_records.extend(recs)

        if page == 1:
            total = data.get("total", 0)
        if page * psz >= (total if page == 1 else len(all_records)):
            break
        page += 1
        time.sleep(0.3)

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


async def get_sector_members(sector_code: str) -> list[dict]:
    """获取板块成分股列表"""
    code = normalize_sector_code(sector_code)
    all_records = []
    page = 1
    psz = 100
    total = 0

    while True:
        params = {
            "fid": "f3", "po": "1", "pz": str(psz), "pn": str(page),
            "np": "1", "fltt": "2", "invt": "2",
            "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
            "fs": f"b:{code}", "fields": MEMBER_FIELDS,
        }
        result = _try_push2(params)
        if not result:
            break

        data = result["data"]
        diff = data.get("diff")
        if not diff:
            break

        if page == 1:
            total = data.get("total", 0)

        for rec in diff:
            item = {"sector_code": code}
            item["stock_code"] = rec.get("f12", "")
            item["stock_name"] = rec.get("f14", "")

            for api_f, db_c in [
                ("f2", "latest_price"), ("f3", "change_pct"), ("f4", "change_amount"),
                ("f5", "volume"), ("f6", "turnover"), ("f7", "amplitude"),
                ("f8", "turnover_rate"), ("f10", "volume_ratio"),
                ("f15", "high"), ("f16", "low"), ("f17", "open_today"),
                ("f18", "close_yesterday"), ("f23", "pb"),
            ]:
                val = rec.get(api_f)
                if api_f in DIVIDE_100_MEMBER and val is not None:
                    item[db_c] = _safe_float(val)
                    if item[db_c] is not None:
                        item[db_c] = round(item[db_c] / 100.0, 4)
                else:
                    item[db_c] = _safe_float(val)

            pe_val = rec.get("f9")
            if pe_val is not None and pe_val not in ("-", ""):
                item["pe_dynamic"] = round(_safe_float(pe_val) or 0 / 100.0, 4) if pe_val else None
            else:
                item["pe_dynamic"] = None

            all_records.append(item)

        if page * psz >= total:
            break
        page += 1
        time.sleep(0.3)

    return all_records


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
    # 回退网络
    params = {
        "secid": f"90.{code}",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101", "fqt": "1", "end": "20500101", "lmt": str(limit),
    }

    result = _try_kline(params, timeout=15)
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
            item = {"sector_code": code, "sector_name": box.get("name", code)}
            for i, c in enumerate(cols):
                v = parts[i].strip()
                try:
                    item[c] = float(v) if v not in ("-", "") else None
                except ValueError:
                    item[c] = v
            items.append(item)

    return items
