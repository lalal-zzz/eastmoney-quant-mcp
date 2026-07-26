"""
股票数据工具: 列表、K线、实时行情、技术指标
"""

import pandas as pd
import akshare as ak

from ..data.network import normalize_symbol, to_prefixed_symbol
from ..data.indicators import compute_all_indicators


# ── 股票列表 ──


async def get_stock_list() -> list[dict]:
    """获取 A 股股票基本信息列表"""
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


async def get_latest_indicators() -> list[dict]:
    """获取全市场最新行情(直连东财API, curl_cffi 多host重试)"""
    from ..data.network import http_get

    all_rows = None
    for host_url in SPOT_HOSTS:
        page = 1
        psz = 100
        temp_rows = []
        failed = False
        while True:
            params = {
                "fid": "f3", "po": "1", "pz": str(psz), "pn": str(page),
                "np": "1", "fltt": "2", "invt": "2",
                "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
                "fs": SPOT_FS, "fields": SPOT_FIELDS,
            }
            payload = http_get(host_url, params=params, retries=2, timeout=30)
            if not payload:
                failed = True
                break
            data = payload.get("data")
            if not data:
                failed = True
                break
            diff = data.get("diff")
            if not diff:
                failed = True
                break
            temp_rows.extend(diff)
            total = data.get("total", 0)
            if page * psz >= total:
                break
            page += 1
        if not failed and temp_rows:
            all_rows = temp_rows
            break

    if not all_rows:
        # fallback: 旧版 akshare API (字段少)
        import akshare as ak
        try:
            df = ak.stock_zh_a_spot()
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
    kline = await get_stock_history(
        symbol,
        start_date=pd.Timestamp.now().strftime("%Y%m%d"),
        end_date=pd.Timestamp.now().strftime("%Y%m%d"),
    )

    if not kline:
        # 尝试拉取更长历史
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
