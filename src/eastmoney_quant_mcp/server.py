"""
东方财富量化 MCP Server 入口

启动方式:
    python -m eastmoney_quant_mcp.server
    或
    eastmoney-quant-mcp

MCP 客户端配置 (claude_desktop_config.json / codex.yaml):
    {
      "mcpServers": {
        "eastmoney-quant": {
          "command": "python",
          "args": ["-m", "eastmoney_quant_mcp.server"]
        }
      }
    }
"""

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools.stock_data import (
    get_stock_list,
    get_stock_history,
    get_latest_indicators,
    get_stock_indicators,
    search_stock,
)
from .tools.stock_rank import (
    get_popularity_rankings,
    get_top_gainers_rank,
    get_top_volume_rank,
    get_top_turnover_rank,
)
from .tools.sector_data import (
    get_sector_list,
    get_sector_members,
    get_sector_kline,
)
from .tools.pattern_scan import (
    PATTERNS,
    PATTERN_DESCRIPTIONS,
)
from .tools.sector_screen import (
    screen_top_sectors,
    screen_main_inflow_sectors,
    screen_sector_with_leaders,
    screen_sector_by_capital_flow,
    get_full_sector_analysis,
)
from .tools.data_manager import (
    init_full_data,
    update_daily_data,
    get_data_status,
    search_stock_full,
    get_kline_local_or_net,
    get_rank_history,
    get_rank_trend_data,
    batch_download_kline,
    download_top_klines,
    search_sector_full,
    get_sector_kline,
    get_top_sectors_rank,
    get_stock_belong_sectors,
    get_sector_members_flow,
    screen_stocks,
)
from .tools.analysis import generate_stock_report

server = Server("eastmoney-quant-mcp")

# ── 工具注册 ──

TOOL_HANDLERS = {}


def register(name: str, description: str, input_schema: dict):
    def decorator(func):
        TOOL_HANDLERS[name] = {"func": func, "description": description, "schema": input_schema}
        return func

    return decorator


# ════════════════════════════════════════
# 股票数据工具
# ════════════════════════════════════════

@register("get_stock_list", "获取A股所有股票基本信息列表(代码+名称)", {
    "type": "object",
    "properties": {},
    "required": [],
})
async def _get_stock_list() -> list[dict]:
    return await get_stock_list()


@register("get_stock_history", "获取单只股票历史K线数据(开高低收量额)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码,如 000001 或 sz000001"},
        "start_date": {"type": "string", "description": "开始日期 YYYYMMDD"},
        "end_date": {"type": "string", "description": "结束日期 YYYYMMDD"},
        "adjust": {"type": "string", "description": "复权方式: qfq(前复权)/hfq(后复权)/空(不复权),默认qfq"},
    },
    "required": ["symbol", "start_date", "end_date"],
})
async def _get_stock_history(symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[dict]:
    return await get_stock_history(symbol, start_date, end_date, adjust)


@register("get_latest_indicators", "获取全市场股票最新实时行情(价格/涨跌幅/量比/换手/PE/PB/市值等)", {
    "type": "object",
    "properties": {},
    "required": [],
})
async def _get_latest_indicators() -> list[dict]:
    return await get_latest_indicators()


@register("get_stock_indicators", "获取单只股票K线+技术指标(MA/RSI/MACD/BOLL/KDJ/ATR)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码,如 000001"},
        "days": {"type": "integer", "description": "最近交易日数,默认120"},
    },
    "required": ["symbol"],
})
async def _get_stock_indicators(symbol: str, days: int = 120) -> list[dict]:
    return await get_stock_indicators(symbol, days)


@register("search_stock", "模糊搜索股票(代码或名称关键词)", {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "description": "搜索关键词,如 '银行' 或 '000001'"},
    },
    "required": ["keyword"],
})
async def _search_stock(keyword: str) -> list[dict]:
    return await search_stock(keyword)


# ════════════════════════════════════════
# 人气榜单工具
# ════════════════════════════════════════

@register("get_popularity_rankings", "获取东方财富人气排名榜单(按人气排名升序,前N只)", {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "description": "返回数量,默认50"},
    },
    "required": [],
})
async def _get_popularity_rankings(top_n: int = 50) -> list[dict]:
    return await get_popularity_rankings(top_n)


@register("get_top_gainers_rank", "获取涨幅最高的人气榜股票", {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "description": "返回数量,默认50"},
    },
    "required": [],
})
async def _get_top_gainers_rank(top_n: int = 50) -> list[dict]:
    return await get_top_gainers_rank(top_n)


