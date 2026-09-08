"""
strategies/patterns.py — 技术形态识别引擎
(移植自"股票信息"项目 patterns/stock_patterns.py, 扩展为股票/板块双宇宙)

识别五类上涨形态 (2010 年起, 纯技术面、客观可量化规则, 不使用主观数浪):
  trend_pullback  上涨趋势回调企稳 (回踩关键点位: 均线/斐波那契回调位/前高, 含假跌破)
  ma_rebound      下跌趋势中长均线 (季线/半年线/年线) 企稳反弹
  w_bottom        W底右底 (右底反弹 + 放量突破颈线两档信号)
  m_neckline      M形颈线支撑 (回调至颈线企稳, 博第二波上涨)
  box_breakout    平台箱体放量突破

关键点位引擎: 均线体系(周MA5/半月MA10/月MA20/MA30/季MA60/半年MA120/年MA250)
            + 斐波那契回调位(0.382/0.5/0.618/0.786, 基于最近上涨波段)
            + 结构位(颈线/前高/箱体沿), 多点命中计 resonance 共振数。
波段结构: pivot 序列构建 zigzag, 客观标记 wave_phase (首波回调/二次回调/突破新高...)。

标的宇宙 (universe 参数):
  "stocks"  → stock_kline + stock_indicators (symbol, date)      [本地库]
  "sectors" → sector_kline + sector_indicators (sector_code, trade_date) [本地库]
字段映射: 板块的 trade_date→date, turnover_rate→turnover; KDJ_K/KDJ_D/KDJ_J→K/D/J。
历史不足 MIN_BARS=260 的标的自动跳过 (历史短的板块自然过滤)。
板块首版沿用股票参数与过滤阈值, 待回测/优化后校准。

所有信号严格避免未来函数: pivot 在 right 根K线后才确认; 前向收益以次日开盘为基准
(回测在 pattern_backtest.py 中完成)。

供 MCP 工具使用的入口:
  scan_universe()     全市场/指定标的扫描 (scan_patterns / scan_sector_patterns)
  get_pattern_history() 单标的 (股票/板块) 历史信号列表
  get_key_levels()    单标的当前关键位 (MA/斐波那契/结构位)
"""

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.constants import MIN_PATTERN_BARS
from ..data.storage import get_stock_db, get_sector_db

BACKTEST_START = "2010-01-01"          # 回测/历史数据起点 (用户要求 2010 之后)
MIN_BARS = MIN_PATTERN_BARS             # backward-compatible public constant

PATTERN_NAMES = {
    "trend_pullback": "趋势回调企稳",
    "ma_rebound": "下跌均线反弹",
    "w_bottom": "W底右底",
    "m_neckline": "M形颈线支撑",
    "box_breakout": "平台放量突破",
}

# 每形态精细筛选 (per-pattern)。由 pattern_backtest.py v3 趋势上下文版全量回测校准
# (2011-2026, ~25万信号, 全期贪心2因子): 基线10日胜率 46.9~49.7% → 筛后 52.7~55.3%。
PATTERN_FILTERS = {
    "trend_pullback": {"change_rate": (None, 1.8), "potential_gain": (0.0, 0.028)},
    "w_bottom": {"change_rate": (None, 1.75), "turnover_ma20": (0.02, 0.6)},
    "m_neckline": {"bias60": (None, 0.04), "up_days_ratio_20": (0.6, None)},
    "box_breakout": {"vol_ratio": (1.0, 1.75), "change_rate": (None, 2.1)},
    "ma_rebound": {"up_days_ratio_20": (0.6, None), "bias60": (0.045, None)},
}

# 优中选优档: 后缀 _in 为类别条件 (字段值必须属于列表)
# 由 pattern_optimize.py 双稳健搜索产生 (train<2022 搜索, test 2022+ 时间外验证)。
PATTERN_STRICT_FILTERS = {
    "trend_pullback": {"change_rate": (None, 1.81), "fib_in": ["fib_618"]},
    "w_bottom": {"bias60": (None, -0.07), "vol_ratio": (0.4, 1.87)},
    "m_neckline": {"bias60": (None, 0.024), "change_rate": (None, 1.24)},
    "box_breakout": {"bias60": (None, 0.074), "turnover": (0.05, 1.16)},
    "ma_rebound": {"variant_in": ["MA250_hold"], "potential_gain": (0.01, 0.151)},
}

# 同形态信号冷却交易日数 (避免同一形态密集重复触发)
PATTERN_COOLDOWN = {
    "trend_pullback": 10, "ma_rebound": 20, "w_bottom": 15,
    "m_neckline": 15, "box_breakout": 15,
}

FIB_RATIOS = (0.382, 0.5, 0.618, 0.786)


# ---------------------------------------------------------------------------
# 标的宇宙 / 数据加载
# ---------------------------------------------------------------------------

def _universe_defs() -> dict:
    """Lazy universe definitions (paths computed on first access)."""
    return {
        # universe: (库路径, K线表, 指标表, 基础表, K线日期列, 标的ID列)
        "stocks": (get_stock_db(), "stock_kline", "stock_indicators", "stock_basic",
                   "date", "symbol"),
        "sectors": (get_sector_db(), "sector_kline", "sector_indicators", "sector_basic",
                    "trade_date", "sector_code"),
    }

_KLINE_COLS = ("open", "high", "low", "close", "volume")
_IND_COLS = ("MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
             "RSI6", "RSI14", "DIF", "DEA", "VOL_MA5", "VOL_MA10",
             "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER")


def _connect(universe: str) -> sqlite3.Connection:
    defs = _universe_defs()
    if universe not in defs:
        raise ValueError(f"unknown universe: {universe} (stocks|sectors)")
    return sqlite3.connect(defs[universe][0], timeout=60)


