"""
数据同步模块: 全量初始化 + 增量每日更新

协调网络下载与本地 SQLite 存储。
"""

import asyncio
import time
from datetime import date, datetime, timedelta

from .storage import (
    init_all as init_dbs,
    save_stock_basic,
    save_stock_kline,
    save_stock_indicators,
    save_stock_spot,
    save_stock_rank,
    save_sector_basic,
    save_sector_kline,
    save_sector_member,
    set_meta_stock,
    set_meta_sector,
    get_meta_stock,
    get_meta_sector,
    query_stock_db,
    query_sector_db,
    get_db_paths,
)

from ..tools.stock_data import get_stock_list, get_stock_history, get_latest_indicators
from ..tools.stock_rank import _fetch_all_rankings, _format_rank_item
from ..tools.sector_data import get_sector_list, get_sector_kline, get_sector_members
from .indicators import compute_all_indicators

import pandas as pd

_TODAY = date.today().isoformat()


# ════════════════════════════════════════
# 全量初始化
# ════════════════════════════════════════

async def init_all_data(include_sector_members: bool = True) -> dict:
    """一次性全量下载所有数据"""
    init_dbs()
    log = []

    step = 0
    total_steps = 7 if include_sector_members else 5

    async def _step(msg: str):
        nonlocal step
        step += 1
        log.append(f"[{step}/{total_steps}] {msg}")

    # 1. 股票基本信息
    await _step("下载股票列表...")
    stocks = await get_stock_list()
    save_stock_basic(stocks)
    set_meta_stock("stock_count", str(len(stocks)))
    log[-1] += f" 共 {len(stocks)} 只"

    # 2. 股票实时行情
    await _step("下载全市场实时行情...")
    spots = await get_latest_indicators()
    recent = []
    for s in spots:
        s["updated_date"] = _TODAY
        recent.append(s)
    save_stock_spot(recent)
    set_meta_stock("spot_updated", _TODAY)
    log[-1] += f" 共 {len(recent)} 只"

    # 3. 人气排名
    await _step("下载人气排名...")
    raw_rank = await _fetch_all_rankings()
    rank_rows = [_format_rank_item(r) for r in raw_rank]
    for r in rank_rows:
        r["rank_date"] = _TODAY
    save_stock_rank(rank_rows)
    set_meta_stock("rank_updated", _TODAY)
    log[-1] += f" 共 {len(rank_rows)} 条"

    # 4. 板块列表(概念+行业)
    await _step("下载概念板块...")
    concept_sectors = await get_sector_list("concept")
    await _step("下载行业板块...")
    industry_sectors = await get_sector_list("industry")
    all_sectors = concept_sectors + industry_sectors
    for s in all_sectors:
        s["updated_date"] = _TODAY
    save_sector_basic(all_sectors)
    set_meta_sector("sector_count", str(len(all_sectors)))
    set_meta_sector("sector_updated", _TODAY)
    log[-1] += f" 概念 {len(concept_sectors)} + 行业 {len(industry_sectors)}"

    # 5. 板块 K 线
    await _step(f"下载 {len(all_sectors)} 个板块 K 线...")
    kline_total = 0
    for i, sec in enumerate(all_sectors):
        code = sec.get("sector_code", "")
        if not code:
            continue
        try:
            kl = await get_sector_kline(code, limit=250)
            if kl:
                save_sector_kline(kl)
                kline_total += len(kl)
        except Exception:
            pass
        if (i + 1) % 50 == 0:
            await asyncio.sleep(0.5)
    set_meta_sector("kline_updated", _TODAY)
    log[-1] += f" 共 {kline_total} 条"

    # 6-7. 板块成分股(可选,耗时较长)
    if include_sector_members:
        await _step(f"下载 {len(all_sectors)} 个板块成分股...")
        member_total = 0
        for i, sec in enumerate(all_sectors):
            code = sec.get("sector_code", "")
            if not code:
                continue
            try:
                members = await get_sector_members(code)
                if members:
                    processed = []
                    for m in members:
                        m["updated_date"] = _TODAY
                        if "sector_code" not in m:
                            m["sector_code"] = code
                        processed.append(m)
                    save_sector_member(processed)
                    member_total += len(processed)
            except Exception:
                pass
            if (i + 1) % 30 == 0:
                await asyncio.sleep(0.5)
        set_meta_sector("member_updated", _TODAY)
        set_meta_sector("member_sector_count", str(len(all_sectors)))
        log[-1] += f" 共 {member_total} 条"
    else:
        await _step("跳过成分股下载(include_sector_members=False)")

    return {"status": "ok", "log": log, "paths": get_db_paths()}


# ════════════════════════════════════════
# 增量每日更新
# ════════════════════════════════════════

async def update_daily_stocks() -> dict:
    """增量更新股票数据: 实时行情 + 人气排名"""
    log = []

    # 实时行情
    log.append("更新全市场实时行情...")
    try:
        spots = await get_latest_indicators()
        for s in spots:
            s["updated_date"] = _TODAY
        save_stock_spot(spots)
        set_meta_stock("spot_updated", _TODAY)
        log[-1] += f" 共 {len(spots)} 只"
    except Exception as e:
        log[-1] += f" 失败: {e}"

    # 人气排名
    log.append("更新人气排名...")
    try:
        raw_rank = await _fetch_all_rankings()
        rank_rows = [_format_rank_item(r) for r in raw_rank]
        for r in rank_rows:
            r["rank_date"] = _TODAY
        save_stock_rank(rank_rows)
        set_meta_stock("rank_updated", _TODAY)
        log[-1] += f" 共 {len(rank_rows)} 条"
    except Exception as e:
        log[-1] += f" 失败: {e}"

    # 股票列表变更检测
    log.append("更新股票列表...")
    try:
        stocks = await get_stock_list()
        save_stock_basic(stocks)
        set_meta_stock("stock_count", str(len(stocks)))
        log[-1] += f" 共 {len(stocks)} 只"
    except Exception as e:
        log[-1] += f" 失败: {e}"

    return {"status": "ok", "log": log}


