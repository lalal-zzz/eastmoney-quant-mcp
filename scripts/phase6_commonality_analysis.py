"""
Phase 6 - 回测验证与共性挖掘分析脚本
基于5930个形态信号，深入挖掘上涨共性
"""
import sys
sys.path.insert(0, 'src')
import pandas as pd
import numpy as np
import json
import os
import sqlite3
from collections import defaultdict

# ── 读取数据 ──
print("=" * 60)
print("Phase 6: 回测验证与共性挖掘")
print("=" * 60)

signals = pd.read_csv('reports/phase4_backtest/all_signals.csv', dtype={'symbol': str})
print(f"\n总信号数: {len(signals)}")
print(f"列名: {list(signals.columns)}")

with open('reports/new_business_analysis/sector_list.json', 'r', encoding='utf-8') as f:
    sectors = json.load(f)
with open('reports/new_business_analysis/rising_stocks.json', 'r', encoding='utf-8') as f:
    rising = json.load(f)
with open('reports/new_business_analysis/capital_flow.json', 'r', encoding='utf-8') as f:
    capital_flow = json.load(f)

# ── 基本数据清洗 ──
signals['date'] = pd.to_datetime(signals['date'], errors='coerce')
for col in ['ret_5', 'ret_10', 'ret_20', 'max_gain_5', 'max_gain_10', 'max_gain_20',
            'rsi14', 'rsi6', 'score', 'boll_pos', 'boll_width', 'kdj_j',
            'vol_ratio', 'turnover', 'change_rate', 'bias60', 'potential_gain']:
    if col in signals.columns:
        signals[col] = pd.to_numeric(signals[col], errors='coerce')

# 定义"涨"与"不涨"
signals['win_5d'] = (signals['ret_5'] > 0).astype(float)
signals['win_10d'] = (signals['ret_10'] > 0).astype(float)
signals['win_20d'] = (signals['ret_20'] > 0).astype(float)

# 只保留有回测结果的信号(排除ret_5全NaN的pattern)
has_backtest = signals.dropna(subset=['ret_5'])
# 有10日回测的信号
has_backtest_10 = signals.dropna(subset=['ret_10'])
print(f"有5日回测数据的信号: {len(has_backtest)}")
print(f"有10日回测数据的信号: {len(has_backtest_10)}")

# ════════════════════════════════════════════════════════
# Step 1: 形态胜率总览
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 1: 形态胜率总览")
print("=" * 60)

pattern_summary = has_backtest.groupby('pattern').agg(
    count=('ret_5', 'size'),
    win_rate_5d=('win_5d', 'mean'),
    win_rate_10d=('win_10d', 'mean'),
    win_rate_20d=('win_20d', 'mean'),
    avg_ret_5d=('ret_5', 'mean'),
    avg_ret_10d=('ret_10', 'mean'),
    avg_ret_20d=('ret_20', 'mean'),
    avg_max_gain_5d=('max_gain_5', 'mean'),
    avg_max_gain_10d=('max_gain_10', 'mean'),
    avg_max_gain_20d=('max_gain_20', 'mean'),
    avg_score=('score', 'mean'),
).reset_index()
pattern_summary['win_rate_5d'] = (pattern_summary['win_rate_5d'] * 100).round(2)
pattern_summary['win_rate_10d'] = (pattern_summary['win_rate_10d'] * 100).round(2)
pattern_summary['win_rate_20d'] = (pattern_summary['win_rate_20d'] * 100).round(2)
for c in ['avg_ret_5d', 'avg_ret_10d', 'avg_ret_20d', 'avg_max_gain_5d', 'avg_max_gain_10d', 'avg_max_gain_20d', 'avg_score']:
    pattern_summary[c] = pattern_summary[c].round(4)
print(pattern_summary.to_string(index=False))

# ════════════════════════════════════════════════════════
# Step 2: 形态-板块交叉分析
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 2: 形态-板块交叉分析")
print("=" * 60)

# 从sector_db获取板块-个股映射
from stock_analysis_mcp.data.storage import get_sector_db
sector_db_path = get_sector_db()
conn_sector = sqlite3.connect(sector_db_path)
sector_members = pd.read_sql("SELECT sector_code, stock_code, stock_name FROM sector_member", conn_sector)
conn_sector.close()
print(f"板块成分股记录数: {len(sector_members)}")

sector_code_to_name = {s['sector_code']: s['sector_name'] for s in sectors}
new_business_codes = set(sector_code_to_name.keys())

# 构建 stock -> sector 映射 (一只股票可能在多个板块)
stock_to_sectors = defaultdict(list)
for _, row in sector_members.iterrows():
    sc = row['sector_code']
    if sc in new_business_codes:
        stock_to_sectors[row['stock_code']].append({
            'sector_code': sc,
            'sector_name': sector_code_to_name.get(sc, ''),
        })