def load_pattern_df(universe: str, symbol: str, start: str = BACKTEST_START,
                    end: str | None = None, tail: int | None = None) -> pd.DataFrame:
    """读取单标的K线 + 指标缓存, 补算 MA120/MA250, 返回按日期升序的 DataFrame。

    股票/板块字段映射统一输出: date/open/high/low/close/volume/change_rate/turnover
    + 指标列 (K/D/J 由 KDJ_K/KDJ_D/KDJ_J 映射)。
    tail: 只取 start~end 范围内最后 N 行 (scan 加速用)。
    """
    db_path, kt, it, _bt, kdate_col, id_col = _universe_defs()[universe]
    id_field = f"h.{id_col}"
    stock_join = " AND c.adjust_type = h.adjust_type" if universe == "stocks" else ""
    stock_where = " AND h.adjust_type = 'qfq'" if universe == "stocks" else ""

    select_common = f"""
        SELECT h.{kdate_col} AS date, h.open, h.high, h.low, h.close,
               h.volume,
               h.change_pct AS change_rate, h.turnover_rate AS turnover,
               c.MA5, c.MA10, c.MA20, c.MA30, c.MA60, c.MA100, c.MA200,
               c.RSI14, c.DIF, c.DEA, c.VOL_MA5, c.VOL_MA10,
               c.RSI6, c.KDJ_K AS K, c.KDJ_D AS D, c.KDJ_J AS J,
               c.BOLL_UPPER, c.BOLL_MIDDLE, c.BOLL_LOWER
        FROM {kt} h
        LEFT JOIN {it} c
            ON c.{kdate_col} = h.{kdate_col} AND c.{id_col} = {id_field}{stock_join}
    """
    where = f"WHERE h.{id_col} = ? AND h.{kdate_col} >= ?{stock_where}"
    params: list = [symbol, start]
    if end:
        where += f" AND h.{kdate_col} <= ?"
        params.append(end)
    if tail:
        sql = (f"SELECT * FROM ({select_common} {where} "
               f"ORDER BY h.{kdate_col} DESC LIMIT {int(tail)}) ORDER BY date")
    else:
        sql = f"{select_common} {where} ORDER BY h.{kdate_col}"

    with sqlite3.connect(db_path, timeout=60) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return df

    num_cols = [c for c in df.columns if c != "date"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 补算指标缓存里没有的均线 + 防御性补算 (缓存整列缺失时)
    close = df["close"]
    for w in (120, 250):
        df[f"MA{w}"] = close.rolling(w, min_periods=w).mean()
    if df["VOL_MA5"].isna().all():
        df["VOL_MA5"] = df["volume"].rolling(5, min_periods=5).mean()
    if df["MA5"].isna().all():
        df["MA5"] = close.rolling(5, min_periods=5).mean()
    if df["RSI14"].isna().all():
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        rs = (gain.ewm(alpha=1 / 14, adjust=False).mean()
              / loss.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan))
        df["RSI14"] = 100 - 100 / (1 + rs)
    return df


def get_universe_list(universe: str, exclude_st: bool = True,
                      sector_type: str | None = None) -> pd.DataFrame:
    """标的清单 (symbol, name)。股票默认剔除 ST; 板块可按 sector_type 过滤。"""
    db_path, _kt, _it, bt, _kdate_col, id_col = _universe_defs()[universe]
    if universe == "stocks":
        sql = f"SELECT {id_col} AS symbol, name FROM {bt}"
        if exclude_st:
            sql += " WHERE name NOT LIKE '%ST%'"
        sql += " ORDER BY symbol"
    else:
        sql = f"SELECT {id_col} AS symbol, sector_name AS name FROM {bt}"
        if sector_type:
            sql += f" WHERE sector_type = ?"
        sql += " ORDER BY sector_code"
    with sqlite3.connect(db_path, timeout=60) as conn:
        params = (sector_type,) if (universe == "sectors" and sector_type) else ()
        return pd.read_sql_query(sql, conn, params=params)


def get_latest_trade_date(universe: str) -> str | None:
    db_path, kt, _it, _bt, kdate_col, _id_col = _universe_defs()[universe]
    with sqlite3.connect(db_path, timeout=60) as conn:
        suffix = " WHERE adjust_type='qfq'" if universe == "stocks" else ""
        row = conn.execute(f"SELECT MAX({kdate_col}) FROM {kt}{suffix}").fetchone()
    return row[0] if row else None


def resolve_universe_symbol(universe: str, query: str) -> tuple[str, str]:
    """按代码或名称解析标的 → (symbol, name)。未命中抛 ValueError。"""
    query = str(query).strip()
    db_path, _kt, _it, bt, _kdate_col, id_col = _universe_defs()[universe]
    name_col = "name" if universe == "stocks" else "sector_name"
    with sqlite3.connect(db_path, timeout=60) as conn:
        # 代码精确匹配优先 (兼容 'BK1090' / '1090' / 'sh600000' 等格式)
        candidates = [query]
        digits = "".join(ch for ch in query if ch.isdigit())
        if digits and digits != query:
            candidates.append(digits)
        for cand in candidates:
            row = conn.execute(
                f"SELECT {id_col}, {name_col} FROM {bt} WHERE {id_col} = ?", (cand,)).fetchone()
            if row:
                return row[0], row[1] or ""
        # 板块裸代码补 BK 前缀 (1090 → BK1090)
        if universe == "sectors" and digits and not query.upper().startswith("BK"):
            row = conn.execute(
                f"SELECT {id_col}, {name_col} FROM {bt} WHERE {id_col} = ?",
                (f"BK{digits}",)).fetchone()
            if row:
                return row[0], row[1] or ""
        # 名称模糊匹配
        rows = conn.execute(
            f"SELECT {id_col}, {name_col} FROM {bt} WHERE {name_col} LIKE ? "
            f"ORDER BY {id_col} LIMIT 1", (f"%{query}%",)).fetchall()
        if rows:
            return rows[0][0], rows[0][1] or ""
    raise ValueError(f"无法解析{('板块' if universe == 'sectors' else '股票')}: {query}")


# ---------------------------------------------------------------------------
# 摆动点 / zigzag 波段结构
# ---------------------------------------------------------------------------


@dataclass
class Pivot:
    idx: int          # 所在K线下标
    typ: str          # 'H' 高点 / 'L' 低点
    price: float
    confirm: int      # 确认下标 = idx + pivot_right (此前不可用, 避免未来函数)


def build_pivot_events(df: pd.DataFrame, left: int = 5, right: int = 5) -> list[Pivot]:
    """局部极值检测: high[i] 为 [i-left, i+right] 窗口最大值 -> 高点候选。

    相等平台产生的重复候选由 zigzag 清洗处理。
    """
    high = df["high"]
    low = df["low"]
    w = left + right + 1
    roll_max = high.rolling(w).max().shift(-right)
    roll_min = low.rolling(w).min().shift(-right)

    hv = high.to_numpy(dtype=float)
    lv = low.to_numpy(dtype=float)
    rm = roll_max.to_numpy(dtype=float)
    rmin = roll_min.to_numpy(dtype=float)

    events: list[Pivot] = []
    with np.errstate(invalid="ignore"):
        for idx in np.where(hv == rm)[0]:
            events.append(Pivot(int(idx), "H", hv[idx], int(idx) + right))
        for idx in np.where(lv == rmin)[0]:
            events.append(Pivot(int(idx), "L", lv[idx], int(idx) + right))
    events.sort(key=lambda p: (p.confirm, p.idx))
    return events


