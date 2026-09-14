"""patterns/pivots.py — 摆动点 (pivot) 与 zigzag 波段结构"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


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
