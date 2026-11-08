# -*- coding: utf-8 -*-
"""市场情绪温度计与仓位建议。规则完全透明、可解释,参数集中在 CFG 便于自定义。"""
from __future__ import annotations


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


CFG = {
    "breadth_scale": 80.0,   # 涨跌家数占比每偏离50%一个点换算的分数
    "breadth_cap": 18.0,
    "zt_unit": 160.0,        # 涨停家数满分基准
    "dt_unit": 120.0,
    "zt_cap": 15.0,
    "vol_scale": 18.0,       # 量能:相对前5日均量的偏离换算
    "vol_cap": 10.0,
    "flow_scale": 45.0,      # 主力净流入:每45亿=±1分
    "flow_cap": 12.0,
    "margin_scale": 3.0,     # 融资余额5日变化%换算
    "margin_cap": 5.0,
    "zb_rate_hot": 0.45,     # 炸板率超过该值视为退潮
    "zb_rate_cold": 0.20,
}


def market_temperature(quotes, pools, amount_yi, amt_ma5_yi, main_net_yi, margin_chg5_pct):
    """综合情绪温度:基础分50,叠加六个可解释维度,输出 0~100 分及明细。"""
    sh = next((q for q in quotes if q["code"] == "000001"), {})
    sz = next((q for q in quotes if q["code"] == "399001"), {})
    up = (sh.get("up") or 0) + (sz.get("up") or 0)
    down = (sh.get("down") or 0) + (sz.get("down") or 0)
    parts = []

    # 1. 广度
    ratio = up / max(up + down, 1)
    b = _clamp((ratio - 0.5) * CFG["breadth_scale"], -CFG["breadth_cap"], CFG["breadth_cap"])
    parts.append(("涨跌家数", b, f"上涨 {up} 家 / 下跌 {down} 家,上涨占比 {ratio * 100:.0f}%"))

    # 2. 涨跌停结构
    zt, dt, zb = pools.get("zt_count") or 0, pools.get("dt_count") or 0, pools.get("zb_count") or 0
    z = _clamp(min(zt, 200) / CFG["zt_unit"] * 12 - min(dt, 160) / CFG["dt_unit"] * 12,
               -CFG["zt_cap"], CFG["zt_cap"])
    parts.append(("涨停/跌停", z, f"涨停 {zt} 家,跌停 {dt} 家"))

    # 3. 量能(量价配合)
    sh_pct = sh.get("pct") or 0
    if amt_ma5_yi and amount_yi:
        vol = _clamp((amount_yi / amt_ma5_yi - 1) * CFG["vol_scale"] * (1 if sh_pct >= 0 else -1),
                     -CFG["vol_cap"], CFG["vol_cap"])
        parts.append(("量能配合", vol,
                      f"两市成交 {amount_yi:.0f} 亿,为前5日均量的 {amount_yi / amt_ma5_yi * 100:.0f}%"))
    else:
        parts.append(("量能配合", 0.0, "量能数据不足"))

    # 4. 主力资金
    f = _clamp(main_net_yi / CFG["flow_scale"], -CFG["flow_cap"], CFG["flow_cap"])
    parts.append(("主力资金", f, f"全市场主力净流入 {main_net_yi:+.0f} 亿"))

    # 5. 杠杆情绪(两融,T+1)
    if margin_chg5_pct is not None:
        mg = _clamp(margin_chg5_pct * CFG["margin_scale"], -CFG["margin_cap"], CFG["margin_cap"])
        parts.append(("杠杆(两融)", mg, f"融资余额5日变化 {margin_chg5_pct:+.2f}%"))
    else:
        parts.append(("杠杆(两融)", 0.0, "两融数据不足"))

    # 6. 涨停效应(炸板率)
    zb_rate = zb / max(zt + zb, 1) if (zt + zb) else 0.0
    zb_pts = 0.0
    if zt + zb > 0:
        if zb_rate >= CFG["zb_rate_hot"]:
            zb_pts = -6.0
        elif zb_rate <= CFG["zb_rate_cold"] and zt >= 60:
            zb_pts = 4.0
    parts.append(("涨停效应", zb_pts,
                  f"炸板 {zb} 家,炸板率 {zb_rate * 100:.0f}%" if zt + zb else "无涨停数据"))

    score = int(round(_clamp(50 + sum(p[1] for p in parts), 2, 98)))
    if score <= 20:
        label, mood = "冰点", "情绪极度低迷,防守优先,多看少动"
    elif score <= 40:
        label, mood = "降温", "赚钱效应偏弱,谨慎参与,控制仓位"
    elif score <= 60:
        label, mood = "中性", "多空均衡,结构性行情,跟随主线"
    elif score <= 80:
        label, mood = "回暖", "赚钱效应回升,可积极参与但留有后路"
    else:
        label, mood = "过热", "情绪亢奋,注意逢高兑现与回撤风险"

    return {"score": score, "label": label, "mood": mood, "parts": parts,
            "up": up, "down": down, "flat": (sh.get("flat") or 0) + (sz.get("flat") or 0),
            "zb_rate": zb_rate}