async def update_daily_sectors(include_members: bool = True) -> dict:
    """增量更新板块数据: 行情 + K线 + 成分股"""
    log = []

    # 板块列表
    log.append("更新概念板块...")
    try:
        concept = await get_sector_list("concept")
        for s in concept:
            s["updated_date"] = _TODAY
        log[-1] += f" 共 {len(concept)} 个"
    except Exception as e:
        concept = []
        log[-1] += f" 失败: {e}"

    log.append("更新行业板块...")
    try:
        industry = await get_sector_list("industry")
        for s in industry:
            s["updated_date"] = _TODAY
        log[-1] += f" 共 {len(industry)} 个"
    except Exception as e:
        industry = []
        log[-1] += f" 失败: {e}"

    all_sectors = concept + industry
    save_sector_basic(all_sectors)
    set_meta_sector("sector_count", str(len(all_sectors)))
    set_meta_sector("sector_updated", _TODAY)

    # 板块 K 线(只更新最近一条)
    log.append(f"更新 {len(all_sectors)} 个板块 K 线...")
    kline_total = 0
    for i, sec in enumerate(all_sectors):
        code = sec.get("sector_code", "")
        if not code:
            continue
        try:
            kl = await get_sector_kline(code, limit=5)
            if kl:
                save_sector_kline(kl)
                kline_total += len(kl)
        except Exception:
            pass
        if (i + 1) % 50 == 0:
            await asyncio.sleep(0.3)
    set_meta_sector("kline_updated", _TODAY)
    log[-1] += f" 共 {kline_total} 条"

    # 成分股
    if include_members:
        log.append(f"更新 {len(all_sectors)} 个板块成分股...")
        member_total = 0
        for i, sec in enumerate(all_sectors):
            code = sec.get("sector_code", "")
            if not code:
                continue
            try:
                members = await get_sector_members(code)
                if members:
                    processed = []
                    for m in members:
                        m["updated_date"] = _TODAY
                        if "sector_code" not in m:
                            m["sector_code"] = code
                        processed.append(m)
                    save_sector_member(processed)
                    member_total += len(processed)
            except Exception:
                pass
            if (i + 1) % 30 == 0:
                await asyncio.sleep(0.3)
        set_meta_sector("member_updated", _TODAY)
        log[-1] += f" 共 {member_total} 条"

    return {"status": "ok", "log": log}


async def update_daily_all(include_sector_members: bool = True) -> dict:
    stock_result = await update_daily_stocks()
    sector_result = await update_daily_sectors(include_sector_members)
    return {
        "status": "ok",
        "stock_log": stock_result["log"],
        "sector_log": sector_result["log"],
        "paths": get_db_paths(),
    }


# ════════════════════════════════════════
# 个股 K 线下载(按需)
# ════════════════════════════════════════

async def download_stock_kline(symbol: str, days: int = 365, adjust: str = "qfq") -> dict:
    """下载单只股票 K 线到本地数据库, 同时计算并存储技术指标"""
    end = date.today()
    start = end - timedelta(days=days + 30)
    try:
        klines = await get_stock_history(
            symbol,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )
        if klines:
            save_stock_kline(klines)
            # 计算并存储技术指标
            try:
                df = pd.DataFrame(klines)
                df = df.sort_values("date", ascending=True)
                ind_df = compute_all_indicators(df)
                # 只取需要的列
                ind_cols = [
                    "symbol", "date",
                    "MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
                    "RSI6", "RSI14", "RSI24",
                    "DIF", "DEA", "MACD",
                    "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
                    "K", "D", "J",
                    "VOL_MA5", "VOL_MA10",
                    "ATR14",
                ]
                available = [c for c in ind_cols if c in ind_df.columns]
                indicator_rows = ind_df[available].rename(columns={"K": "KDJ_K", "D": "KDJ_D", "J": "KDJ_J"})
                indicator_rows = indicator_rows.where(indicator_rows.notna(), None).to_dict(orient="records")
                if indicator_rows:
                    save_stock_indicators(indicator_rows)
            except Exception:
                pass
            return {"status": "ok", "symbol": symbol, "count": len(klines), "start": str(start), "end": str(end)}
        return {"status": "empty", "symbol": symbol}
    except Exception as e:
        return {"status": "error", "symbol": symbol, "error": str(e)}


async def download_top_stocks_kline(top_n: int = 200) -> dict:
    """下载人气排名前 N 只股票的 K 线"""
    spots = query_stock_db(
        "SELECT s.symbol FROM stock_spot s ORDER BY s.change_pct DESC LIMIT ?",
        (top_n,),
    )
    if not spots:
        ranked = query_stock_db(
            "SELECT DISTINCT symbol FROM stock_rank ORDER BY popularity_rank ASC LIMIT ?",
            (top_n,),
        )
        symbols = [r["symbol"] for r in ranked]
    else:
        symbols = [r["symbol"] for r in spots]

    log = []
    total = 0
    for sym in symbols:
        res = await download_stock_kline(sym)
        total += res.get("count", 0)
        if (len(log)) % 20 == 0:
            await asyncio.sleep(0.2)
    set_meta_stock("kline_top_n", str(top_n))
    return {"status": "ok", "stocks": len(symbols), "total_klines": total}