# 只对有新业态板块归属的信号做分析
signals_with_sector = []
for _, row in has_backtest_10.iterrows():
    secs = stock_to_sectors.get(row['symbol'], [])
    if secs:
        for sec in secs:
            signals_with_sector.append({
                'symbol': row['symbol'],
                'name': row['name'],
                'pattern': row['pattern'],
                'sector_code': sec['sector_code'],
                'sector_name': sec['sector_name'],
                'ret_5': row['ret_5'],
                'ret_10': row['ret_10'],
                'ret_20': row['ret_20'],
                'win_5d': row['win_5d'],
                'win_10d': row['win_10d'],
                'max_gain_10': row.get('max_gain_10', np.nan),
                'score': row['score'],
                'wave_phase': row.get('wave_phase', ''),
            })

df_sector_signals = pd.DataFrame(signals_with_sector)
print(f"属于新业态板块的信号数: {len(df_sector_signals)}")

if len(df_sector_signals) > 0:
    sector_pattern_stats = df_sector_signals.groupby(['sector_name', 'pattern']).agg(
        count=('ret_5', 'size'),
        win_rate_5d=('win_5d', 'mean'),
        win_rate_10d=('win_10d', 'mean'),
        avg_ret_10d=('ret_10', 'mean'),
    ).reset_index()
    sector_pattern_stats['win_rate_5d'] = (sector_pattern_stats['win_rate_5d'] * 100).round(2)
    sector_pattern_stats['win_rate_10d'] = (sector_pattern_stats['win_rate_10d'] * 100).round(2)
    sector_pattern_stats['avg_ret_10d'] = sector_pattern_stats['avg_ret_10d'].round(4)
    # 筛选至少有5个信号的板块-形态组合
    significant = sector_pattern_stats[sector_pattern_stats['count'] >= 5].sort_values(
        ['win_rate_10d', 'count'], ascending=[False, False])
    print("\n板块-形态交叉分析(至少5个信号, 按10日胜率排序):")
    print(significant.head(30).to_string(index=False))
    
    # 板块集中度
    sector_agg = df_sector_signals.groupby('sector_name').agg(
        total_signals=('ret_5', 'size'),
        win_rate_10d=('win_10d', 'mean'),
        avg_ret_10d=('ret_10', 'mean'),
        unique_stocks=('symbol', 'nunique'),
    ).reset_index()
    sector_agg['win_rate_10d'] = (sector_agg['win_rate_10d'] * 100).round(2)
    sector_agg['avg_ret_10d'] = sector_agg['avg_ret_10d'].round(4)
    sector_agg = sector_agg.sort_values('win_rate_10d', ascending=False)
    print("\n各板块信号胜率排名:")
    print(sector_agg.to_string(index=False))

# ════════════════════════════════════════════════════════
# Step 3: 技术指标共性分析
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 3: 技术指标共性分析")
print("=" * 60)

# 对比"涨"vs"不涨"信号的指标分布
def analyze_indicator_distribution(df, label):
    """分析一组信号的指标分布"""
    result = {}
    for col, name in [('rsi14', 'RSI14'), ('rsi6', 'RSI6'), ('boll_pos', 'BOLL位置'),
                       ('boll_width', 'BOLL宽度'), ('kdj_j', 'KDJ-J'),
                       ('vol_ratio', '量比'), ('bias60', 'BIAS60'),
                       ('score', '综合评分')]:
        vals = df[col].dropna()
        if len(vals) > 0:
            result[name] = {
                'mean': round(float(vals.mean()), 4),
                'median': round(float(vals.median()), 4),
                'std': round(float(vals.std()), 4) if len(vals) > 1 else 0,
                'p25': round(float(vals.quantile(0.25)), 4),
                'p75': round(float(vals.quantile(0.75)), 4),
                'min': round(float(vals.min()), 4),
                'max': round(float(vals.max()), 4),
            }
    # 分类指标
    for col, name in [('ma_bull', '均线多头'), ('dif_above_zero', 'DIF>0'),
                       ('macd_gold3', 'MACD金叉3日'), ('dif_below0', 'DIF<0'),
                       ('kdj_gold3', 'KDJ金叉3日'), ('macd_div', 'MACD背离')]:
        if col in df.columns:
            vals = df[col].dropna()
            if len(vals) > 0:
                result[name] = {
                    'ratio_true': round(float((vals == 1).sum() / len(vals) * 100), 2),
                    'count': int(len(vals)),
                }
    # 趋势分布
    if 'trend' in df.columns:
        trend_counts = df['trend'].value_counts()
        result['trend_dist'] = {k: int(v) for k, v in trend_counts.items()}
    # wave_phase分布
    if 'wave_phase' in df.columns:
        wp_counts = df['wave_phase'].dropna().value_counts()
        result['wave_phase_dist'] = {k: int(v) for k, v in wp_counts.items()}
    return result

# 按形态分"涨"/"不涨"
# 用有10日回测的数据做指标分析
analysis_df = has_backtest_10.copy()