def position_advice(score, align, macd_state):
    """基于温度与技术趋势给出仓位参考(仅供参考,不构成投资建议)。"""
    if score <= 20:
        pct, text = 3, "情绪冰点,多看少动,仓位建议 ≤3 成,等待放量收复5日线的企稳信号"
    elif score <= 40:
        pct, text = 5, "情绪偏弱,轻仓试探,仓位建议 3~5 成,严格止损、不轻易补仓"
    elif score <= 60:
        pct, text = 6, "中性震荡,灵活应对,仓位建议 5~6 成,跟随资金主线"
    elif score <= 80:
        pct, text = 8, "情绪回暖,顺势而为,仓位建议 6~8 成,分批参与注意节奏"
    else:
        pct, text = 6, "情绪过热,谨防冲高回落,建议逢高兑现利润,仓位降至 5~6 成"

    risks = []
    if align == "bearish":
        risks.append("日线均线呈空头排列,反弹宜以减仓思维对待")
        pct = max(2, pct - 2)
        text += ";技术面偏空,仓位再降一档"
    elif align == "bullish" and score <= 40:
        text += ";均线多头提供一定支撑,可在支撑位附近低吸"
    if macd_state == "死叉":
        risks.append("MACD 刚形成死叉,短线动能转弱,注意回踩风险")
    if macd_state == "金叉":
        risks.append("MACD 刚形成金叉,可作为短线企稳参考,结合量能确认")
    return {"pct": pct, "text": text, "risks": risks}


def cycle_phase(score, align, macd_state):
    """情绪周期定位:冰点 → 修复 → 回暖 → 过热 → 退潮。纯描述性框架,不预测。"""
    if score <= 20:
        if align == "bearish":
            return ("冰点期(下行末段)",
                    "情绪与趋势双弱,右侧机会尚未出现;历史上冰点之后数个交易日常有超跌修复,"
                    "但必须以放量阳线收复关键均线确认,不可提前抢跑")
        return ("冰点期(酝酿修复)", "情绪极低但技术结构未完全走坏,重点关注率先止跌走强的方向")
    if score <= 40:
        return ("降温/退潮期", "赚钱效应收缩,容易'赚了指数不赚钱',宜降低操作频率、收缩战线")
    if score <= 60:
        return ("震荡期", "多空均衡的结构市,跟随资金主线,快进快出为主")
    if score <= 80:
        return ("回暖期", "赚钱效应扩散,可顺势参与;注意'分歧转一致'时的节奏")
    return ("过热期", "一致预期过强常是阶段顶部信号,以兑现利润、控制回撤为先")