@register("get_top_volume_rank", "获取成交量最大的人气榜股票", {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "description": "返回数量,默认50"},
    },
    "required": [],
})
async def _get_top_volume_rank(top_n: int = 50) -> list[dict]:
    return await get_top_volume_rank(top_n)


@register("get_top_turnover_rank", "获取换手率最高的人气榜股票", {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "description": "返回数量,默认50"},
    },
    "required": [],
})
async def _get_top_turnover_rank(top_n: int = 50) -> list[dict]:
    return await get_top_turnover_rank(top_n)


# ════════════════════════════════════════
# 板块数据工具
# ════════════════════════════════════════

@register("get_sector_list", "获取行业/概念板块列表及其当日行情数据(涨跌幅/资金流向)", {
    "type": "object",
    "properties": {
        "sector_type": {
            "type": "string",
            "description": "板块类型: concept(概念板块)/industry(行业板块),默认concept",
        },
    },
    "required": [],
})
async def _get_sector_list(sector_type: str = "concept") -> list[dict]:
    return await get_sector_list(sector_type)


@register("get_sector_members", "获取指定板块的成分股列表(含涨跌幅/价格/换手率等)", {
    "type": "object",
    "properties": {
        "sector_code": {"type": "string", "description": "板块代码,如 BK1090"},
    },
    "required": ["sector_code"],
})
async def _get_sector_members(sector_code: str) -> list[dict]:
    return await get_sector_members(sector_code)


@register("get_sector_kline", "获取板块历史K线数据", {
    "type": "object",
    "properties": {
        "sector_code": {"type": "string", "description": "板块代码,如 BK1090"},
        "limit": {"type": "integer", "description": "K线条数,默认120"},
    },
    "required": ["sector_code"],
})
async def _get_sector_kline(sector_code: str, limit: int = 120) -> list[dict]:
    return await get_sector_kline(sector_code, limit)


# ════════════════════════════════════════
# 形态选股工具
# ════════════════════════════════════════

@register("screen_by_pattern", "根据技术形态筛选股票(金叉/超跌反弹/放量突破/强势突破/低估值/多头排列)", {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": f"形态类型: {', '.join(PATTERN_DESCRIPTIONS.keys())}",
        },
        "top_n": {"type": "integer", "description": "返回数量,默认30"},
    },
    "required": ["pattern"],
})
async def _screen_by_pattern(pattern: str, top_n: int = 30) -> list[dict]:
    func = PATTERNS.get(pattern)
    if not func:
        return [{"error": f"未知形态 '{pattern}', 可选: {list(PATTERNS.keys())}"}]
    return await func(top_n=top_n)


@register("get_pattern_list", "获取所有支持的选股形态列表及说明", {
    "type": "object",
    "properties": {},
    "required": [],
})
async def _get_pattern_list() -> list[dict]:
    return [{"pattern": k, "description": v} for k, v in PATTERN_DESCRIPTIONS.items()]


# ════════════════════════════════════════
# 板块选择工具
# ════════════════════════════════════════

@register("screen_top_sectors", "按涨跌幅筛选强势板块", {
    "type": "object",
    "properties": {
        "sector_type": {"type": "string", "description": "concept(概念)或industry(行业),默认concept"},
        "top_n": {"type": "integer", "description": "返回数量,默认20"},
    },
    "required": [],
})
async def _screen_top_sectors(sector_type: str = "concept", top_n: int = 20) -> list[dict]:
    return await screen_top_sectors(sector_type, top_n)


@register("screen_main_inflow_sectors", "按主力资金净流入筛选板块", {
    "type": "object",
    "properties": {
        "sector_type": {"type": "string", "description": "concept(概念)或industry(行业),默认concept"},
        "top_n": {"type": "integer", "description": "返回数量,默认20"},
    },
    "required": [],
})
async def _screen_main_inflow_sectors(sector_type: str = "concept", top_n: int = 20) -> list[dict]:
    return await screen_main_inflow_sectors(sector_type, top_n)


@register("screen_sector_with_leaders", "筛选强势板块并返回龙头成分股榜单", {
    "type": "object",
    "properties": {
        "sector_type": {"type": "string", "description": "concept(概念)或industry(行业),默认concept"},
        "top_n": {"type": "integer", "description": "板块数量,默认10"},
        "member_count": {"type": "integer", "description": "每板块龙头成分股数,默认10"},
    },
    "required": [],
})
async def _screen_sector_with_leaders(sector_type: str = "concept", top_n: int = 10, member_count: int = 10) -> list[dict]:
    return await screen_sector_with_leaders(sector_type, top_n, member_count)


