"""
个股综合技术分析报告

基于本地K线+指标数据生成:
- 支撑位/阻力位
- 技术指标状态
- 风险评估
- 仓位管理建议
"""

from datetime import date
import numpy as np

from ..data.storage import query_stock_db, query_sector_db
from ..data.sync import download_stock_kline


def _today() -> str:
    """当前日期(每次调用时求值, 避免长驻进程跨天后日期固化)"""
    return date.today().isoformat()


# 通用: 将 None 转为安全字符串输出
def _na(val, fmt=".2f"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(float(val), 2) if isinstance(val, (int, float)) else val


def _r(val, ndigits=2):
    """None 安全的 round; 0 是合法值不会被丢弃"""
    return round(float(val), ndigits) if val is not None else None


def _pct(val, sign=True):
    """百分比格式化"""
    if val is None:
        return None
    v = round(float(val), 2)
    return f"{'+' if sign and v > 0 else ''}{v}%"


def _get_kline_data(symbol: str, days: int = 250):
    """获取K线原始数据(最近N天)"""
    rows = query_stock_db(
        "SELECT * FROM stock_kline WHERE symbol=? AND adjust_type='qfq' ORDER BY date ASC",
        (symbol,),
    )
    return rows[-days:] if len(rows) > days else rows


def _get_indicator_data(symbol: str, limit: int = 250):
    """获取最近N条技术指标(JOIN K线补充 close/high/low, 指标表本身不存价格)"""
    rows = query_stock_db(
        """SELECT i.*, k.close, k.high, k.low
           FROM stock_indicators i
           JOIN stock_kline k ON i.symbol = k.symbol AND i.date = k.date
                AND i.adjust_type = k.adjust_type
           WHERE i.symbol=? AND i.adjust_type='qfq' ORDER BY i.date DESC LIMIT ?""",
        (symbol, limit),
    )
    return list(reversed(rows))


def _get_spot_data(symbol: str):
    rows = query_stock_db("SELECT * FROM stock_spot WHERE symbol=?", (symbol,))
    return rows[0] if rows else None


def _get_name(symbol: str):
    rows = query_stock_db("SELECT name FROM stock_basic WHERE symbol=?", (symbol,))
    return rows[0]["name"] if rows else symbol


# ═══════════════════ 分析逻辑 ═══════════════════


def _find_support_resistance(ind_rows: list[dict], latest_close: float, latest_atr: float = None) -> dict:
    """
    从指标数据(已排序升序)计算支撑/阻力位
    """
    if not ind_rows or latest_close is None:
        return {"supports": [], "resistances": []}

    last = ind_rows[-1]
    supports = []
    resistances = []

    # 均线(强度用显式映射, 避免字符串包含判断把 MA200 误判为"强")
    for key, strength in [("MA20", "强"), ("MA60", "中"), ("MA100", "参考"), ("MA200", "参考")]:
        v = last.get(key)
        if v is not None and v > 0:
            (supports if v < latest_close else resistances).append(
                {"level": round(v, 2), "type": key, "strength": strength}
            )

    # BOLL
    for key, label, cat in [("BOLL_UPPER", "BOLL上轨", "r"), ("BOLL_MIDDLE", "BOLL中轨", "r" if last.get("BOLL_MIDDLE") and last["BOLL_MIDDLE"] > latest_close else "s"), ("BOLL_LOWER", "BOLL下轨", "s")]:
        v = last.get(key)
        if v and v > 0:
            (resistances if cat == "r" else supports).append(
                {"level": round(v, 2), "type": label, "strength": "中"}
            )

    # 排序: 支撑从高到低, 阻力从低到高
    supports.sort(key=lambda x: x["level"], reverse=True)
    resistances.sort(key=lambda x: x["level"])

    return {
        "supports": supports[:5],
        "resistances": resistances[:5],
        "atr": round(latest_atr, 2) if latest_atr else None,
    }


def _analyze_trend(ind_rows: list[dict], latest_close: float) -> dict:
    """趋势分析"""
    if not ind_rows:
        return {"direction": "未知", "description": "数据不足"}

    last = ind_rows[-1]
    ma5 = last.get("MA5")
    ma10 = last.get("MA10")
    ma20 = last.get("MA20")
    ma60 = last.get("MA60")

    # 均线排列
    if ma5 and ma10 and ma20 and ma60 and ma5 > ma10 > ma20 > ma60:
        arrangement = "多头排列(强势)"
    elif ma5 and ma10 and ma20 and ma5 < ma10 < ma20:
        arrangement = "空头排列(弱势)"
    elif ma5 and ma20 and ma5 > ma20:
        arrangement = "短期均线上穿中期(偏多)"
    else:
        arrangement = "均线缠绕(震荡)"

    # 近期涨跌幅(基于真实收盘价, 由 _get_indicator_data JOIN K线提供)
    changes = {}
    for offset, label in [(5, "5日"), (10, "10日"), (20, "20日"), (60, "60日")]:
        if len(ind_rows) > offset:
            past_close = ind_rows[-offset - 1].get("close")
            if past_close and past_close > 0:
                pct = (latest_close - past_close) / past_close * 100
                changes[label] = f"{'+' if pct > 0 else ''}{pct:.1f}%"

    # 方向判断
    if changes:
        dir_5 = float(changes.get("5日", "0%").replace("+", "").replace("%", ""))
        dir_20 = float(changes.get("20日", "0%").replace("+", "").replace("%", ""))
        if dir_5 > 3 and dir_20 > 0:
            direction = "短期强势上扬"
        elif dir_5 < -3 and dir_20 < 0:
            direction = "短期持续下跌"
        elif dir_5 > 0:
            direction = "短期企稳回升"
        elif dir_5 < 0:
            direction = "短期回调"
        else:
            direction = "横盘震荡"
    else:
        direction = "数据不足"

    return {
        "direction": direction,
        "arrangement": arrangement,
        "recent_changes": changes,
        "ma_status": {
            "MA5": _r(ma5),
            "MA10": _r(ma10),
            "MA20": _r(ma20),
            "MA60": _r(ma60),
        },
    }


def _analyze_indicators(ind_rows: list[dict]) -> dict:
    """技术指标状态"""
    if not ind_rows:
        return {"rsi": None, "macd": None, "kdj": None, "boll": None}

    last = ind_rows[-1]
    prev = ind_rows[-2] if len(ind_rows) > 1 else None

    # RSI
    rsi14 = last.get("RSI14")
    rsi_status = None
    if rsi14 is not None:
        if rsi14 > 80:
            rsi_status = "严重超买"
        elif rsi14 > 70:
            rsi_status = "超买区域"
        elif rsi14 < 20:
            rsi_status = "严重超卖"
        elif rsi14 < 30:
            rsi_status = "超卖区域"
        elif rsi14 >= 40 and rsi14 <= 60:
            rsi_status = "中性"
        else:
            rsi_status = "偏强" if rsi14 > 60 else "偏弱"

    # MACD
    dif = last.get("DIF")
    dea = last.get("DEA")
    macd_hist = last.get("MACD")
    macd_signal = None
    if dif is not None and dea is not None:
        prev_dif = prev.get("DIF") if prev else None
        prev_dea = prev.get("DEA") if prev else None
        if dif > dea:
            if prev_dif is not None and prev_dea is not None and prev_dif <= prev_dea:
                macd_signal = "金叉(买入信号)"
            else:
                macd_signal = "多头运行"
        else:
            if prev_dif is not None and prev_dea is not None and prev_dif >= prev_dea:
                macd_signal = "死叉(卖出信号)"
            else:
                macd_signal = "空头运行"

    # KDJ
    k = last.get("KDJ_K")
    d = last.get("KDJ_D")
    j = last.get("KDJ_J")
    kdj_status = None
    if k is not None and d is not None and j is not None:
        if j > 100:
            kdj_status = "J值超买(>100), 警惕回调"
        elif j < 0:
            kdj_status = "J值超卖(<0), 可能反弹"
        elif k > 80 and d > 80:
            kdj_status = "超买区域, 高位钝化"
        elif k < 20 and d < 20:
            kdj_status = "超卖区域, 低位钝化"
        elif k > d:
            kdj_status = "K上穿D, 偏多"
        else:
            kdj_status = "K下穿D, 偏空"

    # BOLL 位置
    boll_pos = None
    boll_upper = last.get("BOLL_UPPER")
    boll_lower = last.get("BOLL_LOWER")
    boll_mid = last.get("BOLL_MIDDLE")
    if last.get("close") and boll_upper and boll_lower:
        close = last["close"]
        width = boll_upper - boll_lower
        if width > 0:
            pos_pct = (close - boll_lower) / width * 100
            if pos_pct > 90:
                boll_pos = f"紧贴上轨({pos_pct:.0f}%), 短期有回调压力"
            elif pos_pct > 70:
                boll_pos = f"偏强区域({pos_pct:.0f}%), 运行在上半区"
            elif pos_pct < 10:
                boll_pos = f"紧贴下轨({pos_pct:.0f}%), 有反弹需求"
            elif pos_pct < 30:
                boll_pos = f"偏弱区域({pos_pct:.0f}%), 运行在下半区"
            else:
                boll_pos = f"中轨附近({pos_pct:.0f}%), 方向待选择"
        if boll_mid and close > boll_mid:
            boll_pos = (boll_pos or "") + ", 站上中轨偏多"

    atr14 = last.get("ATR14")
    if atr14 and last.get("close") and last["close"] > 0:
        atr_pct = atr14 / last["close"] * 100
    else:
        atr_pct = None

    return {
        "RSI": {"value": _r(rsi14), "status": rsi_status},
        "MACD": {
            "DIF": _r(dif, 4),
            "DEA": _r(dea, 4),
            "MACD_hist": _r(macd_hist, 4),
            "signal": macd_signal,
        },
        "KDJ": {
            "K": _r(k), "D": _r(d), "J": _r(j),
            "status": kdj_status,
        },
        "BOLL": {
            "upper": _r(boll_upper),
            "middle": _r(boll_mid),
            "lower": _r(boll_lower),
            "position": boll_pos,
        },
        "ATR": {"value14": _r(atr14, 4), "pct": _r(atr_pct)},
    }


def _assess_risk(ind_rows: list[dict], spot: dict | None, latest_close: float) -> dict:
    """风险评估"""
    risks = []
    level = "低"

    if not ind_rows:
        return {"level": "无法评估", "items": ["数据不足"]}

    last = ind_rows[-1]
    rsi14 = last.get("RSI14")
    kdj_j = last.get("KDJ_J")
    atr14 = last.get("ATR14")

    # 技术风险
    if rsi14 is not None and rsi14 > 80:
        risks.append(f"RSI={rsi14:.1f}, 严重超买, 短期回调风险高")
        level = "高"
    elif rsi14 is not None and rsi14 > 70:
        risks.append(f"RSI={rsi14:.1f}, 处于超买区域, 注意回落")
        if level == "低":
            level = "中"

    if kdj_j is not None and kdj_j > 100:
        risks.append(f"KDJ J={kdj_j:.1f}, J值>100超买, 回调概率大")
        level = "高"

    if atr14 and latest_close > 0:
        atr_pct = atr14 / latest_close * 100
        if atr_pct > 8:
            risks.append(f"ATR波幅{atr_pct:.1f}%, 波动极高, 风险大")
            if level == "低":
                level = "高"
        elif atr_pct > 5:
            risks.append(f"ATR波幅{atr_pct:.1f}%, 波动较高")
            if level == "低":
                level = "中"

    # 估值风险
    if spot:
        pe = spot.get("pe_dynamic")
        pb = spot.get("pb")
        if pe is None or pe <= 0:
            risks.append("PE为负或亏损, 基本面风险")
            level = "高"
        elif pe > 100:
            risks.append(f"PE={pe:.0f}, 估值偏高")
            if level == "低":
                level = "中"
        if pb is not None and pb > 10:
            risks.append(f"PB={pb:.1f}, 市净率偏高")

    # 流动性风险
    if spot:
        turnover = spot.get("turnover_rate")
        if turnover is not None and turnover < 1:
            risks.append(f"换手率{turnover:.2f}%, 流动性不足")

    # 趋势风险
    if len(ind_rows) >= 60:
        ma60 = last.get("MA60")
        if ma60 and latest_close < ma60:
            ratio = (latest_close - ma60) / ma60 * 100
            risks.append(f"跌破MA60({ma60:.2f}), 偏离{ratio:.1f}%, 中期趋势偏弱")

    if not risks:
        risks.append("未检测到显著风险信号")

    return {"level": level, "items": risks}


def _position_advice(
    ind_rows: list[dict],
    sr_levels: dict,
    spot: dict | None,
) -> dict:
    """仓位管理建议"""
    if not ind_rows:
        return {"suggestion": "数据不足, 无法给出仓位建议"}

    latest_close = ind_rows[-1].get("close")
    atr14 = ind_rows[-1].get("ATR14")
    if not latest_close or latest_close <= 0:
        return {"suggestion": "数据不足"}

    supports = sr_levels.get("supports", [])
    resistances = sr_levels.get("resistances", [])

    # 最近支撑
    nearest_support = supports[0]["level"] if supports else None
    # 最近阻力
    nearest_resistance = resistances[0]["level"] if resistances else None

    # 止损位: 最近支撑 - 1*ATR, 最低不低于均线支撑
    stop_loss = None
    if atr14 and supports:
        stop_loss = round(nearest_support - atr14, 2)
        # 确保止损在合理范围
        stop_loss_pct = (latest_close - stop_loss) / latest_close * 100
        if stop_loss_pct > 15:
            stop_loss = round(latest_close * 0.93, 2)  # 最多亏损7%
    elif atr14:
        stop_loss = round(latest_close - 2 * atr14, 2)
    else:
        stop_loss = round(latest_close * 0.95, 2)

    # 止盈位: 最近阻力
    take_profit = nearest_resistance

    # 风险收益比
    rr_ratio = None
    if stop_loss and take_profit and stop_loss != latest_close:
        risk = latest_close - stop_loss
        reward = take_profit - latest_close
        if risk > 0 and reward > 0:
            rr_ratio = round(reward / risk, 2)
        elif risk > 0:
            rr_ratio = -1

    # 仓位建议
    position = "观望"
    position_pct = None

    # 综合判断: 趋势 + RSI + 风险
    rsi14 = ind_rows[-1].get("RSI14")
    ma20 = ind_rows[-1].get("MA20")
    ma60 = ind_rows[-1].get("MA60")

    upside = ma20 and latest_close > ma20
    trend_ok = ma20 and ma60 and ma20 > ma60

    if rr_ratio is not None and rr_ratio >= 3:
        if trend_ok and upside and (rsi14 is None or rsi14 < 70):
            position = "可积极介入"
            position_pct = "30-50%"
        elif upside:
            position = "可适量参与"
            position_pct = "15-30%"
        else:
            position = "轻仓试探"
            position_pct = "5-15%"
    elif rr_ratio is not None and rr_ratio >= 2:
        if upside:
            position = "可适量参与"
            position_pct = "10-20%"
        else:
            position = "观望或极小仓位"
            position_pct = "<10%"
    elif rr_ratio is not None and rr_ratio > 0:
        position = "风险收益比不理想, 观望"
        position_pct = None
    else:
        position = "暂无明确交易机会, 观望"

    return {
        "suggestion": position,
        "position_pct": position_pct,
        "stop_loss": stop_loss,
        "stop_loss_pct": f"{(latest_close - stop_loss) / latest_close * 100:.1f}%" if stop_loss else None,
        "take_profit": take_profit,
        "risk_reward_ratio": rr_ratio,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
    }


# ════════════════════════════════════════
# 主报告生成
# ════════════════════════════════════════

async def generate_stock_report(symbol: str) -> dict:
    """生成个股综合分析报告"""

    # 确保有K线数据
    kline_data = _get_kline_data(symbol, 250)
    if not kline_data or len(kline_data) < 20:
        await download_stock_kline(symbol, days=250)
        kline_data = _get_kline_data(symbol, 250)

    if not kline_data or len(kline_data) < 5:
        return {"error": f"股票 {symbol} K线数据不足"}

    ind_rows = _get_indicator_data(symbol, 250)
    spot = _get_spot_data(symbol)
    name = _get_name(symbol)

    latest = kline_data[-1]
    latest_close = latest.get("close")
    atr14 = ind_rows[-1].get("ATR14") if ind_rows else None

    # 1. 基础信息
    basic = {
        "symbol": symbol,
        "name": name,
        "latest_price": round(latest_close, 2) if latest_close else None,
        "change_pct": _pct(latest.get("change_pct")) if latest else None,
        "date": latest.get("date") if latest else _today(),
    }
    if spot:
        basic.update({
            "volume_ratio": _na(spot.get("volume_ratio")),
            "turnover_rate": _na(spot.get("turnover_rate")),
            "pe_dynamic": _na(spot.get("pe_dynamic"), ".1f"),
            "pb": _na(spot.get("pb"), ".2f"),
            "total_market_cap": _na(spot.get("total_market_cap"), ".1f"),
            "amplitude": _na(spot.get("amplitude")),
            "sixty_day_change": _pct(spot.get("sixty_day_change")),
            "ytd_change": _pct(spot.get("ytd_change")),
        })

    # 2. 趋势分析
    trend = _analyze_trend(ind_rows, latest_close)

    # 3. 技术指标
    indicators = _analyze_indicators(ind_rows)

    # 4. 支撑/阻力
    sr_levels = _find_support_resistance(ind_rows, latest_close, atr14)

    # 5. 风险评估
    risk = _assess_risk(ind_rows, spot, latest_close)

    # 6. 仓位建议
    position = _position_advice(ind_rows, sr_levels, spot)

    return {
        "report_title": f"{name}({symbol}) 技术分析报告",
        "report_date": _today(),
        "disclaimer": "本报告基于技术指标自动生成, 仅供学习参考, 不构成任何投资建议。投资有风险, 入市需谨慎。",
        "basic_info": basic,
        "trend_analysis": trend,
        "technical_indicators": indicators,
        "support_resistance": sr_levels,
        "risk_assessment": risk,
        "position_advice": position,
    }
