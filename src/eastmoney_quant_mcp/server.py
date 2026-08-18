"""
东方财富量化 MCP Server — 精简入口
暴露 14 个核心工具: 10 个数据/分析工具 + 4 个形态工具 (scan_patterns / scan_sector_patterns /
get_pattern_history / get_key_levels, 同步函数经 asyncio.to_thread 包装)。
其余逻辑由 Skill 组合实现。
"""

import asyncio
import json
from datetime import datetime, timezone

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
from .tools.stock_data import get_stock_kline_period
from .strategies.patterns import (
    scan_universe,
    get_pattern_history,
    get_key_levels,
)

server = Server("eastmoney-quant-mcp")

TOOL_HANDLERS = {}


def register(name, description, input_schema):
    def decorator(func):
        TOOL_HANDLERS[name] = {"func": func, "description": description, "schema": input_schema}
        return func
    return decorator


# ═══════════════════ 数据管理 (3) ═══════════════════

@register("init_full_data", (
    "一次性下载数据到本地SQLite(首次必调)。quick=true为快速模式(秒级): 仅股票列表+实时行情+人气排名, "
    "板块成分股在首次使用时自动下载缓存; quick=false为完整模式(含全部板块K线+成分股, 约1-2分钟)"
), {
    "type": "object",
    "properties": {
        "include_sector_members": {"type": "boolean", "description": "是否下载板块成分股(完整模式下耗时但完整),默认true"},
        "quick": {"type": "boolean", "description": "快速初始化模式(秒级可用),默认false"},
    },
    "required": [],
})
async def _init(include_sector_members=True, quick=False) -> dict:
    return await init_full_data(include_sector_members, quick)


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
        "days": {"type": "integer", "minimum": 1, "description": "默认250个交易日"},
        "adjust": {"type": "string", "enum": ["qfq", "hfq", ""], "description": "复权方式: qfq前复权/hfq后复权/空字符串不复权, 默认qfq"},
    },
    "required": ["symbol"],
})
async def _kline(symbol, days=250, adjust="qfq") -> list[dict]:
    return await get_kline_local_or_net(symbol, days, adjust)


@register("get_stock_kline_period", (
    "个股多周期K线(纯网络实时): 1/5/15/30/60分钟线, 101日线, 102周线, 103月线。"
    "与 get_kline_local_or_net(仅日线+本地缓存)互补, 适合盘中看分时结构"
), {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "description": "股票代码"},
        "period": {"type": "string", "enum": ["1", "5", "15", "30", "60", "101", "102", "103"],
                   "description": "周期: 1/5/15/30/60(分钟) 101(日) 102(周) 103(月), 默认60"},
        "limit": {"type": "integer", "minimum": 1, "description": "返回条数,默认240"},
        "adjust": {"type": "string", "enum": ["qfq", "hfq", ""], "description": "复权方式, 默认qfq"},
    },
    "required": ["symbol"],
})
async def _kline_period(symbol, period="60", limit=240, adjust="qfq") -> list[dict]:
    return await get_stock_kline_period(symbol, period, limit, adjust)


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
        "sector_type": {"type": "string", "enum": ["concept", "industry"], "description": "concept(概念)/industry(行业),默认concept"},
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


# ═══════════════════ 形态识别 (4) ═══════════════════

_PATTERN_SCHEMA_COMMON = {
    "date": {"type": "string", "description": "扫描日期(YYYY-MM-DD), 默认本地库最新交易日"},
    "patterns": {
        "type": "array", "items": {"type": "string"},
        "description": "形态列表: trend_pullback/ma_rebound/w_bottom/m_neckline/box_breakout, 默认全部",
    },
    "min_score": {"type": "number", "minimum": 0, "maximum": 1, "description": "形态标准度阈值, 默认0.6"},
    "workers": {"type": "integer", "minimum": 1, "description": "并发线程数, 默认8"},
}


