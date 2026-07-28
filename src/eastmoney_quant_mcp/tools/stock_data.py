"""
股票数据工具: 列表、K线、实时行情、技术指标

网络请求为同步实现(akshare/curl_cffi), 对外 async 接口统一用 asyncio.to_thread
包装, 使 asyncio.gather 能真正并发(sync.py 的批量下载依赖这一点)。
"""

import asyncio
import math

import pandas as pd
import akshare as ak

from ..data.network import normalize_symbol, to_prefixed_symbol
from ..data.indicators import compute_all_indicators


# ── 股票列表 ──


async def get_stock_list() -> list[dict]:
    """获取 A 股股票基本信息列表"""
    return await asyncio.to_thread(_stock_list_sync)


def _stock_list_sync() -> list[dict]:
    """股票列表同步实现(供 to_thread 调用)"""
    try:
        df = ak.stock_zh_a_spot_em()
        result = []
        for _, row in df.iterrows():
            symbol = normalize_symbol(str(row["代码"]))
            result.append({
                "symbol": symbol,
                "name": str(row["名称"]),
                "raw_symbol": str(row["代码"]),
            })
        return result
    except Exception:
        df = ak.stock_zh_a_spot()
        result = []
        for _, row in df.iterrows():
            symbol = normalize_symbol(str(row["代码"]))
            result.append({
                "symbol": symbol,
                "name": str(row["名称"]),
                "raw_symbol": str(row["代码"]),
            })
        return result


# ── K 线历史 ──


async def get_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
) -> list[dict]:
    """获取单只股票历史 K 线数据"""
    return await asyncio.to_thread(_stock_history_sync, symbol, start_date, end_date, adjust)


