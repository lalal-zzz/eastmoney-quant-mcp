"""
数据管理工具: 本地初始化、增量更新、本地搜索、板块→股票流程

所有函数均返回 list[dict] 或 dict，供 MCP server.py 注册为工具。
"""

from ..data.sync import (
    init_all_data,
    update_daily_all,
    download_stock_kline as sync_download_stock_kline,
    download_top_stocks_kline,
)
from ..data.search import (
    search_stock_local as local_search_stock,
    search_sector_local as local_search_sector,
    get_stock_kline_local,
    get_stock_rank_history,
    get_rank_trend,
    get_sector_kline_local,
    get_sector_members_local,
    get_sectors_by_stock,
    get_top_sectors,
    get_sector_to_stocks_flow,
    get_db_status as _get_db_status,
    get_stock_spot_batch,
    screen_stocks_local,
)

from ..tools.stock_data import get_stock_history, search_stock


# ════════════════════════════════════════
# 数据管理
# ════════════════════════════════════════


async def init_full_data(include_sector_members: bool = True) -> dict:
    """全量初始化: 一次性下载股票+板块全部数据到本地数据库"""
    return await init_all_data(include_sector_members=include_sector_members)


async def update_daily_data(include_sector_members: bool = True) -> dict:
    """增量每日更新: 只更新当日变化的数据"""
    return await update_daily_all(include_sector_members=include_sector_members)


async def get_data_status() -> dict:
    """查看本地数据库状态(数据量、更新时间)"""
    return _get_db_status()


# ════════════════════════════════════════
# 股票本地搜索
# ════════════════════════════════════════


async def search_stock_full(keyword: str, limit: int = 50) -> list[dict]:
    """搜索股票(本地优先, 无结果回退网络)"""
    results = local_search_stock(keyword, limit)
    if results:
        return results
    return await search_stock(keyword)


async def get_kline_local_or_net(symbol: str, days: int = 250, adjust: str = "qfq") -> list[dict]:
    """获取股票K线(本地优先, 无数据自动下载)"""
    klines = get_stock_kline_local(symbol, days)
    if klines and len(klines) >= 10:
        return klines
    await sync_download_stock_kline(symbol, days=days, adjust=adjust)
    return get_stock_kline_local(symbol, days)


async def get_rank_history(symbol: str = None, limit: int = 100) -> list[dict]:
    """获取历史人气排名"""
    return get_stock_rank_history(symbol=symbol, limit=limit)


async def get_rank_trend_data(symbol: str, days: int = 30) -> list[dict]:
    """获取单只股票人气排名趋势"""
    return get_rank_trend(symbol, days)


async def batch_download_kline(symbols: str, days: int = 365, adjust: str = "qfq") -> dict:
    """批量下载多只股票K线(逗号分隔代码)"""
    codes = [s.strip() for s in symbols.split(",") if s.strip()]
    log = []
    total = 0
    for code in codes:
        res = await sync_download_stock_kline(code, days=days, adjust=adjust)
        log.append(res)
        total += res.get("count", 0)
    return {"status": "ok", "symbols": len(codes), "total_klines": total, "detail": log}


async def download_top_klines(top_n: int = 200) -> dict:
    """下载人气前N只股票的K线"""
    return await download_top_stocks_kline(top_n)


# ════════════════════════════════════════
# 板块本地搜索
# ════════════════════════════════════════


async def search_sector_full(keyword: str, limit: int = 50) -> list[dict]:
    """搜索板块(本地优先)"""
    return local_search_sector(keyword, limit)


async def get_sector_kline(sector_code: str, limit: int = 250) -> list[dict]:
    """获取板块K线(本地)"""
    return get_sector_kline_local(sector_code, limit)


async def get_top_sectors_rank(sort_by: str = "change_pct", sector_type: str = None, limit: int = 20) -> list[dict]:
    """本地排行榜: 涨幅最强/资金流入最多的板块"""
    return get_top_sectors(sort_by=sort_by, sector_type=sector_type, limit=limit)


async def get_stock_belong_sectors(stock_code: str) -> list[dict]:
    """查询某只股票属于哪些板块"""
    return get_sectors_by_stock(stock_code)


async def get_sector_members_flow(sector_code: str, member_limit: int = 50, sort_by: str = "change_pct") -> dict:
    """
    从板块获取成分股全面信息(行情/资金流向/人气排名)

    实现 板块 → 股票 的完整分析流程。
    """
    return await get_sector_to_stocks_flow(sector_code, member_limit, sort_by)


# ════════════════════════════════════════
# 多条件选股(本地)
# ════════════════════════════════════════

async def screen_stocks(
    conditions: dict = None,
    top_n: int = 50,
    sort_by: str = "change_pct",
    sector_code: str = None,
    name_keyword: str = None,
) -> list[dict]:
    """
    多条件本地选股(使用本地数据库, 需先初始化)

    conditions 字典支持的键:
      min_price, max_price          — 价格区间
      min_change_pct, max_change_pct — 涨跌幅区间
      min_volume_ratio              — 最小量比
      min_turnover_rate, max_turnover_rate — 换手率区间
      min_pe, max_pe                — 市盈率区间
      min_pb, max_pb                — 市净率区间
      min_market_cap, max_market_cap — 总市值区间(亿元)
      min_float_market_cap          — 最小流通市值(亿元)
      min_sixty_day_change          — 最小60日涨跌幅
      min_ytd_change                — 最小年初至今涨跌幅
      min_amplitude, max_amplitude  — 振幅区间
    """
    return screen_stocks_local(
        conditions=conditions,
        top_n=top_n,
        sort_by=sort_by,
        sector_code=sector_code,
        name_keyword=name_keyword,
    )
