"""快速冒烟测试 - 验证 9 个工具链路

手动运行: python tests/test_smoke.py
(会发起真实网络请求, 不随 pytest 自动执行)
"""
import asyncio

async def smoke():
    from stock_analysis_mcp.tools.data_manager import (
        get_data_status, screen_stocks, get_kline_local_or_net,
        get_rank_trend_data, get_stock_belong_sectors,
    )
    from stock_analysis_mcp.tools.sector_data import get_sector_list
    from stock_analysis_mcp.tools.analysis import generate_stock_report

    # 1. status
    s = await get_data_status()
    print(f'[OK] status: stock_cnt={s["stock"]["count"]}, sector_cnt={s["sector"]["count"]}')

    # 2. sector list (network)
    secs = await get_sector_list("concept")
    print(f'[OK] get_sector_list: {len(secs)} sectors')

    # 3. screen (local)
    r = await screen_stocks(name_keyword="000001", top_n=5)
    if not r:
        print("[SKIP] screen_stocks: DB empty, run init_full_data first")
        return
    print(f'[OK] screen_stocks(000001): {r[0]["name"]} price={r[0]["latest_price"]}')

    # 4-5. kline + report
    k = await get_kline_local_or_net("000001", days=30)
    print(f'[OK] kline: {len(k)} days')
    rep = await generate_stock_report("000001")
    print(f'[OK] report: trend={rep.get("trend_analysis",{}).get("direction")}')

    # 6-7. rank + sectors
    rt = await get_rank_trend_data("000001", days=10)
    print(f'[OK] rank_trend: {len(rt)} entries')
    b = await get_stock_belong_sectors("000001")
    print(f'[OK] belong_sectors: {len(b)} sectors' if b else '[SKIP] belong_sectors: no data')

    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(smoke())
