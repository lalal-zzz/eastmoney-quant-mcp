"""
Phase 5 Supplement: 补充分析剩余31个新业态板块的个股
- 排除已覆盖的15个板块(资金流入前15)
- 对剩余31个板块逐一分析成分股
- 结果追加到已有数据文件中
"""
import sys
import os
import json
import asyncio
import sqlite3
import traceback
from datetime import datetime

sys.path.insert(0, 'src')

from stock_analysis_mcp.data.storage import get_stock_db, get_sector_db, query_stock_db
from stock_analysis_mcp.tools.analysis import generate_stock_report
from stock_analysis_mcp.strategies.patterns import (
    get_key_levels, scan_universe, prepare_df, detect_patterns,
    PATTERN_NAMES, passes_filter, PATTERN_FILTERS,
)

# ── 配置 ──
MAX_STOCKS_PER_SECTOR = 30   # 每板块最多分析股票数
OUTPUT_DIR = "reports/new_business_analysis"

# 已覆盖的15个板块(不需要重复分析)
COVERED_SECTORS = {
    "AI应用", "AIGC概念", "AI智能体", "多模态AI", "跨境电商",
    "数据要素", "AI语料", "区块链", "元宇宙概念", "智谱AI概念",
    "虚拟机器人", "转基因", "基因测序", "光伏设备", "时空大数据",
}


def load_remaining_sectors() -> list[dict]:
    """加载板块列表，排除已覆盖的15个"""
    with open(os.path.join(OUTPUT_DIR, 'sector_list.json'), 'r', encoding='utf-8') as f:
        all_sectors = json.load(f)
    remaining = [s for s in all_sectors if s["sector_name"] not in COVERED_SECTORS]
    return remaining


def get_sector_members_from_db(sector_code: str) -> list[dict]:
    """从本地板块数据库获取成分股"""
    db_path = get_sector_db()
    try:
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT stock_code, stock_name FROM sector_member WHERE sector_code = ?",
                (sector_code,)
            ).fetchall()
            return [{"stock_code": r["stock_code"], "stock_name": r["stock_name"]} for r in rows]
    except Exception as e:
        print(f"  [warn] 查询成分股失败 {sector_code}: {e}")
        return []


def has_local_kline(symbol: str) -> bool:
    """检查股票是否有本地K线数据"""
    try:
        rows = query_stock_db(
            "SELECT COUNT(*) as cnt FROM stock_kline WHERE symbol = ? AND adjust_type='qfq'",
            (symbol,)
        )
        return rows[0]["cnt"] >= 20 if rows else False
    except Exception:
        return False


def get_stocks_with_kline(members: list[dict], max_count: int = MAX_STOCKS_PER_SECTOR) -> list[dict]:
    """筛选有本地K线数据的股票"""
    result = []
    for m in members:
        code = m["stock_code"]
        if has_local_kline(code):
            result.append(m)
            if len(result) >= max_count:
                break
    return result


def _is_good_trend(report: dict) -> bool:
    """判断报告中的股票是否趋势较好"""
    trend = report.get("trend_analysis", {})
    direction = trend.get("direction", "")
    arrangement = trend.get("arrangement", "")
    if "多头排列" in arrangement:
        return True
    if "强势上扬" in direction or "企稳回升" in direction:
        return True
    if "偏多" in arrangement:
        return True
    return False


