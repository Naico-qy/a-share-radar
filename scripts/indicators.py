# -*- coding: utf-8 -*-
"""纯 Python 技术指标:MA / MACD / RSI / 均线排列。
指标口径与 InStock、akshare 等开源项目的常用实现保持一致(MACD 柱 = 2*(DIF-DEA))。
前端 assets/js/indicators.js 为同口径的 JS 版本,用于自选股实时计算。
"""
from __future__ import annotations


def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def sma_series(vals, n):
    out = []
    for i in range(len(vals)):
        out.append(sum(vals[i - n + 1:i + 1]) / n if i + 1 >= n else None)
    return out


def ema_series(vals, n):
    k = 2.0 / (n + 1)
    out, e = [], None
    for v in vals:
        e = v if e is None else (v - e) * k + e
        out.append(e)
    return out


def macd(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow + sig:
        return None
    dif_s = [a - b for a, b in zip(ema_series(closes, fast), ema_series(closes, slow))]
    dea_s = ema_series(dif_s, sig)
    hist_s = [(d - m) * 2 for d, m in zip(dif_s, dea_s)]
    d, m, h = dif_s[-1], dea_s[-1], hist_s[-1]
    pd_, pm, ph = dif_s[-2], dea_s[-2], hist_s[-2]
    if pd_ <= pm and d > m:
        state = "金叉"
    elif pd_ >= pm and d < m:
        state = "死叉"
    elif d > m:
        state = "多头运行"
    else:
        state = "空头运行"
    return {"dif": d, "dea": m, "hist": h, "hist_prev": ph,
            "momentum": "增强" if abs(h) > abs(ph) else "衰减",
            "state": state}


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def ma_view(closes):
    ma = {f"ma{n}": sma(closes, n) for n in (5, 10, 20, 60)}
    m5, m10, m20 = ma["ma5"], ma["ma10"], ma["ma20"]
    align = "mixed"
    if m5 and m10 and m20:
        if m5 > m10 > m20:
            align = "bullish"
        elif m5 < m10 < m20:
            align = "bearish"
    return {"ma": ma, "align": align}


def technical_view(klines):
    """输入日K列表(升序),输出综合技术面视图。"""
    closes = [k["close"] for k in klines]
    if not closes:
        return None
    mv = ma_view(closes)
    m = macd(closes)
    r = rsi(closes)
    last = closes[-1]
    chg5 = (last / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    chg20 = (last / closes[-21] - 1) * 100 if len(closes) >= 21 else None
    ma20 = mv["ma"]["ma20"]
    pos20 = (last / ma20 - 1) * 100 if ma20 else None
    return {"last": last, "ma": mv["ma"], "align": mv["align"],
            "macd": m, "rsi14": r, "chg5": chg5, "chg20": chg20,
            "pos_vs_ma20": pos20, "date": klines[-1]["date"]}