def update_zigzag(zz: list[Pivot], p: Pivot, swing_min: float = 0.03) -> None:
    """将已确认 pivot 并入交替波段序列: 同类型保留更极端, 异类型需满足最小摆动幅度。"""
    if not zz:
        zz.append(p)
        return
    last = zz[-1]
    if last.typ == p.typ:
        if (p.typ == "H" and p.price > last.price) or (p.typ == "L" and p.price < last.price):
            zz[-1] = p
        return
    if last.price <= 0 or p.price <= 0:
        return
    if abs(p.price / last.price - 1.0) >= swing_min:
        zz.append(p)


# ---------------------------------------------------------------------------
# 因子列 (向量化预计算)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 形态检测上下文
# ---------------------------------------------------------------------------


class _Ctx:
    """单标的检测上下文: numpy 数组 + 截至 current i 的 zigzag。"""

    _COLUMNS = ("open", "high", "low", "close", "volume", "change_rate",
                "turnover", "MA5", "MA10", "MA20", "MA30", "MA60", "MA100",
                "MA120", "MA200", "MA250", "RSI14", "DIF", "VOL_MA5",
                "updown_ratio_20", "up_days_ratio_20", "turnover_ma20",
                "vol_ratio", "ma_bull", "dif_above_zero", "bias60",
                "macd_gold3", "dif_below0", "kdj_gold3", "J", "K", "D",
                "boll_pos", "boll_width", "rsi6")

    def __init__(self, df: pd.DataFrame, ma_windows: tuple[int, ...]):
        self.df = df
        self.n = len(df)
        self.dates = df["date"].tolist()
        for col in self._COLUMNS:
            self.__setattr__(col, df[col].to_numpy(dtype=float))
        self.cand = {
            "rebound": df["is_yang"].to_numpy() & df["above_ma5"].to_numpy()
                       & df["break_high5"].to_numpy(),
            "yang_vol15": df["is_yang"].to_numpy() & (df["vol_ratio"].to_numpy() >= 1.5),
            "box": df["is_yang"].to_numpy() & df["break_close40"].to_numpy()
                   & (df["vol_ratio"].to_numpy() >= 1.5),
        }
        self.ma_windows = ma_windows
        self.zz: list[Pivot] = []

    def ma(self, w: int, i: int) -> float:
        return getattr(self, f"MA{w}")[i]



# 支持的均线窗口集合 —— 由 _Ctx._COLUMNS 单一来源派生, 避免两处硬编码漂移
MA_WINDOW_WHITELIST = frozenset(
    int(c[2:]) for c in _Ctx._COLUMNS if c.startswith("MA") and c[2:].isdigit()
)

def _valid(x: float) -> bool:
    return x is not None and not np.isnan(x)


def score_range(value: float, ideal_lo: float, ideal_hi: float,
                tol_lo: float, tol_hi: float) -> float:
    """形态标准度评分: 值在 [ideal_lo, ideal_hi] 内=1.0, 线性衰减到容忍边界 [tol_lo, tol_hi]=0。

    真实形态是"类似的"而非精确落在固定阈值内 —— 评分制让边界外的近似形态
    也能被识别 (低分), 而不是被硬性拒绝。返回 0~1。
    """
    if np.isnan(value):
        return 0.0
    if ideal_lo <= value <= ideal_hi:
        return 1.0
    if value < ideal_lo:
        span = ideal_lo - tol_lo
        return max(0.0, 1.0 - (ideal_lo - value) / span) if span > 0 else 0.0
    span = tol_hi - ideal_hi
    return max(0.0, 1.0 - (value - ideal_hi) / span) if span > 0 else 0.0


def wave_phase(ctx: _Ctx, i: int, lookback: int = 250) -> str:
    """客观波段阶段标记 (非主观数浪): 突破新高 / 首次回调 / 二次回调 / 后期回调。"""
    lo = max(0, i - lookback)
    seg = ctx.close[lo:i + 1]
    if len(seg) == 0:
        return ""
    if ctx.close[i] >= seg.max() * 0.995:
        return "breakout_new_high"
    nh = sum(1 for p in ctx.zz if p.typ == "H" and p.idx >= lo)
    return {1: "first_pullback", 2: "second_pullback"}.get(nh, "later_pullback")


def trend_context(ctx: _Ctx, i: int, lookback: int = 250,
                  min_span: float = 0.20) -> dict:
    """趋势上下文引擎 —— 一切形态判定的前置层。

    基于近 lookback 日的已确认 zigzag 波段:
      swing_high / swing_low  显著最高点与最低点 (斐波那契的锚点)
      结构: HH+HL (高点低点都抬高) = 上升结构; LH+LL = 下降结构
    判定:
      up   = 低点在前高点在后, 波段涨幅>=min_span, 且(站上MA120 或 HH/HL结构)
      down = 高点在前低点在后, 波段跌幅>=min_span, 且(跌破MA120 或 LH/LL结构)
      其余 = range 震荡
    """
    lo = i - lookback
    recent: list[Pivot] = []
    for p in reversed(ctx.zz):
        if p.idx < lo:
            break
        recent.append(p)
    recent.reverse()
    hs = [p for p in recent if p.typ == "H"]
    lls = [p for p in recent if p.typ == "L"]
    swing_high = max(hs, key=lambda p: p.price) if hs else None
    swing_low = min(lls, key=lambda p: p.price) if lls else None

    hh_hl = (len(hs) >= 2 and hs[-1].price > hs[-2].price
             and len(lls) >= 2 and lls[-1].price > lls[-2].price)
    lh_ll = (len(hs) >= 2 and hs[-1].price < hs[-2].price
             and len(lls) >= 2 and lls[-1].price < lls[-2].price)

    trend = "range"
    if swing_high is not None and swing_low is not None:
        span = swing_high.price / swing_low.price - 1.0
        if span >= min_span:
            ma120 = ctx.MA120[i]
            ma_ok_up = (not _valid(ma120)) or ctx.close[i] > ma120
            ma_ok_dn = (not _valid(ma120)) or ctx.close[i] < ma120
            if swing_low.idx < swing_high.idx and ma_ok_up and (hh_hl or span >= 0.30):
                trend = "up"
            elif swing_high.idx < swing_low.idx and ma_ok_dn and (lh_ll or span >= 0.30):
                trend = "down"
    return {"trend": trend, "swing_high": swing_high, "swing_low": swing_low,
            "hh_hl": hh_hl, "lh_ll": lh_ll}