async def analyze_sector_stocks(sectors: list[dict]) -> tuple[list, list, list, dict]:
    """分析各板块成分股，返回 (all_reports, key_levels_results, rising_stocks, stats)"""
    all_reports = []
    key_levels_results = []
    rising_stocks = []
    stats = {}  # sector_name -> {total, analyzed, bullish}

    total_sectors = len(sectors)
    total_stocks_analyzed = 0

    for si, sector in enumerate(sectors, 1):
        code = sector["sector_code"]
        name = sector["sector_name"]
        inflow = sector.get("main_net_inflow", 0) or 0

        print(f"\n[{si}/{total_sectors}] 板块: {name} ({code}) 主力净流入: {inflow/1e8:+.2f}亿")

        # Step 1: 获取成分股
        members = get_sector_members_from_db(code)
        print(f"  成分股总数: {len(members)}")

        sector_stat = {"total_members": len(members), "analyzed": 0, "bullish": 0, "skipped": False}

        if not members:
            print("  无成分股数据，跳过")
            sector_stat["skipped"] = True
            stats[name] = sector_stat
            continue

        # Step 2: 筛选有本地K线数据的
        stocks = get_stocks_with_kline(members, MAX_STOCKS_PER_SECTOR)
        print(f"  有本地K线数据: {len(stocks)} 只 (分析上限: {MAX_STOCKS_PER_SECTOR})")

        if not stocks:
            print("  无可用K线数据，跳过")
            sector_stat["skipped"] = True
            stats[name] = sector_stat
            continue

        # Step 3: 生成技术分析报告
        sector_reports = []
        for j, stock in enumerate(stocks, 1):
            sym = stock["stock_code"]
            sname = stock["stock_name"]
            try:
                report = await generate_stock_report(sym)
                if "error" in report:
                    print(f"    [{j}/{len(stocks)}] {sname}({sym}): {report['error']}")
                    continue

                report["sector_code"] = code
                report["sector_name"] = name
                report["sector_inflow"] = inflow

                sector_reports.append(report)
                total_stocks_analyzed += 1
                sector_stat["analyzed"] += 1

                trend = report.get("trend_analysis", {})
                direction = trend.get("direction", "未知")
                arrangement = trend.get("arrangement", "未知")
                macd_sig = report.get("technical_indicators", {}).get("MACD", {}).get("signal", "")

                print(f"    [{j}/{len(stocks)}] {sname}({sym}): {direction} | {arrangement} | MACD:{macd_sig}")

            except Exception as e:
                print(f"    [{j}/{len(stocks)}] {sname}({sym}): 错误 - {e}")

        all_reports.extend(sector_reports)

        # Step 4: 对趋势好的股票获取关键位
        good_reports = [r for r in sector_reports if _is_good_trend(r)]
        sector_stat["bullish"] = len(good_reports)
        print(f"  趋势较好的股票: {len(good_reports)} 只")

        for r in good_reports:
            sym = r["basic_info"]["symbol"]
            sname = r["basic_info"]["name"]
            try:
                kl = get_key_levels("stocks", sym)
                kl["sector_code"] = code
                kl["sector_name"] = name
                key_levels_results.append(kl)
                trend_cn = kl.get("trend_cn", "未知")
                support_count = len(kl.get("support", []))
                print(f"    关键位 {sname}({sym}): {trend_cn}, 支撑位{support_count}个")
            except Exception as e:
                print(f"    关键位 {sname}({sym}): 错误 - {e}")

        stats[name] = sector_stat

    print(f"\n{'='*60}")
    print(f"分析完成: {total_sectors}个板块, {total_stocks_analyzed}只个股")
    return all_reports, key_levels_results, rising_stocks, stats


async def scan_rising_patterns(stock_symbols: list[str]) -> list[dict]:
    """对指定股票列表进行五类上涨形态扫描"""
    if not stock_symbols:
        return []

    print(f"\n{'='*60}")
    print(f"五类上涨形态扫描: {len(stock_symbols)} 只股票")
    print(f"{'='*60}")

    try:
        sigs = scan_universe(
            "stocks",
            symbols=stock_symbols,
            patterns=list(PATTERN_NAMES.keys()),
            workers=4,
            progress=True,
            min_score=0.6,
        )
        return sigs
    except Exception as e:
        print(f"形态扫描出错: {e}")
        traceback.print_exc()
        return []