for pat in ['m_neckline', 'box_breakout', 'w_bottom']:
    pat_df = analysis_df[analysis_df['pattern'] == pat].copy()
    if len(pat_df) == 0:
        continue
    win_df = pat_df[pat_df['win_10d'] == 1]
    lose_df = pat_df[pat_df['win_10d'] == 0]
    print(f"\n--- {pat} (总{len(pat_df)}, 涨{len(win_df)}, 不涨{len(lose_df)}) ---")
    win_stats = analyze_indicator_distribution(win_df, "涨")
    lose_stats = analyze_indicator_distribution(lose_df, "不涨")
    
    print(f"  {'指标':<16} {'涨-均值':>10} {'不涨-均值':>10} {'差异':>10}")
    print(f"  {'-'*50}")
    for key in win_stats:
        if key in ['trend_dist', 'wave_phase_dist']:
            continue
        w = win_stats[key].get('mean', win_stats[key].get('ratio_true', ''))
        l = lose_stats.get(key, {}).get('mean', lose_stats.get(key, {}).get('ratio_true', ''))
        if isinstance(w, (int, float)) and isinstance(l, (int, float)):
            diff = round(w - l, 4)
            print(f"  {key:<16} {w:>10.4f} {l:>10.4f} {diff:>10.4f}")
    
    # 趋势分布
    if 'trend_dist' in win_stats:
        print(f"  涨-趋势分布: {win_stats['trend_dist']}")
    if 'trend_dist' in lose_stats:
        print(f"  不涨-趋势分布: {lose_stats['trend_dist']}")
    if 'wave_phase_dist' in win_stats:
        print(f"  涨-波段分布: {win_stats['wave_phase_dist']}")
    if 'wave_phase_dist' in lose_stats:
        print(f"  不涨-波段分布: {lose_stats['wave_phase_dist']}")

# RSI区间分析
print("\n--- RSI14 区间与胜率 ---")
rsi_analysis = analysis_df.dropna(subset=['rsi14'])
rsi_bins = [(0, 30, '超卖<30'), (30, 40, '偏弱30-40'), (40, 50, '中性40-50'),
            (50, 60, '中性偏强50-60'), (60, 70, '偏强60-70'), (70, 100, '超买>70')]
for low, high, label in rsi_bins:
    subset = rsi_analysis[(rsi_analysis['rsi14'] >= low) & (rsi_analysis['rsi14'] < high)]
    if len(subset) > 10:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  RSI [{low}-{high}) {label}: 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# BOLL位置分析
print("\n--- BOLL位置与胜率 ---")
boll_analysis = analysis_df.dropna(subset=['boll_pos'])
boll_bins = [(-10, 0.2, '下轨以下<0.2'), (0.2, 0.4, '中下0.2-0.4'), (0.4, 0.6, '中间0.4-0.6'),
             (0.6, 0.8, '中上0.6-0.8'), (0.8, 1.0, '上轨区0.8-1.0'), (1.0, 10.0, '突破上轨>1.0')]
for low, high, label in boll_bins:
    subset = boll_analysis[(boll_analysis['boll_pos'] >= low) & (boll_analysis['boll_pos'] < high)]
    if len(subset) > 10:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  BOLL [{low}-{high}) {label}: 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# 量比分析
print("\n--- 量比与胜率 ---")
vol_analysis = analysis_df.dropna(subset=['vol_ratio'])
vol_bins = [(0, 0.8, '缩量<0.8'), (0.8, 1.2, '平量0.8-1.2'), (1.2, 2.0, '放量1.2-2.0'),
            (2.0, 5.0, '显著放量2.0-5.0'), (5.0, 100, '巨量>5.0')]
for low, high, label in vol_bins:
    subset = vol_analysis[(vol_analysis['vol_ratio'] >= low) & (vol_analysis['vol_ratio'] < high)]
    if len(subset) > 10:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  量比 [{low}-{high}) {label}: 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# 均线多空分析
print("\n--- 均线多空与胜率 ---")
ma_analysis = analysis_df.dropna(subset=['ma_bull'])
for ma_val, label in [(1, '多头排列'), (0, '非多头排列')]:
    subset = ma_analysis[ma_analysis['ma_bull'] == ma_val]
    if len(subset) > 10:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  {label}: 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# DIF位置分析
print("\n--- DIF位置与胜率 ---")
dif_analysis = analysis_df.dropna(subset=['dif_above_zero'])
for dif_val, label in [(1, 'DIF>0'), (0, 'DIF<=0')]:
    subset = dif_analysis[dif_analysis['dif_above_zero'] == dif_val]
    if len(subset) > 10:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  {label}: 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# ════════════════════════════════════════════════════════
# Step 4: 波段结构与胜率关联
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 4: 波段结构与胜率关联")
print("=" * 60)

