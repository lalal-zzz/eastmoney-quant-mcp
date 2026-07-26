"""
板块选择工具: 基于板块行情和资金流向筛选强势板块
"""

from .sector_data import get_sector_list, get_sector_members


async def screen_top_sectors(
    sector_type: str = "concept", top_n: int = 20, sort_by: str = "change_pct"
) -> list[dict]:
    """筛选强势板块(按涨跌幅/主力净流入排序)"""
    sectors = await get_sector_list(sector_type)
    if not sectors:
        return []

    valid = [s for s in sectors if s.get(sort_by) is not None]
    valid.sort(key=lambda x: x.get(sort_by) or 0, reverse=True)
    return valid[:top_n]


async def screen_main_inflow_sectors(
    sector_type: str = "concept", top_n: int = 20
) -> list[dict]:
    """筛选主力资金净流入最多的板块"""
    sectors = await get_sector_list(sector_type)
    if not sectors:
        return []

    valid = [s for s in sectors if s.get("main_net_inflow") is not None]
    valid.sort(key=lambda x: x.get("main_net_inflow") or 0, reverse=True)
    return valid[:top_n]


async def screen_sector_with_leaders(
    sector_type: str = "concept", top_n: int = 10, member_count: int = 10
) -> list[dict]:
    """筛选强势板块并返回龙头成分股"""
    top_sectors = await screen_top_sectors(sector_type, top_n)

    results = []
    for sec in top_sectors:
        code = sec.get("sector_code", "")
        members = await get_sector_members(code)
        leaders = sorted(
            members,
            key=lambda x: x.get("change_pct") or -999,
            reverse=True,
        )[:member_count]

        results.append({
            "sector_code": sec["sector_code"],
            "sector_name": sec["sector_name"],
            "change_pct": sec.get("change_pct"),
            "main_net_inflow": sec.get("main_net_inflow"),
            "main_net_pct": sec.get("main_net_pct"),
            "lead_stock_name": sec.get("lead_stock_name"),
            "lead_stock_code": sec.get("lead_stock_code"),
            "top_members": [
                {
                    "stock_code": m.get("stock_code"),
                    "stock_name": m.get("stock_name"),
                    "change_pct": m.get("change_pct"),
                    "latest_price": m.get("latest_price"),
                }
                for m in leaders
            ],
        })

    return results


async def screen_sector_by_capital_flow(
    sector_type: str = "concept",
    min_large_net: float = 0,
    top_n: int = 20,
) -> list[dict]:
    """按大单净流入筛选板块"""
    sectors = await get_sector_list(sector_type)
    if not sectors:
        return []

    valid = [
        s for s in sectors
        if s.get("large_net") is not None and (s.get("large_net") or 0) >= min_large_net
    ]
    valid.sort(key=lambda x: x.get("large_net") or 0, reverse=True)
    return valid[:top_n]


async def get_full_sector_analysis(
    sector_code: str, member_limit: int = 30
) -> dict:
    """获取板块综合分析: 行情 + 成分股 + 资金流向"""
    sectors = await get_sector_list("concept")
    sectors += await get_sector_list("industry")

    sector_info = None
    for s in sectors:
        if s.get("sector_code") == sector_code:
            sector_info = s
            break

    if not sector_info:
        return {"error": f"未找到板块 {sector_code}"}

    members = await get_sector_members(sector_code)

    gainers = [m for m in members if m.get("change_pct") and m["change_pct"] > 0]
    losers = [m for m in members if m.get("change_pct") and m["change_pct"] <= 0]

    sorted_members = sorted(
        members, key=lambda x: x.get("change_pct") or -999, reverse=True
    )[:member_limit]

    return {
        "sector_code": sector_info["sector_code"],
        "sector_name": sector_info["sector_name"],
        "sector_type": sector_info.get("sector_type"),
        "latest_index": sector_info.get("latest_index"),
        "change_pct": sector_info.get("change_pct"),
        "main_net_inflow": sector_info.get("main_net_inflow"),
        "main_net_pct": sector_info.get("main_net_pct"),
        "super_large_net": sector_info.get("super_large_net"),
        "large_net": sector_info.get("large_net"),
        "medium_net": sector_info.get("medium_net"),
        "small_net": sector_info.get("small_net"),
        "lead_stock_name": sector_info.get("lead_stock_name"),
        "lead_stock_code": sector_info.get("lead_stock_code"),
        "member_count": len(members),
        "gainer_count": len(gainers),
        "loser_count": len(losers),
        "members": [
            {
                "stock_code": m.get("stock_code"),
                "stock_name": m.get("stock_name"),
                "latest_price": m.get("latest_price"),
                "change_pct": m.get("change_pct"),
                "volume_ratio": m.get("volume_ratio"),
                "turnover_rate": m.get("turnover_rate"),
                "pe_dynamic": m.get("pe_dynamic"),
                "pb": m.get("pb"),
            }
            for m in sorted_members
        ],
    }
