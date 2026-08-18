"""
多数据源 provider 真网集成测试: 腾讯/新浪/搜狐 + 降级链端到端。
默认不随 pytest 执行: pytest -m integration
运行: python tests/test_provider_live.py
"""
import asyncio

import pytest

pytestmark = pytest.mark.integration


def test_tencent_stock_kline_daily_qfq():
    from eastmoney_quant_mcp.data.providers import tencent

    rows = tencent.fetch_stock_kline(
        "600000", limit=250, klt="101", adjust="qfq",
        start_date="20250101", end_date="20261231",
    )
    assert rows, "腾讯日K为空"
    assert len(rows) >= 200, f"条数不足: {len(rows)}"
    assert rows[0]["date"] <= rows[-1]["date"]  # 升序
    last = rows[-1]
    assert last["open"] and last["close"] and last["volume"]
    assert last["change_pct"] is not None
    print(f"  腾讯日K: {len(rows)} 根, 最新 {last['date']} close={last['close']}")


def test_tencent_stock_kline_minute():
    from eastmoney_quant_mcp.data.providers import tencent

    for klt in ("5", "60"):
        rows = tencent.fetch_stock_kline("600000", limit=100, klt=klt)
        assert rows, f"腾讯 m{klt} 为空"
        assert "datetime" in rows[0] and len(str(rows[0]["datetime"])) >= 12
        assert rows[-1]["volume"] is not None
        print(f"  腾讯 m{klt}: {len(rows)} 根, 最新 {rows[-1]['datetime']}")


def test_tencent_board_rank_and_kline():
    from eastmoney_quant_mcp.data.providers import tencent

    rank = tencent.fetch_board_rank("hy")
    assert rank, "行业排行为空"
    pt = rank[0]["code"]
    name = rank[0]["name"]
    rows = tencent.fetch_board_kline(pt, limit=60)
    assert rows, f"板块bar为空: {name}"
    # 实测限制: 腾讯板块K线只返回最新 1 根
    assert len(rows) == 1
    assert rows[0]["close"] and rows[0]["volume"]
    print(f"  腾讯板块(仅当日1根): {name}({pt}) close={rows[0]['close']}")


def test_sina_nodes_and_members():
    from eastmoney_quant_mcp.data.providers import sina

    maps = sina.get_name_node_index(refresh=True)
    assert maps["industry"], "新浪行业节点为空"
    name, node = next(iter(maps["industry"].items()))
    items = sina.fetch_sector_members(node, sector_code="BKTEST")
    assert items, f"新浪成分股为空: {name}"
    first = items[0]
    assert len(first["stock_code"]) == 6
    assert first["latest_price"] is not None
    assert first["volume"] is not None
    print(f"  新浪成分股: {name}({node}) {len(items)} 只, 样本 {first['stock_code']}")


def _sohu_fetch_with_retry(symbol, start_date, attempts=2, wait=30):
    """搜狐对高频 IP 会间歇性 503, 失败后等待重试一次"""
    import time as _time

    from eastmoney_quant_mcp.data.providers import sohu

    for i in range(attempts):
        rows = sohu.fetch_stock_kline_daily(symbol, start_date=start_date)
        if rows:
            return rows
        if i < attempts - 1:
            _time.sleep(wait)
    return []


def test_sohu_full_history_daily():
    from eastmoney_quant_mcp.data.providers import sohu

    rows = _sohu_fetch_with_retry("600000", "20240101")
    if not rows:
        pytest.skip("搜狐间歇性限流(503), 稍后重试; 解析逻辑已由单测覆盖")
    assert rows[0]["date"] <= rows[-1]["date"]  # order=A 升序
    last = rows[-1]
    assert last["amount"] and last["amount"] > 1e6  # 万元已转元
    assert last["turnover_rate"] is not None
    print(f"  搜狐日K: {len(rows)} 根, 最新 {last['date']} close={last['close']}")


def test_close_price_cross_source_consistency():
    """腾讯(qfq) vs 搜狐(不复权) 最新收盘价一致性(近期无除权时应相等)"""
    from eastmoney_quant_mcp.data.providers import tencent

    t = tencent.fetch_stock_kline("600000", limit=5, klt="101", adjust="qfq")
    s = _sohu_fetch_with_retry("600000", "20260701")
    if not s:
        pytest.skip("搜狐间歇性限流(503), 无法做跨源对照")
    assert t
    t_map = {r["date"]: r["close"] for r in t}
    s_map = {r["date"]: r["close"] for r in s}
    common = sorted(set(t_map) & set(s_map))
    assert common, "两源无共同交易日"
    diffs = [abs(t_map[d] - s_map[d]) for d in common[-3:]]
    assert all(d < 0.01 for d in diffs), f"收盘价不一致(可能有除权): {diffs}"
    print(f"  跨源收盘价一致: {common[-1]} 差异 {max(diffs):.4f}")


