# -*- coding: utf-8 -*-
"""
数据采集层(零硬依赖,纯 Python 标准库)。

- 指数日K优先使用 akshare(GitHub 高星开源财经数据库 https://github.com/akfamily/akshare)
  获取;未安装或调用失败时自动降级为东方财富 push2his 直连接口(与 akshare 同源)。
- 其余数据(行情快照/大盘资金流/板块资金/涨跌停池/两融)直接调用东方财富公开接口。

所有数据均来自公开渠道,仅用于学习研究,不构成投资建议。
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import random
import ssl
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 15
_CTX = ssl.create_default_context()

AKSHARE_OK = False
try:
    import akshare as ak  # optional dependency
    AKSHARE_OK = True
except Exception:
    ak = None

_ZT_UT = "7eea3edcaed734bea9cbfc24409ed989"  # 东财公开页通用 token


def _get(url: str, retries: int = 3) -> str:
    """带重试的 GET,返回文本。"""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "*/*",
                "Accept-Encoding": "gzip",
                "Referer": "https://quote.eastmoney.com/",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (i + 1) + random.random())
    raise RuntimeError(f"请求失败 {url[:90]} -> {last}")


def get_json(url: str):
    return json.loads(_get(url))


# ---------------------------------------------------------------- 行情快照

def fetch_index_quotes() -> list:
    """沪深核心指数实时快照(含涨跌家数、主力净流入)。"""
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2"
           "&secids=1.000001,0.399001,0.399006,1.000688"
           "&fields=f2,f3,f4,f5,f6,f12,f13,f14,f18,f62,f104,f105,f106")
    diff = get_json(url)["data"]["diff"]
    out = []
    for d in diff:
        out.append({
            "secid": f"{d['f13']}.{d['f12']}",
            "code": str(d["f12"]),
            "name": d["f14"],
            "price": d.get("f2"),
            "pct": d.get("f3"),
            "chg": d.get("f4"),
            "volume": d.get("f5"),
            "amount": d.get("f6"),
            "main_net": d.get("f62"),
            "up": d.get("f104") or 0,
            "down": d.get("f105") or 0,
            "flat": d.get("f106") or 0,
        })
    return out


# ---------------------------------------------------------------- K线

_AK_SYMBOL = {"1.000001": "sh000001", "0.399001": "sz399001",
              "0.399006": "sz399006", "1.000688": "sh000688"}


def fetch_kline(secid: str, lmt: int = 180) -> list:
    """指数日K(优先 akshare,失败降级直连)。返回按日期升序的列表。"""
    if AKSHARE_OK and secid in _AK_SYMBOL:
        try:
            df = ak.stock_zh_index_daily_em(symbol=_AK_SYMBOL[secid])
            recs = df.to_dict("records")[-lmt:]
            out = []
            for r in recs:
                out.append({
                    "date": str(r.get("date"))[:10],
                    "open": float(r["open"]),
                    "close": float(r["close"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "vol": float(r.get("volume", 0) or 0),
                    "amt": float(r.get("amount", 0) or 0),
                })
            if out:
                return out
        except Exception:
            pass  # akshare 异常时降级为直连
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=" + secid +
           "&klt=101&fqt=1&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57&end=20500101&lmt=" + str(lmt))
    j = get_json(url)
    out = []
    for line in (j.get("data") or {}).get("klines") or []:
        p = line.split(",")
        out.append({"date": p[0], "open": float(p[1]), "close": float(p[2]),
                    "high": float(p[3]), "low": float(p[4]),
                    "vol": float(p[5]), "amt": float(p[6])})
    return out


# ---------------------------------------------------------------- 资金流

def fetch_market_main_flow(lmt: int = 80) -> list:
    """沪深两市合计主力资金日度历史。
    优先使用 akshare.stock_market_fund_flow(),失败降级为同源直连接口。"""
    if AKSHARE_OK:
        try:
            df = ak.stock_market_fund_flow()
            recs = df.to_dict("records")[-lmt:]
            out = []
            for r in recs:
                out.append({
                    "date": str(r["日期"])[:10],
                    "main": float(r["主力净流入-净额"]),
                    "small": float(r["小单净流入-净额"]),
                    "mid": float(r["中单净流入-净额"]),
                    "big": float(r["大单净流入-净额"]),
                    "super": float(r["超大单净流入-净额"]),
                })
            if out:
                return out
        except Exception:
            pass  # 降级直连
    url = ("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=0&klt=101"
           "&secid=1.000001&secid2=0.399001&fields1=f1,f2,f3,f7"
           "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
           "&ut=b2884a393a59ad64002292a3e90d46a5")
    j = get_json(url)
    out = []
    for line in (j.get("data") or {}).get("klines") or []:
        p = line.split(",")
        out.append({"date": p[0], "main": float(p[1]), "small": float(p[2]),
                    "mid": float(p[3]), "big": float(p[4]), "super": float(p[5])})
    return out[-lmt:]


def fetch_sector_flow(board: str = "industry", pz: int = 100,
                      fid: str = "f62", po: int = 1) -> list:
    """板块资金/行情列表。board: industry(行业) / concept(概念)。fid=f62 按主力净流入排序。"""
    fs = "m:90+t:2" if board == "industry" else "m:90+t:3"
    url = ("https://push2.eastmoney.com/api/qt/clist/get?fid=" + fid +
           "&po=" + str(po) + "&pz=" + str(pz) + "&pn=1&np=1&fltt=2&invt=2&fs=" + fs +
           "&fields=f12,f14,f2,f3,f62,f66,f72,f184,f128,f140")
    j = get_json(url)
    out = []
    for d in (j.get("data") or {}).get("diff") or []:
        out.append({
            "code": str(d.get("f12")),
            "name": d.get("f14"),
            "price": d.get("f2"),
            "pct": d.get("f3"),
            "main": d.get("f62") or 0,
            "super": d.get("f66") or 0,
            "big": d.get("f72") or 0,
            "main_pct": d.get("f184"),
            "leader": d.get("f128"),
            "leader_code": d.get("f140"),
        })
    return out


def fetch_stock_flow_top(pz: int = 20) -> list:
    """全A个股主力净流入排行 Top N。"""
    url = ("https://push2.eastmoney.com/api/qt/clist/get?fid=f62&po=1&pz=" + str(pz) +
           "&pn=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
           "&fields=f12,f14,f2,f3,f62,f184,f21,f100")
    j = get_json(url)
    out = []
    for d in (j.get("data") or {}).get("diff") or []:
        out.append({
            "code": str(d.get("f12")),
            "name": d.get("f14"),
            "price": d.get("f2"),
            "pct": d.get("f3"),
            "main": d.get("f62") or 0,
            "main_pct": d.get("f184"),
            "float_mv": d.get("f21"),
            "industry": d.get("f100"),
        })
    return out


# ---------------------------------------------------------------- 涨跌停/炸板池

def _pool(kind: str, date: str, pagesize: int = 600, sort: str = "fbt%3Aasc") -> dict:
    url = (f"https://push2ex.eastmoney.com/getTopic{kind}Pool?ut={_ZT_UT}&dpt=wz.ztzt"
           f"&Pageindex=0&pagesize={pagesize}&sort={sort}&date={date}")
    return get_json(url).get("data") or {}


def _hhmmss(v) -> str:
    try:
        v = int(v)
        return f"{v // 10000:02d}:{(v // 100) % 100:02d}:{v % 100:02d}"
    except Exception:
        return ""


def _norm_pool_item(item: dict) -> dict:
    z = item.get("zttj") or {}
    return {
        "code": str(item.get("c")),
        "name": item.get("n"),
        "price": (item.get("p") or 0) / 1000,
        "pct": round(item.get("zdp") or 0, 2),
        "lbc": item.get("lbc") or 0,
        "fund": item.get("fund"),
        "zbc": item.get("zbc") or 0,
        "hybk": item.get("hybk"),
        "fbt": _hhmmss(item.get("fbt")),
        "days": z.get("days"),
        "ct": z.get("ct"),
    }


def fetch_pools(max_back: int = 12) -> dict:
    """涨停/跌停/炸板池。自动回溯到最近一个有涨停数据的交易日(周末/节假日兜底)。
    日期以接口返回的 qdate 为准(非交易日请求会返回最近交易日的数据)。"""
    today = dt.date.today()
    zt_data, date_used = None, None
    for i in range(max_back):
        cand = (today - dt.timedelta(days=i)).strftime("%Y%m%d")
        data = _pool("ZT", cand)
        if not data:
            continue
        qdate = str(data.get("qdate") or cand)
        if (data.get("tc") or 0) > 0:
            zt_data, date_used = data, qdate
            break
        if i == 0:  # 交易日盘中暂无涨停,也保留当日
            zt_data, date_used = data, qdate
    if zt_data is None:
        return {"date": None, "zt": [], "dt": [], "zb": [],
                "zt_count": 0, "dt_count": 0, "zb_count": 0}
    dt_data = _pool("DT", date_used, sort="lbt%3Aasc") or {}
    zb_data = _pool("ZB", date_used) or {}
    return {
        "date": f"{date_used[:4]}-{date_used[4:6]}-{date_used[6:]}",
        "zt": [_norm_pool_item(x) for x in (zt_data.get("pool") or [])],
        "dt": [_norm_pool_item(x) for x in (dt_data.get("pool") or [])],
        "zb": [_norm_pool_item(x) for x in (zb_data.get("pool") or [])],
        "zt_count": zt_data.get("tc") or 0,
        "dt_count": dt_data.get("tc") or 0,
        "zb_count": zb_data.get("tc") or 0,
    }


# ---------------------------------------------------------------- 两融

def fetch_margin(days: int = 70) -> list:
    """沪深北两融历史(T+1 披露),返回按日期升序的列表。"""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_RZRQ_LSHJ"
           "&columns=ALL&sortColumns=dim_date&sortTypes=-1&pageSize=" + str(days) +
           "&pageNumber=1&source=WEB&client=WEB")
    j = get_json(url)
    rows = ((j.get("result") or {}).get("data")) or []
    out = []
    for r in rows:
        out.append({
            "date": str(r.get("DIM_DATE"))[:10],
            "rzye": r.get("RZYE"),    # 融资余额(元)
            "rzmre": r.get("RZMRE"),  # 融资买入额(元)
            "rzjme": r.get("RZJME"),  # 融资净买入(元)
        })
    out.sort(key=lambda x: x["date"])
    return out
