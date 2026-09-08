"""
新业态板块识别与形态扫描脚本
- Step 1: 获取全部概念+行业板块列表
- Step 2: 按关键词筛选新业态板块
- Step 3: 板块K线形态分析
- Step 4: 资金流向分析
- Step 5: 保存结果
"""
import sys
import os
import json
import asyncio
import traceback

sys.path.insert(0, 'src')

from eastmoney_quant_mcp.tools.sector_data import get_sector_list, get_sector_kline
from eastmoney_quant_mcp.tools.sector_screen import (
    screen_top_sectors,
    screen_main_inflow_sectors,
    screen_sector_by_capital_flow,
)

# ── 关键词列表 ──
KEYWORDS = [
    "新能源", "人工智能", "AI", "机器人", "芯片", "半导体", "量子", "区块链",
    "数字经济", "云计算", "大数据", "物联网", "5G", "元宇宙",
    "生物医药", "基因", "碳中和", "光伏", "储能", "氢能",
    "新型消费", "直播经济", "跨境电商", "智能制造",
    "数据要素", "算力", "低空经济", "新质生产力",
]


def match_keywords(name: str) -> list[str]:
    """返回名称中匹配到的关键词列表"""
    return [kw for kw in KEYWORDS if kw in name]


def compute_ma(closes: list[float], period: int) -> list[float | None]:
    """简单移动平均"""
    result = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(closes[i - period + 1:i + 1]) / period)
    return result


def compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """RSI 指标"""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        result[period] = 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            result[i] = 100 - 100 / (1 + avg_gain / avg_loss)
    return result


def analyze_sector_pattern(klines: list[dict], sector_name: str) -> dict:
    """基于K线数据做简单形态分析"""
    if len(klines) < 20:
        return {"sector_name": sector_name, "signals": [], "error": "K线数据不足"}

    closes = [float(k["close"]) for k in klines]
    volumes = [float(k["volume"]) for k in klines]
    latest = closes[-1]
    signals = []

    # MA5 / MA20 金叉
    ma5 = compute_ma(closes, 5)
    ma20 = compute_ma(closes, 20)
    if ma5[-1] is not None and ma20[-1] is not None and ma5[-2] is not None and ma20[-2] is not None:
        if ma5[-1] > ma20[-1] and ma5[-2] <= ma20[-2]:
            signals.append("golden_cross_MA5_MA20")

    # 多头排列: MA5 > MA10 > MA20 > MA60
    ma10 = compute_ma(closes, 10)
    ma60 = compute_ma(closes, 60) if len(closes) >= 60 else [None] * len(closes)
    if all(v is not None for v in [ma5[-1], ma10[-1], ma20[-1], ma60[-1]]):
        if ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1]:
            signals.append("ma_bullish_alignment")

    # 放量: 最新日成交量 > 5日均量 * 2
    if len(volumes) >= 6:
        vol_ma5 = sum(volumes[-6:-1]) / 5
        if vol_ma5 > 0 and volumes[-1] > vol_ma5 * 2:
            signals.append("volume_surge")

    # RSI
    rsi_vals = compute_rsi(closes, 14)
    latest_rsi = rsi_vals[-1]
    if latest_rsi is not None:
        if latest_rsi < 30:
            signals.append("oversold_RSI")
        elif latest_rsi > 70:
            signals.append("overbought_RSI")

    # 近5日涨跌幅
    if len(closes) >= 6:
        pct_5d = (closes[-1] / closes[-6] - 1) * 100
    else:
        pct_5d = 0

    # 近20日涨跌幅
    if len(closes) >= 21:
        pct_20d = (closes[-1] / closes[-21] - 1) * 100
    else:
        pct_20d = 0

    return {
        "sector_name": sector_name,
        "latest_close": latest,
        "kline_count": len(klines),
        "signals": signals,
        "rsi14": round(latest_rsi, 2) if latest_rsi else None,
        "pct_5d": round(pct_5d, 2),
        "pct_20d": round(pct_20d, 2),
        "ma5": round(ma5[-1], 2) if ma5[-1] else None,
        "ma20": round(ma20[-1], 2) if ma20[-1] else None,
    }


