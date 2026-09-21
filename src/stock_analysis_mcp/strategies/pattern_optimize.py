"""
strategies/pattern_optimize.py — 形态信号"优中选优"深度搜索 + 标准基线生成
(移植自"股票信息"项目 patterns/pattern_optimize.py, 支持股票/板块双宇宙)

在每形态内部用 beam search 搜索多因子阈值组合（数值因子分位切分 + 类别因子），
把 10 日收盘胜率推向目标（默认 80%），接受样本收缩——优中选优。

防过拟合: 按时间分割训练/验证（默认 2011-2021 训练, 2022-2026 验证），
报告 train/test 两段胜率差距; 全部尝试（每层 top 候选）写入 --md 指定文件。

用法:
    python -m stock_analysis_mcp.strategies.pattern_optimize --cache signals.csv
    python -m stock_analysis_mcp.strategies.pattern_optimize --cache signals.csv \\
        --universe sectors --target 0.75 --min-samples 80
    python -m stock_analysis_mcp.strategies.pattern_optimize --cache signals.csv --md trials.md
"""

import argparse
import itertools
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

NUM_FACTORS = [
    "score", "turnover", "turnover_ma20", "updown_ratio_20", "up_days_ratio_20",
    "vol_ratio", "pullback_vol_shrink", "rsi14", "bias60", "change_rate",
    "break_days", "break_depth", "potential_gain",
]
CAT_RULES = {
    "variant": None,        # 等值, 值在数据里发现
    "wave_phase": None,
    "fib_level": None,
}
QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


@dataclass
class Rule:
    factor: str
    op: str            # '<=' '>=' '==' 'contains'
    value: object

    def __str__(self):
        v = self.value
        v = f"{v:.4g}" if isinstance(v, float) else v
        return f"{self.factor}{self.op}{v}"


@dataclass
class Cand:
    rules: list = field(default_factory=list)
    mask: np.ndarray | None = None
    n: int = 0
    win: float = 0.0
    avg: float = 0.0


def rule_mask(df: pd.DataFrame, rule: Rule) -> np.ndarray:
    col = df[rule.factor]
    if rule.op == "<=":
        return (col <= rule.value).to_numpy()
    if rule.op == ">=":
        return (col >= rule.value).to_numpy()
    if rule.op == "==":
        return (col == rule.value).to_numpy()
    if rule.op == "contains":
        return col.astype(str).str.contains(str(rule.value), regex=False).to_numpy()
    raise ValueError(rule.op)


def gen_rules(sub: pd.DataFrame) -> list[Rule]:
    rules = []
    for f in NUM_FACTORS:
        s = sub[f].dropna()
        if len(s) < 30 or s.nunique() < 3:
            continue
        for q in QUANTILES:
            cut = float(s.quantile(q))
            rules.append(Rule(f, "<=", cut))
            rules.append(Rule(f, ">=", cut))
    for f in ("variant", "wave_phase", "fib_level"):
        if f not in sub.columns:
            continue
        for v in sub[f].dropna().unique()[:12]:
            rules.append(Rule(f, "==", v))
    return rules


def beam_search(g: pd.DataFrame, beam_width: int, max_depth: int,
                min_n: int, target: float, trials: list) -> list[Cand]:
    g = g.reset_index(drop=True)
    base_mask = np.ones(len(g), dtype=bool)
    beam = [Cand([], base_mask, len(g), 0.0, 0.0)]
    finals: list[Cand] = []
    for depth in range(1, max_depth + 1):
        pool: dict[str, Cand] = {}
        for cand in beam:
            sub = g[cand.mask]
            if len(sub) < min_n:
                continue
            for rule in gen_rules(sub):
                m = cand.mask & rule_mask(g, rule)
                n = int(m.sum())
                if n < min_n or n > cand.n * 0.95:      # 避免无信息切分
                    continue
                ret = g.loc[m, "ret_10"]
                if len(ret) < min_n:
                    continue
                win = float((ret > 0).mean())
                new = Cand(cand.rules + [rule], m, n, win, float(ret.mean()))
                key = ";".join(str(r) for r in new.rules)
                prev = pool.get(key)
                if prev is None or new.win > prev.win:
                    pool[key] = new
                trials.append((depth, key, n, win))
        if not pool:
            break
        ranked = sorted(pool.values(), key=lambda c: -c.win)[:beam_width]
        beam = ranked
        finals.extend(ranked)
        if ranked[0].win >= target:
            break
    return finals


