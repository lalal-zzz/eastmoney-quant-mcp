"""K线图渲染: 日K → 周K/月K 重采样, 输出供视觉分析的蜡烛图 + 量能图。

供 chart-trend-analysis Skill / render_stock_charts MCP 工具使用: 把日K数据
画成图片, 由 Agent 读图做形态 / 波浪 / 量价关系分析。纯 matplotlib 实现,
无 mplfinance 依赖。matplotlib 属可选依赖 (chart extra), 延迟到渲染时导入。
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

from .data.network import normalize_symbol

UP_COLOR = "#d64541"    # A股习惯: 涨红
DOWN_COLOR = "#2e8b57"  # 跌绿
MA_SPECS = [(5, "#f39c12"), (10, "#2980b9"), (20, "#8e44ad"), (60, "#16a085")]


def _plt():
    """延迟导入 matplotlib 并固定无显示后端 (避免 import 本模块就污染宿主进程后端)。"""
    try:
        import matplotlib
    except ImportError as e:
        raise RuntimeError(
            "图表渲染需要 chart extra: pip install 'eastmoney-quant-mcp[chart]'") from e
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # Windows 下中文字体; 找不到时 matplotlib 自动回退, 仅图例可能乱码
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "PingFang SC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt

UP_COLOR = "#d64541"    # A股习惯: 涨红
DOWN_COLOR = "#2e8b57"  # 跌绿
MA_SPECS = [(5, "#f39c12"), (10, "#2980b9"), (20, "#8e44ad"), (60, "#16a085")]


def _to_df(klines: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(klines)
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "close", "high", "low"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")
    return df.dropna(subset=["date", "open", "close", "high", "low"]).sort_values("date").reset_index(drop=True)


def resample_daily(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """日K → 周K(rule='W-FRI') / 月K(rule='ME')。收盘取周期最后一日, 高低取周期极值。"""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    out = (df.set_index("date")
             .resample(rule)
             .agg(agg)
             .dropna(subset=["open", "close", "high", "low"])
             .reset_index())
    return out


def _draw_candles(ax, df: pd.DataFrame):
    from matplotlib.patches import Rectangle
    x = range(len(df))
    width = 0.6
    for i, row in df.iterrows():
        up = row["close"] >= row["open"]
        color = UP_COLOR if up else DOWN_COLOR
        # 影线
        ax.vlines(i, row["low"], row["high"], color=color, linewidth=0.8, zorder=2)
        # 实体: 阳线空心(白芯), 阴线实心
        bottom = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), row["close"] * 1e-4)
        face = "white" if up else color
        ax.add_patch(Rectangle((i - width / 2, bottom), width, height,
                               facecolor=face, edgecolor=color, linewidth=0.9, zorder=3))
    return x


def _add_mas(ax, df: pd.DataFrame):
    for n, color in MA_SPECS:
        if len(df) < n:
            continue
        ma = df["close"].rolling(n).mean()
        ax.plot(range(len(df)), ma, color=color, linewidth=1.1, label=f"MA{n}")
    if not df.empty:
        ax.legend(loc="upper left", fontsize=8, framealpha=0.5, ncol=len(MA_SPECS))


def _pivots(df: pd.DataFrame, kind: str, k: int = 5) -> list[tuple[int, float]]:
    """枢轴点: kind='low' 取波谷(左右各k根内最低), kind='high' 取波峰。返回 [(索引, 价)]。
    注: 每点 O(k) 切片, 日K几百根规模足够; 大数据量可再向量化。"""
    pts = []
    for i in range(k, len(df) - k):
        win = df.iloc[i - k:i + k + 1]
        if kind == "low" and df["low"].iloc[i] == win["low"].min():
            pts.append((i, float(df["low"].iloc[i])))
        elif kind == "high" and df["high"].iloc[i] == win["high"].max():
            pts.append((i, float(df["high"].iloc[i])))
    return pts


def _draw_trendlines(ax, df: pd.DataFrame):
    """Draw the same confirmed structures used by screening/key-level APIs."""
    from .strategies.structure import analyze_market_structure

    snapshot = analyze_market_structure(
        df, include_positions=False,
        scales={"chart": {"left": 5, "right": 5, "swing_min": 0.03}},
    )
    x_end = len(df) - 1
    active = [x for x in snapshot["trendlines"]
              if x["status"] == "confirmed" and x.get("kind", "trendline") == "trendline"]
    # Limit clutter while keeping the strongest current support and resistance.
    for role, color, label in (("support", "#c0392b", "确认支撑线"),
                               ("resistance", "#2980b9", "确认压力线")):
        matches = [x for x in active if x["role"] == role]
        if not matches:
            continue
        line = sorted(matches, key=lambda x: (-x["score"], -x["anchor2_idx"]))[0]
        y1 = line["anchor1_price"]
        draw_end = min(x_end, line.get("valid_until_idx") or x_end)
        y2 = y1 + line["slope"] * (draw_end - line["anchor1_idx"])
        ax.plot([line["anchor1_idx"], draw_end], [y1, y2], color=color,
                linewidth=1.6, linestyle="-", alpha=0.9, zorder=4)
        ax.scatter(list(line["touch_indices"]),
                   [y1 + line["slope"] * (i - line["anchor1_idx"])
                    for i in line["touch_indices"]],
                   s=18, color=color, zorder=5)
        ax.annotate(label, xy=(draw_end, y2), xytext=(-68, 10),
                    textcoords="offset points", color=color, fontsize=8)

    converted = [x for x in snapshot["trendlines"]
                 if x.get("kind") == "horizontal_level" and x.get("converted_level") is not None]
    for line in sorted(converted, key=lambda x: -x["score"])[:2]:
        color = "#c0392b" if line["role"] == "support" else "#2980b9"
        ax.axhline(line["converted_level"], color=color, linewidth=0.9,
                   linestyle=":", alpha=0.65, zorder=2)

    channels = [x for x in snapshot["channels"] if x["status"] == "confirmed"]
    if channels:
        channel = sorted(channels, key=lambda x: (-x["score"], -x["confirmation_idx"]))[0]
        start = min((*channel["lower_touches"], *channel["upper_touches"]))
        xs = list(range(start, x_end + 1))
        lower = [channel["lower_intercept"] + channel["slope"] * i for i in xs]
        upper = [channel["upper_intercept"] + channel["slope"] * i for i in xs]
        ax.plot(xs, lower, color="#8e44ad", linewidth=1.0, alpha=0.75, zorder=3)
        ax.plot(xs, upper, color="#8e44ad", linewidth=1.0, alpha=0.75, zorder=3)
        ax.fill_between(xs, lower, upper, color="#8e44ad", alpha=0.05, zorder=1)

    ranges = [x for x in snapshot["ranges"] if x["status"] == "confirmed"]
    if ranges:
        box = sorted(ranges, key=lambda x: (-x["score"], -x["end_idx"]))[0]
        ax.hlines([box["lower"], box["upper"]], box["start_idx"], x_end,
                  colors="#e67e22", linewidth=1.1, linestyles="--", alpha=0.8, zorder=3)

    # Show at most one recent W and one recent M so visual QA can verify that
    # the selected pivots and neckline match the candles without hiding price.
    patterns = [x for x in snapshot["double_patterns"] if x["status"] != "invalidated"]
    for pattern, color, label, text_offset in (("w_bottom", "#d35400", "W", (5, -18)),
                                               ("m_top", "#34495e", "M", (5, 18))):
        matches = [x for x in patterns if x["pattern"] == pattern]
        if not matches:
            continue
        item = sorted(matches, key=lambda x: (-x["right_idx"], -x["score"]))[0]
        xs = [item["left_idx"], item["middle_idx"], item["right_idx"]]
        ys = [item["left_price"], item["middle_price"], item["right_price"]]
        ax.plot(xs, ys, color=color, linewidth=1.4, alpha=0.9, zorder=5)
        ax.scatter(xs, ys, color=color, s=22, zorder=6)
        neck_end = item.get("breakout_idx") or x_end
        ax.hlines(item["neckline"], item["middle_idx"], neck_end,
                  colors=color, linewidth=1.0, linestyles="-.", alpha=0.8, zorder=4)
        ax.annotate(f"{label}:{item['status']}", xy=(item["right_idx"], item["right_price"]),
                    xytext=text_offset, textcoords="offset points", color=color, fontsize=8)


def _date_ticks(ax, df: pd.DataFrame, step: int):
    ticks = list(range(0, len(df), step))
    if ticks and ticks[-1] != len(df) - 1:
        ticks.append(len(df) - 1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([df["date"].iloc[i].strftime("%y-%m-%d") for i in ticks],
                       fontsize=8, rotation=0)
    ax.set_xlim(-1, len(df))


def render_kline_chart(df: pd.DataFrame, title: str, out_path: str,
                       figsize=(14, 8.5), dpi=120) -> str:
    """渲染 蜡烛图+MA+成交量 到 PNG, 返回文件路径。"""
    if df.empty:
        raise ValueError("empty kline data")
    plt = _plt()
    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=figsize, dpi=dpi, sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05})

    _draw_candles(ax_price, df)
    _add_mas(ax_price, df)
    _draw_trendlines(ax_price, df)
    ax_price.set_title(f"{title}   (生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')})",
                       fontsize=13, loc="left")
    ax_price.grid(True, linestyle="--", alpha=0.3)
    ax_price.set_ylabel("价格")
    # 现价参考线
    last = df.iloc[-1]
    ax_price.axhline(last["close"], color="#7f8c8d", linewidth=0.8, linestyle=":", alpha=0.8)

    colors = [UP_COLOR if c >= o else DOWN_COLOR
              for o, c in zip(df["open"], df["close"])]
    ax_vol.bar(range(len(df)), df["volume"].fillna(0), color=colors, width=0.6, alpha=0.75)
    ax_vol.set_ylabel("成交量")
    ax_vol.grid(True, linestyle="--", alpha=0.3)
    step = max(1, len(df) // 10)
    _date_ticks(ax_vol, df, step)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _default_out_dir() -> str:
    # 复用 core.config 的目录体系: Windows 默认 Desktop, Linux/macOS 默认 ~/.eastmoney-quant/data
    from .core.config import get_settings
    base = os.environ.get("EASTMONEY_DATA_DIR") or str(get_settings().data_root)
    return os.path.join(base, "K线图片")


def _stock_name(symbol: str) -> str:
    """从本地 stock_basic 查名称, 查不到回退代码本身。"""
    try:
        from .data.storage import query_stock_db
        rows = query_stock_db(
            "SELECT name FROM stock_basic WHERE symbol = ?", (normalize_symbol(symbol),))
        if rows and rows[0].get("name"):
            return str(rows[0]["name"])
    except Exception:
        pass
    return normalize_symbol(symbol)


def generate_analysis_charts(symbol: str, days: int = 1200,
                             out_dir: str | None = None,
                             klines: list[dict] | None = None) -> dict:
    """生成 日K/周K/月K 三张分析图, 返回 {daily, weekly, monthly} 图片路径。

    klines 可注入已取好的日K列表(便于测试); 否则本地优先, 本地不足
    (少于请求的 8 成)时经腾讯链路 fetch_kline_history 拉取全量前复权历史。
    """
    adjustment = "qfq"
    if klines is None:
        from .data.search import get_stock_kline_local
        history_days = max(days, 5000)
        klines = get_stock_kline_local(normalize_symbol(symbol), history_days)
        if len(klines) < min(days, history_days) * 0.8:
            try:
                from .data.sources import fetch_kline_history
                net = fetch_kline_history(symbol, adjust="qfq", limit=history_days)
                if len(net) > len(klines):
                    klines = net
            except Exception:
                pass  # 网络失败时用本地已有数据出图
    if not klines:
        raise RuntimeError(f"{symbol} 无可用日K数据, 请先 init_full_data/update_daily_data")

    df = _to_df(klines)
    price_cols = ["open", "high", "low", "close"]
    if (df[price_cols] <= 0).any().any():
        try:
            from .data.sources import fetch_kline_history
            hfq = _to_df(fetch_kline_history(symbol, adjust="hfq", limit=max(days, 5000)))
            if not hfq.empty and not (hfq[price_cols] <= 0).any().any():
                df = hfq
                adjustment = "hfq"
            else:
                last_bad = df.index[(df[price_cols] <= 0).any(axis=1)].max()
                df = df.iloc[int(last_bad) + 1:].reset_index(drop=True)
        except Exception:
            last_bad = df.index[(df[price_cols] <= 0).any(axis=1)].max()
            df = df.iloc[int(last_bad) + 1:].reset_index(drop=True)
    name = str(klines[-1].get("name") or _stock_name(symbol))
    out_dir = out_dir or _default_out_dir()
    stem = f"{name}_{normalize_symbol(symbol)}"

    daily = df.tail(days).reset_index(drop=True)
    daily_path = render_kline_chart(daily, f"{name}({symbol}) 日K ({len(daily)}日,{adjustment})",
                                    os.path.join(out_dir, f"{stem}_daily.png"))
    weekly = resample_daily(df, "W-FRI").tail(520).reset_index(drop=True)
    weekly_path = render_kline_chart(weekly, f"{name}({symbol}) 周K ({len(weekly)}周,{adjustment})",
                                     os.path.join(out_dir, f"{stem}_weekly.png"))
    monthly = resample_daily(df, "ME").tail(240).reset_index(drop=True)
    monthly_path = render_kline_chart(monthly, f"{name}({symbol}) 月K ({len(monthly)}月,{adjustment})",
                                      os.path.join(out_dir, f"{stem}_monthly.png"))
    return {"daily": daily_path, "weekly": weekly_path, "monthly": monthly_path,
            "bars": {"daily": len(daily), "weekly": len(weekly), "monthly": len(monthly)},
            "history_bars": len(df), "adjustment": adjustment}