def fib_levels_from_swings(tc: dict, peak_close: float | None = None) -> dict[str, float]:
    """斐波那契回调位 —— 以本轮趋势波段的最高点与最低点为锚。

    低点在前、高点在后 (上涨波段) → 从高点回撤的支撑位 0.382/0.5/0.618/0.786;
    高点在前、低点在后 (下跌波段) → 从低点反弹的压力位 0.382/0.5/0.618。
    peak_close: 若当前峰尚未确认为 pivot, 用它覆盖波段高点 (取更高者)。
    """
    sh, sl = tc.get("swing_high"), tc.get("swing_low")
    if sh is None or sl is None or sh.price <= 0 or sl.price <= 0:
        return {}
    if sl.idx < sh.idx:                          # 上涨波段 → 回调支撑位
        high = max(sh.price, peak_close) if peak_close else sh.price
        span = high - sl.price
        return {f"fib_{int(r * 1000)}": high - span * r for r in FIB_RATIOS}
    high, low = sh.price, sl.price               # 下跌波段 → 反弹压力位
    span = high - low
    return {f"retr_{int(r * 1000)}": low + span * r for r in (0.382, 0.5, 0.618)}


# ---------------------------------------------------------------------------
# 信号构造
# ---------------------------------------------------------------------------


def _base_signal(ctx: _Ctx, i: int, symbol: str, name: str, pattern: str,
                 variant: str, **extra) -> dict:
    sig = {
        "symbol": symbol,
        "name": name,
        "date": ctx.dates[i],
        "pattern": pattern,
        "pattern_cn": PATTERN_NAMES[pattern],
        "variant": variant,
        "close": round(ctx.close[i], 3),
        "change_rate": ctx.change_rate[i],
        "turnover": ctx.turnover[i],
        "turnover_ma20": ctx.turnover_ma20[i],
        "updown_ratio_20": ctx.updown_ratio_20[i],
        "up_days_ratio_20": ctx.up_days_ratio_20[i],
        "vol_ratio": ctx.vol_ratio[i],
        "pullback_vol_shrink": np.nan,
        "rsi14": ctx.RSI14[i],
        "ma_bull": int(ctx.ma_bull[i]),
        "dif_above_zero": int(ctx.dif_above_zero[i]),
        "bias60": ctx.bias60[i],
        "hit_levels": "",
        "fib_level": "",
        "resonance": 0,
        "wave_phase": "",
        "break_days": 0,
        "break_depth": 0.0,
        "potential_gain": np.nan,
        "score": 0.0,
        "trend": "",
        # MACD / KDJ / BOLL 指标因子 (0/1 或数值)
        "macd_gold3": int(ctx.macd_gold3[i]),
        "dif_below0": int(ctx.dif_below0[i]),
        "kdj_gold3": int(ctx.kdj_gold3[i]),
        "kdj_j": ctx.J[i],
        "boll_pos": ctx.boll_pos[i],
        "boll_width": ctx.boll_width[i],
        "rsi6": ctx.rsi6[i],
        "macd_div": 0,
    }
    sig.update(extra)
    return sig


# ---------------------------------------------------------------------------
# 形态 1: 趋势回调企稳 (trend_pullback) — 评分制
#   gate(硬性逻辑前提): 均线多头 + 120日涨幅>=15% + 回撤[2%,20%] + 峰距[2,35]日
#                       + 回调低点距关键点位<=4% + 信号日企稳动作
#   score: 回撤深度0.30 + 时长0.20 + 点位贴近度0.35 + 趋势强度0.15
# ---------------------------------------------------------------------------


def _detect_trend_pullback(ctx: _Ctx, i: int, symbol: str, name: str,
                           tolerance: float) -> dict | None:
    if not ctx.cand["rebound"][i]:
        return None
    if not (ctx.MA20[i] > ctx.MA60[i] and ctx.close[i] > ctx.MA60[i]):
        return None
    # 前置: 必须处于上涨趋势 (250日显著高低点结构, 详见 trend_context)
    tc = trend_context(ctx, i)
    if tc["trend"] != "up":
        return None
    sh, sl = tc["swing_high"], tc["swing_low"]
    if sh is None or sl is None:
        return None
    trend_gain = sh.price / sl.price - 1.0
    lo120 = max(0, i - 120)
    seg120 = ctx.close[lo120:i + 1]
    if len(seg120) < 121 or seg120[-121] <= 0:
        return None
    if seg120.max() / seg120[-121] - 1.0 < 0.15:
        return None
    lo30 = i - 29 if i >= 29 else 0
    seg30 = ctx.close[lo30:i + 1]
    peak_rel = int(np.argmax(seg30))
    peak_idx = lo30 + peak_rel
    dsp = i - peak_idx
    if not (2 <= dsp <= 35):
        return None
    peak_close = float(seg30[peak_rel])
    since = ctx.close[peak_idx:i + 1]
    min_close_since = float(since.min())
    low_since = ctx.low[peak_idx:i + 1]
    min_low_since = float(low_since.min())
    pullback_low_idx = peak_idx + int(np.argmin(low_since))
    drawdown = (peak_close - min_close_since) / peak_close
    if not (0.02 <= drawdown <= 0.20):
        return None
    # 关键点位: 均线 + 斐波那契 (本轮波段最高点→最低点) + 已确认前高
    levels: dict[str, float] = {}
    for w in ctx.ma_windows:
        v = ctx.ma(w, i)
        if _valid(v):
            levels[f"MA{w}"] = v
    levels.update(fib_levels_from_swings(tc, peak_close))
    for p in reversed(ctx.zz):
        if p.typ == "H" and p.idx < peak_idx - 5:
            levels["prev_high"] = p.price
            break
    main_name, main_lv, main_dist = None, None, None
    for lv_name, lv in levels.items():
        if lv <= 0 or np.isnan(lv) or peak_close < lv * 0.99:
            continue
        if min_low_since > lv * 1.04:
            continue
        dist = abs(min_low_since - lv) / lv
        if dist > 0.04:
            continue
        if main_lv is None or lv > main_lv:
            main_name, main_lv, main_dist = lv_name, lv, dist
    if main_name is None:
        return None
    # 分档: strong_hold / fake_break(假跌破<=3日收回) / near_level(近似形态) / soft
    closes_since = ctx.close[peak_idx:i + 1]
    broken = int((closes_since < main_lv * 0.999).sum())
    break_depth = max(0.0, (main_lv - min_close_since) / main_lv)
    if broken == 0 and main_dist <= tolerance:
        variant = "strong_hold"
    elif broken <= 3 and ctx.close[i] >= main_lv:
        variant = "fake_break"
    elif main_dist > tolerance:
        variant = "near_level"
    else:
        variant = "soft_pullback"
    hit_names = [n for n, lv in levels.items()
                 if lv > 0 and not np.isnan(lv)
                 and abs(min_low_since - lv) / lv <= tolerance
                 and peak_close >= lv * (1 + tolerance)]
    fib_hit = next((h for h in hit_names if h.startswith("fib_")), "")
    up_len = dsp
    up_seg = ctx.volume[max(0, peak_idx - up_len):peak_idx]
    pb_seg = ctx.volume[peak_idx:i + 1]
    vol_shrink = float(pb_seg.mean() / up_seg.mean()) if len(up_seg) and up_seg.mean() > 0 else np.nan
    s_dd = score_range(drawdown, 0.04, 0.13, 0.02, 0.20)
    s_dur = score_range(float(dsp), 4, 20, 2, 35)
    s_touch = 1.0 if main_dist <= tolerance else max(0.0, 1.0 - (main_dist - tolerance) / (0.04 - tolerance))
    s_trend = score_range(trend_gain, 0.30, 2.0, 0.15, 5.0)
    score = 0.30 * s_dd + 0.20 * s_dur + 0.35 * s_touch + 0.15 * s_trend
    high120 = float(seg120.max())
    return _base_signal(
        ctx, i, symbol, name, "trend_pullback", variant,
        hit_levels=",".join(hit_names) or main_name, fib_level=fib_hit,
        resonance=max(1, len(hit_names)), wave_phase=wave_phase(ctx, i),
        break_days=broken, break_depth=round(break_depth, 4),
        pullback_vol_shrink=vol_shrink,
        potential_gain=high120 / ctx.close[i] - 1.0,
        swing_start_date=ctx.dates[sl.idx], swing_start_price=round(float(sl.price), 3),
        swing_peak_date=ctx.dates[peak_idx], swing_peak_price=round(peak_close, 3),
        pullback_low_date=ctx.dates[pullback_low_idx], pullback_low_price=round(min_low_since, 3),
        pullback_pct=round(drawdown, 4), key_level_name=main_name,
        key_level_value=round(float(main_lv), 3),
        score=round(score, 3), trend="up",
    )


