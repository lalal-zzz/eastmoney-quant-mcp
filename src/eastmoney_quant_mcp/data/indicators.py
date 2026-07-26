"""
技术指标计算模块

MA, RSI, MACD, BOLL, KDJ, VOL_MA, ATR
"""

import numpy as np
import pandas as pd


def calc_ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_hist = 2 * (dif - dea)
    return dif, dea, macd_hist


def calc_boll(close: pd.Series, window: int = 20, num_std: float = 2.0):
    middle = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3):
    lowest_low = low.rolling(window=n, min_periods=n).min()
    highest_high = high.rolling(window=n, min_periods=n).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1.0 / m1, min_periods=m1, adjust=False).mean()
    d = k.ewm(alpha=1.0 / m2, min_periods=m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def compute_all_indicators(kline_df: pd.DataFrame) -> pd.DataFrame:
    """对已排序的 K 线 DataFrame 计算全部指标"""
    result = kline_df.copy()
    close = result["close"]
    high = result["high"]
    low = result["low"]
    volume = result["volume"]

    for w in [5, 10, 20, 30, 60, 100, 200]:
        result[f"MA{w}"] = calc_ma(close, w)
    for p in [6, 14, 24]:
        result[f"RSI{p}"] = calc_rsi(close, p)

    dif, dea, macd_hist = calc_macd(close)
    result["DIF"] = dif
    result["DEA"] = dea
    result["MACD"] = macd_hist

    upper, middle, lower = calc_boll(close)
    result["BOLL_UPPER"] = upper
    result["BOLL_MIDDLE"] = middle
    result["BOLL_LOWER"] = lower

    k, d, j = calc_kdj(high, low, close)
    result["K"] = k
    result["D"] = d
    result["J"] = j

    for w in [5, 10]:
        result[f"VOL_MA{w}"] = volume.rolling(window=w, min_periods=w).mean()

    result["ATR14"] = calc_atr(high, low, close, 14)

    return result
