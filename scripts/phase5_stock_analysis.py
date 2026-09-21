"""
Phase 5: 新业态板块个股深度分析
- Step 1: 获取资金流入前15板块的成分股
- Step 2: 对有本地K线数据的成分股生成技术分析报告
- Step 3: 对高评分股票获取关键位分析
- Step 4: 筛选符合上涨形态的个股
- Step 5: 保存结果
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
TOP_SECTORS_COUNT = 15       # 资金流入前N板块
MAX_STOCKS_PER_SECTOR = 20   # 每板块最多分析股票数
OUTPUT_DIR = "reports/new_business_analysis"


def load_sector_data():
    """加载板块列表和资金流向数据"""
    with open('reports/new_business_analysis/capital_flow.json', 'r', encoding='utf-8') as f:
        capital_flow = json.load(f)
    # 按主力净流入排序，取前N
    capital_flow.sort(key=lambda x: x.get("main_net_inflow") or 0, reverse=True)
    return capital_flow[:TOP_SECTORS_COUNT]


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
    """筛选有本地K线数据的股票，最多返回max_count只"""
    result = []
    for m in members:
        code = m["stock_code"]
        if has_local_kline(code):
            result.append(m)
            if len(result) >= max_count:
                break
    return result


async def analyze_sector_stocks(top_sectors: list[dict]) -> tuple[list, list, list]:
    """分析各板块成分股，返回 (all_reports, key_levels_results, rising_stocks)"""
    all_reports = []
    key_levels_results = []
    rising_stocks = []
    
    total_sectors = len(top_sectors)
    total_stocks_analyzed = 0
    
    for si, sector in enumerate(top_sectors, 1):
        code = sector["sector_code"]
        name = sector["sector_name"]
        inflow = sector.get("main_net_inflow", 0) or 0
        
        print(f"\n[{si}/{total_sectors}] 板块: {name} ({code}) 主力净流入: {inflow/1e8:+.2f}亿")
        
        # Step 1: 获取成分股
        members = get_sector_members_from_db(code)
        print(f"  成分股总数: {len(members)}")
        
        if not members:
            print("  无成分股数据，跳过")
            continue
        
        # Step 2: 筛选有本地K线数据的
        stocks = get_stocks_with_kline(members, MAX_STOCKS_PER_SECTOR)
        print(f"  有本地K线数据: {len(stocks)} 只 (分析上限: {MAX_STOCKS_PER_SECTOR})")
        
        if not stocks:
            print("  无可用K线数据，跳过")
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
                
                # 附加板块信息
                report["sector_code"] = code
                report["sector_name"] = name
                report["sector_inflow"] = inflow
                
                sector_reports.append(report)
                total_stocks_analyzed += 1
                
                # 简要输出
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
    
    print(f"\n{'='*60}")
    print(f"分析完成: {total_sectors}个板块, {total_stocks_analyzed}只个股")
    return all_reports, key_levels_results, rising_stocks


def _is_good_trend(report: dict) -> bool:
    """判断报告中的股票是否趋势较好"""
    trend = report.get("trend_analysis", {})
    direction = trend.get("direction", "")
    arrangement = trend.get("arrangement", "")
    
    # 多头排列或强势上扬
    if "多头排列" in arrangement:
        return True
    if "强势上扬" in direction or "企稳回升" in direction:
        return True
    if "偏多" in arrangement:
        return True
    return False


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


async def main():
    print("=" * 60)
    print("Phase 5: 新业态板块个股深度分析")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # ── Step 1: 加载板块数据 ──
    print("\n[Step 1] 加载资金流入前15板块...")
    top_sectors = load_sector_data()
    for i, s in enumerate(top_sectors, 1):
        inflow = (s.get("main_net_inflow") or 0) / 1e8
        print(f"  {i:3d}. [{s['sector_code']}] {s['sector_name']:20s} 净流入: {inflow:+8.2f}亿")
    
    # ── Step 2-4: 分析成分股 ──
    print("\n[Step 2-4] 成分股技术分析与关键位获取...")
    all_reports, key_levels_results, _ = await analyze_sector_stocks(top_sectors)
    
    # ── Step 4b: 五类上涨形态扫描 ──
    # 收集所有分析过的股票代码
    all_symbols = list(set(r["basic_info"]["symbol"] for r in all_reports if "basic_info" in r))
    print(f"\n已分析 {len(all_symbols)} 只不重复个股")
    
    # 形态扫描
    pattern_sigs = await scan_rising_patterns(all_symbols)
    print(f"\n五类上涨形态信号: {len(pattern_sigs)} 个")
    
    # ── 构建 rising_stocks ──
    rising_stocks = []
    
    # 从形态信号构建
    sig_by_symbol = {}
    for sig in pattern_sigs:
        sym = sig.get("symbol", "")
        if sym not in sig_by_symbol:
            sig_by_symbol[sym] = []
        sig_by_symbol[sym].append(sig)
    
    # 从报告中提取板块归属
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
    
    # 也从趋势报告中添加多头排列的股票
    for r in all_reports:
        if "basic_info" not in r:
            continue
        sym = r["basic_info"]["symbol"]
        if sym in sig_by_symbol:
            continue  # 已有形态信号
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
    
    # 按score降序排
    rising_stocks.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # ── Step 5: 保存结果 ──
    print(f"\n[Step 5] 保存结果...")
    
    # 保存成分股分析报告 (只保存摘要，避免文件过大)
    report_summaries = []
    for r in all_reports:
        if "basic_info" not in r:
            continue
        bi = r["basic_info"]
        trend = r.get("trend_analysis", {})
        ind = r.get("technical_indicators", {})
        risk = r.get("risk_assessment", {})
        pos = r.get("position_advice", {})
        sr = r.get("support_resistance", {})
        report_summaries.append({
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
    
    reports_path = os.path.join(OUTPUT_DIR, "stock_reports.json")
    with open(reports_path, "w", encoding="utf-8") as f:
        json.dump(report_summaries, f, ensure_ascii=False, indent=2, default=str)
    print(f"  成分股报告: {reports_path} ({len(report_summaries)} 条)")
    
    # 保存关键位
    kl_path = os.path.join(OUTPUT_DIR, "key_levels.json")
    with open(kl_path, "w", encoding="utf-8") as f:
        json.dump(key_levels_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  关键位分析: {kl_path} ({len(key_levels_results)} 条)")
    
    # 保存上涨形态个股
    rising_path = os.path.join(OUTPUT_DIR, "rising_stocks.json")
    with open(rising_path, "w", encoding="utf-8") as f:
        json.dump(rising_stocks, f, ensure_ascii=False, indent=2, default=str)
    print(f"  上涨形态个股: {rising_path} ({len(rising_stocks)} 条)")
    
    # 保存形态扫描原始信号
    sigs_path = os.path.join(OUTPUT_DIR, "pattern_signals_stocks.json")
    with open(sigs_path, "w", encoding="utf-8") as f:
        json.dump(pattern_sigs, f, ensure_ascii=False, indent=2, default=str)
    print(f"  形态扫描信号: {sigs_path} ({len(pattern_sigs)} 条)")
    
    # ── 汇总报告 ──
    print(f"\n{'='*60}")
    print("Phase 5 分析汇总")
    print(f"{'='*60}")
    print(f"分析板块数: {len(top_sectors)}")
    print(f"分析报告数: {len(report_summaries)}")
    print(f"关键位分析数: {len(key_levels_results)}")
    print(f"上涨形态个股: {len(rising_stocks)}")
    
    if rising_stocks:
        print(f"\n上涨形态个股明细:")
        for i, rs in enumerate(rising_stocks[:50], 1):
            score_str = f"score={rs['score']:.3f}" if rs.get("score") else ""
            print(f"  {i:3d}. {rs['name']}({rs['symbol']}) [{rs['sector_name']}] "
                  f"{rs['pattern_cn']} {rs.get('variant','')} {score_str}")
    
    # 按板块统计
    sector_stats = {}
    for rs in rising_stocks:
        sn = rs.get("sector_name", "未知")
        if sn not in sector_stats:
            sector_stats[sn] = 0
        sector_stats[sn] += 1
    
    if sector_stats:
        print(f"\n各板块上涨形态个股数:")
        for sn, cnt in sorted(sector_stats.items(), key=lambda x: -x[1]):
            print(f"  {sn}: {cnt} 只")
    
    print(f"\n保存文件:")
    print(f"  1. {reports_path}")
    print(f"  2. {kl_path}")
    print(f"  3. {rising_path}")
    print(f"  4. {sigs_path}")
    print(f"\n完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
