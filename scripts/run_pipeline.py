# -*- coding: utf-8 -*-
"""每日数据流水线:采集 -> 分析 -> 生成 data/*.json。
- GitHub Actions:每个交易日 15:35(北京时间)自动运行并提交 data/ 变更。
- 本地:python scripts/run_pipeline.py 随时手动运行。

所有数据均来自公开渠道,仅用于学习研究,不构成投资建议。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import analyze as az       # noqa: E402
import fetch_data as fd    # noqa: E402
import indicators as ind   # noqa: E402
import report as rp        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HISTORY_MAX = 150


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("  ->", name)


def step(title):
    print(f"[{title}]")


def main():
    os.makedirs(DATA, exist_ok=True)
    errors = []

    def guard(name, fn):
        try:
            return fn()
        except Exception:
            errors.append(f"{name}: {traceback.format_exc(limit=2)}")
            print(f"  !! {name} 失败(已跳过):", traceback.format_exc(limit=1).strip().splitlines()[-1])
            return None

    now_iso = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 行情快照
    step("1/6 行情快照")
    quotes = guard("行情快照", fd.fetch_index_quotes) or []
    if quotes:
        save("snapshot.json", {"updated_at": now_iso, "indexes": quotes})

    # 2. 指数K线
    step("2/6 指数K线(akshare 优先,失败自动直连)")
    k_sh = guard("上证K线", lambda: fd.fetch_kline("1.000001", 180)) or []
    k_cyb = guard("创业板K线", lambda: fd.fetch_kline("0.399006", 180)) or []
    k_sz = guard("深市K线", lambda: fd.fetch_kline("0.399001", 180)) or []
    if k_sh:
        save("kline_sh.json", k_sh)
    if k_cyb:
        save("kline_cyb.json", k_cyb)
    if k_sz:
        save("kline_sz.json", k_sz)   # 供缓存重建工具精确计算两市均量
    trade_date = k_sh[-1]["date"] if k_sh else dt.date.today().strftime("%Y-%m-%d")

    # 3. 资金流
    step("3/6 大盘与板块资金")
    main_series = guard("大盘主力资金", lambda: fd.fetch_market_main_flow(80)) or []
    if main_series:
        save("main_flow.json", main_series[-60:])

    # 行业资金:分别取净流入与净流出两端(接口单次只能按一个方向排序)
    industries_in = guard("行业资金流入", lambda: fd.fetch_sector_flow("industry", 60, po=1)) or []
    industries_out = guard("行业资金流出", lambda: fd.fetch_sector_flow("industry", 60, po=0)) or []
    seen, industries = set(), []
    for r in industries_in + industries_out:
        if r["code"] not in seen:
            seen.add(r["code"])
            industries.append(r)
    concepts = guard("概念涨幅榜", lambda: fd.fetch_sector_flow("concept", 30, fid="f3")) or []
    if industries or concepts:  # 采集失败时保留旧数据,不用空数据覆盖
        industry_gainers = sorted(industries, key=lambda r: -(r.get("pct") or -999))[:15] if industries else []
        save("sectors.json", {"industry": industries,
                              "industry_gainers": industry_gainers,
                              "concept_gainers": concepts})
    stocks = guard("个股资金Top", lambda: fd.fetch_stock_flow_top(20)) or []
    if stocks:
        save("stocks_flow.json", {"date": trade_date, "list": stocks})

    # 4. 涨跌停池 & 两融
    step("4/6 涨跌停池与两融")
    pools = guard("涨跌停池", fd.fetch_pools) or {"date": None, "zt": [], "dt": [], "zb": [],
                                                  "zt_count": 0, "dt_count": 0, "zb_count": 0}
    if pools.get("date"):
        save("zt.json", pools)
    margin = guard("两融", lambda: fd.fetch_margin(70)) or []
    if margin:
        save("margin.json", margin)

    # 5. 分析计算
    # 5/6. 分析计算与报告(核心数据缺失时跳过,不覆盖已有 report/history)
    core_ok = bool(quotes) and bool(k_sh)
    temp = None
    if core_ok:
        step("5/6 温度计与技术面")
        sh_q = next((q for q in quotes if q["code"] == "000001"), {})
        sz_q = next((q for q in quotes if q["code"] == "399001"), {})
        amount_yi = ((sh_q.get("amount") or 0) + (sz_q.get("amount") or 0)) / 1e8
        # 两市5日均量:上证K线 amt=沪市总成交额,深证成指K线 amt=深市总成交额
        amt_ma5_yi = None
        if len(k_sh) >= 6 and len(k_sz) >= 6:
            amt_ma5_yi = (sum(k["amt"] for k in k_sh[-6:-1]) / 5 +
                          sum(k["amt"] for k in k_sz[-6:-1]) / 5) / 1e8
        main_net_yi = (main_series[-1]["main"] / 1e8) if main_series else 0.0
        margin_chg5 = None
        if len(margin) >= 6 and margin[-1]["rzye"] and margin[-6]["rzye"]:
            margin_chg5 = (margin[-1]["rzye"] / margin[-6]["rzye"] - 1) * 100

        temp = az.market_temperature(quotes, pools, amount_yi, amt_ma5_yi, main_net_yi, margin_chg5)
        tech_sh = ind.technical_view(k_sh) if k_sh else None
        tech_cyb = ind.technical_view(k_cyb) if k_cyb else None
        pos = az.position_advice(temp["score"],
                                 tech_sh["align"] if tech_sh else "mixed",
                                 tech_sh["macd"]["state"] if tech_sh and tech_sh.get("macd") else None)
        print(f"  温度 {temp['score']}({temp['label']}),仓位参考 {pos['pct']} 成")

        step("6/6 生成报告")
        rep = rp.build_report(trade_date, quotes, temp, pos, tech_sh, tech_cyb,
                              industries, concepts, pools, main_series, margin,
                              amount_yi, amt_ma5_yi, margin_chg5)
        save("report.json", rep)

        hpath = os.path.join(DATA, "history.json")
        try:
            with open(hpath, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
        entry = {"date": trade_date, "temp": temp["score"], "label": temp["label"],
                 "sh_pct": sh_q.get("pct"), "amount_yi": round(amount_yi),
                 "zt": pools.get("zt_count", 0), "dt": pools.get("dt_count", 0),
                 "main_yi": round(main_net_yi)}
        if history and history[-1].get("date") == trade_date:
            history[-1] = entry
        else:
            history.append(entry)
        history = history[-HISTORY_MAX:]
        save("history.json", history)
    else:
        print("  !! 核心数据(行情/K线)缺失,跳过分析与报告,保留既有数据不覆盖")

    if core_ok:   # 失败运行不覆盖 meta,避免站点显示错误的"数据日期"
        save("meta.json", {"generated_at": now_iso, "date": trade_date,
                           "akshare_used": fd.AKSHARE_OK, "errors": errors})

    if temp:
        print(f"\n完成:数据日期 {trade_date},温度 {temp['score']}({temp['label']}),"
              f"共 {len(errors)} 个采集项失败")
    if not core_ok:
        print("核心数据(行情/K线)缺失,退出码 1")
        sys.exit(1)


if __name__ == "__main__":
    main()