def bull_bear_points(quotes, temp, tech_sh, main_net_yi, amt_ratio, margin_chg5, pools):
    """多空要点:每个要点都由当日数据直接推导,尽量多空平衡,供独立判断而非给结论。"""
    sh = next((q for q in quotes if q["code"] == "000001"), {})
    sz = next((q for q in quotes if q["code"] == "399001"), {})
    up = (sh.get("up") or 0) + (sz.get("up") or 0)
    down = (sh.get("down") or 0) + (sz.get("down") or 0)
    sh_pct = sh.get("pct") or 0
    bull, bear = [], []

    # 资金面
    if main_net_yi > 80:
        bull.append(f"主力资金全天净流入 {main_net_yi:+.0f} 亿,增量资金态度积极")
    elif main_net_yi < -80:
        bear.append(f"主力资金全天净流出 {abs(main_net_yi):.0f} 亿,主动抛压尚未消化")

    # 广度
    ratio = up / max(up + down, 1)
    if ratio >= 0.60:
        bull.append(f"个股上涨占比 {ratio * 100:.0f}%,赚钱效应扩散")
    elif ratio <= 0.35:
        bear.append(f"个股上涨占比仅 {ratio * 100:.0f}%,亏钱效应明显,持股体验差")

    # 量价关系
    if amt_ratio:
        if sh_pct < 0 and amt_ratio < 0.9:
            bull.append("缩量下跌,恐慌性抛压趋于衰竭,客观上利于止跌企稳")
        elif sh_pct < 0 and amt_ratio > 1.15:
            bear.append("放量下跌,资金离场意愿强,不宜急于'接飞刀'")
        elif sh_pct > 0 and amt_ratio > 1.15:
            bull.append("放量上涨,量价配合良好,上涨可信度较高")
        elif sh_pct > 0 and amt_ratio < 0.9:
            bear.append("缩量上涨,反弹缺乏增量资金确认,持续性存疑")

    # 技术面
    if tech_sh:
        if tech_sh["align"] == "bullish":
            bull.append("上证 MA5/10/20 多头排列,中期趋势结构尚未破坏")
        elif tech_sh["align"] == "bearish":
            bear.append("上证均线空头排列,技术性反弹均宜按反抽对待")
        m = tech_sh.get("macd")
        if m and m["state"] == "金叉":
            bull.append("MACD 刚形成金叉,短线动能修复")
        elif m and m["state"] == "死叉":
            bear.append("MACD 刚形成死叉,调整可能延续")
        pos20 = tech_sh.get("pos_vs_ma20")
        if pos20 is not None and pos20 >= 0:
            bull.append(f"指数收于 MA20 上方({pos20:+.1f}%),中期支撑有效")
        elif pos20 is not None:
            bear.append(f"指数收于 MA20 下方({pos20:+.1f}%),中期趋势承压")

    # 涨跌停结构
    zt = pools.get("zt_count") or 0
    dt = pools.get("dt_count") or 0
    zb = pools.get("zb_count") or 0
    zb_rate = zb / max(zt + zb, 1) if (zt + zb) else 0
    if zt >= 60:
        bull.append(f"涨停 {zt} 家,短线局部赚钱效应仍在")
    if dt >= 30:
        bear.append(f"跌停 {dt} 家,高位股补跌风险未释放完毕")
    if zb_rate >= 0.45 and (zt + zb):
        bear.append(f"炸板率 {zb_rate * 100:.0f}% 偏高,打板资金亏损明显,情绪退潮信号")
    elif zb_rate <= 0.20 and zt >= 50:
        bull.append(f"炸板率仅 {zb_rate * 100:.0f}%,封板质量高")

    # 杠杆资金
    if margin_chg5 is not None:
        if margin_chg5 >= 0.30:
            bull.append(f"融资余额 5 日增加 {margin_chg5:+.2f}%,杠杆资金仍在进场")
        elif margin_chg5 <= -0.50:
            bear.append(f"融资余额 5 日减少 {margin_chg5:+.2f}%,杠杆资金退潮")

    # 温度位置
    if temp <= 20:
        bear.append("情绪处于冰点区,趋势惯性向下;但极端低迷往往孕育修复,宜等右侧信号而非左侧抢跑")
    elif temp >= 80:
        bear.append("情绪过热、交易拥挤,谨防利好兑现后的踩踏")

    if not bull:
        bull.append("暂无明显利多信号,以观察等待为主")
    if not bear:
        bear.append("暂无明显利空信号,但仍需防范突发波动与黑天鹅")
    return bull[:6], bear[:6]