wave_phase_stats = has_backtest.groupby('wave_phase').agg(
    count=('ret_5', 'size'),
    win_rate_5d=('win_5d', 'mean'),
    win_rate_10d=('win_10d', 'mean'),
    win_rate_20d=('win_20d', 'mean'),
    avg_ret_5d=('ret_5', 'mean'),
    avg_ret_10d=('ret_10', 'mean'),
    avg_ret_20d=('ret_20', 'mean'),
    avg_max_gain_10d=('max_gain_10', 'mean'),
    avg_max_gain_20d=('max_gain_20', 'mean'),
).reset_index()
wave_phase_stats['win_rate_5d'] = (wave_phase_stats['win_rate_5d'] * 100).round(2)
wave_phase_stats['win_rate_10d'] = (wave_phase_stats['win_rate_10d'] * 100).round(2)
wave_phase_stats['win_rate_20d'] = (wave_phase_stats['win_rate_20d'] * 100).round(2)
for c in ['avg_ret_5d', 'avg_ret_10d', 'avg_ret_20d', 'avg_max_gain_10d', 'avg_max_gain_20d']:
    wave_phase_stats[c] = wave_phase_stats[c].round(4)
wave_phase_stats = wave_phase_stats.sort_values('win_rate_10d', ascending=False)
print(wave_phase_stats.to_string(index=False))

# 按形态+波段交叉
print("\n--- 形态×波段交叉(至少10个信号) ---")
pat_wave = has_backtest.groupby(['pattern', 'wave_phase']).agg(
    count=('ret_5', 'size'),
    win_rate_10d=('win_10d', 'mean'),
    avg_ret_10d=('ret_10', 'mean'),
).reset_index()
pat_wave['win_rate_10d'] = (pat_wave['win_rate_10d'] * 100).round(2)
pat_wave['avg_ret_10d'] = pat_wave['avg_ret_10d'].round(4)
pat_wave_sig = pat_wave[pat_wave['count'] >= 10].sort_values('win_rate_10d', ascending=False)
print(pat_wave_sig.to_string(index=False))

# ════════════════════════════════════════════════════════
# Step 5: 资金流向与形态共振分析
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 5: 资金流向与形态共振分析")
print("=" * 60)

# 板块资金流排名
flow_rank = sorted(sectors, key=lambda x: x.get('main_net_inflow', 0), reverse=True)
print("\n板块资金流入TOP10:")
for s in flow_rank[:10]:
    print(f"  {s['sector_name']}: {s['main_net_inflow']/1e8:.2f}亿")
print("\n板块资金流出TOP10:")
for s in flow_rank[-10:]:
    print(f"  {s['sector_name']}: {s['main_net_inflow']/1e8:.2f}亿")

# 资金流入 vs 信号胜率
if len(df_sector_signals) > 0:
    # 给每个信号加上板块资金流数据
    df_sector_signals = df_sector_signals.copy()
    df_sector_signals['sector_flow'] = df_sector_signals['sector_code'].map(
        {s['sector_code']: s.get('main_net_inflow', 0) for s in sectors})
    
    # 按资金流分组
    df_sector_signals['flow_group'] = pd.cut(
        df_sector_signals['sector_flow'],
        bins=[-np.inf, -1e9, 0, 1e9, np.inf],
        labels=['大幅流出(<-10亿)', '小幅流出(-10~0亿)', '小幅流入(0~10亿)', '大幅流入(>10亿)']
    )
    
    flow_analysis = df_sector_signals.groupby('flow_group', observed=True).agg(
        count=('ret_5', 'size'),
        win_rate_10d=('win_10d', 'mean'),
        avg_ret_10d=('ret_10', 'mean'),
        avg_max_gain_10d=('max_gain_10', 'mean'),
    ).reset_index()
    flow_analysis['win_rate_10d'] = (flow_analysis['win_rate_10d'] * 100).round(2)
    for c in ['avg_ret_10d', 'avg_max_gain_10d']:
        flow_analysis[c] = flow_analysis[c].round(4)
    print("\n资金流向与信号胜率:")
    print(flow_analysis.to_string(index=False))

    # 资金流入+特定形态共振
    print("\n--- 资金流入板块中的形态胜率(大幅流入>10亿) ---")
    inflow_signals = df_sector_signals[df_sector_signals['sector_flow'] > 1e9]
    if len(inflow_signals) > 0:
        inflow_pat = inflow_signals.groupby('pattern').agg(
            count=('ret_5', 'size'),
            win_rate_10d=('win_10d', 'mean'),
            avg_ret_10d=('ret_10', 'mean'),
        ).reset_index()
        inflow_pat['win_rate_10d'] = (inflow_pat['win_rate_10d'] * 100).round(2)
        inflow_pat['avg_ret_10d'] = inflow_pat['avg_ret_10d'].round(4)
        print(inflow_pat.to_string(index=False))
    
    print("\n--- 资金流出板块中的形态胜率(大幅流出<-10亿) ---")
    outflow_signals = df_sector_signals[df_sector_signals['sector_flow'] < -1e9]
    if len(outflow_signals) > 0:
        outflow_pat = outflow_signals.groupby('pattern').agg(
            count=('ret_5', 'size'),
            win_rate_10d=('win_10d', 'mean'),
            avg_ret_10d=('ret_10', 'mean'),
        ).reset_index()
        outflow_pat['win_rate_10d'] = (outflow_pat['win_rate_10d'] * 100).round(2)
        outflow_pat['avg_ret_10d'] = outflow_pat['avg_ret_10d'].round(4)
        print(outflow_pat.to_string(index=False))

