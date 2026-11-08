# -*- coding: utf-8 -*-
"""每日复盘报告生成器:把当日数据拼装成结构化的 HTML 片段与要点摘要,
输出到 data/report.json,前端「每日报告」标签页直接渲染。"""
from __future__ import annotations

import datetime as dt

DISCLAIMER = ("本报告由开源程序基于公开市场数据自动生成,所有内容(包括仓位、方向、板块提示)仅为技术与统计层面的"
              "学习交流材料,不构成任何投资建议或收益承诺。数据可能存在延迟或错误,市场有风险,投资需谨慎。")


def _pct(v):
    if not isinstance(v, (int, float)):
        return "--"
    return f"{v:+.2f}%"


def _num(v, d=2):
    if not isinstance(v, (int, float)):
        return "--"
    return f"{v:,.{d}f}"


def _yi(v, d=1):
    if not isinstance(v, (int, float)):
        return "--"
    return f"{v / 1e8:,.{d}f} 亿"


def _flow_table(rows, n=5):
    body = ""
    for r in rows[:n]:
        main = r.get("main") or 0
        css = "up" if main >= 0 else "down"
        body += (f"<tr><td>{r['name']}</td>"
                 f"<td class='{css}'>{main / 1e8:+,.1f} 亿</td>"
                 f"<td>{_pct(r.get('main_pct'))}</td>"
                 f"<td class='{'up' if (r.get('pct') or 0) >= 0 else 'down'}'>{_pct(r.get('pct'))}</td>"
                 f"<td>{r.get('leader') or '--'}</td></tr>")
    return ("<table><thead><tr><th>板块</th><th>主力净流入</th><th>净占比</th>"
            "<th>涨跌幅</th><th>领涨股</th></tr></thead><tbody>" + body + "</tbody></table>")


def _tech_text(name, v):
    if not v:
        return f"<p><b>{name}</b>:数据不足。</p>"
    align_s = {"bullish": "多头排列", "bearish": "空头排列", "mixed": "反复纠缠"}.get(v["align"], "--")
    if v["rsi14"] is None:
        rsi_s = "--"
    elif v["rsi14"] > 70:
        rsi_s = f"{v['rsi14']:.0f}(超买区)"
    elif v["rsi14"] < 30:
        rsi_s = f"{v['rsi14']:.0f}(超卖区)"
    else:
        rsi_s = f"{v['rsi14']:.0f}(中性)"
    macd_s = f"MACD {v['macd']['state']}({v['macd']['momentum']})" if v["macd"] else "MACD --"
    return (f"<p><b>{name}</b>:收盘 {_num(v['last'])},MA5/10/20 <b>{align_s}</b>;"
            f"{macd_s},RSI14 {rsi_s};近5日 {_pct(v['chg5'])},近20日 {_pct(v['chg20'])},"
            f"较MA20 {_pct(v['pos_vs_ma20'])}。</p>")


