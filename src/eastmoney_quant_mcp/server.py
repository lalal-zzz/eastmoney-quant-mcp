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