# ---------------------------------------------------------------------------
# 形态 2: 下跌趋势中长均线企稳反弹 (ma_rebound) — 评分制
#   gate: 近60日回撤>=10% + 弱势(MA60下方或MA60向下) + 触及均线±5% + 收盘守住-7%
#         + 不再创新低 + 收敛或放量 + 信号日反弹动作
#   score: 下跌深度0.25 + 触及贴近0.30 + 守住度0.30 + 震荡收敛0.15
# ---------------------------------------------------------------------------


def _detect_ma_rebound(ctx: _Ctx, i: int, symbol: str, name: str,
                       tolerance: float) -> dict | None:
    if not ctx.cand["rebound"][i]:
        return None
    lo60 = i - 59 if i >= 59 else 0
    seg60 = ctx.close[lo60:i + 1]
    max_close60 = float(seg60.max())
    if max_close60 <= 0:
        return None
    dd60 = (max_close60 - ctx.close[i]) / max_close60
    if dd60 < 0.10:
        return None
    ma60_down = i >= 10 and ctx.MA60[i] < ctx.MA60[i - 10]
    if not (ctx.close[i] < ctx.MA60[i] or ma60_down):
        return None
    best = None
    for w in (60, 120, 250):
        ma = ctx.ma(w, i)
        if not _valid(ma) or ma <= 0:
            continue
        lo15 = i - 14 if i >= 14 else 0
        lows15 = ctx.low[lo15:i + 1]
        closes15 = ctx.close[lo15:i + 1]
        touch = float(lows15.min()) / ma - 1.0        # 触及深度(负=跌破)
        if touch > 0.05:                              # 未进入均线±5%区域
            continue
        hold = float(closes15.min()) / ma - 1.0       # 收盘守住度
        if hold < -0.07:                              # 收盘深度破位超过7%
            continue
        lo10 = i - 9 if i >= 9 else 0
        closes10 = ctx.close[lo10:i + 1]
        low10 = float(closes10.min())
        prior_lows = ctx.close[lo60:i - 9] if i - 9 > lo60 else ctx.close[lo60:i + 1]
        no_new_low = low10 > float(prior_lows.min()) * 0.999
        converge = (float(closes10.max()) - low10) / low10
        vol_up = ctx.vol_ratio[i] >= 1.5
        if no_new_low and (converge <= 0.18 or vol_up):
            s_dd = score_range(dd60, 0.20, 0.70, 0.10, 1.00)
            s_touch = score_range(touch, -0.05, 0.0, -0.08, 0.05)
            s_hold = score_range(hold, 0.0, 0.20, -0.07, 0.30)
            s_conv = score_range(converge, 0.03, 0.10, 0.0, 0.18)
            score = 0.25 * s_dd + 0.30 * s_touch + 0.30 * s_hold + 0.15 * s_conv
            best = (w, ma, score)
            break
    if best is None:
        return None
    w, ma, score = best
    lo120 = i - 119 if i >= 119 else 0
    high120 = float(ctx.close[lo120:i + 1].max())
    return _base_signal(
        ctx, i, symbol, name, "ma_rebound", f"MA{w}_hold",
        hit_levels=f"MA{w}", resonance=1,
        wave_phase="downtrend_ma_support",
        potential_gain=high120 / ctx.close[i] - 1.0,
        key_level_name=f"MA{w}", key_level_value=round(float(ma), 3),
        pullback_pct=round(dd60, 4),
        score=round(score, 3), trend="down",
    )


# ---------------------------------------------------------------------------
# 形态 3: W底右底 (w_bottom) — 评分制
#   gate: L1-H-L2 结构 + 右底不破左底8% + 间隔[8,90]日 + 颈线高度>=5%
#         + 左底前30日跌幅>=8%
#   score: 两底贴近0.35 + 颈线高度0.30 + 间隔0.15 + 前期跌幅0.20
# ---------------------------------------------------------------------------