async def main():
    print("=" * 60)
    print("新业态板块识别与形态扫描")
    print("=" * 60)

    # ── Step 1: 获取板块列表 ──
    print("\n[Step 1] 获取板块列表...")
    concept_sectors = await get_sector_list(sector_type="concept")
    industry_sectors = await get_sector_list(sector_type="industry")
    print(f"  概念板块总数: {len(concept_sectors)}")
    print(f"  行业板块总数: {len(industry_sectors)}")

    all_sectors = concept_sectors + industry_sectors
    print(f"  合计: {len(all_sectors)}")

    # ── Step 2: 筛选新业态板块 ──
    print("\n[Step 2] 筛选新业态板块...")
    new_business = []
    for s in all_sectors:
        name = s.get("sector_name", "")
        matched = match_keywords(name)
        if matched:
            new_business.append({
                **s,
                "matched_keywords": matched,
            })

    print(f"  匹配到的新业态板块数: {len(new_business)}")
    for i, s in enumerate(new_business, 1):
        print(f"  {i:3d}. [{s['sector_code']}] {s['sector_name']}  "
              f"(类型:{s['sector_type']}, 关键词:{','.join(s['matched_keywords'])})")

    # ── Step 3: 板块K线形态分析 ──
    print("\n[Step 3] 板块K线形态扫描...")
    pattern_results = []
    codes = [s["sector_code"] for s in new_business]
    names = [s["sector_name"] for s in new_business]

    for i, (code, name) in enumerate(zip(codes, names), 1):
        print(f"  [{i}/{len(codes)}] 获取K线: {name} ({code})...", end=" ")
        try:
            klines = await get_sector_kline(code, limit=260)
            if not klines or len(klines) < 20:
                print(f"K线不足 ({len(klines) if klines else 0} 根), 跳过")
                continue
            result = analyze_sector_pattern(klines, name)
            result["sector_code"] = code
            # 附加板块行情数据
            for s in new_business:
                if s["sector_code"] == code:
                    result["change_pct"] = s.get("change_pct")
                    result["main_net_inflow"] = s.get("main_net_inflow")
                    result["matched_keywords"] = s.get("matched_keywords")
                    break
            pattern_results.append(result)
            sig_str = ",".join(result["signals"]) if result["signals"] else "无信号"
            print(f"{len(klines)}根K线, 信号: {sig_str}")
        except Exception as e:
            print(f"错误: {e}")

    # 汇总有信号的板块
    signaled = [r for r in pattern_results if r["signals"]]
    print(f"\n  出现形态信号的板块: {len(signaled)}/{len(pattern_results)}")
    for s in signaled:
        print(f"    [{s['sector_code']}] {s['sector_name']}: {', '.join(s['signals'])}")

    # ── Step 4: 资金流向分析 ──
    print("\n[Step 4] 资金流向分析...")
    # 从已获取的板块数据中排序
    capital_flow = []
    for s in new_business:
        capital_flow.append({
            "sector_code": s["sector_code"],
            "sector_name": s["sector_name"],
            "sector_type": s["sector_type"],
            "change_pct": s.get("change_pct"),
            "main_net_inflow": s.get("main_net_inflow"),
            "main_net_pct": s.get("main_net_pct"),
            "super_large_net": s.get("super_large_net"),
            "super_large_pct": s.get("super_large_pct"),
            "large_net": s.get("large_net"),
            "large_pct": s.get("large_pct"),
            "medium_net": s.get("medium_net"),
            "medium_pct": s.get("medium_pct"),
            "small_net": s.get("small_net"),
            "small_pct": s.get("small_pct"),
            "lead_stock_name": s.get("lead_stock_name"),
            "lead_stock_code": s.get("lead_stock_code"),
            "matched_keywords": s.get("matched_keywords"),
        })

    # 按主力净流入排序
    capital_flow.sort(key=lambda x: x.get("main_net_inflow") or 0, reverse=True)

    print("\n  新业态板块资金净流入排名 (前20):")
    for i, cf in enumerate(capital_flow[:20], 1):
        inflow = cf.get("main_net_inflow") or 0
        pct = cf.get("change_pct") or 0
        print(f"  {i:3d}. [{cf['sector_code']}] {cf['sector_name']:20s}  "
              f"主力净流入: {inflow/1e8:+10.2f}亿  涨跌幅: {pct:+6.2f}%")

    # ── Step 5: 保存结果 ──
    print("\n[Step 5] 保存结果...")
    out_dir = "reports/new_business_analysis"
    os.makedirs(out_dir, exist_ok=True)

    # 板块列表 (去掉 matched_keywords 中的冗余字段保存完整信息)
    sector_list_path = os.path.join(out_dir, "sector_list.json")
    with open(sector_list_path, "w", encoding="utf-8") as f:
        json.dump(new_business, f, ensure_ascii=False, indent=2, default=str)
    print(f"  板块列表: {sector_list_path} ({len(new_business)} 条)")

    # 形态扫描结果
    pattern_path = os.path.join(out_dir, "pattern_signals.json")
    with open(pattern_path, "w", encoding="utf-8") as f:
        json.dump(pattern_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  形态信号: {pattern_path} ({len(pattern_results)} 条)")

    # 资金流向
    capital_path = os.path.join(out_dir, "capital_flow.json")
    with open(capital_path, "w", encoding="utf-8") as f:
        json.dump(capital_flow, f, ensure_ascii=False, indent=2, default=str)
    print(f"  资金流向: {capital_path} ({len(capital_flow)} 条)")

    print("\n" + "=" * 60)
    print("分析完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