async def test_stock_history_chain_live():
    """完整链路: 个股日K(应命中腾讯主源)"""
    from eastmoney_quant_mcp.tools.stock_data import _stock_history_sync

    rows = _stock_history_sync("000001", "20250601", "20261231")
    assert rows, "个股K线链路为空"
    assert rows[0]["date"] >= rows[-1]["date"]  # 降序
    assert rows[0]["close"] is not None
    print(f"  个股K线链路: {len(rows)} 根, 最新 {rows[0]['date']}")


async def test_stock_kline_period_chain_live():
    from eastmoney_quant_mcp.tools.stock_data import get_stock_kline_period

    for period in ("5", "101", "102"):
        rows = await get_stock_kline_period("600000", period=period, limit=60)
        assert rows, f"多周期K线为空: klt={period}"
        key = "datetime" if period == "5" else "date"
        assert key in rows[0]
        print(f"  多周期 klt={period}: {len(rows)} 根")


async def test_sector_kline_chain_live():
    from eastmoney_quant_mcp.data import network
    from eastmoney_quant_mcp.tools.sector_data import _sector_kline_net_sync

    # 板块K线为东财单源(腾讯仅当日1根且口径不同); 东财被封时跳过
    network._provider_cooldown_until.pop("em_kline", None)
    network._provider_fail_count.pop("em_kline", None)
    items = _sector_kline_net_sync("BK0438", 30, 101, "食品饮料")
    if not items:
        # 区分"东财不可达"与"解析回归": 原始探针二次确认
        probe = network.try_kline_hosts({
            "secid": "90.BK0438", "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1", "fields2": "f51", "klt": "101", "fqt": "1",
            "end": "20500101", "lmt": "3",
        })
        if probe is None:
            pytest.skip("东财 push2his 不可达(疑似 IP 封禁), 板块K线单源不可测")
        raise AssertionError(f"板块K线解析异常: probe={probe}")
    assert items[-1]["trade_date"] and items[-1]["close"]
    print(f"  板块K线: {len(items)} 根, 最新 {items[-1]['trade_date']}")


async def test_sector_members_chain_live():
    from eastmoney_quant_mcp.tools.sector_data import get_sector_members

    items = await get_sector_members("BK0438", "食品饮料")
    assert items, "成分股链路为空"
    assert items[0]["stock_code"] and len(items[0]["stock_code"]) == 6
    priced = sum(1 for m in items if m.get("latest_price") is not None)
    assert priced >= len(items) * 0.8, f"带行情成分股比例过低: {priced}/{len(items)}"
    print(f"  成分股链路: {len(items)} 只, 带行情 {priced}")


def test_board_volume_unit_consistency():
    """板块当日量纲: 腾讯板块 bar vs 东财 clist 板块成交量应在同一数量级

    两家成分股集合不同, 聚合量有 ±20% 级差异属正常; 本测试只防
    单位量纲错误(手/股差 100 倍)。腾讯板块K线仅当日 1 根(实测限制)。
    """
    from eastmoney_quant_mcp.data.network import http_get
    from eastmoney_quant_mcp.data.providers import boardmap, tencent

    pt = boardmap.resolve_tencent_pt("BK1180", "华为海思")
    assert pt, "名称→pt 映射失败"
    t_rows = tencent.fetch_board_kline(pt, limit=5)
    assert t_rows, "腾讯板块bar为空"
    assert len(t_rows) == 1  # 实测限制: 板块仅返回最新 1 根
    t_vol = t_rows[0]["volume"]
    assert t_vol

    # 东财 clist 板块行情(未被封的 webguest 路径), 翻页找 BK1180
    em_vol = None
    for pn in range(1, 7):
        payload = http_get(
            "https://push2.eastmoney.com/webguest/api/qt/clist/get",
            params={
                "pn": str(pn), "pz": "100", "po": "0", "np": "1",
                "fltt": "2", "invt": "2",
                "ut": "8dec03ba335b81bf4ebdf7b29ec27d15",
                "fs": "m:90+t:3", "fid": "f12", "fields": "f12,f14,f5",
            }, retries=1, timeout=15,
        )
        rows = ((payload or {}).get("data") or {}).get("diff") or []
        for r in rows:
            if r.get("f12") == "BK1180":
                em_vol = r.get("f5")
                break
        if em_vol is not None or not rows:
            break
    assert em_vol, "东财 clist 未找到 BK1180 成交量"
    ratio = t_vol / em_vol
    assert 0.01 < ratio < 100, f"量纲错误(疑似手/股混淆): tencent={t_vol} em={em_vol}"
    print(f"  板块量纲同数量级: tencent={t_vol:.0f} em={em_vol:.0f} ratio={ratio:.3f}"
          f"(成分集合差异属正常)")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s", "-m", "integration"]))