def _detect_w_bottom(ctx: _Ctx, i: int, symbol: str, name: str,
                     tolerance: float, used_keys: set) -> dict | None:
    zz = ctx.zz
    if len(zz) < 3:
        return None
    l1, h, l2 = zz[-3], zz[-2], zz[-1]
    if not (l1.typ == "L" and h.typ == "H" and l2.typ == "L"):
        return None
    gap = l2.idx - l1.idx
    if not (8 <= gap <= 90):
        return None
    l1p, l2p, hp = l1.price, l2.price, h.price
    if l1p <= 0 or hp <= 0:
        return None
    if l2p < l1p * 0.92:                     # 右底破左底8%以上: 不是W底
        return None
    bottom = min(l1p, l2p)
    neck = hp / bottom - 1.0
    if neck < 0.05:                          # 颈线太浅: 结构无意义(容忍下限)
        return None
    # 前置 (W底必须出现在下跌之后): 左底之前250日内的显著最高点, 左底距其跌幅>=20%
    lo250 = max(0, l1.idx - 250)
    pre_hs = [p for p in ctx.zz if p.typ == "H" and lo250 <= p.idx < l1.idx]
    if not pre_hs:
        return None
    pre_high = max(pre_hs, key=lambda p: p.price)
    pre_drop = (pre_high.price - l1p) / pre_high.price
    if pre_drop < 0.20:
        return None
    s_bottoms = score_range(abs(l2p - l1p) / l1p, 0.0, 0.03, 0.0, 0.08)
    if s_bottoms <= 0:
        return None        # 定义性条件: 两底差超容忍(8%)不是W底, 不允许其他项补偿
    s_neck = score_range(neck, 0.10, 0.80, 0.05, 1.50)
    s_gap = score_range(float(gap), 15, 50, 8, 90)
    s_pre = score_range(pre_drop, 0.30, 0.80, 0.20, 1.50)
    score = 0.35 * s_bottoms + 0.30 * s_neck + 0.15 * s_gap + 0.20 * s_pre
    # MACD 底背离: 右底价格不高于左底2% 但 DIF 抬高 (经典双底确认信号)
    macd_div = 0
    d1, d2 = ctx.DIF[l1.idx], ctx.DIF[l2.idx]
    if _valid(d1) and _valid(d2) and l2p <= l1p * 1.02 and d2 > d1:
        macd_div = 1
    # 信号 (b): 放量收盘突破颈线, 每个颈线一次
    key_b = ("w_neck", h.idx)
    if (key_b not in used_keys and i - h.idx <= 60
            and ctx.close[i] > hp and ctx.close[i - 1] <= hp
            and ctx.cand["yang_vol15"][i]):
        used_keys.add(key_b)
        return _base_signal(
            ctx, i, symbol, name, "w_bottom", "neckline_breakout",
            hit_levels="neckline", resonance=1,
            wave_phase="base_breakout",
            potential_gain=(hp + (hp - bottom)) / ctx.close[i] - 1.0,
            left_bottom_date=ctx.dates[l1.idx], left_bottom_price=round(float(l1p), 3),
            right_bottom_date=ctx.dates[l2.idx], right_bottom_price=round(float(l2p), 3),
            neckline_date=ctx.dates[h.idx], neckline_value=round(float(hp), 3),
            bottom_deviation_pct=round(abs(l2p / l1p - 1.0) * 100, 2),
            score=round(score, 3), trend="down", macd_div=macd_div,
        )
    # 信号 (a): 右底确认后反弹中、未到颈线 (博第二波到颈线)
    key_a = ("w_right", l2.idx)
    if (key_a not in used_keys and 0 < i - l2.idx <= 25
            and ctx.cand["rebound"][i]
            and ctx.close[i] >= ctx.close[l2.idx] * 1.02
            and ctx.close[i] <= hp * 0.97):
        used_keys.add(key_a)
        return _base_signal(
            ctx, i, symbol, name, "w_bottom", "right_bottom",
            hit_levels="second_bottom", resonance=1,
            wave_phase="base_rebound",
            potential_gain=hp / ctx.close[i] - 1.0,
            left_bottom_date=ctx.dates[l1.idx], left_bottom_price=round(float(l1p), 3),
            right_bottom_date=ctx.dates[l2.idx], right_bottom_price=round(float(l2p), 3),
            neckline_date=ctx.dates[h.idx], neckline_value=round(float(hp), 3),
            bottom_deviation_pct=round(abs(l2p / l1p - 1.0) * 100, 2),
            score=round(score, 3), trend="down", macd_div=macd_div,
        )
    return None


# ---------------------------------------------------------------------------
# 形态 4: M形颈线支撑 (m_neckline) — 评分制
#   gate: H1-N-H2 结构 + 两高差<=8% + 间隔[8,90] + H1前涨幅>=12%
#         + 回调触及颈线8%内 + 收盘不破颈线2%以下
#   score: 两高贴近0.35 + 前期涨幅0.20 + 间隔0.15 + 颈线守住度0.30
# ---------------------------------------------------------------------------


def _detect_m_neckline(ctx: _Ctx, i: int, symbol: str, name: str,
                       tolerance: float, used_keys: set) -> dict | None:
    if not ctx.cand["rebound"][i]:
        return None
    zz = ctx.zz
    if len(zz) < 3:
        return None
    h1, n, h2 = zz[-3], zz[-2], zz[-1]
    if not (h1.typ == "H" and n.typ == "L" and h2.typ == "H"):
        return None
    gap = h2.idx - h1.idx
    if not (8 <= gap <= 90):
        return None
    h1p, h2p, np_ = h1.price, h2.price, n.price
    two_high = abs(h2p - h1p) / h1p
    if two_high > 0.08 or np_ >= min(h1p, h2p):
        return None
    # 前置 (M顶必须出现在上涨之后): H1之前250日内的显著最低点, H1距其涨幅>=25%
    lo250 = max(0, h1.idx - 250)
    pre_ls = [p for p in ctx.zz if p.typ == "L" and lo250 <= p.idx < h1.idx]
    if not pre_ls:
        return None
    pre_low = min(pre_ls, key=lambda p: p.price)
    if pre_low.price <= 0:
        return None
    pre_rise = (h1p - pre_low.price) / pre_low.price
    if pre_rise < 0.25:
        return None
    if i - h2.idx > 25:
        return None
    lo15 = i - 14 if i >= 14 else 0
    if float(ctx.low[lo15:i + 1].min()) > np_ * 1.08:   # 未回调到颈线附近
        return None
    hold = float(ctx.close[lo15:i + 1].min()) / np_ - 1.0
    if hold < -0.02:                                    # 收盘有效跌破颈线
        return None
    if ctx.close[i] <= np_:
        return None
    key = ("m_neck", h2.idx)
    if key in used_keys:
        return None
    used_keys.add(key)
    up_seg = ctx.volume[n.idx:h2.idx + 1]
    pb_seg = ctx.volume[h2.idx:i + 1]
    vol_shrink = float(pb_seg.mean() / up_seg.mean()) if len(up_seg) and up_seg.mean() > 0 else np.nan
    s_highs = score_range(two_high, 0.0, 0.03, 0.0, 0.08)
    if s_highs <= 0:
        return None        # 定义性条件: 两高差超容忍(8%)不是M顶, 不允许其他项补偿
    s_pre = score_range(pre_rise, 0.40, 2.00, 0.25, 4.00)
    s_gap = score_range(float(gap), 15, 50, 8, 90)
    s_hold = score_range(hold, 0.0, 0.15, -0.02, 0.30)
    score = 0.35 * s_highs + 0.20 * s_pre + 0.15 * s_gap + 0.30 * s_hold
    # MACD 顶背离警示: H2 价格≈H1 但 DIF 降低 (动能衰减, 第二波把握下降)
    macd_div = 0
    d1, d2 = ctx.DIF[h1.idx], ctx.DIF[h2.idx]
    if _valid(d1) and _valid(d2) and h2p >= h1p * 0.98 and d2 < d1:
        macd_div = -1
    return _base_signal(
        ctx, i, symbol, name, "m_neckline", "neckline_hold",
        hit_levels="neckline", resonance=1,
        wave_phase=wave_phase(ctx, i),
        pullback_vol_shrink=vol_shrink,
        potential_gain=max(h1p, h2p) / ctx.close[i] - 1.0,
        first_top_date=ctx.dates[h1.idx], first_top_price=round(float(h1p), 3),
        second_top_date=ctx.dates[h2.idx], second_top_price=round(float(h2p), 3),
        neckline_date=ctx.dates[n.idx], neckline_value=round(float(np_), 3),
        top_deviation_pct=round(two_high * 100, 2),
        score=round(score, 3), trend="up", macd_div=macd_div,
    )