def eval_rules(df: pd.DataFrame, rules: list[Rule]) -> dict:
    m = np.ones(len(df), dtype=bool)
    for r in rules:
        m &= rule_mask(df, r)
    sub = df[m]
    out = {"n": len(sub)}
    if len(sub) == 0:
        return out
    r10 = sub["ret_10"].dropna()
    out["win10"] = float((r10 > 0).mean()) if len(r10) else np.nan
    out["avg10"] = float(r10.mean()) if len(r10) else np.nan
    mg = sub["max_gain_10"].dropna()
    out["ever_up2"] = float((mg > 0.02).mean()) if len(mg) else np.nan
    out["avg_max_gain"] = float(mg.mean()) if len(mg) else np.nan
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="stock-analysis pattern-optimize",
        description="形态信号优中选优 beam search")
    ap.add_argument("--cache", default="signals_full.csv")
    ap.add_argument("--universe", default=None, choices=("stocks", "sectors"),
                    help="仅优化指定宇宙的信号(默认全部; 需信号含 universe 列)")
    ap.add_argument("--target", type=float, default=0.80)
    ap.add_argument("--min-samples", type=int, default=100)
    ap.add_argument("--beam", type=int, default=6)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--split", default="2022-01-01", help="train/test 分割日")
    ap.add_argument("--md", default=None, help="把全部尝试写入 markdown 文件")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.cache, dtype={"symbol": str})
    if "universe" in df.columns and args.universe:
        df = df[df["universe"] == args.universe].reset_index(drop=True)
        print(f"已按 --universe={args.universe} 过滤, 剩余 {len(df)} 个信号")
    if args.universe != "sectors":
        # 股票代码补零; 板块符号 (BKxxxx) 不处理
        df["symbol"] = df["symbol"].str.zfill(6)
    df = df.dropna(subset=["ret_10"]).reset_index(drop=True)
    train = df[df["date"] < args.split].reset_index(drop=True)
    test = df[df["date"] >= args.split].reset_index(drop=True)
    print(f"信号 {len(df)} (train {len(train)} / test {len(test)}), "
          f"目标胜率 {args.target:.0%}, 最小样本 {args.min_samples}, "
          f"beam {args.beam} x depth {args.depth}\n")

    all_trials: list = []
    strict_rules: dict[str, list] = {}
    for pat, g_train in train.groupby("pattern"):
        trials: list = []
        finals = beam_search(g_train, args.beam, args.depth,
                             args.min_samples, args.target, trials)
        all_trials.append((pat, trials))
        # 选 train 胜率最高者; 平手取样本多者
        if not finals:
            print(f"--- {pat}: 无满足条件的组合 ---\n")
            continue
        best = max(finals, key=lambda c: (c.win, c.n))
        ev_tr = eval_rules(g_train, best.rules)
        ev_te = eval_rules(test[test["pattern"] == pat].reset_index(drop=True), best.rules)
        ev_all = eval_rules(df[df["pattern"] == pat].reset_index(drop=True), best.rules)
        strict_rules[pat] = best.rules
        print(f"--- {pat} ---")
        print(f"  规则: {' & '.join(str(r) for r in best.rules)}")
        print(f"  train: n={ev_tr['n']} win10={ev_tr.get('win10', 0) * 100:.1f}% "
              f"avg={ev_tr.get('avg10', 0) * 100:+.2f}%")
        if ev_te.get("n"):
            print(f"  test : n={ev_te['n']} win10={ev_te.get('win10', 0) * 100:.1f}% "
                  f"avg={ev_te.get('avg10', 0) * 100:+.2f}%  "
                  f"(train-test 差距 = 过拟合警报)")
        print(f"  全期 : n={ev_all['n']} win10={ev_all.get('win10', 0) * 100:.1f}% "
              f"曾涨2%={ev_all.get('ever_up2', 0) * 100:.1f}%\n")

    # 合并池: 各形态 strict 信号合并的总体表现
    rows = []
    for pat, rules in strict_rules.items():
        m = np.ones(len(test), dtype=bool)
        d = test["pattern"] == pat
        for r in rules:
            m &= rule_mask(test, r)
        rows.append(pd.Series(m & d))
    if rows:
        pool = pd.concat(rows, axis=1).any(axis=1)
        sub = test[pool]
        r10 = sub["ret_10"].dropna()
        print(f"=== 合并池（各形态 strict 信号合集, test 段 {args.split}+） ===")
        print(f"  n={len(sub)} win10={(r10 > 0).mean() * 100:.1f}% "
              f"avg={r10.mean() * 100:+.2f}% "
              f"曾涨2%={(sub['max_gain_10'] > 0.02).mean() * 100:.1f}%")
        yr = sub.assign(y=sub["date"].str[:4]).groupby("y")["ret_10"]
        for y, s in yr:
            print(f"    {y}: n={len(s)} win10={(s > 0).mean() * 100:.0f}%")

    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write("# 优中选优搜索 — 全部尝试记录\n\n")
            fh.write(f"数据: {args.cache}, train<{args.split}, target={args.target:.0%}, "
                     f"min_samples={args.min_samples}, beam={args.beam}, depth={args.depth}"
                     f"{', universe=' + args.universe if args.universe else ''}\n\n")
            for pat, trials in all_trials:
                fh.write(f"## {pat}\n\n| 层 | 组合 | 样本 | train胜率 |\n|---|---|---|---|\n")
                seen = set()
                for depth, key, n, win in trials:
                    if key in seen:
                        continue
                    seen.add(key)
                    fh.write(f"| {depth} | {key} | {n} | {win * 100:.1f}% |\n")
                fh.write("\n")
        print(f"\n全部尝试已写入: {args.md}")


if __name__ == "__main__":
    main(sys.argv[1:])