@register("get_full_sector_analysis", "获取板块综合分析(行情/资金流向/成分股涨跌分布)", {
    "type": "object",
    "properties": {
        "sector_code": {"type": "string", "description": "板块代码,如 BK1090"},
        "member_limit": {"type": "integer", "description": "成分股返回数,默认30"},
    },
    "required": ["sector_code"],
})
async def _get_full_sector_analysis(sector_code: str, member_limit: int = 30) -> dict:
    return await get_full_sector_analysis(sector_code, member_limit)


# ════════════════════════════════════════
# 数据管理工具(本地存储 + 同步)
# ════════════════════════════════════════

@register("init_full_data", "一次性全量下载股票+板块数据到本地数据库(首次使用必调)", {
    "type": "object",
    "properties": {
        "include_sector_members": {"type": "boolean", "description": "是否下载板块成分股(耗时较长但完整),默认true"},
    },
    "required": [],
})
async def _init_full_data(include_sector_members: bool = True) -> dict:
    return await init_full_data(include_sector_members)


@register("update_daily_data", "增量每日更新股票+板块数据(建议每日运行)", {
    "type": "object",
    "properties": {
        "include_sector_members": {"type": "boolean", "description": "是否更新板块成分股,默认true"},
    },
    "required": [],
})
async def _update_daily_data(include_sector_members: bool = True) -> dict:
    return await update_daily_data(include_sector_members)


@register("get_data_status", "查看本地数据库状态(数据量/更新时间/存储路径)", {
    "type": "object",
    "properties": {},
    "required": [],
})
async def _get_data_status() -> dict:
    return await get_data_status()


# ════════════════════════════════════════
# 股票本地搜索 + K线管理
# ════════════════════════════════════════

@register("search_stock_full", "搜索股票(本地优先,无结果回退网络)", {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "description": "搜索关键词(代码或名称)"},
        "limit": {"type": "integer", "description": "返回数量,默认50"},
    },
    "required": ["keyword"],
})
async def _search_stock_full(keyword: str, limit: int = 50) -> list[dict]:
    return await search_stock_full(keyword, limit)


@register("get_kline_local_or_net", "获取股票K线(本地优先,无数据自动从网络下载)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码"},
        "days": {"type": "integer", "description": "最近天数,默认250"},
        "adjust": {"type": "string", "description": "复权方式: qfq/hfq/空,默认qfq"},
    },
    "required": ["symbol"],
})
async def _get_kline_local_or_net(symbol: str, days: int = 250, adjust: str = "qfq") -> list[dict]:
    return await get_kline_local_or_net(symbol, days, adjust)


@register("get_rank_history", "获取历史人气排名数据", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "可选,指定股票代码;不填则返回全部"},
        "limit": {"type": "integer", "description": "返回条数,默认100"},
    },
    "required": [],
})
async def _get_rank_history(symbol: str = None, limit: int = 100) -> list[dict]:
    return await get_rank_history(symbol, limit)


@register("get_rank_trend_data", "获取单只股票人气排名趋势(近N天)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码"},
        "days": {"type": "integer", "description": "天数,默认30"},
    },
    "required": ["symbol"],
})
async def _get_rank_trend_data(symbol: str, days: int = 30) -> list[dict]:
    return await get_rank_trend_data(symbol, days)


@register("batch_download_kline", "批量下载多只股票K线到本地", {
    "type": "object",
    "properties": {
        "symbols": {"type": "string", "description": "股票代码,逗号分隔,如 '000001,600000,000858'"},
        "days": {"type": "integer", "description": "下载天数,默认365"},
        "adjust": {"type": "string", "description": "复权方式: qfq/hfq/空,默认qfq"},
    },
    "required": ["symbols"],
})
async def _batch_download_kline(symbols: str, days: int = 365, adjust: str = "qfq") -> dict:
    return await batch_download_kline(symbols, days, adjust)


@register("download_top_klines", "批量下载人气前N只股票的K线", {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "description": "下载数量,默认200"},
    },
    "required": [],
})
async def _download_top_klines(top_n: int = 200) -> dict:
    return await download_top_klines(top_n)


# ════════════════════════════════════════
# 板块本地搜索 + 板块↔股票流程
# ════════════════════════════════════════

@register("search_sector_full", "搜索板块(本地数据库)", {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "description": "关键词(板块名称或代码)"},
        "limit": {"type": "integer", "description": "返回数量,默认50"},
    },
    "required": ["keyword"],
})
async def _search_sector_full(keyword: str, limit: int = 50) -> list[dict]:
    return await search_sector_full(keyword, limit)


