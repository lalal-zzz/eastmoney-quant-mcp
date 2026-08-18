"""
strategies/pattern_backtest.py — 形态信号历史回测 + 技术共性分析
(移植自"股票信息"项目 patterns/pattern_backtest.py, 扩展 --universe 双宇宙)

对 patterns.py 识别的五类形态在本地库全历史上回测:
  买入基准: 信号次日开盘价（杜绝未来函数）; 统计未来 5/10/20 日收盘收益与期间最大涨幅。

输出六份报告:
  1. 形态×变体胜率总表
  2. 关键点位分层（命中均线/斐波那契档位的胜率差异）
  3. 波段结构阶段分层（wave_phase）
  4. 分形态因子分层（qcut 四层, 找"涨 vs 不涨"的技术共性）
  5. 推荐精细筛选阈值（每形态自动搜索, 可回写 patterns.PATTERN_FILTERS）
  6. 分年度胜率

用法:
    python -m eastmoney_quant_mcp.strategies.pattern_backtest --sample 300 --workers 8
    python -m eastmoney_quant_mcp.strategies.pattern_backtest --workers 8
    python -m eastmoney_quant_mcp.strategies.pattern_backtest --universe sectors --workers 8
    python -m eastmoney_quant_mcp.strategies.pattern_backtest --cache signals.csv
    python -m eastmoney_quant_mcp.strategies.pattern_backtest --csv out.csv
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .patterns import (
    BACKTEST_START, PATTERN_NAMES, detect_patterns, get_universe_list, prepare_df,
)

FORWARD_DAYS = (5, 10, 20)
MIN_GROUP = 100          # 分层统计最小样本量
NUM_FACTORS = [
    "score", "turnover", "turnover_ma20", "updown_ratio_20", "up_days_ratio_20",
    "vol_ratio", "pullback_vol_shrink", "rsi14", "bias60", "change_rate",
    "break_days", "break_depth", "potential_gain",
    "macd_gold3", "dif_below0", "kdj_gold3", "kdj_j", "boll_pos", "boll_width",
    "rsi6", "macd_div",
]


# ---------------------------------------------------------------------------
# 单标的回测
# ---------------------------------------------------------------------------

def backtest_one(args: tuple) -> list[dict]:
    universe, symbol, name, start, end, patterns, ma_windows, tolerance = args
    try:
        df = prepare_df(universe, symbol, start=start, end=end)
        if len(df) < 300:
            return []
        sigs = detect_patterns(df, symbol, name, patterns, ma_windows, tolerance)
        if not sigs:
            return []
        dates = df["date"].tolist()
        idx_map = {d: k for k, d in enumerate(dates)}
        open_a = df["open"].to_numpy(dtype=float)
        close_a = df["close"].to_numpy(dtype=float)
        high_a = df["high"].to_numpy(dtype=float)
        n = len(df)
        out = []
        for sig in sigs:
            i = idx_map[sig["date"]]
            if i + 1 >= n:
                continue                      # 无次日开盘, 无法买入
            entry = open_a[i + 1]
            if not (entry > 0):
                continue
            sig["entry"] = float(entry)
            for nd in FORWARD_DAYS:
                j = i + 1 + nd
                if j < n:
                    sig[f"ret_{nd}"] = float(close_a[j] / entry - 1.0)
                    sig[f"max_gain_{nd}"] = float(high_a[i + 1:j + 1].max() / entry - 1.0)
                else:
                    sig[f"ret_{nd}"] = np.nan
                    sig[f"max_gain_{nd}"] = np.nan
            out.append(sig)
        return out
    except Exception as e:
        print(f"  [warn] {universe} {symbol} {name}: {e}", flush=True)
        return []


def collect_signals(universe: str, start: str, end: str | None,
                    patterns: list[str] | None,
                    ma_windows: tuple[int, ...], tolerance: float,
                    sample: int | None, workers: int) -> pd.DataFrame:
    stocks = get_universe_list(universe)
    if sample and sample < len(stocks):
        stocks = stocks.sample(n=sample, random_state=42).reset_index(drop=True)
        print(f"抽样 {len(stocks)} 只标的 (random_state=42)")
    tasks = [(universe, row.symbol, row.name, start, end, patterns, ma_windows,
              tolerance) for row in stocks.itertuples()]
    all_sigs: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(backtest_one, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            all_sigs.extend(fut.result())
            done += 1
            if done % 200 == 0:
                print(f"进度: {done}/{len(tasks)} ({done / len(tasks):.0%}) 信号={len(all_sigs)}",
                      flush=True)
    label = "板块" if universe == "sectors" else "股票"
    print(f"检测完成: {len(stocks)} 个{label}, 共 {len(all_sigs)} 个信号")
    return pd.DataFrame(all_sigs)


# ---------------------------------------------------------------------------
# 统计 helper
# ---------------------------------------------------------------------------

def _win(s: pd.Series) -> float:
    s = s.dropna()
    return (s > 0).mean() * 100 if len(s) else np.nan


def _avg(s: pd.Series) -> float:
    return s.mean() * 100 if s.notna().any() else np.nan


def _pnl_ratio(s: pd.Series) -> float:
    s = s.dropna()
    if len(s) < 2:
        return np.nan
    gains, losses = s[s > 0], s[s <= 0]
    if len(losses) == 0 or losses.mean() == 0:
        return np.nan
    return gains.mean() / abs(losses.mean())


def _fmt(df: pd.DataFrame, pct_cols: list[str]) -> str:
    out = df.copy()
    for c in pct_cols:
        if c in out.columns:
            out[c] = out[c].map(lambda v: f"{v:.1f}" if v == v else "-")
    return out.to_string(index=False)


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def report_overall(df: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print("报告1: 形态×变体 胜率总表（买入=次日开盘; 胜率=收益>0 占比）")
    print("=" * 90)
    rows = []
    for (pat, var), g in df.groupby(["pattern_cn", "variant"]):
        rows.append({
            "形态": pat, "变体": var, "样本": len(g),
            "胜率5d%": _win(g["ret_5"]), "胜率10d%": _win(g["ret_10"]),
            "胜率20d%": _win(g["ret_20"]),
            "均收10d%": _avg(g["ret_10"]), "中位10d%": g["ret_10"].median() * 100,
            "盈亏比10d": _pnl_ratio(g["ret_10"]),
            "最大涨10d%": _avg(g["max_gain_10"]),
        })
    rep = pd.DataFrame(rows).sort_values("样本", ascending=False)
    print(_fmt(rep, ["胜率5d%", "胜率10d%", "胜率20d%", "均收10d%", "中位10d%",
                     "盈亏比10d", "最大涨10d%"]))


def report_levels(df: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print("报告2: 关键点位分层（hit_levels 拆分统计; 多点位命中的信号计入多行）")
    print("=" * 90)
    rows = []
    for pat, g in df.groupby("pattern_cn"):
        if g["hit_levels"].isna().all():
            continue
        ex = g.assign(level=g["hit_levels"].str.split(",")).explode("level")
        ex["level"] = ex["level"].str.strip()
        for lv, gg in ex.groupby("level"):
            if len(gg) < 30:
                continue
            rows.append({
                "形态": pat, "点位": lv, "样本": len(gg),
                "胜率10d%": _win(gg["ret_10"]), "均收10d%": _avg(gg["ret_10"]),
                "胜率20d%": _win(gg["ret_20"]),
            })
    if not rows:
        print("（无点位命中数据）")
        return
    rep = pd.DataFrame(rows).sort_values(["形态", "胜率10d%"], ascending=[True, False])
    print(_fmt(rep, ["胜率10d%", "均收10d%", "胜率20d%"]))


def report_wave(df: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print("报告3: 波段结构阶段分层（wave_phase）")
    print("=" * 90)
    rows = []
    for (pat, wp), g in df.groupby(["pattern_cn", "wave_phase"]):
        if len(g) < 30:
            continue
        rows.append({
            "形态": pat, "阶段": wp, "样本": len(g),
            "胜率10d%": _win(g["ret_10"]), "均收10d%": _avg(g["ret_10"]),
            "胜率20d%": _win(g["ret_20"]),
        })
    if not rows:
        print("（无阶段数据）")
        return
    rep = pd.DataFrame(rows).sort_values(["形态", "胜率10d%"], ascending=[True, False])
    print(_fmt(rep, ["胜率10d%", "均收10d%", "胜率20d%"]))


def report_factors(df: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print(f"报告4: 分形态因子分层（qcut 四分位; 仅样本>={MIN_GROUP} 的因子; 胜率为10日）")
    print("=" * 90)
    rows = []
    for pat, g in df.groupby("pattern_cn"):
        for fac in NUM_FACTORS:
            s = g[fac].dropna()
            if len(s) < MIN_GROUP or s.nunique() < 4:
                continue
            try:
                bins = pd.qcut(s, 4, duplicates="drop")
            except ValueError:
                continue
            tmp = g.loc[s.index].copy()
            tmp["layer"] = bins
            for layer, gg in tmp.groupby("layer", observed=True):
                rows.append({
                    "形态": pat, "因子": fac,
                    "区间": f"[{layer.left:.3g},{layer.right:.3g}]",
                    "样本": len(gg), "胜率10d%": _win(gg["ret_10"]),
                    "均收10d%": _avg(gg["ret_10"]),
                })
    if not rows:
        print("（样本不足）")
        return
    rep = pd.DataFrame(rows)
    for pat in rep["形态"].unique():
        print(f"\n--- {pat} ---")
        sub = rep[rep["形态"] == pat].sort_values(["因子", "胜率10d%"])
        print(_fmt(sub, ["胜率10d%", "均收10d%"]))


def report_filter_search(df: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print("报告5: 推荐精细筛选阈值（每形态贪心搜索2个因子; 子样本>="
          f"{MIN_GROUP}; 可回写 patterns.PATTERN_FILTERS）")
    print("=" * 90)

    def best_split(g: pd.DataFrame, used: set[tuple]) -> tuple | None:
        base = _win(g["ret_10"])
        best = None
        for fac in NUM_FACTORS:
            if fac in used or fac not in g.columns:
                continue
            s = g[fac].dropna()
            if len(s) < MIN_GROUP or s.nunique() < 3:
                continue
            cuts = s.quantile([0.2, 0.4, 0.6, 0.8]).drop_duplicates()
            for q, cut in cuts.items():
                for direction in (">=", "<="):
                    sub = g[g[fac] <= cut] if direction == "<=" else g[g[fac] >= cut]
                    if len(sub) < MIN_GROUP or len(sub) > len(g) * 0.9:
                        continue
                    w = _win(sub["ret_10"])
                    lift = w - base
                    if np.isnan(w):
                        continue
                    cand = (lift, w, base, fac, direction, float(cut), len(sub))
                    if best is None or lift > best[0]:
                        best = cand
        return best

    for pat, g in df.groupby("pattern_cn"):
        g = g.dropna(subset=["ret_10"])
        if len(g) < MIN_GROUP:
            print(f"\n--- {pat}: 样本 {len(g)} 不足, 跳过 ---")
            continue
        base = _win(g["ret_10"])
        used: set[str] = set()
        cur = g
        steps = []
        for _ in range(2):
            best = best_split(cur, used)
            if best is None or best[0] <= 0.5:
                break
            lift, w, b, fac, direction, cut, nsub = best
            used.add(fac)
            cur = cur[cur[fac] <= cut] if direction == "<=" else cur[cur[fac] >= cut]
            steps.append((fac, direction, cut, w, nsub))
        print(f"\n--- {pat} (基线胜率 {base:.1f}%, 样本 {len(g)}) ---")
        if not steps:
            print("  未找到显著提升的单一因子阈值（基线已较优或样本不足）")
            continue
        for fac, direction, cut, w, nsub in steps:
            print(f"  {fac} {direction} {cut:.4g}  -> 胜率 {w:.1f}% (样本 {nsub})")
        print(f"  建议过滤: {pat}: " + "; ".join(
            f"{fac} {direction} {cut:.4g}" for fac, direction, cut, _, _ in steps))


def report_yearly(df: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print("报告6: 分年度胜率（10日, 检验稳定性）")
    print("=" * 90)
    tmp = df.copy()
    tmp["year"] = tmp["date"].str[:4]
    rows = []
    for (pat, yr), g in tmp.groupby(["pattern_cn", "year"]):
        if len(g) < 30:
            continue
        rows.append({"形态": pat, "年份": yr, "样本": len(g),
                     "胜率10d%": _win(g["ret_10"]), "均收10d%": _avg(g["ret_10"])})
    if not rows:
        print("（样本不足）")
        return
    rep = pd.DataFrame(rows)
    pivot = rep.pivot(index="形态", columns="年份", values="胜率10d%")
    counts = rep.pivot(index="形态", columns="年份", values="样本")
    print("\n胜率% (样本数):")
    for pat in pivot.index:
        cells = []
        for yr in pivot.columns:
            v, n = pivot.loc[pat, yr], counts.loc[pat, yr]
            cell = "-" if v != v else f"{v:.0f}%({int(n) if n == n else 0})"
            cells.append(f"{yr}: {cell}")
        print(f"  {pat}: " + "  ".join(cells))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_patterns(text: str | None) -> list[str] | None:
    if not text:
        return None
    keys = []
    for tok in text.replace("，", ",").split(","):
        tok = tok.strip()
        if tok in PATTERN_NAMES:
            keys.append(tok)
        else:
            matched = [k for k, cn in PATTERN_NAMES.items() if tok and (tok in cn or cn in tok)]
            keys.extend(matched)
    return list(dict.fromkeys(keys)) or None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="eastmoney-quant pattern-backtest",
        description="形态信号历史回测与技术共性分析")
    parser.add_argument("--universe", default="stocks", choices=("stocks", "sectors"),
                        help="标的宇宙: stocks(股票, 默认) | sectors(板块)")
    parser.add_argument("--start", default=BACKTEST_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--patterns", default=None, help="逗号分隔形态 key/中文名")
    parser.add_argument("--ma", default="20,60,120,250")
    parser.add_argument("--tolerance", type=float, default=0.015)
    parser.add_argument("--sample", type=int, default=None, help="随机抽样标的人数(快跑验证)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--csv", default=None, help="导出信号明细 CSV")
    parser.add_argument("--cache", default=None, help="信号缓存 CSV（存在则直接读取）")
    args = parser.parse_args(argv)

    patterns = parse_patterns(args.patterns)
    ma_windows = tuple(int(x) for x in args.ma.split(","))

    if args.cache and Path(args.cache).exists():
        print(f"读取缓存信号: {args.cache}")
        df = pd.read_csv(args.cache, dtype={"symbol": str})
        df["name"] = df.get("name", "")
        if "universe" not in df.columns:
            df["universe"] = args.universe
    else:
        df = collect_signals(args.universe, args.start, args.end, patterns,
                             ma_windows, args.tolerance, args.sample, args.workers)
        if df.empty:
            print("无信号, 结束")
            return
        if args.cache:
            df.to_csv(args.cache, index=False)
            print(f"信号已缓存: {args.cache}")

    if "universe" in df.columns and df["universe"].nunique() > 1:
        df = df[df["universe"] == args.universe].reset_index(drop=True)
        print(f"已按 --universe={args.universe} 过滤, 剩余 {len(df)} 个信号")

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"信号明细已导出: {args.csv}")

    print(f"\n信号总数 {len(df)}, 涉及标的 {df['symbol'].nunique()} 个, "
          f"日期 {df['date'].min()} ~ {df['date'].max()}")

    report_overall(df)
    report_levels(df)
    report_wave(df)
    report_factors(df)
    report_filter_search(df)
    report_yearly(df)


if __name__ == "__main__":
    main(sys.argv[1:])