def build_rising_stocks(all_reports: list, pattern_sigs: list) -> list:
    """构建 rising_stocks 列表"""
    rising_stocks = []

    sig_by_symbol = {}
    for sig in pattern_sigs:
        sym = sig.get("symbol", "")
        if sym not in sig_by_symbol:
            sig_by_symbol[sym] = []
        sig_by_symbol[sym].append(sig)

    report_by_symbol = {}
    for r in all_reports:
        if "basic_info" in r:
            sym = r["basic_info"]["symbol"]
            report_by_symbol[sym] = r

    for sym, sigs in sig_by_symbol.items():
        r = report_by_symbol.get(sym, {})
        bi = r.get("basic_info", {})
        for sig in sigs:
            rising_stocks.append({
                "symbol": sym,
                "name": bi.get("name", sig.get("name", "")),
                "sector_code": r.get("sector_code", ""),
                "sector_name": r.get("sector_name", ""),
                "pattern": sig["pattern"],
                "pattern_cn": sig.get("pattern_cn", ""),
                "variant": sig.get("variant", ""),
                "score": sig.get("score", 0),
                "close": sig.get("close"),
                "date": sig.get("date"),
                "trend": sig.get("trend", ""),
                "filter_pass": sig.get("filter_pass", False),
                "key_level_name": sig.get("key_level_name", ""),
                "key_level_value": sig.get("key_level_value"),
                "potential_gain": sig.get("potential_gain"),
            })

    # 多头排列的股票
    for r in all_reports:
        if "basic_info" not in r:
            continue
        sym = r["basic_info"]["symbol"]
        if sym in sig_by_symbol:
            continue
        trend = r.get("trend_analysis", {})
        arrangement = trend.get("arrangement", "")
        if "多头排列" in arrangement:
            rising_stocks.append({
                "symbol": sym,
                "name": r["basic_info"].get("name", ""),
                "sector_code": r.get("sector_code", ""),
                "sector_name": r.get("sector_name", ""),
                "pattern": "ma_bullish_alignment",
                "pattern_cn": "多头排列",
                "variant": arrangement,
                "score": 0,
                "close": r["basic_info"].get("latest_price"),
                "date": r.get("report_date"),
                "trend": "up",
                "filter_pass": True,
                "key_level_name": "",
                "key_level_value": None,
                "potential_gain": None,
            })

    rising_stocks.sort(key=lambda x: x.get("score", 0), reverse=True)
    return rising_stocks


def build_report_summaries(all_reports: list) -> list:
    """构建报告摘要"""
    summaries = []
    for r in all_reports:
        if "basic_info" not in r:
            continue
        bi = r["basic_info"]
        trend = r.get("trend_analysis", {})
        ind = r.get("technical_indicators", {})
        risk = r.get("risk_assessment", {})
        pos = r.get("position_advice", {})
        sr = r.get("support_resistance", {})
        summaries.append({
            "symbol": bi.get("symbol"),
            "name": bi.get("name"),
            "latest_price": bi.get("latest_price"),
            "change_pct": bi.get("change_pct"),
            "sector_code": r.get("sector_code"),
            "sector_name": r.get("sector_name"),
            "sector_inflow": r.get("sector_inflow"),
            "trend_direction": trend.get("direction"),
            "trend_arrangement": trend.get("arrangement"),
            "recent_changes": trend.get("recent_changes"),
            "ma_status": trend.get("ma_status"),
            "rsi": ind.get("RSI", {}).get("value"),
            "rsi_status": ind.get("RSI", {}).get("status"),
            "macd_signal": ind.get("MACD", {}).get("signal"),
            "macd_dif": ind.get("MACD", {}).get("DIF"),
            "kdj_status": ind.get("KDJ", {}).get("status"),
            "boll_position": ind.get("BOLL", {}).get("position"),
            "risk_level": risk.get("level"),
            "risk_items": risk.get("items"),
            "position_suggestion": pos.get("suggestion"),
            "position_pct": pos.get("position_pct"),
            "stop_loss": pos.get("stop_loss"),
            "take_profit": pos.get("take_profit"),
            "risk_reward_ratio": pos.get("risk_reward_ratio"),
            "supports": sr.get("supports"),
            "resistances": sr.get("resistances"),
            "report_date": r.get("report_date"),
        })
    return summaries


