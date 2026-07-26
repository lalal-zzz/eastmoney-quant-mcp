"""
东方财富量化 MCP Server — 精简入口
只暴露 9 个核心数据工具，其余逻辑由 Skill 组合实现。
"""

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools.data_manager import (
    init_full_data,
    update_daily_data,
    get_data_status,
    get_kline_local_or_net,
    get_rank_trend_data,
    get_stock_belong_sectors,
    screen_stocks,
)
from .tools.analysis import generate_stock_report
from .tools.sector_data import get_sector_list
from .tools.stock_data import get_stock_history

server = Server("eastmoney-quant-mcp")

TOOL_HANDLERS = {}


def register(name, description, input_schema):
    def decorator(func):
        TOOL_HANDLERS[name] = {"func": func, "description": description, "schema": input_schema}
        return func
    return decorator


# ═══════════════════ 数据管理 (3) ═══════════════════

@register("init_full_data", "一次性全量下载股票+板块数据到本地SQLite(首次必调)", {
    "type": "object",
    "properties": {
        "include_sector_members": {"type": "boolean", "description": "是否下载板块成分股(耗时但完整),默认true"},
    },
    "required": [],
})
async def _init(include_sector_members=True) -> dict:
    return await init_full_data(include_sector_members)


@register("update_daily_data", "增量每日更新(建议收盘后运行)", {
    "type": "object",
    "properties": {
        "include_sector_members": {"type": "boolean", "description": "是否更新板块成分股,默认true"},
    },
    "required": [],
})
async def _update(include_sector_members=True) -> dict:
    return await update_daily_data(include_sector_members)


@register("get_data_status", "查看本地数据库状态(数据量/更新时间/路径)", {
    "type": "object", "properties": {}, "required": [],
})
async def _status() -> dict:
    return await get_data_status()


# ═══════════════════ 选股 (1) ═══════════════════

@register("screen_stocks", (
    "万能本地选股: 18种条件自由组合(价格/涨跌幅/PE/PB/市值/量比/换手/振幅/60日涨幅/年初至今涨幅), "
    "支持板块限定、名称关键词、多字段排序。无本地数据时回退网络。"
    "示例: screen_stocks({\"min_change_pct\":3,\"max_pe\":30,\"min_volume_ratio\":1.5}) 找放量突破低估值股; "
    "screen_stocks(sector_code=\"BK1090\") 查看板块成分股; "
    "screen_stocks(name_keyword=\"银行\",sort_by=\"pe_dynamic\") 按名称搜银行股并PE排序"
), {
    "type": "object",
    "properties": {
        "conditions": {
            "type": "object",
            "description": (
                "全部可选: min_price,max_price, min_change_pct,max_change_pct, "
                "min_volume_ratio, min_turnover_rate,max_turnover_rate, "
                "min_pe,max_pe, min_pb,max_pb, min_market_cap,max_market_cap, "
                "min_float_market_cap, min_sixty_day_change, min_ytd_change, "
                "min_amplitude,max_amplitude"
            ),
        },
        "top_n": {"type": "integer", "description": "返回数量,默认50"},
        "sort_by": {"type": "string", "description": (
            "change_pct/volume_ratio/turnover_rate/pe_dynamic/pb/"
            "total_market_cap/latest_price/volume/amplitude/popularity_rank"
        )},
        "sector_code": {"type": "string", "description": "可选,限定板块(如BK1090), 等效于查该板块成分股"},
        "name_keyword": {"type": "string", "description": "可选,名称关键词模糊搜索"},
    },
    "required": [],
})
async def _screen(conditions=None, top_n=50, sort_by="change_pct",
                  sector_code=None, name_keyword=None) -> list[dict]:
    return await screen_stocks(conditions, top_n, sort_by, sector_code, name_keyword)


# ═══════════════════ 数据查询 (4) ═══════════════════

@register("get_kline_local_or_net", "个股K线(本地优先,不足自动从网络下载并缓存技术指标)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码"},
        "days": {"type": "integer", "description": "默认250个交易日"},
        "adjust": {"type": "string", "description": "qfq/hfq/不复权,默认qfq"},
    },
    "required": ["symbol"],
})
async def _kline(symbol, days=250, adjust="qfq") -> list[dict]:
    return await get_kline_local_or_net(symbol, days, adjust)


@register("get_rank_trend_data", "个股人气排名历史趋势(近N天排行变化)", {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码"},
        "days": {"type": "integer", "description": "默认30"},
    },
    "required": ["symbol"],
})
async def _rank_trend(symbol, days=30) -> list[dict]:
    return await get_rank_trend_data(symbol, days)


@register("get_sector_list", "行业/概念板块列表及行情(涨跌幅/资金流向),可按字段自行排序", {
    "type": "object",
    "properties": {
        "sector_type": {"type": "string", "description": "concept(概念)/industry(行业),默认concept"},
    },
    "required": [],
})
async def _sectors(sector_type="concept") -> list[dict]:
    return await get_sector_list(sector_type)


@register("get_stock_belong_sectors", "反查: 某只股票属于哪些板块(股票→板块)", {
    "type": "object",
    "properties": {"stock_code": {"type": "string", "description": "股票代码"}},
    "required": ["stock_code"],
})
async def _belong(stock_code) -> list[dict]:
    return await get_stock_belong_sectors(stock_code)


# ═══════════════════ 分析报告 (1) ═══════════════════

@register("generate_stock_report", "个股综合分析报告(趋势/支撑阻力/风险等级/仓位建议)", {
    "type": "object",
    "properties": {"symbol": {"type": "string", "description": "股票代码"}},
    "required": ["symbol"],
})
async def _report(symbol) -> dict:
    return await generate_stock_report(symbol)


# ═══════════════════ MCP 生命周期 ═══════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name=n, description=i["description"], inputSchema=i["schema"])
        for n, i in TOOL_HANDLERS.items()
    ]


@server.call_tool()
async def call_tool(name, arguments) -> list[TextContent]:
    info = TOOL_HANDLERS.get(name)
    if not info:
        return [TextContent(type="text", text=f"未知工具: {name}")]
    try:
        result = await info["func"](**arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


def main():
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    asyncio.run(run())


if __name__ == "__main__":
    main()
