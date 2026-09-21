import json
from pathlib import Path

import pandas as pd

from stock_analysis_mcp.charting import _to_df, resample_daily
from stock_analysis_mcp.data.search import get_stock_kline_local
from stock_analysis_mcp.strategies.structure import analyze_market_structure


SYMBOLS = ["600000", "000858", "300750", "601398"]
OUT = Path(__file__).with_name("structure_audit.json")


def atr(df: pd.DataFrame) -> pd.Series:
    previous = df["close"].astype(float).shift(1)
    true_range = pd.concat([
        df["high"].astype(float) - df["low"].astype(float),
        (df["high"].astype(float) - previous).abs(),
        (df["low"].astype(float) - previous).abs(),
    ], axis=1).max(axis=1)
    return true_range.rolling(14, min_periods=1).mean()


def audit_frame(df: pd.DataFrame) -> dict:
    snapshot = analyze_market_structure(
        df, scales={"chart": {"left": 5, "right": 5, "swing_min": 0.03}}
    )
    av = atr(df)
    line_errors = []
    confirmed_lines = [
        line for line in snapshot["trendlines"]
        if line["status"] == "confirmed" and line.get("kind", "trendline") == "trendline"
    ]
    for line in confirmed_lines:
        if len(line["touch_indices"]) < 3 or line["confirmation_idx"] is None:
            line_errors.append({"id": line["id"], "reason": "missing_third_touch"})
            continue
        if line["touch_indices"][2] <= line["anchor2_idx"]:
            line_errors.append({"id": line["id"], "reason": "third_touch_not_independent"})
        for idx in range(line["anchor1_idx"] + 1, len(df)):
            expected = line["anchor1_price"] + line["slope"] * (idx - line["anchor1_idx"])
            if line["role"] == "support":
                crossed = float(df.iloc[idx]["low"]) < expected - 0.5 * float(av.iloc[idx])
            else:
                crossed = float(df.iloc[idx]["high"]) > expected + 0.5 * float(av.iloc[idx])
            if crossed:
                line_errors.append({"id": line["id"], "reason": "wick_crossing", "idx": idx})
                break

    confirmed_channels = [x for x in snapshot["channels"] if x["status"] == "confirmed"]
    channel_errors = []
    for channel in confirmed_channels:
        start = channel["confirmation_idx"]
        if start is None or len(set(channel["lower_touches"])) < 2 or len(set(channel["upper_touches"])) < 2:
            channel_errors.append({"id": channel["id"], "reason": "unconfirmed_boundaries"})
            continue
        for idx in range(start, len(df)):
            lower = channel["lower_intercept"] + channel["slope"] * idx
            upper = channel["upper_intercept"] + channel["slope"] * idx
            if (float(df.iloc[idx]["low"]) < lower - 0.6 * float(av.iloc[idx]) or
                    float(df.iloc[idx]["high"]) > upper + 0.6 * float(av.iloc[idx])):
                channel_errors.append({"id": channel["id"], "reason": "wick_crossing", "idx": idx})
                break

    anchors = {x["id"]: x for x in snapshot["positions"]["anchors"]}
    fib_errors = []
    for zone in snapshot["positions"]["fib_zones"]:
        anchor = anchors[zone["anchor_id"]]
        lo, hi = sorted((anchor["a_price"], anchor["b_price"]))
        if not (lo <= zone["center"] <= hi):
            fib_errors.append({"id": zone["id"], "reason": "zone_outside_anchor"})
        expected = anchor["b_price"] - zone["ratio"] * (anchor["b_price"] - anchor["a_price"])
        if abs(zone["center"] - expected) > 1e-6:
            fib_errors.append({"id": zone["id"], "reason": "wrong_directional_formula"})
    current = float(df.iloc[-1]["close"])
    for item in snapshot["positions"]["retracements"]:
        anchor = anchors[item["anchor_id"]]
        move = anchor["b_price"] - anchor["a_price"]
        expected_retracement = (anchor["b_price"] - current) / move
        expected_position = (current - anchor["a_price"]) / move
        if abs(item["retracement_ratio"] - expected_retracement) > 1e-6:
            fib_errors.append({"id": item["anchor_id"], "reason": "wrong_retracement_ratio"})
        if abs(item["position_ratio"] - expected_position) > 1e-6:
            fib_errors.append({"id": item["anchor_id"], "reason": "wrong_position_ratio"})

    patterns = [x for x in snapshot["double_patterns"] if x["status"] != "invalidated"]
    return {
        "bars": len(df),
        "confirmed_trendlines": len(confirmed_lines),
        "converted_horizontal_levels": sum(x.get("kind") == "horizontal_level" for x in snapshot["trendlines"]),
        "confirmed_channels": len(confirmed_channels),
        "w_patterns": sum(x["pattern"] == "w_bottom" for x in patterns),
        "m_patterns": sum(x["pattern"] == "m_top" for x in patterns),
        "fib_anchors": len(anchors),
        "fib_zones": len(snapshot["positions"]["fib_zones"]),
        "line_errors": line_errors,
        "channel_errors": channel_errors,
        "fib_errors": fib_errors,
    }


result = {}
for symbol in SYMBOLS:
    daily_all = _to_df(get_stock_kline_local(symbol, 5000))
    bad = (daily_all[["open", "high", "low", "close"]] <= 0).any(axis=1)
    if bad.any():
        daily_all = daily_all.iloc[int(daily_all.index[bad].max()) + 1:].reset_index(drop=True)
    frames = {
        "daily": daily_all.tail(500).reset_index(drop=True),
        "weekly": resample_daily(daily_all, "W-FRI").tail(520).reset_index(drop=True),
        "monthly": resample_daily(daily_all, "ME").tail(240).reset_index(drop=True),
    }
    result[symbol] = {name: audit_frame(frame) for name, frame in frames.items()}

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUT)
