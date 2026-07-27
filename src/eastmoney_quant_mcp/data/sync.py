"""
数据同步模块: 全量初始化 + 增量每日更新

使用 asyncio.Semaphore 并发下载(默认 8 并发), 大幅加速批量数据获取。
增量更新只拉取变化数据, 不做全量重复下载。
"""

import asyncio
from datetime import date, timedelta

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
    query_stock_db,
    get_db_paths,
)

from ..tools.stock_data import get_stock_list, get_stock_history, get_latest_indicators
from ..tools.stock_rank import _fetch_all_rankings, _format_rank_item
from ..tools.sector_data import get_sector_list, get_sector_kline_net, get_sector_members
from .indicators import compute_all_indicators

import pandas as pd

_CONCURRENCY = 8


def _today() -> str:
    """当前日期(每次调用时求值, 避免长驻进程跨天后日期固化)"""
    return date.today().isoformat()


def _format_rank_items(items: list[dict]) -> list[dict]:
    """批量格式化排名数据, 跳过无法识别代码的脏数据, 避免单条异常炸掉整批更新"""
    result = []
    for item in items:
        try:
            result.append(_format_rank_item(item))
        except ValueError:
            continue
    return result


# ── 并发控制 ──


async def _concurrent_map(items, async_fn, desc="", batch_size=30):
    """对 items 并发执行 async_fn, 每 batch_size 个等待一小段"""
    total = len(items)
    results = []
    for i in range(0, total, _CONCURRENCY):
        batch = items[i:i + _CONCURRENCY]
        batch_results = await asyncio.gather(*[async_fn(item) for item in batch], return_exceptions=True)
        results.extend(batch_results)
        if (i + _CONCURRENCY) % (batch_size * _CONCURRENCY) == 0:
            await asyncio.sleep(0.3)  # 批次间小歇, 降低 API 压力
    return results


async def _fetch_kline(item):
    code, limit = item if isinstance(item, tuple) else (item, 250)
    try:
        return await get_sector_kline_net(code, limit)
    except Exception:
        return []


async def _fetch_members(code):
    try:
        return code, await get_sector_members(code)
    except Exception:
        return code, []


# ═══════════════════ 全量初始化 ═══════════════════

async def init_all_data(include_sector_members: bool = True) -> dict:
    """一次性全量下载(并发加速)"""
    init_dbs()
    log = []
    today = _today()
    total_steps = 7 if include_sector_members else 5
    step = 0

    def _step(msg):
        nonlocal step
        step += 1
        log.append(f"[{step}/{total_steps}] {msg}")

    # 1. 股票列表(单次 API)
    _step("下载股票列表...")
    stocks = await get_stock_list()
    save_stock_basic(stocks)
    set_meta_stock("stock_count", str(len(stocks)))
    log[-1] += f" {len(stocks)} 只"

    # 2. 全市场实时行情(单次 API)
    _step("下载全市场实时行情...")
    spots = await get_latest_indicators()
    for s in spots:
        s["updated_date"] = today
    save_stock_spot(spots)
    set_meta_stock("spot_updated", today)
    log[-1] += f" {len(spots)} 只"

    # 3. 人气排名(分页 API)
    _step("下载人气排名...")
    raw_rank = await _fetch_all_rankings()
    rank_rows = _format_rank_items(raw_rank)
    for r in rank_rows:
        r["rank_date"] = today
    save_stock_rank(rank_rows)
    set_meta_stock("rank_updated", today)
    log[-1] += f" {len(rank_rows)} 条"

    # 4. 板块列表
    _step("下载概念板块...")
    concept = await get_sector_list("concept")
    _step("下载行业板块...")
    industry = await get_sector_list("industry")
    all_sectors = concept + industry
    for s in all_sectors:
        s["updated_date"] = today
    save_sector_basic(all_sectors)
    set_meta_sector("sector_count", str(len(all_sectors)))
    set_meta_sector("sector_updated", today)
    log[-1] += f" 概念{len(concept)}+行业{len(industry)}={len(all_sectors)}"

    # 5. 板块 K 线(并发下载, 限250条)
    codes = [s.get("sector_code", "") for s in all_sectors if s.get("sector_code")]
    _step(f"并发下载 {len(codes)} 个板块 K 线...")
    tasks = [(code, 250) for code in codes]
    all_klines = await _concurrent_map(tasks, _fetch_kline, desc="板块K线")
    kline_total = 0
    for kl in all_klines:
        if kl:
            save_sector_kline(kl)
            kline_total += len(kl)
    set_meta_sector("kline_updated", today)
    log[-1] += f" {kline_total} 条"

    # 6-7. 板块成分股(可选, 并发下载)
    if include_sector_members:
        _step(f"并发下载 {len(codes)} 个板块成分股...")
        member_results = await _concurrent_map(codes, _fetch_members, desc="成分股", batch_size=15)
        member_total = 0
        for code, members in member_results:
            if members:
                for m in members:
                    m["updated_date"] = today
                    if "sector_code" not in m:
                        m["sector_code"] = code
                save_sector_member(members)
                member_total += len(members)
        set_meta_sector("member_updated", today)
        set_meta_sector("member_sector_count", str(len(codes)))
        log[-1] += f" {member_total} 条"
    else:
        _step("跳过成分股下载")

    return {"status": "ok", "log": log, "paths": get_db_paths()}


# ═══════════════════ 增量每日更新 ═══════════════════

