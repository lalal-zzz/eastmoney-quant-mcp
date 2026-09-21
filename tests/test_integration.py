"""
集成测试: 逐一验证 9 个 MCP 工具的链路是否正常。
会发起真实网络请求并写入本地数据库, 默认不随 pytest 执行。
运行: python tests/test_integration.py 或 pytest -m integration
"""
import asyncio
import traceback

import pytest

pytestmark = pytest.mark.integration

async def test_all():
    results = {}
    passed = 0
    failed = 0

    async def try_tool(name, coro, expect_key=None):
        nonlocal passed, failed
        try:
            r = await coro
            ok = r is not None
            if isinstance(r, dict) and "error" in r:
                ok = False
            if isinstance(r, list) and len(r) == 0:
                ok = True  # empty is OK for fresh DB
            if expect_key and isinstance(r, dict):
                ok = expect_key in r
            if ok:
                passed += 1
                icon = "OK"
                summary = type(r).__name__ + (f" len={len(r)}" if isinstance(r, list) else f" keys={list(r.keys())[:5] if isinstance(r, dict) else 'N/A'}")
            else:
                failed += 1
                icon = "FAIL"
                summary = str(r)[:120]
            print(f"  [{icon}] {name}: {summary}")
            results[name] = ok
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
            traceback.print_exc()
            results[name] = False

    print("=" * 60)
    print("Step 1: 数据库状态检查")
    print("=" * 60)
    await try_tool("get_data_status",
        __import__("stock_analysis_mcp.tools.data_manager", fromlist=["get_data_status"]).get_data_status(),
        expect_key="stock")

    print("\n" + "=" * 60)
    print("Step 2: 初始化数据库 (跳过成分股, 快速模式)")
    print("=" * 60)
    dm = __import__("stock_analysis_mcp.tools.data_manager", fromlist=["init_full_data"])
    await try_tool("init_full_data(include_sector_members=False)",
        dm.init_full_data(include_sector_members=False),
        expect_key="status")

    print("\n" + "=" * 60)
    print("Step 3: 验证数据库状态")
    print("=" * 60)
    await try_tool("get_data_status (after init)",
        __import__("stock_analysis_mcp.tools.data_manager", fromlist=["get_data_status"]).get_data_status(),
        expect_key="stock")

    print("\n" + "=" * 60)
    print("Step 4: screen_stocks  —— 通用查询")
    print("=" * 60)
    await try_tool("screen_stocks (全市场最新行情)",
        dm.screen_stocks(conditions={}, top_n=5, sort_by="change_pct"))
    await try_tool("screen_stocks (名称搜索'银行')",
        dm.screen_stocks(name_keyword="银行", top_n=5))
    await try_tool("screen_stocks (代码搜索'000001')",
        dm.screen_stocks(name_keyword="000001", top_n=5))
    await try_tool("screen_stocks (放量突破条件)",
        dm.screen_stocks(conditions={"min_change_pct": 3, "min_volume_ratio": 2, "max_pe": 50}, top_n=5))

    print("\n" + "=" * 60)
    print("Step 5: get_kline_local_or_net —— 下载K线+指标")
    print("=" * 60)
    await try_tool("get_kline_local_or_net(000001, days=120)",
        dm.get_kline_local_or_net("000001", days=120))

    print("\n" + "=" * 60)
    print("Step 6: generate_stock_report —— 分析报告")
    print("=" * 60)
    await try_tool("generate_stock_report(000001)",
        __import__("stock_analysis_mcp.tools.analysis", fromlist=["generate_stock_report"]).generate_stock_report("000001"),
        expect_key="basic_info")

    print("\n" + "=" * 60)
    print("Step 7: get_rank_trend_data —— 人气趋势")
    print("=" * 60)
    await try_tool("get_rank_trend_data(000001, days=10)",
        __import__("stock_analysis_mcp.tools.data_manager", fromlist=["get_rank_trend_data"]).get_rank_trend_data("000001", days=10))

    print("\n" + "=" * 60)
    print("Step 8: get_sector_list —— 板块列表")
    print("=" * 60)
    await try_tool("get_sector_list(concept)",
        __import__("stock_analysis_mcp.tools.sector_data", fromlist=["get_sector_list"]).get_sector_list("concept"))

    print("\n" + "=" * 60)
    print("Step 9: get_stock_belong_sectors —— 反查(需成分股数据)")
    print("=" * 60)
    await try_tool("get_stock_belong_sectors(000001)",
        dm.get_stock_belong_sectors("000001"))

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败 (共 {passed+failed})")
    return passed, failed

if __name__ == "__main__":
    p, f = asyncio.run(test_all())
    exit(0 if f == 0 else 1)