@register("get_sector_kline_local", "获取板块K线(本地数据库,需先初始化)", {
    "type": "object",
    "properties": {
        "sector_code": {"type": "string", "description": "板块代码,如 BK1090"},
        "limit": {"type": "integer", "description": "K线条数,默认250"},
    },
    "required": ["sector_code"],
})
async def _get_sector_kline_local(sector_code: str, limit: int = 250) -> list[dict]:
    return await get_sector_kline(sector_code, limit)


@register("get_top_sectors_rank", "本地排行: 涨幅最强/资金流入最多的板块", {
    "type": "object",
    "properties": {
        "sort_by": {"type": "string", "description": "排序字段: change_pct/main_net_inflow/large_net,默认change_pct"},
        "sector_type": {"type": "string", "description": "板块类型: concept/industry,为空则两者都查"},
        "limit": {"type": "integer", "description": "返回数量,默认20"},
    },
    "required": [],
})
async def _get_top_sectors_rank(sort_by: str = "change_pct", sector_type: str = None, limit: int = 20) -> list[dict]:
    return await get_top_sectors_rank(sort_by, sector_type, limit)


@register("get_stock_belong_sectors", "查询某只股票属于哪些板块", {
    "type": "object",
    "properties": {
        "stock_code": {"type": "string", "description": "股票代码,如 000001"},
    },
    "required": ["stock_code"],
})
async def _get_stock_belong_sectors(stock_code: str) -> list[dict]:
    return await get_stock_belong_sectors(stock_code)


@register("get_sector_members_flow", "板块→股票: 获取板块成分股行情/资金流向/人气排名", {
    "type": "object",
    "properties": {
        "sector_code": {"type": "string", "description": "板块代码,如 BK1090"},
        "member_limit": {"type": "integer", "description": "成分股数量,默认50"},
        "sort_by": {"type": "string", "description": "排序: change_pct/turnover_rate/volume_ratio/volume,默认change_pct"},
    },
    "required": ["sector_code"],
})
async def _get_sector_members_flow(sector_code: str, member_limit: int = 50, sort_by: str = "change_pct") -> dict:
    return await get_sector_members_flow(sector_code, member_limit, sort_by)


# ════════════════════════════════════════
# 多条件选股(本地数据库)
# ════════════════════════════════════════

@register("screen_stocks", "多条件本地选股(价格/涨跌幅/PE/PB/市值/量比/换手/板块等组合筛选)", {
    "type": "object",
    "properties": {
        "conditions": {
            "type": "object",
            "description": (
                "筛选条件JSON对象。支持的键: min_price,max_price(价格区间), "
                "min_change_pct,max_change_pct(涨跌幅区间), "
                "min_volume_ratio(最小量比), "
                "min_turnover_rate,max_turnover_rate(换手率区间), "
                "min_pe,max_pe(市盈率区间), min_pb,max_pb(市净率区间), "
                "min_market_cap,max_market_cap(总市值区间/亿), "
                "min_float_market_cap(最小流通市值/亿), "
                "min_sixty_day_change(最小60日涨幅), min_ytd_change(最小年初至今涨幅), "
                "min_amplitude,max_amplitude(振幅区间)。"
                "示例: {\"min_change_pct\":3,\"max_pe\":30,\"min_volume_ratio\":1.5}"
            ),
        },
        "top_n": {"type": "integer", "description": "返回数量,默认50"},
        "sort_by": {"type": "string", "description": "排序字段: change_pct/volume_ratio/turnover_rate/pe_dynamic/pb/total_market_cap/popularity_rank等,默认change_pct"},
        "sector_code": {"type": "string", "description": "可选,限定板块代码如BK1090"},
        "name_keyword": {"type": "string", "description": "可选,股票名称关键词"},
    },
    "required": [],
})
async def _screen_stocks(conditions: dict = None, top_n: int = 50, sort_by: str = "change_pct",
                         sector_code: str = None, name_keyword: str = None) -> list[dict]:
    return await screen_stocks(conditions, top_n, sort_by, sector_code, name_keyword)


# ════════════════════════════════════════
# 综合分析报告
# ════════════════════════════════════════

@register("generate_stock_report", "生成个股综合分析报告(趋势/支撑阻力/风险/仓位管理)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码,如 000001"},
    },
    "required": ["symbol"],
})
async def _generate_stock_report(symbol: str) -> dict:
    return await generate_stock_report(symbol)


# ════════════════════════════════════════
# MCP 生命周期
# ════════════════════════════════════════


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name=name,
            description=info["description"],
            inputSchema=info["schema"],
        )
        for name, info in TOOL_HANDLERS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    info = TOOL_HANDLERS.get(name)
    if not info:
        return [TextContent(type="text", text=f"未知工具: {name}")]

    try:
        result = await info["func"](**arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


def main():
    """MCP 服务入口"""
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
