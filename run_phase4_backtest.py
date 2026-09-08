"""Phase 4: 全市场形态回测执行脚本"""
import sys
import os
import json
import time
from pathlib import Path

sys.path.insert(0, 'src')

import numpy as np
import pandas as pd

from eastmoney_quant_mcp.strategies.pattern_backtest import (
    collect_signals, report_overall, report_levels, report_wave,
    report_factors, report_filter_search, report_yearly,
    FORWARD_DAYS, BACKTEST_START,
)
from eastmoney_quant_mcp.strategies.patterns import PATTERN_NAMES

# ── 配置 ──
UNIVERSE = "stocks"
START = BACKTEST_START  # "2010-01-01"
END = None  # 到最新
WORKERS = 8
SAMPLE = None  # 全量
OUTPUT_DIR = "reports/phase4_backtest"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("Phase 4: 全市场形态回测")
print(f"  宇宙: {UNIVERSE}")
print(f"  回测区间: {START} ~ {END or '最新'}")
print(f"  _workers: {WORKERS}")
print(f"  抽样: {'全量' if SAMPLE is None else SAMPLE}")
print("=" * 80)

t0 = time.time()

# ── Step 1: 收集信号并计算前向收益 ──
print("\n[Step 1] 收集信号并计算前向收益...")
df = collect_signals(UNIVERSE, START, END, None, (20, 60, 120, 250), 0.015, SAMPLE, WORKERS)

elapsed = time.time() - t0
print(f"\n信号收集完成, 耗时 {elapsed:.1f}s, 共 {len(df)} 个信号")

if df.empty:
    print("无信号, 退出")
    sys.exit(1)

# ── Step 2: 保存原始信号数据 ──
print("\n[Step 2] 保存信号数据...")
signal_csv = os.path.join(OUTPUT_DIR, "all_signals.csv")
df.to_csv(signal_csv, index=False)
print(f"  信号明细已保存: {signal_csv}")

# ── Step 3: 基础统计 ──
print("\n[Step 3] 基础统计...")
print(f"  信号总数: {len(df)}")
print(f"  涉及标的: {df['symbol'].nunique()} 个")
print(f"  日期范围: {df['date'].min()} ~ {df['date'].max()}")

# 按形态统计
print("\n--- 按形态统计 ---")
pattern_stats = []
for pat_key, pat_cn in PATTERN_NAMES.items():
    sub = df[df["pattern"] == pat_key]
    if sub.empty:
        continue
    stats = {
        "pattern": pat_key,
        "pattern_cn": pat_cn,
        "count": len(sub),
        "symbols": sub["symbol"].nunique(),
        "win_rate_5d": (sub["ret_5"].dropna() > 0).mean() * 100,
        "win_rate_10d": (sub["ret_10"].dropna() > 0).mean() * 100,
        "win_rate_20d": (sub["ret_20"].dropna() > 0).mean() * 100,
        "avg_ret_10d": sub["ret_10"].mean() * 100,
        "avg_max_gain_10d": sub["max_gain_10"].mean() * 100,
    }
    pattern_stats.append(stats)
    print(f"  {pat_cn}({pat_key}): {stats['count']}个信号, "
          f"胜率10d={stats['win_rate_10d']:.1f}%, "
          f"均收10d={stats['avg_ret_10d']:.2f}%, "
          f"最大涨10d={stats['avg_max_gain_10d']:.2f}%")

# 按变体统计
print("\n--- 按形态×变体统计 ---")
variant_stats = []
for (pat, var), g in df.groupby(["pattern", "variant"]):
    variant_stats.append({
        "pattern": pat,
        "variant": var,
        "count": len(g),
        "win_rate_10d": (g["ret_10"].dropna() > 0).mean() * 100,
        "avg_ret_10d": g["ret_10"].mean() * 100,
    })
variant_df = pd.DataFrame(variant_stats).sort_values(["pattern", "count"], ascending=[True, False])
for _, row in variant_df.iterrows():
    print(f"  {row['pattern']} / {row['variant']}: {row['count']}个, "
          f"胜率10d={row['win_rate_10d']:.1f}%, 均收10d={row['avg_ret_10d']:.2f}%")

# ── Step 4: 生成六份报告 (捕获输出) ──
print("\n[Step 4] 生成详细报告...")

import io
report_outputs = {}

def capture_report(func, name):
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        func(df)
    except Exception as e:
        buf.write(f"\n报告生成异常: {e}")
    finally:
        sys.stdout = old_stdout
    report_outputs[name] = buf.getvalue()
    print(f"  {name} 完成")

capture_report(report_overall, "report1_overall")
capture_report(report_levels, "report2_levels")
capture_report(report_wave, "report3_wave")
capture_report(report_factors, "report4_factors")
capture_report(report_filter_search, "report5_filter_search")
capture_report(report_yearly, "report6_yearly")

# 打印报告到控制台
for name, content in report_outputs.items():
    print(f"\n{'='*80}")
    print(f"  {name}")
    print(f"{'='*80}")
    print(content)

# ── Step 5: 保存报告文本 ──
print("\n[Step 5] 保存报告文件...")
reports_txt = os.path.join(OUTPUT_DIR, "reports.txt")
with open(reports_txt, "w", encoding="utf-8") as f:
    for name, content in report_outputs.items():
        f.write(f"\n{'='*80}\n{name}\n{'='*80}\n")
        f.write(content)
        f.write("\n")
print(f"  报告文本已保存: {reports_txt}")

# ── Step 6: 保存JSON摘要 ──
print("\n[Step 6] 保存JSON摘要...")

# 评分分布统计
score_dist = {}
for pat_key in PATTERN_NAMES:
    sub = df[df["pattern"] == pat_key]
    if sub.empty:
        continue
    scores = sub["score"].dropna()
    score_dist[pat_key] = {
        "count": len(scores),
        "mean": float(scores.mean()),
        "median": float(scores.median()),
        "max": float(scores.max()),
        "min": float(scores.min()),
    }

# 年度胜率
yearly_stats = []
tmp = df.copy()
tmp["year"] = tmp["date"].str[:4]
for (pat, yr), g in tmp.groupby(["pattern", "year"]):
    if len(g) < 30:
        continue
    yearly_stats.append({
        "pattern": pat,
        "year": yr,
        "count": len(g),
        "win_rate_10d": float((g["ret_10"].dropna() > 0).mean() * 100),
        "avg_ret_10d": float(g["ret_10"].mean() * 100),
    })

summary = {
    "total_signals": len(df),
    "total_symbols": int(df["symbol"].nunique()),
    "date_range": [str(df["date"].min()), str(df["date"].max())],
    "backtest_period": f"{START} ~ {END or 'latest'}",
    "elapsed_seconds": round(elapsed, 1),
    "pattern_stats": pattern_stats,
    "variant_stats": variant_df.to_dict(orient="records"),
    "score_distribution": score_dist,
    "yearly_stats": yearly_stats,
}

summary_json = os.path.join(OUTPUT_DIR, "summary.json")
with open(summary_json, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
print(f"  摘要已保存: {summary_json}")

# ── 完成 ──
total_time = time.time() - t0
print(f"\n{'='*80}")
print(f"Phase 4 回测完成! 总耗时 {total_time:.1f}s")
print(f"输出目录: {OUTPUT_DIR}/")
print(f"  - all_signals.csv    ({len(df)} 个信号)")
print(f"  - summary.json       (统计摘要)")
print(f"  - reports.txt        (六份详细报告)")
print(f"{'='*80}")
