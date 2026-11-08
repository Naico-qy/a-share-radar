# -*- coding: utf-8 -*-
"""从 data/ 已保存的缓存数据重建 report.json / history.json / meta.json(零网络请求)。

适用场景:
- 本地 IP 被数据源临时限流,无法完整运行 run_pipeline.py;
- 想基于现有快照调整 analyze.py 参数后重算分析结果。

用法: python scripts/rebuild_from_cache.py
注意:板块/个股等原始列表仍使用缓存数据;下次成功运行 run_pipeline.py 后自动更新。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import analyze as az       # noqa: E402
import indicators as ind   # noqa: E402
import report as rp        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HISTORY_MAX = 150


def load(name, default=None):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("  ->", name)


def main():
    quotes = (load("snapshot.json") or {}).get("indexes") or []
    k_sh = load("kline_sh.json") or []
    k_cyb = load("kline_cyb.json") or []
    k_sz = load("kline_sz.json") or []
    main_series = load("main_flow.json") or []
    sectors = load("sectors.json") or {}
    industries = sectors.get("industry") or []
    concepts = sectors.get("concept_gainers") or []
    pools = load("zt.json") or {"date": None, "zt": [], "dt": [], "zb": [],
                                "zt_count": 0, "dt_count": 0, "zb_count": 0}
    margin = load("margin.json") or []

    if not quotes or not k_sh:
        print("核心缓存缺失(需要 snapshot.json 与 kline_sh.json),无法重建")
        sys.exit(1)

    trade_date = k_sh[-1]["date"]
    sh_q = next((q for q in quotes if q["code"] == "000001"), {})
    sz_q = next((q for q in quotes if q["code"] == "399001"), {})
    amount_yi = ((sh_q.get("amount") or 0) + (sz_q.get("amount") or 0)) / 1e8

    # 两市前5日均量:优先用深市K线精确计算;无深市缓存时按今日深/沪比例近似
    amt_ma5_yi = None
    if len(k_sh) >= 6:
        sh5 = sum(k["amt"] for k in k_sh[-6:-1]) / 5
        if len(k_sz) >= 6:
            amt_ma5_yi = (sh5 + sum(k["amt"] for k in k_sz[-6:-1]) / 5) / 1e8
        elif sh_q.get("amount") and sz_q.get("amount"):
            ratio = 1 + sz_q["amount"] / max(sh_q["amount"], 1)
            amt_ma5_yi = sh5 * ratio / 1e8
            print(f"  (无深市K线缓存,按今日深/沪比例 {ratio:.2f} 近似两市均量)")

    main_net_yi = (main_series[-1]["main"] / 1e8) if main_series else 0.0
    margin_chg5 = None
    if len(margin) >= 6 and margin[-1]["rzye"] and margin[-6]["rzye"]:
        margin_chg5 = (margin[-1]["rzye"] / margin[-6]["rzye"] - 1) * 100

    temp = az.market_temperature(quotes, pools, amount_yi, amt_ma5_yi, main_net_yi, margin_chg5)
    tech_sh = ind.technical_view(k_sh)
    tech_cyb = ind.technical_view(k_cyb)
    pos = az.position_advice(temp["score"],
                             tech_sh["align"] if tech_sh else "mixed",
                             tech_sh["macd"]["state"] if tech_sh and tech_sh.get("macd") else None)

    rep = rp.build_report(trade_date, quotes, temp, pos, tech_sh, tech_cyb,
                          industries, concepts, pools, main_series, margin,
                          amount_yi, amt_ma5_yi, margin_chg5)
    save("report.json", rep)

    history = load("history.json") or []
    entry = {"date": trade_date, "temp": temp["score"], "label": temp["label"],
             "sh_pct": sh_q.get("pct"), "amount_yi": round(amount_yi),
             "zt": pools.get("zt_count", 0), "dt": pools.get("dt_count", 0),
             "main_yi": round(main_net_yi)}
    if history and history[-1].get("date") == trade_date:
        history[-1] = entry
    else:
        history.append(entry)
    save("history.json", history[-HISTORY_MAX:])

    save("meta.json", {"generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "date": trade_date, "akshare_used": None, "rebuilt": True, "errors": []})
    print(f"\n重建完成:数据日期 {trade_date},温度 {temp['score']}({temp['label']})")


if __name__ == "__main__":
    main()