def build_report(trade_date, quotes, temp, pos, tech_sh, tech_cyb,
                 industries, concepts, pools, main_series, margin,
                 amount_yi, amt_ma5_yi):
    sh = next((q for q in quotes if q["code"] == "000001"), {})
    sh_pct = sh.get("pct") or 0
    score = temp["score"]
    zb_rate = temp.get("zb_rate") or 0

    sections = []

    # 1 大盘速览
    rows = ""
    for q in quotes:
        css = "up" if (q.get("pct") or 0) >= 0 else "down"
        extra = ""
        if q["code"] in ("000001", "399001"):
            extra = f"<td>{q.get('up')}/{q.get('down')}</td>"
        rows += (f"<tr><td>{q['name']}</td><td>{_num(q.get('price'))}</td>"
                 f"<td class='{css}'>{_pct(q.get('pct'))}</td><td>{_num(q.get('chg'))}</td>"
                 f"<td>{_yi(q.get('amount'), 0)}</td>{extra}</tr>")
    head = "<tr><th>指数</th><th>收盘</th><th>涨跌幅</th><th>涨跌</th><th>成交额</th><th>涨/跌家数</th></tr>"
    sections.append({"id": "overview", "title": "① 大盘速览",
                     "html": f"<table><thead>{head}</thead><tbody>{rows}</tbody></table>"
                             f"<p>两市合计成交 <b>{amount_yi:,.0f} 亿</b>,为前5日均量的 "
                             f"{(amount_yi / amt_ma5_yi * 100) if amt_ma5_yi else '--'}%。</p>"})

    # 2 市场温度
    chips = "".join(
        f"<span class='chip {'neg' if p[1] < 0 else ('pos' if p[1] > 0 else '')}'>"
        f"{p[0]} <b>{p[1]:+.1f}</b><i>{p[2]}</i></span>"
        for p in temp["parts"])
    sections.append({"id": "temp", "title": "② 市场温度计",
                     "html": f"<p class='big'><b>{score} / 100 · {temp['label']}</b> —— {temp['mood']}</p>"
                             f"<div class='chips'>{chips}</div>"
                             f"<p>打分规则:基础分 50 分,叠加涨跌家数、涨跌停结构、量能、主力资金、两融、"
                             f"炸板率六个维度(参数见 <code>scripts/analyze.py</code>),规则透明可复核。</p>"})

    # 3 资金面
    today_main = main_series[-1]["main"] if main_series else None
    ma5_main = (sum(x["main"] for x in main_series[-6:-1]) / 5) if main_series and len(main_series) >= 6 else None
    flow_html = "<p>全市场主力资金:"
    if today_main is not None:
        trend = "高于" if (ma5_main and today_main > ma5_main) else "低于"
        flow_html += (f"<b class='{'up' if today_main >= 0 else 'down'}'>"
                      f"{today_main / 1e8:+,.0f} 亿</b>,{trend}近5日均值"
                      f"({ma5_main / 1e8:+,.0f} 亿)。" if ma5_main is not None else f"{today_main / 1e8:+,.0f} 亿。")
    else:
        flow_html += "数据暂缺。"
    if margin:
        m = margin[-1]
        chg5 = ((m["rzye"] / margin[-6]["rzye"] - 1) * 100) if len(margin) >= 6 else None
        flow_html += (f"两融(T-1 披露):融资余额 <b>{m['rzye'] / 1e12:.2f} 万亿</b>"
                      + (f",5日变化 {chg5:+.2f}%,最新单日融资净买入 {m['rzjme'] / 1e8:+,.1f} 亿。" if chg5 is not None else "。"))
    sections.append({"id": "funds", "title": "③ 资金面", "html": flow_html})
    if industries:
        inflow = sorted(industries, key=lambda r: -(r.get("main") or 0))[:5]
        outflow = sorted(industries, key=lambda r: (r.get("main") or 0))[:5]
        sections.append({"id": "funds2", "title": "④ 行业主力资金 Top5",
                         "html": "<p><b>净流入居前</b>(资金进攻方向):</p>" + _flow_table(inflow) +
                                 "<p><b>净流出居前</b>(资金撤退方向,持仓注意回避):</p>" + _flow_table(outflow)})

    # 5 涨停梯队
    if pools.get("date"):
        zt, dt_, zb = pools["zt_count"], pools["dt_count"], pools["zb_count"]
        max_lbc = max([x.get("lbc") or 0 for x in pools["zt"]] or [0])
        lian = sorted([x for x in pools["zt"] if (x.get("lbc") or 0) >= 2],
                      key=lambda x: -(x.get("lbc") or 0))[:12]
        body = (f"<p>涨停 <b class='up'>{zt}</b> 家 · 跌停 <b class='down'>{dt_}</b> 家 · "
                f"炸板 {zb} 家(炸板率 {zb_rate * 100:.0f}%) · 最高连板 <b>{max_lbc} 板</b>"
                f"(数据日期 {pools['date']})</p>")
        if lian:
            rows = "".join(
                f"<tr><td>{x['name']}</td><td>{x['code']}</td>"
                f"<td class='up'>{x['lbc']} 连板</td><td>{x['hybk'] or '--'}</td>"
                f"<td>{_yi(x.get('fund'), 1)}</td><td>{x.get('fbt') or '--'}</td></tr>"
                for x in lian)
            body += ("<table><thead><tr><th>股票</th><th>代码</th><th>连板</th><th>行业</th>"
                     "<th>封单</th><th>首次封板</th></tr></thead><tbody>" + rows + "</tbody></table>")
        sections.append({"id": "zt", "title": "⑤ 涨停梯队与打板情绪", "html": body})

    # 6 技术面
    sections.append({"id": "tech", "title": "⑥ 技术面(指数)",
                     "html": _tech_text("上证指数", tech_sh) + _tech_text("创业板指", tech_cyb)})

    # 7 热点主线
    if concepts:
        rows = ""
        for r in concepts[:10]:
            main = r.get("main") or 0
            star = " ★" if main > 0 else ""
            css = "up" if (r.get("pct") or 0) >= 0 else "down"
            rows += (f"<tr><td>{r['name']}{star}</td>"
                     f"<td class='{css}'>{_pct(r.get('pct'))}</td>"
                     f"<td class='{'up' if main >= 0 else 'down'}'>{main / 1e8:+,.1f} 亿</td>"
                     f"<td>{r.get('leader') or '--'}</td></tr>")
        sections.append({"id": "hot", "title": "⑦ 热点板块(概念涨幅榜)",
                         "html": "<p>★ = 该板块当日主力资金为净流入(涨幅与资金共振,持续性更佳)。</p>"
                                 "<table><thead><tr><th>概念</th><th>涨跌幅</th><th>主力净流入</th>"
                                 "<th>领涨股</th></tr></thead><tbody>" + rows + "</tbody></table>"})

    # 8 明日参考与操作建议
    hot = [r for r in industries if (r.get("main") or 0) > 0 and (r.get("pct") or 0) > 0]
    hot.sort(key=lambda r: -(r.get("main") or 0))
    direction = "、".join(f"<b>{r['name']}</b>({r['main'] / 1e8:+,.1f} 亿,领涨股 {r['leader']})" for r in hot[:3]) \
        or "暂无资金与涨幅共振的板块,建议观望为主"
    risks = list(pos.get("risks") or [])
    if amt_ma5_yi and amount_yi and amount_yi / amt_ma5_yi < 0.85 and sh_pct < 0:
        risks.append("两市明显缩量下跌,资金观望,反弹质量存疑")
    if zb_rate >= 0.45:
        risks.append(f"炸板率 {zb_rate * 100:.0f}% 偏高,打板情绪退潮,追高风险大")
    if score >= 80:
        risks.append("情绪过热,波动可能放大,注意控制回撤")
    if score <= 20:
        risks.append("冰点之后常有修复,但也可能继续阴跌,勿盲目抄底")
    if not risks:
        risks.append("暂无特别风险信号,关注量能与主线的持续性")
    risk_html = "".join(f"<li>{r}</li>" for r in risks)
    sections.append({"id": "advice", "title": "⑧ 明日参考与操作建议",
                     "html": f"<div class='advice-box'><b>仓位参考:{pos['pct']} 成左右</b><br>{pos['text']}</div>"
                             f"<p><b>资金+涨幅共振方向</b>:{direction}</p>"
                             f"<p><b>风险提示</b>:</p><ul>{risk_html}</ul>"})

    # 9 免责声明
    sections.append({"id": "disclaimer", "title": "⑨ 免责声明", "html": f"<p>{DISCLAIMER}</p>"})

    # 首页要点
    if today_main is not None:
        flow_text = f"主力资金净{'流入' if today_main >= 0 else '流出'} {abs(today_main) / 1e8:,.0f} 亿"
    else:
        flow_text = "主力资金数据暂缺"
    suggestions = [
        {"icon": "🧭", "text": f"市场温度 {score}/100({temp['label']}):{temp['mood']}"},
        {"icon": "💰", "text": flow_text},
        {"icon": "📊", "text": f"仓位参考约 {pos['pct']} 成(仅供参考)"},
    ]
    headline = (f"{trade_date} 收盘:上证 {_pct(sh_pct)},两市成交 {amount_yi:,.0f} 亿,"
                f"市场温度 {score}/100({temp['label']})")

    return {"date": trade_date,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temperature": {"score": score, "label": temp["label"], "mood": temp["mood"]},
            "position": pos, "headline": headline, "suggestions": suggestions,
            "sections": sections, "disclaimer": DISCLAIMER}