def merge_json_file(filepath: str, new_data: list) -> tuple[list, int]:
    """合并JSON文件: 读取已有数据 + 追加新数据 + 去重 + 保存"""
    existing = []
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    # 去重: 对 stock_reports 按 symbol+sector_code 去重; 对 rising_stocks 按 symbol+sector_code+pattern 去重
    existing_keys = set()
    for item in existing:
        if "pattern" in item:
            key = (item.get("symbol"), item.get("sector_code"), item.get("pattern"))
        else:
            key = (item.get("symbol"), item.get("sector_code"))
        existing_keys.add(key)

    added = 0
    for item in new_data:
        if "pattern" in item:
            key = (item.get("symbol"), item.get("sector_code"), item.get("pattern"))
        else:
            key = (item.get("symbol"), item.get("sector_code"))
        if key not in existing_keys:
            existing.append(item)
            existing_keys.add(key)
            added += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, default=str)

    return existing, added


async def main():
    print("=" * 60)
    print("Phase 5 Supplement: 补充分析剩余31个新业态板块")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1: 加载剩余板块 ──
    print("\n[Step 1] 加载剩余板块(排除已覆盖15个)...")
    remaining_sectors = load_remaining_sectors()
    print(f"  需要分析的板块: {len(remaining_sectors)} 个")
    for i, s in enumerate(remaining_sectors, 1):
        inflow = (s.get("main_net_inflow") or 0) / 1e8
        print(f"  {i:3d}. [{s['sector_code']}] {s['sector_name']:20s} 净流入: {inflow:+8.2f}亿")

    # ── Step 2-4: 分析成分股 ──
    print(f"\n[Step 2-4] 成分股技术分析与关键位获取...")
    all_reports, key_levels_results, _, sector_stats = await analyze_sector_stocks(remaining_sectors)

    # ── Step 4b: 五类上涨形态扫描 ──
    all_symbols = list(set(r["basic_info"]["symbol"] for r in all_reports if "basic_info" in r))
    print(f"\n已分析 {len(all_symbols)} 只不重复个股")

    pattern_sigs = await scan_rising_patterns(all_symbols)
    print(f"\n五类上涨形态信号: {len(pattern_sigs)} 个")

    # ── 构建 rising_stocks ──
    new_rising = build_rising_stocks(all_reports, pattern_sigs)

    # ── 构建 report summaries ──
    new_summaries = build_report_summaries(all_reports)

    # ── Step 5: 合并保存结果 ──
    print(f"\n[Step 5] 合并保存结果...")

    # 合并 stock_reports.json
    reports_path = os.path.join(OUTPUT_DIR, "stock_reports.json")
    merged_reports, added_reports = merge_json_file(reports_path, new_summaries)
    print(f"  成分股报告: {reports_path}")
    print(f"    新增 {len(new_summaries)} 条, 去重后实际新增 {added_reports} 条, 合并后总计 {len(merged_reports)} 条")

    # 合并 key_levels.json
    kl_path = os.path.join(OUTPUT_DIR, "key_levels.json")
    # key_levels 去重按 symbol
    existing_kl = []
    if os.path.exists(kl_path):
        with open(kl_path, 'r', encoding='utf-8') as f:
            existing_kl = json.load(f)
    existing_kl_symbols = set(item.get("symbol") for item in existing_kl)
    added_kl = 0
    for kl in key_levels_results:
        if kl.get("symbol") not in existing_kl_symbols:
            existing_kl.append(kl)
            existing_kl_symbols.add(kl.get("symbol"))
            added_kl += 1
    with open(kl_path, 'w', encoding='utf-8') as f:
        json.dump(existing_kl, f, ensure_ascii=False, indent=2, default=str)
    print(f"  关键位分析: {kl_path}")
    print(f"    新增 {len(key_levels_results)} 条, 去重后实际新增 {added_kl} 条, 合并后总计 {len(existing_kl)} 条")

    # 合并 rising_stocks.json
    rising_path = os.path.join(OUTPUT_DIR, "rising_stocks.json")
    merged_rising, added_rising = merge_json_file(rising_path, new_rising)
    print(f"  上涨形态个股: {rising_path}")
    print(f"    新增 {len(new_rising)} 条, 去重后实际新增 {added_rising} 条, 合并后总计 {len(merged_rising)} 条")

    # 合并 pattern_signals_stocks.json
    sigs_path = os.path.join(OUTPUT_DIR, "pattern_signals_stocks.json")
    existing_sigs = []
    if os.path.exists(sigs_path):
        with open(sigs_path, 'r', encoding='utf-8') as f:
            existing_sigs = json.load(f)
    existing_sigs_keys = set((s.get("symbol"), s.get("pattern")) for s in existing_sigs)
    added_sigs = 0
    for sig in pattern_sigs:
        key = (sig.get("symbol"), sig.get("pattern"))
        if key not in existing_sigs_keys:
            existing_sigs.append(sig)
            existing_sigs_keys.add(key)
            added_sigs += 1
    with open(sigs_path, 'w', encoding='utf-8') as f:
        json.dump(existing_sigs, f, ensure_ascii=False, indent=2, default=str)
    print(f"  形态扫描信号: {sigs_path}")
    print(f"    新增 {len(pattern_sigs)} 条, 去重后实际新增 {added_sigs} 条, 合并后总计 {len(existing_sigs)} 条")

    # ── 汇总报告 ──
    print(f"\n{'='*60}")
    print("Phase 5 Supplement 分析汇总")
    print(f"{'='*60}")
    print(f"目标板块数: {len(remaining_sectors)}")
    actual_analyzed = sum(1 for s in sector_stats.values() if not s.get("skipped"))
    print(f"实际分析板块数: {actual_analyzed}")
    print(f"新增分析报告数: {len(new_summaries)}")
    print(f"新增关键位分析数: {len(key_levels_results)}")
    print(f"新增上涨形态个股: {len(new_rising)}")
    print(f"\n合并后文件总记录数:")
    print(f"  stock_reports.json: {len(merged_reports)} 条")
    print(f"  key_levels.json: {len(existing_kl)} 条")
    print(f"  rising_stocks.json: {len(merged_rising)} 条")
    print(f"  pattern_signals_stocks.json: {len(existing_sigs)} 条")

    # 各板块统计
    print(f"\n各板块覆盖情况:")
    print(f"{'板块名称':<20s} {'成分股':>6s} {'已分析':>6s} {'多头/强势':>8s} {'状态':>6s}")
    print("-" * 55)
    for name, st in sorted(sector_stats.items(), key=lambda x: -x[1]["analyzed"]):
        status = "跳过" if st.get("skipped") else "完成"
        print(f"  {name:<18s} {st['total_members']:>6d} {st['analyzed']:>6d} {st['bullish']:>8d} {status:>6s}")

    # 新增上涨形态明细
    if new_rising:
        print(f"\n新增上涨形态个股明细(前50):")
        for i, rs in enumerate(new_rising[:50], 1):
            score_str = f"score={rs['score']:.3f}" if rs.get("score") else ""
            print(f"  {i:3d}. {rs['name']}({rs['symbol']}) [{rs['sector_name']}] "
                  f"{rs['pattern_cn']} {rs.get('variant','')} {score_str}")

    print(f"\n保存文件:")
    print(f"  1. {reports_path}")
    print(f"  2. {kl_path}")
    print(f"  3. {rising_path}")
    print(f"  4. {sigs_path}")
    print(f"\n完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
