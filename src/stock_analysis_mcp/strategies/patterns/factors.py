"""patterns/factors.py — 因子列 (向量化预计算)"""

import numpy as np
import pandas as pd


def add_factor_columns(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    open_ = df["open"]
    yang = (close > open_).astype(int)
    yin = (close < open_).astype(int)
    up = (close > close.shift(1)).astype(int)

    df["updown_ratio_20"] = yang.rolling(20).sum() / yin.rolling(20).sum().replace(0, np.nan)
    df["up_days_ratio_20"] = up.rolling(20).mean()
    df["turnover_ma20"] = df["turnover"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["VOL_MA5"]
    df["ma_bull"] = ((df["MA5"] > df["MA10"]) & (df["MA10"] > df["MA20"])).astype(int)
    df["dif_above_zero"] = (df["DIF"] > 0).astype(int)
    df["bias60"] = df["close"] / df["MA60"] - 1.0
    # --- MACD / KDJ / BOLL 指标因子 ---
    df["macd_gold"] = ((df["DIF"] > df["DEA"]) & (df["DIF"].shift(1) <= df["DEA"].shift(1))).astype(int)
    df["macd_gold3"] = df["macd_gold"].rolling(3, min_periods=1).max().astype(int)   # 近3日金叉
    df["dif_below0"] = (df["DIF"] < 0).astype(int)                                   # 零轴下方(低位)
    df["kdj_gold"] = ((df["K"] > df["D"]) & (df["K"].shift(1) <= df["D"].shift(1))).astype(int)
    df["kdj_gold3"] = df["kdj_gold"].rolling(3, min_periods=1).max().astype(int)
    boll_span = df["BOLL_UPPER"] - df["BOLL_LOWER"]
    df["boll_pos"] = (df["close"] - df["BOLL_LOWER"]) / boll_span.replace(0, np.nan)  # 带内位置0~1
    df["boll_width"] = boll_span / df["BOLL_MIDDLE"].replace(0, np.nan)               # 带宽(收敛度)
    df["rsi6"] = df["RSI6"]
    # 信号日候选预筛列
    df["is_yang"] = yang.astype(bool)
    df["above_ma5"] = close > df["MA5"]
    df["break_high5"] = close > df["high"].rolling(5).max().shift(1)
    df["break_high10"] = close > df["high"].rolling(10).max().shift(1)
    df["break_close40"] = close > close.rolling(40).max().shift(1)
    return df