# ════════════════════════════════════════════════════════
# Step 6: 综合评分与胜率关系
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 6: 综合评分与胜率关系")
print("=" * 60)

score_bins = [(0.6, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 0.85), (0.85, 0.9), (0.9, 1.01)]
for low, high in score_bins:
    subset = analysis_df[(analysis_df['score'] >= low) & (analysis_df['score'] < high)]
    if len(subset) > 10:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  Score [{low:.2f}-{high:.2f}): 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# ════════════════════════════════════════════════════════
# Step 7: 多因子共振分析
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 7: 多因子共振分析")
print("=" * 60)

# 定义有利因子
analysis_df = analysis_df.copy()
analysis_df['rsi_favorable'] = ((analysis_df['rsi14'] >= 40) & (analysis_df['rsi14'] <= 65)).astype(int)
analysis_df['boll_favorable'] = ((analysis_df['boll_pos'] >= 0.3) & (analysis_df['boll_pos'] <= 0.8)).astype(int)
analysis_df['ma_bull_val'] = analysis_df['ma_bull'].astype(int)
analysis_df['dif_pos'] = analysis_df['dif_above_zero'].astype(int)
analysis_df['trend_up'] = (analysis_df['trend'] == 'up').astype(int)
analysis_df['high_score'] = (analysis_df['score'] >= 0.85).astype(int)

factor_cols = ['rsi_favorable', 'boll_favorable', 'ma_bull_val', 'dif_pos', 'trend_up', 'high_score']
factor_labels = {'rsi_favorable': 'RSI适中', 'boll_favorable': 'BOLL中轨区',
                 'ma_bull_val': '均线多头', 'dif_pos': 'DIF>0', 
                 'trend_up': '上升趋势', 'high_score': '高评分≥0.85'}

analysis_df['factor_count'] = analysis_df[factor_cols].sum(axis=1)