def _stock_history_sync(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
) -> list[dict]:
    """个股 K 线同步实现(供 to_thread 调用)"""
    symbol = normalize_symbol(symbol)
    prefixed = to_prefixed_symbol(symbol)
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")

    df = None

    try:
        df = ak.stock_zh_a_daily(
            symbol=prefixed, start_date=start, end_date=end, adjust=adjust
        )
    except Exception:
        pass

    if df is None or df.empty:
        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=prefixed, start_date=start, end_date=end, adjust=adjust, timeout=15
            )
        except Exception:
            pass

    if df is None or df.empty:
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily", start_date=start, end_date=end,
                adjust=adjust, timeout=15
            )
        except Exception:
            return []

    if df is None or df.empty:
        return []

    rename = {
        "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
        "收盘": "close", "成交量": "volume", "成交额": "amount",
        "振幅": "amplitude", "涨跌幅": "change_pct", "涨跌额": "change_amount",
        "换手率": "turnover_rate",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["symbol"] = symbol
    df = df.sort_values("date", ascending=False)

    cols = ["date", "symbol", "open", "high", "low", "close", "volume", "amount",
            "amplitude", "change_pct", "change_amount", "turnover_rate"]
    result_cols = [c for c in cols if c in df.columns]
    return df[result_cols].to_dict(orient="records")


# ── 实时行情(东财 spot, 直连API绕过akshare的requests) ──

SPOT_HOSTS = [
    "https://push2.eastmoney.com/webguest/api/qt/clist/get",
    "https://82.push2.eastmoney.com/webguest/api/qt/clist/get",
    "https://73.push2.eastmoney.com/webguest/api/qt/clist/get",
]
SPOT_FIELDS = (
    "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,"
    "f20,f21,f23,f24,f25,f62,f115,f128,f140,f141,f136,f152"
)
SPOT_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

FIELD_MAP = {
    "f2":  "latest_price",   "f3":  "change_pct",
    "f4":  "change_amount",  "f5":  "volume",
    "f6":  "amount",         "f7":  "amplitude",
    "f8":  "turnover_rate",  "f9":  "pe_dynamic",
    "f10": "volume_ratio",   "f12": "raw_code",
    "f14": "name",           "f15": "high",
    "f16": "low",            "f17": "open",
    "f18": "pre_close",      "f20": "total_market_cap",
    "f21": "float_market_cap","f23": "pb",
    "f24": "sixty_day_change","f25": "ytd_change",
    "f62": "main_net_inflow","f115":"pe_ttm",
    "f128":"sector_name",    "f140":"speed",
    "f141":"five_min_change","f136":"volume_ratio_5d",
    "f152":"amplitude_5d",
}


_SPOT_PAGE_SIZE = 100  # push2 clist 接口单页上限, pz>100 会被截断为 100
_SPOT_PAGE_CONCURRENCY = 16


def _spot_page_sync(host_url: str, page: int) -> dict | None:
    """全市场行情单页请求(同步, 供 to_thread 调用)"""
    from ..data.network import http_get

    params = {
        "fid": "f3", "po": "1", "pz": str(_SPOT_PAGE_SIZE), "pn": str(page),
        "np": "1", "fltt": "2", "invt": "2",
        "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
        "fs": SPOT_FS, "fields": SPOT_FIELDS,
    }
    return http_get(host_url, params=params, retries=2, timeout=30)


async def _spot_all_rows(host_url: str) -> list[dict] | None:
    """在指定 host 上拉取全部行情: 第1页拿 total, 剩余页并发"""
    first = await asyncio.to_thread(_spot_page_sync, host_url, 1)
    if not first:
        return None
    data = first.get("data")
    if not data or not data.get("diff"):
        return None

    rows = list(data["diff"])
    total = data.get("total", 0) or len(rows)
    pages = math.ceil(total / _SPOT_PAGE_SIZE)
    if pages <= 1:
        return rows

    sem = asyncio.Semaphore(_SPOT_PAGE_CONCURRENCY)

    async def _page(pn: int) -> list:
        async with sem:
            r = await asyncio.to_thread(_spot_page_sync, host_url, pn)
            d = (r or {}).get("data") or {}
            return list(d.get("diff") or [])

    chunks = await asyncio.gather(*(_page(p) for p in range(2, pages + 1)))
    for chunk in chunks:
        rows.extend(chunk)
    return rows


async def get_latest_indicators() -> list[dict]:
    """获取全市场最新行情(直连东财API, 分页并发, 多host重试)"""
    all_rows = None
    for host_url in SPOT_HOSTS:
        all_rows = await _spot_all_rows(host_url)
        if all_rows:
            break

    if not all_rows:
        # fallback: 旧版 akshare API (字段少)
        try:
            df = await asyncio.to_thread(ak.stock_zh_a_spot)
        except Exception:
            return []
        result = []
        for _, row in df.iterrows():
            symbol = normalize_symbol(str(row.get("代码", "")))
            result.append({
                "symbol": symbol, "name": str(row.get("名称", "")),
                "latest_price": _safe_float(row.get("最新价")),
                "change_pct": _safe_float(row.get("涨跌幅")),
                "change_amount": _safe_float(row.get("涨跌额")),
                "volume": _safe_float(row.get("成交量")),
                "amount": _safe_float(row.get("成交额")),
                "high": _safe_float(row.get("最高")),
                "low": _safe_float(row.get("最低")),
                "open": _safe_float(row.get("今开")),
                "pre_close": _safe_float(row.get("昨收")),
            })
        return result

    result = []
    for row in all_rows:
        item = {}
        for fkey, ename in FIELD_MAP.items():
            val = row.get(fkey)
            if val is not None and val not in ("-", ""):
                try:
                    item[ename] = float(val)
                except (ValueError, TypeError):
                    item[ename] = str(val)
            else:
                item[ename] = None
        symbol = normalize_symbol(str(row.get("f12", "")))
        item["symbol"] = symbol
        result.append(item)
    return result


def _safe_float(val):
    if val is None or val in ("-", ""):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── 技术指标 ──


async def get_stock_indicators(symbol: str, days: int = 120) -> list[dict]:
    """获取股票 K 线 + 全部技术指标"""
    from datetime import timedelta

    end = pd.Timestamp.now()
    start = end - timedelta(days=days + 30)
    kline = await get_stock_history(
        symbol,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )

    if not kline:
        return []

    df = pd.DataFrame(kline)
    df = df.sort_values("date", ascending=True)

    if "close" not in df.columns or df.empty:
        return []

    try:
        indicators_df = compute_all_indicators(df)
    except Exception:
        return kline[-days:]

    result_df = indicators_df.tail(days)
    return result_df.where(result_df.notna(), None).to_dict(orient="records")


# ── 搜索 ──


async def search_stock(keyword: str) -> list[dict]:
    """模糊搜索股票(代码或名称)"""
    stocks = await get_stock_list()
    keyword_lower = keyword.strip().lower()
    results = []
    for s in stocks:
        if keyword_lower in s["symbol"] or keyword_lower in s["name"].lower():
            results.append(s)
        if len(results) >= 20:
            break
    return results


# ── 多周期 K 线(分钟/日/周/月, 纯网络) ──

_KLT_CHOICES = {"1", "5", "15", "30", "60", "101", "102", "103"}
_FQT_MAP = {"qfq": "1", "hfq": "2", "": "0"}


def _normalize_klt(period) -> str:
    """周期归一化为东财 klt 字符串: 1/5/15/30/60(分钟) 101(日) 102(周) 103(月)"""
    p = str(period).strip()
    if p not in _KLT_CHOICES:
        raise ValueError(f"不支持的周期: {period}, 可选: {sorted(_KLT_CHOICES, key=int)}")
    return p


def _stock_kline_period_sync(symbol: str, period: str, limit: int, adjust: str) -> list[dict]:
    """多周期 K 线同步实现(供 to_thread 调用)"""
    from ..data.network import try_kline_hosts

    symbol = normalize_symbol(symbol)
    klt = _normalize_klt(period)
    # secid 规则与 akshare 一致: 沪市 1.xxxxxx, 深/北市 0.xxxxxx
    secid = ("1." if symbol.startswith("6") else "0.") + symbol
    params = {
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": klt, "fqt": _FQT_MAP.get(adjust, "1"),
        "end": "20500101", "lmt": str(limit),
    }

    result = try_kline_hosts(params, timeout=15)
    if not result:
        return []

    box = result.get("data") or {}
    klines_list = box.get("klines")
    if not klines_list:
        return []

    # 分钟级带时分秒, 用 datetime 键; 日/周/月只有日期, 保持 date 键
    time_key = "date" if int(klt) >= 101 else "datetime"
    cols = ["open", "close", "high", "low", "volume", "amount",
            "amplitude", "change_pct", "change_amount", "turnover_rate"]

    items = []
    for row_str in klines_list:
        parts = row_str.split(",")
        if len(parts) < len(cols) + 1:
            continue
        item = {"symbol": symbol, time_key: parts[0].strip()}
        for i, c in enumerate(cols, start=1):
            v = parts[i].strip()
            try:
                item[c] = float(v) if v not in ("-", "") else None
            except ValueError:
                item[c] = v
        items.append(item)

    return items


async def get_stock_kline_period(
    symbol: str,
    period: str = "60",
    limit: int = 240,
    adjust: str = "qfq",
) -> list[dict]:
    """
    个股多周期 K 线(纯网络实时, 不写本地库)。

    period: "1"/"5"/"15"/"30"/"60"(分钟), "101"(日线), "102"(周线), "103"(月线)
    limit:  返回条数, 默认 240
    adjust: "qfq"前复权 / "hfq"后复权 / ""不复权
    """
    return await asyncio.to_thread(_stock_kline_period_sync, symbol, period, limit, adjust)