async def update_daily_stocks() -> dict:
    """增量更新股票: 行情+排名+列表(三项各一次 API)"""
    log = []
    today = _today()
    for label, coro, on_ok in [
        ("实时行情", get_latest_indicators(),
         lambda r: (save_stock_spot([{**s, "updated_date": today} for s in r]),
                    set_meta_stock("spot_updated", today), f"{len(r)} 只")),
        ("人气排名", _fetch_all_rankings(),
         lambda r: (save_stock_rank([{**x, "rank_date": today} for x in _format_rank_items(r)]),
                    set_meta_stock("rank_updated", today), f"{len(r)} 条")),
        ("股票列表", get_stock_list(),
         lambda r: (save_stock_basic(r), set_meta_stock("stock_count", str(len(r))), f"{len(r)} 只")),
    ]:
        try:
            result = await coro
            ret = on_ok(result)  # 副作用只执行一次
            log.append(f"{label}: OK {ret[-1]}")
        except Exception as e:
            log.append(f"{label}: FAIL {e}")
    return {"status": "ok", "log": log}


async def update_daily_sectors(include_members: bool = True, top_n: int = 50) -> dict:
    """
    增量更新板块 — 智能策略, 避免全量重复下载。

    - 板块列表: 全量更新(几个 API 调用, 很快)
    - K 线: 仅更新涨跌幅前 top_n 板块的最近 5 条(避免 280+ 次 API 调用)
    - 成分股: 仅更新涨跌幅前 top_n 板块(与 K 线一致)
    """
    log = []
    today = _today()

    # 板块列表(全量, 快)
    all_sectors = []
    for st in ["concept", "industry"]:
        try:
            secs = await get_sector_list(st)
            for s in secs:
                s["updated_date"] = today
            all_sectors.extend(secs)
            log.append(f"板块列表({st}): {len(secs)} 个")
        except Exception as e:
            log.append(f"板块列表({st}): FAIL {e}")
    save_sector_basic(all_sectors)
    set_meta_sector("sector_count", str(len(all_sectors)))
    set_meta_sector("sector_updated", today)

    # 筛选活跃板块(top_n 按涨跌幅绝对值)
    active = sorted(
        [s for s in all_sectors if s.get("change_pct") is not None],
        key=lambda x: abs(x.get("change_pct") or 0), reverse=True,
    )[:top_n]
    active_codes = [s["sector_code"] for s in active]

    # K 线(仅活跃板块, 最近 5 条) → 并发
    try:
        log.append(f"板块K线(Top{len(active_codes)}, 最近5条): 并发...")
        tasks = [(code, 5) for code in active_codes]
        all_klines = await _concurrent_map(tasks, _fetch_kline)
        kline_total = 0
        for kl in all_klines:
            if kl:
                save_sector_kline(kl)
                kline_total += len(kl)
        set_meta_sector("kline_updated", today)
        log[-1] += f" OK {kline_total} 条"
    except Exception as e:
        log.append(f"板块K线: FAIL {e}")

    # 成分股(仅活跃板块) → 并发
    if include_members and active_codes:
        try:
            log.append(f"成分股(Top{len(active_codes)}): 并发...")
            member_results = await _concurrent_map(active_codes, _fetch_members)
            member_total = 0
            for code, members in member_results:
                if members:
                    for m in members:
                        m["updated_date"] = today
                        if "sector_code" not in m:
                            m["sector_code"] = code
                    save_sector_member(members)
                    member_total += len(members)
            set_meta_sector("member_updated", today)
            log[-1] += f" OK {member_total} 条"
        except Exception as e:
            log.append(f"成分股: FAIL {e}")

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


# ═══════════════════ 个股 K 线(按需, 并发批量) ═══════════════════

async def _download_one_kline(symbol: str, days: int = 365, adjust: str = "qfq") -> dict:
    end = date.today()
    start = end - timedelta(days=days + 30)
    try:
        klines = await get_stock_history(
            symbol, start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust=adjust,
        )
        if klines:
            save_stock_kline(klines)
            try:
                df = pd.DataFrame(klines)
                df = df.sort_values("date", ascending=True)
                ind_df = compute_all_indicators(df)
                ind_cols = [
                    "symbol", "date",
                    "MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
                    "RSI6", "RSI14", "RSI24",
                    "DIF", "DEA", "MACD",
                    "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
                    "K", "D", "J", "VOL_MA5", "VOL_MA10", "ATR14",
                ]
                available = [c for c in ind_cols if c in ind_df.columns]
                ind_rows = ind_df[available].rename(columns={"K": "KDJ_K", "D": "KDJ_D", "J": "KDJ_J"})
                ind_rows = ind_rows.where(ind_rows.notna(), None).to_dict(orient="records")
                if ind_rows:
                    save_stock_indicators(ind_rows)
            except Exception:
                pass
            return {"status": "ok", "symbol": symbol, "count": len(klines)}
        return {"status": "empty", "symbol": symbol}
    except Exception as e:
        return {"status": "error", "symbol": symbol, "error": str(e)}


async def download_stock_kline(symbol: str, days: int = 365, adjust: str = "qfq") -> dict:
    return await _download_one_kline(symbol, days, adjust)


async def download_stocks_kline_batch(symbols: list[str], days: int = 365, adjust: str = "qfq") -> dict:
    """并发批量下载多只股票 K 线"""
    async def _task(sym):
        return await _download_one_kline(sym, days, adjust)

    results = await _concurrent_map(symbols, _task, desc="K线批量")
    total = sum(r.get("count", 0) for r in results if isinstance(r, dict))
    return {"status": "ok", "symbols": len(symbols), "total_klines": total, "detail": results}