# ---------------------------------------------------------------------------
# 形态 5: 平台箱体放量突破 (box_breakout) — 评分制
#   gate: 箱体宽度<=25% + 收盘有效突破(0.3%) + 量比>=1.5 + 阳线
#   score: 箱体规整度0.40 + 突破量能0.35 + 突破幅度0.25
# ---------------------------------------------------------------------------


def _detect_box_breakout(ctx: _Ctx, i: int, symbol: str, name: str,
                         tolerance: float, box_window: int = 40) -> dict | None:
    if i < box_window + 5:
        return None
    if not ctx.cand["box"][i]:
        return None
    # 箱体上沿须同时突破近120日高点 ("看前面更多": 突破的级别要够)
    if i >= 120 and ctx.close[i] <= ctx.close[i - 120:i].max() * 0.999:
        return None
    box_high = float(ctx.close[i - box_window:i].max())
    box_low = float(ctx.close[i - box_window:i].min())
    if box_low <= 0:
        return None
    width = (box_high - box_low) / box_low
    if width > 0.25:
        return None
    breakout = ctx.close[i] / box_high - 1.0
    if breakout < 0.003:
        return None
    s_box = score_range(width, 0.05, 0.12, 0.02, 0.25)
    if s_box <= 0:
        return None        # 定义性条件: 宽度超容忍不是平台
    s_vol = score_range(ctx.vol_ratio[i], 2.0, 8.0, 1.5, 20.0)
    s_brk = score_range(breakout, 0.005, 0.05, 0.003, 0.099)
    score = 0.40 * s_box + 0.35 * s_vol + 0.25 * s_brk
    return _base_signal(
        ctx, i, symbol, name, "box_breakout", "box_breakout",
        hit_levels="box_high", resonance=1,
        wave_phase="box_breakout",
        potential_gain=(box_high + (box_high - box_low)) / ctx.close[i] - 1.0,
        box_start_date=ctx.dates[i - box_window], box_end_date=ctx.dates[i - 1],
        box_high=round(box_high, 3), box_low=round(box_low, 3),
        box_width_pct=round(width * 100, 2), breakout_pct=round(breakout * 100, 2),
        score=round(score, 3), trend="range",
    )


# ---------------------------------------------------------------------------
# 检测主流程
# ---------------------------------------------------------------------------


def detect_patterns(df: pd.DataFrame, symbol: str, name: str = "",
                    patterns: list[str] | None = None,
                    ma_windows: tuple[int, ...] = (20, 60, 120, 250),
                    tolerance: float = 0.015,
                    pivot_left: int = 5, pivot_right: int = 5,
                    swing_min: float = 0.03,
                    min_score: float = 0.6) -> list[dict]:
    """对单标的 DataFrame (load_pattern_df + add_factor_columns 后) 检测全部形态信号。

    股票/板块通用; 历史不足 MIN_BARS 的标的自动跳过 (历史短的板块自然过滤)。
    min_score: 形态标准度阈值 (0~1)。评分制下"类似形态" (参数偏离理想区间但在
    容忍范围内) 也会被识别, 只是 score 较低; score 低于 min_score 的丢弃。
    """
    if len(df) < MIN_BARS:
        return []
    if patterns is None:
        patterns = list(PATTERN_NAMES.keys())
    events = build_pivot_events(df, pivot_left, pivot_right)
    ctx = _Ctx(df, tuple(w for w in ma_windows if w in MA_WINDOW_WHITELIST))
    signals: list[dict] = []
    cooldown: dict[str, int] = {}
    used_keys: set = set()
    ei = 0
    ne = len(events)

    for i in range(MIN_BARS, ctx.n):
        while ei < ne and events[ei].confirm <= i:
            update_zigzag(ctx.zz, events[ei], swing_min)
            ei += 1
        # 通用排除: 停牌 / 低价股 / 一字涨停无法买入 / 关键数据缺失
        if ctx.volume[i] <= 0 or ctx.close[i] < 1.5:
            continue
        if not (_valid(ctx.open[i]) and _valid(ctx.close[i])
                and _valid(ctx.MA5[i]) and _valid(ctx.VOL_MA5[i])):
            continue
        if ctx.high[i] == ctx.low[i] and ctx.change_rate[i] >= 9.5:
            continue
        for pat in patterns:
            last_i = cooldown.get(pat, -10**9)
            if i - last_i < PATTERN_COOLDOWN[pat]:
                continue
            sig = None
            if pat == "trend_pullback":
                sig = _detect_trend_pullback(ctx, i, symbol, name, tolerance)
            elif pat == "ma_rebound":
                sig = _detect_ma_rebound(ctx, i, symbol, name, tolerance)
            elif pat == "w_bottom":
                sig = _detect_w_bottom(ctx, i, symbol, name, tolerance, used_keys)
            elif pat == "m_neckline":
                sig = _detect_m_neckline(ctx, i, symbol, name, tolerance, used_keys)
            elif pat == "box_breakout":
                sig = _detect_box_breakout(ctx, i, symbol, name, tolerance)
            if sig is not None:
                if sig["score"] < min_score:
                    continue
                cooldown[pat] = i
                signals.append(sig)
    return signals


def prepare_df(universe: str, symbol: str, start: str = BACKTEST_START,
               end: str | None = None, tail: int | None = None) -> pd.DataFrame:
    """load_pattern_df + add_factor_columns 一步到位 (股票/板块通用)。"""
    df = load_pattern_df(universe, symbol, start=start, end=end, tail=tail)
    if df.empty:
        return df
    return add_factor_columns(df)


def passes_filter(sig: dict, filters: dict | None = None) -> bool:
    """按形态专属因子阈值筛选; 支持 <field>_in 类别条件与 (下限, 上限) 数值条件。

    因子缺失/NaN 不通过。
    """
    f = (filters if filters is not None else PATTERN_FILTERS).get(sig["pattern"])
    if not f:
        return True
    for key, cond in f.items():
        if key.endswith("_in"):
            field = key[:-3]
            if sig.get(field) not in cond:
                return False
            continue
        lo, hi = cond
        v = sig.get(key)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return False
        if lo is not None and v < lo:
            return False
        if hi is not None and v > hi:
            return False
    return True