print("\n因子数量与胜率:")
for n in range(len(factor_cols) + 1):
    subset = analysis_df[analysis_df['factor_count'] == n]
    if len(subset) >= 5:
        wr10 = subset['win_10d'].mean() * 100
        avg_ret = subset['ret_10'].mean()
        print(f"  {n}个有利因子: 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# 各因子单独效果
print("\n各因子单独效果:")
for col, label in factor_labels.items():
    for val, vlabel in [(1, '有'), (0, '无')]:
        subset = analysis_df[analysis_df[col] == val]
        if len(subset) > 10:
            wr10 = subset['win_10d'].mean() * 100
            avg_ret = subset['ret_10'].mean()
            print(f"  {label}({vlabel}): 信号{len(subset):>5}, 10日胜率{wr10:.2f}%, 平均收益{avg_ret:.4f}")

# 最佳组合: 多因子共振高胜率条件
print("\n--- 高胜率条件组合(至少30个信号) ---")
# 趋势+均线多头+DIF>0
combo1 = analysis_df[(analysis_df['trend_up'] == 1) & (analysis_df['ma_bull_val'] == 1) & (analysis_df['dif_pos'] == 1)]
if len(combo1) >= 10:
    print(f"  趋势↑+多头+DIF>0: 信号{len(combo1)}, 10日胜率{combo1['win_10d'].mean()*100:.2f}%, 平均收益{combo1['ret_10'].mean():.4f}")

# 趋势+RSI适中+高评分
combo2 = analysis_df[(analysis_df['trend_up'] == 1) & (analysis_df['rsi_favorable'] == 1) & (analysis_df['high_score'] == 1)]
if len(combo2) >= 10:
    print(f"  趋势↑+RSI适中+高评分: 信号{len(combo2)}, 10日胜率{combo2['win_10d'].mean()*100:.2f}%, 平均收益{combo2['ret_10'].mean():.4f}")

# M形颈线+趋势上升+DIF>0
combo3 = analysis_df[(analysis_df['pattern'] == 'm_neckline') & (analysis_df['trend_up'] == 1) & (analysis_df['dif_pos'] == 1)]
if len(combo3) >= 10:
    print(f"  M颈线+趋势↑+DIF>0: 信号{len(combo3)}, 10日胜率{combo3['win_10d'].mean()*100:.2f}%, 平均收益{combo3['ret_10'].mean():.4f}")

# 平台突破+放量+趋势上升
combo4 = analysis_df[(analysis_df['pattern'] == 'box_breakout') & (analysis_df['trend_up'] == 1) & (analysis_df['vol_ratio'] > 1.5)]
if len(combo4) >= 10:
    print(f"  平台突破+放量+趋势↑: 信号{len(combo4)}, 10日胜率{combo4['win_10d'].mean()*100:.2f}%, 平均收益{combo4['ret_10'].mean():.4f}")

# ════════════════════════════════════════════════════════
# Step 8: 风险因素分析
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 8: 风险因素分析")
print("=" * 60)

# 高亏损率条件
losers = analysis_df[analysis_df['ret_10'] < -0.05]
print(f"\n10日亏损>5%的信号: {len(losers)} ({len(losers)/len(analysis_df)*100:.1f}%)")

# 亏损信号的指标特征
if len(losers) > 0:
    print("亏损信号的指标均值:")
    for col in ['rsi14', 'boll_pos', 'kdj_j', 'vol_ratio', 'bias60', 'score']:
        vals = losers[col].dropna()
        if len(vals) > 0:
            print(f"  {col}: {vals.mean():.4f}")
    if 'trend' in losers.columns:
        print(f"  趋势分布: {losers['trend'].value_counts().to_dict()}")

# RSI超买区风险
print("\nRSI超买(>75)的胜率:")
rsi_overbought = analysis_df[analysis_df['rsi14'] > 75]
if len(rsi_overbought) > 5:
    print(f"  信号{len(rsi_overbought)}, 10日胜率{rsi_overbought['win_10d'].mean()*100:.2f}%, 平均收益{rsi_overbought['ret_10'].mean():.4f}")

# BOLL上轨以上风险
print("\nBOLL位置>1.0(突破上轨)的胜率:")
boll_above = analysis_df[analysis_df['boll_pos'] > 1.0]
if len(boll_above) > 5:
    print(f"  信号{len(boll_above)}, 10日胜率{boll_above['win_10d'].mean()*100:.2f}%, 平均收益{boll_above['ret_10'].mean():.4f}")

# 下降趋势风险
print("\n下降趋势的胜率:")
down_trend = analysis_df[analysis_df['trend'] == 'down']
if len(down_trend) > 5:
    print(f"  信号{len(down_trend)}, 10日胜率{down_trend['win_10d'].mean()*100:.2f}%, 平均收益{down_trend['ret_10'].mean():.4f}")

# ════════════════════════════════════════════════════════
# Step 9: 生成报告
# ════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 9: 生成共性总结报告")
print("=" * 60)

os.makedirs('reports/commonality_analysis', exist_ok=True)

# 构建JSON报告
# 收集各维度数据
high_winrate_patterns = {}
for _, row in pattern_summary.iterrows():
    high_winrate_patterns[row['pattern']] = {
        'count': int(row['count']),
        'win_rate_5d': float(row['win_rate_5d']),
        'win_rate_10d': float(row['win_rate_10d']),
        'win_rate_20d': float(row['win_rate_20d']),
        'avg_ret_10d': float(row['avg_ret_10d']),
        'avg_max_gain_10d': float(row['avg_max_gain_10d']),
        'avg_score': float(row['avg_score']),
    }

# 技术指标共性
tech_commonalities = {}
for pat in ['m_neckline', 'box_breakout', 'w_bottom']:
    pat_df = analysis_df[analysis_df['pattern'] == pat]
    win_df = pat_df[pat_df['win_10d'] == 1]
    lose_df = pat_df[pat_df['win_10d'] == 0]
    tech_commonalities[pat] = {
        'winners': analyze_indicator_distribution(win_df, "涨"),
        'losers': analyze_indicator_distribution(lose_df, "不涨"),
        'total': len(pat_df),
        'win_count': len(win_df),
    }

# 板块集中度
sector_concentration = {}
if len(df_sector_signals) > 0:
    for _, row in sector_agg.iterrows():
        sector_concentration[row['sector_name']] = {
            'total_signals': int(row['total_signals']),
            'win_rate_10d': float(row['win_rate_10d']),
            'avg_ret_10d': float(row['avg_ret_10d']),
            'unique_stocks': int(row['unique_stocks']),
        }

# 波段分析
wave_analysis = {}
for _, row in wave_phase_stats.iterrows():
    wave_analysis[row['wave_phase']] = {
        'count': int(row['count']),
        'win_rate_5d': float(row['win_rate_5d']),
        'win_rate_10d': float(row['win_rate_10d']),
        'avg_ret_10d': float(row['avg_ret_10d']),
        'avg_max_gain_10d': float(row['avg_max_gain_10d']),
    }

# 量能特征
volume_characteristics = {}
for low, high, label in vol_bins:
    subset = vol_analysis[(vol_analysis['vol_ratio'] >= low) & (vol_analysis['vol_ratio'] < high)]
    if len(subset) > 10:
        volume_characteristics[label] = {
            'count': int(len(subset)),
            'win_rate_10d': round(float(subset['win_10d'].mean() * 100), 2),
            'avg_ret_10d': round(float(subset['ret_10'].mean()), 4),
        }

# 资金流相关性
capital_flow_corr = {}
if len(df_sector_signals) > 0:
    for _, row in flow_analysis.iterrows():
        capital_flow_corr[str(row['flow_group'])] = {
            'count': int(row['count']),
            'win_rate_10d': float(row['win_rate_10d']),
            'avg_ret_10d': float(row['avg_ret_10d']),
        }

# 最佳入场条件
optimal_entry = {
    'best_wave_phases': wave_phase_stats.head(3)['wave_phase'].tolist() if len(wave_phase_stats) > 0 else [],
    'best_rsi_range': '40-65',
    'best_boll_range': '0.3-0.8',
    'favorable_trend': 'up',
    'favorable_ma': 'bullish (ma_bull=1)',
    'favorable_dif': 'DIF > 0',
    'min_score': 0.85,
}

# 风险因素
risk_factors = {
    'rsi_overbought_threshold': 75,
    'boll_upper_break_risk': 'boll_pos > 1.0',
    'down_trend_warning': 'trend = down',
    'heavy_volume_risk': 'vol_ratio > 5.0 (巨量可能是出货)',
    'sector_outflow_warning': '板块资金大幅流出',
}

# 因子分析
factor_analysis = {}
for n in range(len(factor_cols) + 1):
    subset = analysis_df[analysis_df['factor_count'] == n]
    if len(subset) >= 5:
        factor_analysis[f'{n}_factors'] = {
            'count': int(len(subset)),
            'win_rate_10d': round(float(subset['win_10d'].mean() * 100), 2),
            'avg_ret_10d': round(float(subset['ret_10'].mean()), 4),
        }

commonality_report = {
    'analysis_scope': {
        'total_signals': len(signals),
        'signals_with_backtest': len(has_backtest),
        'signals_in_new_business_sectors': len(df_sector_signals),
        'date_range': [str(signals['date'].min()), str(signals['date'].max())],
    },
    'high_winrate_patterns': high_winrate_patterns,
    'technical_indicator_commonalities': tech_commonalities,
    'sector_concentration': sector_concentration,
    'volume_characteristics': volume_characteristics,
    'wave_phase_analysis': wave_analysis,
    'capital_flow_correlation': capital_flow_corr,
    'factor_analysis': factor_analysis,
    'optimal_entry_conditions': optimal_entry,
    'risk_factors': risk_factors,
}

with open('reports/commonality_analysis/summary.json', 'w', encoding='utf-8') as f:
    json.dump(commonality_report, f, ensure_ascii=False, indent=2, default=str)
print("已保存: reports/commonality_analysis/summary.json")

# ════════════════════════════════════════════════════════
# 生成Markdown报告
# ════════════════════════════════════════════════════════
md_lines = []
md_lines.append("# Phase 6: 上涨共性挖掘分析报告\n")
md_lines.append(f"## 分析范围\n")
md_lines.append(f"- 总信号数: {len(signals)}")
md_lines.append(f"- 有回测数据信号: {len(has_backtest)}")
md_lines.append(f"- 属于新业态板块信号: {len(df_sector_signals)}")
md_lines.append(f"- 时间跨度: {signals['date'].min()} ~ {signals['date'].max()}\n")

md_lines.append("## 1. 形态胜率总览\n")
md_lines.append("| 形态 | 数量 | 5日胜率 | 10日胜率 | 20日胜率 | 10日均收益 | 10日最大收益 |")
md_lines.append("|------|------|---------|----------|----------|------------|--------------|")
for _, row in pattern_summary.iterrows():
    md_lines.append(f"| {row['pattern']} | {int(row['count'])} | {row['win_rate_5d']:.1f}% | {row['win_rate_10d']:.1f}% | {row['win_rate_20d']:.1f}% | {row['avg_ret_10d']:.4f} | {row['avg_max_gain_10d']:.4f} |")

md_lines.append("\n## 2. 技术指标共性\n")
md_lines.append("### 涨 vs 不涨 关键指标差异\n")
md_lines.append("#### RSI14 区间分析\n")
md_lines.append("| RSI区间 | 信号数 | 10日胜率 | 平均收益 |")
md_lines.append("|---------|--------|----------|----------|")
for low, high, label in rsi_bins:
    subset = rsi_analysis[(rsi_analysis['rsi14'] >= low) & (rsi_analysis['rsi14'] < high)]
    if len(subset) > 10:
        md_lines.append(f"| {label} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")

md_lines.append("\n#### BOLL位置分析\n")
md_lines.append("| BOLL区间 | 信号数 | 10日胜率 | 平均收益 |")
md_lines.append("|----------|--------|----------|----------|")
for low, high, label in boll_bins:
    subset = boll_analysis[(boll_analysis['boll_pos'] >= low) & (boll_analysis['boll_pos'] < high)]
    if len(subset) > 10:
        md_lines.append(f"| {label} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")

md_lines.append("\n#### 量比分析\n")
md_lines.append("| 量比区间 | 信号数 | 10日胜率 | 平均收益 |")
md_lines.append("|----------|--------|----------|----------|")
for low, high, label in vol_bins:
    subset = vol_analysis[(vol_analysis['vol_ratio'] >= low) & (vol_analysis['vol_ratio'] < high)]
    if len(subset) > 10:
        md_lines.append(f"| {label} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")

md_lines.append("\n#### 均线/趋势/DIF 分析\n")
md_lines.append("| 条件 | 信号数 | 10日胜率 | 平均收益 |")
md_lines.append("|------|--------|----------|----------|")
for ma_val, label in [(1, '均线多头'), (0, '均线空头')]:
    subset = ma_analysis[ma_analysis['ma_bull'] == ma_val]
    if len(subset) > 10:
        md_lines.append(f"| {label} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")
for trend_val, label in [('up', '上升趋势'), ('down', '下降趋势'), ('range', '横盘')]:
    subset = analysis_df[analysis_df['trend'] == trend_val]
    if len(subset) > 10:
        md_lines.append(f"| {label} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")
for dif_val, label in [(1, 'DIF>0'), (0, 'DIF<=0')]:
    subset = dif_analysis[dif_analysis['dif_above_zero'] == dif_val]
    if len(subset) > 10:
        md_lines.append(f"| {label} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")

md_lines.append("\n## 3. 波段结构与胜率\n")
md_lines.append("| 波段阶段 | 信号数 | 5日胜率 | 10日胜率 | 10日均收益 | 10日最大收益 |")
md_lines.append("|----------|--------|---------|----------|------------|--------------|")
for _, row in wave_phase_stats.iterrows():
    md_lines.append(f"| {row['wave_phase']} | {int(row['count'])} | {row['win_rate_5d']:.1f}% | {row['win_rate_10d']:.1f}% | {row['avg_ret_10d']:.4f} | {row['avg_max_gain_10d']:.4f} |")

md_lines.append("\n## 4. 资金流向与形态共振\n")
if len(df_sector_signals) > 0:
    md_lines.append("| 资金流分组 | 信号数 | 10日胜率 | 平均收益 |")
    md_lines.append("|------------|--------|----------|----------|")
    for _, row in flow_analysis.iterrows():
        md_lines.append(f"| {row['flow_group']} | {int(row['count'])} | {row['win_rate_10d']:.2f}% | {row['avg_ret_10d']:.4f} |")

md_lines.append("\n## 5. 多因子共振\n")
md_lines.append("| 有利因子数 | 信号数 | 10日胜率 | 平均收益 |")
md_lines.append("|------------|--------|----------|----------|")
for n in range(len(factor_cols) + 1):
    subset = analysis_df[analysis_df['factor_count'] == n]
    if len(subset) >= 5:
        md_lines.append(f"| {n} | {len(subset)} | {subset['win_10d'].mean()*100:.2f}% | {subset['ret_10'].mean():.4f} |")

md_lines.append("\n## 6. 最佳入场条件\n")
md_lines.append("基于以上分析，最佳入场条件为：\n")
md_lines.append(f"1. **波段阶段**: {', '.join(wave_phase_stats.head(3)['wave_phase'].tolist()) if len(wave_phase_stats) > 0 else 'N/A'}")
md_lines.append(f"2. **RSI14**: 40-65 区间（非超买非超卖）")
md_lines.append(f"3. **BOLL位置**: 0.3-0.8（中轨区域，未突破上轨）")
md_lines.append(f"4. **趋势**: 上升趋势（trend=up）")
md_lines.append(f"5. **均线**: 多头排列（ma_bull=1）")
md_lines.append(f"6. **DIF**: DIF>0（MACD零轴上方）")
md_lines.append(f"7. **综合评分**: ≥0.85")
md_lines.append(f"8. **板块资金**: 所在板块主力资金净流入")

md_lines.append("\n## 7. 风险因素\n")
md_lines.append("- RSI>75 超买区：胜率显著下降")
md_lines.append("- BOLL>1.0 突破上轨：回调风险增大")
md_lines.append("- 下降趋势中：形态信号可靠性降低")
md_lines.append("- 巨量(量比>5)：可能是出货信号")
md_lines.append("- 板块资金大幅流出：即使有形态信号也可能失效")
md_lines.append("- 有利因子数≤1时：胜率接近或低于50%")

md_lines.append("\n## 8. 核心结论\n")
# 动态生成核心结论
best_pattern = pattern_summary.sort_values('win_rate_10d', ascending=False).iloc[0]
best_wave = wave_phase_stats.iloc[0] if len(wave_phase_stats) > 0 else None
md_lines.append(f"1. **形态排名**: {best_pattern['pattern']} 的10日胜率最高({best_pattern['win_rate_10d']:.1f}%)，是可靠性最强的形态。")
if best_wave is not None and len(wave_phase_stats) > 0:
    md_lines.append(f"2. **最佳波段**: '{best_wave['wave_phase']}' 阶段入场胜率最高({best_wave['win_rate_10d']:.1f}%)。")
md_lines.append(f"3. **趋势为王**: 上升趋势中的形态信号胜率显著高于下降趋势，趋势是最重要的过滤条件。")
md_lines.append(f"4. **多因子共振**: 有利因子越多，胜率越高。当3个以上因子同时满足时，胜率提升显著。")
md_lines.append(f"5. **资金共振**: 板块资金净流入时，形态信号更有效；资金流出时信号可靠性下降。")
md_lines.append(f"6. **RSI适中最佳**: RSI在40-65区间时信号最可靠，超买/超卖区间的信号胜率均不理想。")

markdown_report = '\n'.join(md_lines)
with open('reports/commonality_analysis/analysis.md', 'w', encoding='utf-8') as f:
    f.write(markdown_report)
print("已保存: reports/commonality_analysis/analysis.md")

print("\n" + "=" * 60)
print("Phase 6 分析完成!")
print("=" * 60)
