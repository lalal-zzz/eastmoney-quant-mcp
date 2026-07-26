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


# ── 实时行情(东财 spot) ──


async def get_latest_indicators() -> list[dict]:
    """获取全市场最新行情(L2 数据: 量比/换手/涨跌幅等)"""
    import akshare as ak

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception:
        df = ak.stock_zh_a_spot()

    if df is None or df.empty:
        return []

    result = []
    col_map = {
        "代码": "symbol", "名称": "name",
        "最新价": "latest_price", "涨跌幅": "change_pct",
        "涨跌额": "change_amount", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude",
        "最高": "high", "最低": "low",
        "今开": "open", "昨收": "pre_close",
        "量比": "volume_ratio", "换手率": "turnover_rate",
        "市盈率-动态": "pe_dynamic", "市净率": "pb",
        "总市值": "total_market_cap", "流通市值": "float_market_cap",
        "涨速": "speed", "60日涨跌幅": "sixty_day_change",
        "年初至今涨跌幅": "ytd_change",
    }

    for _, row in df.iterrows():
        item = {}
        for cn, en in col_map.items():
            if cn in df.columns:
                val = row[cn]
                try:
                    item[en] = float(val) if val not in (None, "-", "") else None
                except (ValueError, TypeError):
                    item[en] = str(val) if val not in (None, "-", "") else None
        if "symbol" in item or "代码" in str(df.columns):
            raw_code = row.get("代码", "")
            item["symbol"] = normalize_symbol(str(raw_code))
        result.append(item)

    return result


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