# ---------------------------------------------------------------------------
# 扫描 / 历史信号 / 关键点位 (供 MCP 工具调用)
# ---------------------------------------------------------------------------


def _sig_clean(sig: dict) -> dict:
    """NaN → None, 便于 JSON 序列化。"""
    return {k: (None if (isinstance(v, float) and np.isnan(v)) else v)
            for k, v in sig.items()}


def scan_universe(universe: str, date: str | None = None,
                  patterns: list[str] | None = None,
                  ma_windows: tuple[int, ...] = (20, 60, 120, 250),
                  tolerance: float = 0.015,
                  strict: bool = False, no_filter: bool = False,
                  workers: int = 8, symbols: list[str] | None = None,
                  sector_type: str | None = None,
                  min_score: float = 0.6,
                  progress: bool = True) -> list[dict]:
    """全市场 (或指定标的) 形态扫描, 返回带 filter_pass/strict_pass 的信号列表。

    universe: stocks|sectors; symbols 非空时只扫指定标的;
    sector_type: 仅板块宇宙生效 (concept/industry, 缺省=全部);
    date: 缺省=本地库最新交易日; 结果只保留指定日期的信号 (scan 语义)。
    """
    if date is None:
        date = get_latest_trade_date(universe)
    if date is None:
        raise RuntimeError(f"{universe} 本地库无K线数据, 请先执行数据初始化/重建")
    if symbols:
        items = []
        for q in symbols:
            try:
                items.append(resolve_universe_symbol(universe, q))
            except ValueError:
                continue
    else:
        lst = get_universe_list(universe, sector_type=sector_type)
        items = list(zip(lst["symbol"].tolist(), lst["name"].tolist()))

    all_sigs: list[dict] = []
    done = 0

    def _scan_one(item: tuple) -> list[dict]:
        sym, nm = item
        try:
            df = prepare_df(universe, sym, end=date, tail=420)
            if len(df) < MIN_BARS:
                return []
            sigs = detect_patterns(df, sym, nm, patterns, ma_windows,
                                   tolerance, min_score=min_score)
            return [s for s in sigs if s["date"] == date]
        except Exception as e:  # 单标的失败不影响整体扫描
            if progress:
                print(f"  [warn] {universe} {sym} {nm}: {e}", file=sys.stderr, flush=True)
            return []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_scan_one, it): it for it in items}
        for fut in as_completed(futures):
            all_sigs.extend(fut.result())
            done += 1
            if progress and done % 500 == 0:
                print(f"进度: {done}/{len(items)} ({done / len(items):.0%}) "
                      f"信号={len(all_sigs)}", file=sys.stderr, flush=True)

    if not all_sigs:
        return []
    for s in all_sigs:
        s["filter_pass"] = passes_filter(s)
        s["strict_pass"] = passes_filter(s, PATTERN_STRICT_FILTERS)
    if strict:
        all_sigs = [s for s in all_sigs if s["strict_pass"]]
    elif not no_filter:
        all_sigs = [s for s in all_sigs if s["filter_pass"]]
    return [_sig_clean(s) for s in all_sigs]


def get_pattern_history(universe: str, symbol: str, start: str | None = None,
                        end: str | None = None, patterns: list[str] | None = None,
                        ma_windows: tuple[int, ...] = (20, 60, 120, 250),
                        tolerance: float = 0.015,
                        min_score: float = 0.6) -> list[dict]:
    """单标的 (股票/板块) 历史形态信号列表, 按日期升序。"""
    sym, name = resolve_universe_symbol(universe, symbol)
    df = prepare_df(universe, sym, start=start or BACKTEST_START, end=end)
    if df.empty:
        raise RuntimeError(f"{sym} {name} 无K线数据")
    sigs = detect_patterns(df, sym, name, patterns, ma_windows, tolerance,
                           min_score=min_score)
    sigs.sort(key=lambda s: s["date"])
    return [_sig_clean(s) for s in sigs]


def get_key_levels(universe: str, symbol: str,
                   ma_windows: tuple[int, ...] = (5, 10, 20, 30, 60, 120, 200, 250),
                   tolerance: float = 0.015) -> dict:
    """单标的当前关键位: MA体系 + 斐波那契 + 结构位 (前高/前低) + 趋势判定。"""
    sym, name = resolve_universe_symbol(universe, symbol)
    df = prepare_df(universe, sym)
    if len(df) < MIN_BARS:
        raise RuntimeError(f"{sym} {name} 数据不足 ({len(df)} < {MIN_BARS} 根K线)")
    i = len(df) - 1
    ctx = _Ctx(df, ())
    close = float(ctx.close[i])
    events = build_pivot_events(df)
    zz: list[Pivot] = []
    for p in events:
        if p.confirm <= i:
            update_zigzag(zz, p)
    ctx.zz = zz
    tc = trend_context(ctx, i)

    levels = []
    for w in ma_windows:
        v = ctx.ma(w, i)
        if _valid(v):
            levels.append({"type": f"MA{w}", "value": round(float(v), 3),
                           "distance_pct": round((v / close - 1) * 100, 2)})
    # 斐波那契 (本轮趋势波段最高点→最低点, 近30日峰覆盖)
    seg30 = ctx.close[i - 29:i + 1]
    for nm, lv in fib_levels_from_swings(tc, float(seg30.max())).items():
        label = f"回调位{nm[4:]}" if nm.startswith("fib") else f"反弹位{nm[5:]}"
        levels.append({"type": label, "value": round(float(lv), 3),
                       "distance_pct": round((lv / close - 1) * 100, 2)})
    # 结构位: 已确认 zigzag 的前高/前低
    hs = [p for p in zz if p.typ == "H"]
    ls = [p for p in zz if p.typ == "L"]
    if hs:
        levels.append({"type": f"前高({ctx.dates[hs[-1].idx]})",
                       "value": round(float(hs[-1].price), 3),
                       "distance_pct": round((hs[-1].price / close - 1) * 100, 2)})
    if ls:
        levels.append({"type": f"前低({ctx.dates[ls[-1].idx]})",
                       "value": round(float(ls[-1].price), 3),
                       "distance_pct": round((ls[-1].price / close - 1) * 100, 2)})
    levels.sort(key=lambda r: abs(r["distance_pct"]))

    trend_cn = {"up": "上涨趋势", "down": "下跌趋势", "range": "震荡"}[tc["trend"]]
    return {
        "universe": universe,
        "symbol": sym,
        "name": name,
        "date": ctx.dates[i],
        "close": round(close, 3),
        "trend": tc["trend"],
        "trend_cn": trend_cn,
        "levels": levels,
        "resistance": [r for r in levels if r["distance_pct"] > 0][:6],
        "support": [r for r in levels if r["distance_pct"] <= 0][:6],
    }