@register("scan_patterns", (
    "股票形态扫描: 全市场或指定股票, 识别五类上涨形态(趋势回调企稳/下跌均线反弹/W底/M形颈线/"
    "平台放量突破), 输出信号含评分/关键点位/共振/因子; strict=true 只留优中选优档信号"
), {
    "type": "object",
    "properties": {
        **_PATTERN_SCHEMA_COMMON,
        "strict": {"type": "boolean", "description": "只返回 strict 档(优中选优)信号, 默认false"},
        "no_filter": {"type": "boolean", "description": "不过滤(返回全部原始信号), 默认false"},
        "symbols": {
            "type": "array", "items": {"type": "string"},
            "description": "指定股票代码/名称列表(省略=全市场扫描)",
        },
    },
    "required": [],
})
async def _scan_patterns(date=None, patterns=None, min_score=0.6, workers=8,
                          strict=False, no_filter=False, symbols=None) -> list[dict]:
    return await asyncio.to_thread(
        scan_universe, "stocks", date=date, patterns=patterns,
        strict=strict, no_filter=no_filter, workers=workers, symbols=symbols,
        min_score=min_score)


@register("scan_sector_patterns", (
    "板块形态扫描: 概念/行业板块全量或指定板块, 识别与股票同一套五类形态(板块指数K线, "
    "历史不足260根K线的板块自动跳过), 输出信号含评分/关键点位/共振/因子"
), {
    "type": "object",
    "properties": {
        **_PATTERN_SCHEMA_COMMON,
        "sector_type": {"type": "string", "enum": ["concept", "industry"],
                        "description": "板块类型: concept(概念)/industry(行业), 默认全部"},
        "symbols": {
            "type": "array", "items": {"type": "string"},
            "description": "指定板块代码/名称列表(如 BK1090/1090/人工智能, 省略=全板块扫描)",
        },
    },
    "required": [],
})
async def _scan_sector_patterns(date=None, patterns=None, min_score=0.6, workers=8,
                                 sector_type=None, symbols=None) -> list[dict]:
    return await asyncio.to_thread(
        scan_universe, "sectors", date=date, patterns=patterns,
        workers=workers, symbols=symbols, sector_type=sector_type,
        min_score=min_score)


@register("get_pattern_history", "单标的(股票/板块)历史形态信号列表, 按日期升序", {
    "type": "object",
    "properties": {
        "universe": {"type": "string", "enum": ["stocks", "sectors"],
                      "description": "标的宇宙: stocks(股票)/sectors(板块), 默认stocks"},
        "symbol": {"type": "string", "description": "股票代码或板块代码(支持 BK1090/1090/名称)"},
        "start": {"type": "string", "description": "起始日期, 默认2010-01-01"},
        "end": {"type": "string", "description": "截止日期, 默认最新"},
        "patterns": {
            "type": "array", "items": {"type": "string"},
            "description": "形态列表, 默认全部",
        },
        "min_score": {"type": "number", "minimum": 0, "maximum": 1, "description": "形态标准度阈值, 默认0.6"},
    },
    "required": ["symbol"],
})
async def _pattern_history(universe="stocks", symbol=None, start=None, end=None,
                           patterns=None, min_score=0.6) -> list[dict]:
    return await asyncio.to_thread(
        get_pattern_history, universe, symbol, start=start, end=end,
        patterns=patterns, min_score=min_score)


@register("get_key_levels", "单标的(股票/板块)当前关键位: MA体系/斐波那契回调位/结构位(前高前低)+趋势判定", {
    "type": "object",
    "properties": {
        "universe": {"type": "string", "enum": ["stocks", "sectors"],
                      "description": "标的宇宙: stocks(股票)/sectors(板块), 默认stocks"},
        "symbol": {"type": "string", "description": "股票代码或板块代码(支持 BK1090/1090/名称)"},
    },
    "required": ["symbol"],
})
async def _key_levels(universe="stocks", symbol=None) -> dict:
    return await asyncio.to_thread(get_key_levels, universe, symbol)


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
        envelope = {
            "data": result,
            "meta": {
                "source": "eastmoney-quant",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "cache_status": "unknown",
            },
            "warnings": [],
            "error": None,
        }
        return [TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"data": None, "meta": {}, "warnings": [], "error": {"code": "TOOL_ERROR", "message": str(e)}}, ensure_ascii=False))]


def main():
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    asyncio.run(run())


if __name__ == "__main__":
    main()
