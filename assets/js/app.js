/* A股市场雷达 前端逻辑
 * - 静态快照:加载 data/*.json(由 GitHub Actions 每交易日生成)
 * - 实时增强:交易时段通过东财 JSONP 接口每 30 秒刷新指数与自选股行情
 * - 自选股:localStorage 本地保存,K线与指标在浏览器本地计算
 */
'use strict';

/* ---------------- 工具 ---------------- */
const $ = s => document.querySelector(s);
const cls = v => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const sign = v => (v > 0 ? '+' : '');
const fmt = {
  pct(v) { return (v == null || v === '-') ? '--' : sign(+v) + (+v).toFixed(2) + '%'; },
  num(v, d = 2) { return (v == null || v === '-') ? '--' : (+v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d }); },
  yi(v, d = 0) { return (v == null || v === '-') ? '--' : (v / 1e8).toLocaleString('zh-CN', { maximumFractionDigits: d }); },
  yiSign(v, d = 1) { return (v == null) ? '--' : sign(v) + (v / 1e8).toLocaleString('zh-CN', { maximumFractionDigits: d }) + ' 亿'; },
};
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
function tableHTML(head, rows) {
  return '<table><thead><tr>' + head.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>' +
    rows.map(r => '<tr>' + r.map(c => `<td>${c}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
}
function jsonp(url, timeout = 8000) {
  return new Promise((resolve, reject) => {
    const cb = 'asrCb_' + Math.random().toString(36).slice(2);
    const s = document.createElement('script');
    const timer = setTimeout(() => { cleanup(); reject(new Error('jsonp timeout')); }, timeout);
    function cleanup() { clearTimeout(timer); try { delete window[cb]; } catch (e) { window[cb] = undefined; } s.remove(); }
    window[cb] = d => { cleanup(); resolve(d); };
    s.onerror = () => { cleanup(); reject(new Error('jsonp error')); };
    s.src = url + (url.includes('?') ? '&' : '?') + 'cb=' + cb;
    document.head.appendChild(s);
  });
}
function beijingNow() {
  return new Date(Date.now() + (480 + new Date().getTimezoneOffset()) * 60000);
}
function isTradingTime() {
  const d = beijingNow();
  const wd = d.getDay();
  if (wd === 0 || wd === 6) return false;
  const hm = d.getHours() * 100 + d.getMinutes();
  return (hm >= 925 && hm <= 1135) || (hm >= 1255 && hm <= 1505);
}

/* ---------------- 数据加载 ---------------- */
const FILES = ['meta', 'snapshot', 'kline_sh', 'kline_cyb', 'main_flow',
  'sectors', 'stocks_flow', 'zt', 'margin', 'history', 'report'];
const DATA = {};

async function loadAll() {
  const results = await Promise.all(FILES.map(f =>
    fetch('data/' + f + '.json').then(r => r.ok ? r.json() : null).catch(() => null)));
  FILES.forEach((f, i) => DATA[f] = results[i]);
}

/* ---------------- ECharts 基础 ---------------- */
const charts = {};
function chart(id, option) {
  if (typeof echarts === 'undefined') return null;
  const el = document.getElementById(id);
  if (!el) return null;
  if (!charts[id]) charts[id] = echarts.init(el);
  charts[id].setOption(option, true);
  return charts[id];
}
window.addEventListener('resize', () => Object.values(charts).forEach(c => c.resize()));

const AXIS = {
  axisLine: { lineStyle: { color: '#24304a' } },
  axisLabel: { color: '#8b98ac', fontSize: 11 },
  splitLine: { lineStyle: { color: 'rgba(36,48,74,.5)' } },
  axisTick: { show: false },
};
function tooltipFixed(extra) {
  return Object.assign({ trigger: 'axis', backgroundColor: '#1a2436', borderColor: '#24304a', textStyle: { color: '#e6edf3', fontSize: 12 } }, extra || {});
}

/* ---------------- 顶部与徽标 ---------------- */
function renderMeta() {
  const m = DATA.meta;
  if (!m) return;
  $('#update-time').textContent = `数据日期 ${m.date} · 生成于 ${m.generated_at}`;
}

function setBadge(mode, text) {
  const el = $('#live-badge');
  el.className = 'badge' + (mode === 'live' ? ' live' : mode === 'err' ? ' err' : '');
  el.textContent = text;
}

/* ---------------- 指数卡片 ---------------- */
function renderIndexCards() {
  const idx = (DATA.snapshot && DATA.snapshot.indexes) || [];
  const el = $('#index-cards');
  el.innerHTML = idx.map(q => {
    const L = liveQuoteMap[q.secid] || {};   // 交易时段会被实时数据覆盖
    const price = L.price != null ? L.price : q.price;
    const pct = L.pct != null ? L.pct : q.pct;
    const amount = L.amount != null ? L.amount : q.amount;
    const main = L.main_net != null ? L.main_net : q.main_net;
    const c = cls(+pct || 0);
    const extra = (q.code === '000001' || q.code === '399001')
      ? `<div class="row"><span>上涨 ${q.up}</span><span>下跌 ${q.down}</span><span>平 ${q.flat}</span></div>` : '';
    return `<div class="card">
      <div class="name">${esc(q.name)}</div>
      <div class="price ${c}">${fmt.num(price)}</div>
      <div class="main-net ${cls(+pct || 0)}">${sign(+pct || 0)}${fmt.num(+pct || 0)}%</div>
      <div class="row"><span>成交 ${fmt.yi(amount)} 亿</span><span>主力 ${fmt.yiSign(main)}</span></div>
      ${extra}
    </div>`;
  }).join('');
}

/* ---------------- 温度计 ---------------- */
function renderGauge() {
  const rep = DATA.report;
  if (!rep) return;
  const t = rep.temperature;
  $('#temp-label').textContent = `${rep.date}`;
  chart('gauge', {
    series: [{
      type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100,
      radius: '105%', center: ['50%', '60%'],
      axisLine: { lineStyle: { width: 14, color: [[0.2, '#3d7eff'], [0.4, '#2ec27e'], [0.6, '#e6a23c'], [1, '#f04a5a']] } },
      pointer: { length: '60%', width: 5, itemStyle: { color: '#e6edf3' } },
      axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: '#8b98ac', distance: 20, fontSize: 10 },
      detail: {
        formatter: v => v + '\n' + t.label, color: '#e6edf3', fontSize: 22, offsetCenter: [0, '35%'],
        lineHeight: 28, fontWeight: 700,
      },
      data: [{ value: t.score }],
      title: { show: false },
    }],
  });
}

function renderTempComponents() {
  const rep = DATA.report;
  if (!rep) return;
  const sec = rep.sections.find(s => s.id === 'temp');
  if (!sec) return;
  const box = document.createElement('div');
  box.innerHTML = sec.html;
  const chips = box.querySelector('.chips');
  if (chips) $('#temp-components').innerHTML = chips.innerHTML;
}

function renderHistory() {
  const h = DATA.history || [];
  const dates = h.map(x => x.date.slice(5));
  const vals = h.map(x => x.temp);
  chart('temp-history', {
    grid: { left: 34, right: 14, top: 16, bottom: 24 },
    xAxis: Object.assign({ type: 'category', data: dates }, AXIS, { boundaryGap: false }),
    yAxis: Object.assign({ type: 'value', min: 0, max: 100 }, AXIS),
    series: [{
      type: 'line', data: vals, smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#5b8cff', width: 2 },
      areaStyle: { color: 'rgba(91,140,255,.15)' },
      markLine: { silent: true, symbol: 'none', label: { color: '#6b7891', fontSize: 10 },
        lineStyle: { color: 'rgba(107,120,145,.5)', type: 'dashed' },
        data: [{ yAxis: 50, label: { formatter: '中性 50' } }] },
      tooltip: { valueFormatter: v => v + ' 分' },
    }],
    tooltip: tooltipFixed(),
  });
  if (h.length < 5) $('#history-note').textContent = `当前仅 ${h.length} 个交易日数据,部署后每个交易日自动累积。`;
}

/* ---------------- K线 ---------------- */
function renderKline() {
  const k = (DATA.kline_sh || []).slice(-120);
  if (!k.length) return;
  const dates = k.map(x => x.date);
  const closes = k.map(x => x.close);
  const maOpt = [[5, '#e6a23c'], [10, '#5b8cff'], [20, '#c678dd'], [60, '#56b6c2']];
  const candle = k.map(x => [x.open, x.close, x.low, x.high]);
  const amt = k.map((x, i) => ({ value: +(x.amt / 1e8).toFixed(0),
    itemStyle: { color: x.close >= x.open ? 'rgba(240,74,90,.7)' : 'rgba(46,194,126,.7)' } }));
  chart('kline-sh', {
    animation: false,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: tooltipFixed({
      axisPointer: { type: 'cross', label: { backgroundColor: '#1a2436', borderColor: '#24304a', color: '#e6edf3' } },
    }),
    grid: [{ left: 56, right: 16, top: 12, height: '58%' }, { left: 56, right: 16, top: '76%', height: '16%' }],
    xAxis: [
      Object.assign({ type: 'category', data: dates, boundaryGap: true }, AXIS, { axisLabel: { show: false } }),
      Object.assign({ type: 'category', data: dates, gridIndex: 1 }, AXIS),
    ],
    yAxis: [
      Object.assign({ type: 'value', scale: true }, AXIS, { splitLine: { show: true, lineStyle: { color: 'rgba(36,48,74,.5)' } } }),
      Object.assign({ type: 'value', gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } }),
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 55, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 2, height: 16, borderColor: '#24304a', textStyle: { color: '#8b98ac' } },
    ],
    series: [
      { name: '日K', type: 'candlestick', data: candle, itemStyle: { color: '#f04a5a', color0: '#2ec27e', borderColor: '#f04a5a', borderColor0: '#2ec27e' } },
      ...maOpt.map(([n, color]) => ({
        name: 'MA' + n, type: 'line', data: IND.smaSeries(closes, n), symbol: 'none',
        lineStyle: { width: 1, color }, emphasis: { disabled: true },
      })),
      { name: '成交额', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: amt, tooltip: { valueFormatter: v => v + ' 亿' } },
    ],
    legend: { show: true, data: ['MA5', 'MA10', 'MA20', 'MA60'], textStyle: { color: '#8b98ac', fontSize: 11 }, top: 0, icon: 'rect', itemWidth: 12, itemHeight: 3 },
  });
}

/* ---------------- 涨跌停 ---------------- */
function renderPools() {
  const zt = DATA.zt;
  if (!zt || !zt.date) { $('#pool-stats').innerHTML = '<span class="muted small">数据暂缺</span>'; return; }
  $('#pool-date').textContent = zt.date;
  const rate = zt.zt_count + zt.zb_count > 0 ? (zt.zb_count / (zt.zt_count + zt.zb_count) * 100).toFixed(0) : '--';
  const maxLbc = Math.max(0, ...(zt.zt || []).map(x => x.lbc || 0));
  $('#pool-stats').innerHTML = `
    <span class="chip big pos"><b>${zt.zt_count}</b><i>涨停</i></span>
    <span class="chip big neg"><b>${zt.dt_count}</b><i>跌停</i></span>
    <span class="chip"><b>${zt.zb_count}(${rate}%)</b><i>炸板(率)</i></span>
    <span class="chip"><b>${maxLbc} 板</b><i>最高连板</i></span>`;
  const lian = (zt.zt || []).filter(x => (x.lbc || 0) >= 2).sort((a, b) => (b.lbc || 0) - (a.lbc || 0)).slice(0, 12);
  $('#lianban-list').innerHTML = lian.length
    ? tableHTML(['股票', '连板', '行业', '封单', '首次封板'],
      lian.map(x => [esc(x.name), `<span class="up">${x.lbc} 板</span>`, esc(x.hybk || '--'),
        fmt.yiSign(x.fund), esc(x.fbt || '--')]))
    : '<span class="muted small">无 2 连板以上个股</span>';
}

/* ---------------- 报告摘要(总览) ---------------- */
function renderBrief() {
  const rep = DATA.report;
  const el = $('#report-brief');
  if (!rep) { el.innerHTML = '<span class="muted small">报告暂缺</span>'; return; }
  const pos = rep.position || {};
  el.innerHTML = `
    <p style="margin-bottom:10px">${esc(rep.headline)}</p>
    <div class="chips">${(rep.suggestions || []).map(s =>
      `<span class="chip"><b>${s.icon} ${esc(s.text)}</b></span>`).join('')}</div>
    <div class="advice-box" style="margin-top:12px"><b>仓位参考:${pos.pct} 成</b><br>${esc(pos.text || '')}</div>
    <button id="go-report" style="margin-top:6px" class="link-btn">查看完整每日报告 →</button>`;
  $('#go-report').onclick = () => switchTab('report');
}

/* ---------------- 资金页 ---------------- */
function renderSectorFlow() {
  const ind = (DATA.sectors && DATA.sectors.industry) || [];
  if (!ind.length) return;
  const inflow = ind.slice().sort((a, b) => (b.main || 0) - (a.main || 0)).slice(0, 12);
  const outflow = ind.slice().sort((a, b) => (a.main || 0) - (b.main || 0)).slice(0, 8);
  const rows = inflow.concat(outflow).sort((a, b) => (b.main || 0) - (a.main || 0));
  chart('sector-flow-chart', {
    grid: { left: 90, right: 60, top: 10, bottom: 24 },
    xAxis: Object.assign({}, AXIS, { type: 'value', axisLabel: { formatter: v => (v / 1e8).toFixed(0) + '亿', color: '#8b98ac' } }),
    yAxis: Object.assign({}, AXIS, { type: 'category', data: rows.map(r => r.name), inverse: false, axisLabel: { color: '#c9d4e5', fontSize: 11 } }),
    series: [{
      type: 'bar', data: rows.map(r => ({ value: r.main,
        itemStyle: { color: (r.main || 0) >= 0 ? '#f04a5a' : '#2ec27e', borderRadius: 3 } })),
      label: { show: true, position: 'right', color: '#8b98ac', fontSize: 10, formatter: p => (p.value / 1e8).toFixed(1) + '亿' },
      tooltip: { valueFormatter: v => fmt.yiSign(v) },
    }],
    tooltip: tooltipFixed(),
  });
}

function renderMainFlow() {
  const s = (DATA.main_flow || []).slice(-60);
  if (!s.length) return;
  chart('main-flow-chart', {
    grid: { left: 70, right: 16, top: 14, bottom: 26 },
    xAxis: Object.assign({}, AXIS, { type: 'category', data: s.map(x => x.date.slice(5)) }),
    yAxis: Object.assign({}, AXIS, { type: 'value', axisLabel: { formatter: v => (v / 1e8).toFixed(0) + '亿', color: '#8b98ac' } }),
    series: [{
      type: 'bar', data: s.map(x => ({ value: x.main,
        itemStyle: { color: x.main >= 0 ? '#f04a5a' : '#2ec27e' } })),
      tooltip: { valueFormatter: v => fmt.yiSign(v) },
    }],
    tooltip: tooltipFixed(),
  });
}

function renderStockFlow() {
  const list = (DATA.stocks_flow && DATA.stocks_flow.list) || [];
  $('#stock-flow-table').innerHTML = list.length ? tableHTML(
    ['股票', '现价', '涨跌幅', '主力净流入', '净占比', '行业'],
    list.map(r => [`${esc(r.name)}<br><span class="muted small">${esc(r.code)}</span>`,
      fmt.num(r.price), `<span class="${cls(r.pct)}">${fmt.pct(r.pct)}</span>`,
      `<span class="${cls(r.main)}">${fmt.yiSign(r.main)}</span>`,
      fmt.pct(r.main_pct), esc(r.industry || '--')])) : '<span class="muted small">数据暂缺</span>';
}

function renderMargin() {
  const m = DATA.margin || [];
  if (!m.length) return;
  const last = m[m.length - 1];
  const chg5 = m.length >= 6 ? (last.rzye / m[m.length - 6].rzye - 1) * 100 : null;
  $('#margin-latest').innerHTML = `
    <span class="chip"><b>${(last.rzye / 1e12).toFixed(2)} 万亿</b><i>融资余额(${last.date})</i></span>
    <span class="chip ${cls(last.rzjme) || ''}"><b>${fmt.yiSign(last.rzjme)}</b><i>单日融资净买入</i></span>
    ${chg5 != null ? `<span class="chip ${cls(chg5) || ''}"><b>${sign(chg5)}${chg5.toFixed(2)}%</b><i>5日变化</i></span>` : ''}`;
  chart('margin-chart', {
    grid: { left: 56, right: 14, top: 14, bottom: 24 },
    xAxis: Object.assign({}, AXIS, { type: 'category', data: m.slice(-60).map(x => x.date.slice(5)), boundaryGap: false }),
    yAxis: Object.assign({}, AXIS, { type: 'value', scale: true, axisLabel: { formatter: v => v.toFixed(1) + '万亿', color: '#8b98ac' } }),
    series: [{ type: 'line', data: m.slice(-60).map(x => +(x.rzye / 1e12).toFixed(3)), symbol: 'none',
      lineStyle: { color: '#5b8cff', width: 2 }, areaStyle: { color: 'rgba(91,140,255,.12)' } }],
    tooltip: tooltipFixed({ valueFormatter: v => v + ' 万亿' }),
  });
}

/* ---------------- 板块页 ---------------- */
function sectorRows(list) {
  return list.map(r => [esc(r.name),
    `<span class="${cls(r.pct)}">${fmt.pct(r.pct)}</span>`,
    `<span class="${cls(r.main)}">${fmt.yiSign(r.main)}</span>`,
    `${esc(r.leader || '--')}<br><span class="muted small">${esc(r.leader_code || '')}</span>`]);
}
function renderSectors() {
  const s = DATA.sectors || {};
  $('#industry-table').innerHTML = s.industry_gainers && s.industry_gainers.length
    ? tableHTML(['行业', '涨跌幅', '主力净流入', '领涨股'], sectorRows(s.industry_gainers))
    : '<span class="muted small">数据暂缺</span>';
  $('#concept-table').innerHTML = s.concept_gainers && s.concept_gainers.length
    ? tableHTML(['概念', '涨跌幅', '主力净流入', '领涨股'], sectorRows(s.concept_gainers))
    : '<span class="muted small">数据暂缺</span>';
}

/* ---------------- 报告页 ---------------- */
function renderReport() {
  const rep = DATA.report;
  if (!rep) { $('#report-body').innerHTML = '<span class="muted small">报告暂缺</span>'; return; }
  $('#report-title').textContent = '每日报告 · ' + rep.headline;
  $('#report-body').innerHTML = rep.sections.map(s =>
    `<h4 style="font-size:15px;color:#e6edf3;margin-top:20px">${esc(s.title)}</h4><div>${s.html}</div>`).join('');
}

/* ---------------- 自选股 ---------------- */
const WL_KEY = 'asr_watchlist_v1';
const WL_DEFAULT = ['600519', '300750', '601318', '000001'];
let watchCodes = loadWatch();
const liveQuoteMap = {};   // secid -> live fields
let expandedCode = null;

function loadWatch() {
  try {
    const v = JSON.parse(localStorage.getItem(WL_KEY));
    if (Array.isArray(v) && v.every(x => /^\d{6}$/.test(x))) return v;
  } catch (e) { /* ignore */ }
  return WL_DEFAULT.slice();
}
function saveWatch() { localStorage.setItem(WL_KEY, JSON.stringify(watchCodes)); }
function secidOf(code) {
  if (/^(6|900)/.test(code)) return '1.' + code;
  return '0.' + code;   // 0/3 开头深市,4/8/920 开头北交所
}
function watchSecids() {
  return ['1.000001', '0.399001', '0.399006', '1.000688'].concat(watchCodes.map(secidOf));
}

function renderWatch() {
  const codes = watchCodes;
  const idx = (DATA.snapshot && DATA.snapshot.indexes) || [];
  const rows = codes.map(code => {
    const secid = secidOf(code);
    const L = liveQuoteMap[secid] || {};
    const price = L.price, pct = L.pct;
    const main = L.main_net;
    const name = L.name || code;
    return [`${esc(name)}<br><span class="muted small">${esc(code)}</span>`,
      price != null ? fmt.num(price) : '<span class="muted">待刷新</span>',
      pct != null ? `<span class="${cls(pct)}">${fmt.pct(pct)}</span>` : '--',
      main != null ? `<span class="${cls(main)}">${fmt.yiSign(main)}</span>` : '--',
      L.turnover != null ? fmt.num(L.turnover) + '%' : '--',
      L.vol_ratio != null ? fmt.num(L.vol_ratio) : '--',
      `<button class="del-btn" data-code="${code}">删除</button>`];
  });
  $('#watch-table').innerHTML = codes.length
    ? tableHTML(['名称', '现价', '涨跌幅', '主力净流入', '换手', '量比', ''], rows)
    : '<span class="muted small">自选股为空,输入代码添加</span>';
  document.querySelectorAll('#watch-table .del-btn').forEach(btn => {
    btn.onclick = e => {
      e.stopPropagation();
      watchCodes = watchCodes.filter(c => c !== btn.dataset.code);
      saveWatch(); renderWatch(); liveRefresh(true);
    };
  });
  document.querySelectorAll('#watch-table tbody tr').forEach((tr, i) => {
    if (!codes.length) return;
    tr.onclick = () => expandWatch(codes[i]);
  });
}

function addWatch() {
  const input = $('#watch-input');
  const code = (input.value || '').trim();
  if (!/^\d{6}$/.test(code)) { input.focus(); input.placeholder = '请输入 6 位数字代码'; return; }
  if (!watchCodes.includes(code)) { watchCodes.push(code); saveWatch(); }
  input.value = '';
  renderWatch();
  liveRefresh(true);
  expandWatch(code);
}

/* 展开自选股 K 线 + 信号 */
const klineCache = {};
async function expandWatch(code) {
  expandedCode = code;
  const secid = secidOf(code);
  const name = (liveQuoteMap[secid] && liveQuoteMap[secid].name) || code;
  $('#watch-detail').style.display = 'block';
  $('#watch-detail-name').textContent = `${name} (${code}) 日K与信号`;
  $('#watch-detail-signals').innerHTML = '<span class="chip">加载中…</span>';
  try {
    let klines = klineCache[secid];
    if (!klines) {
      const url = `https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=${secid}` +
        '&klt=101&fqt=1&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&end=20500101&lmt=140';
      const j = await jsonp(url);
      klines = ((j.data || {}).klines || []).map(line => {
        const p = line.split(',');
        return { date: p[0], open: +p[1], close: +p[2], high: +p[3], low: +p[4], vol: +p[5], amt: +p[6] };
      });
      klineCache[secid] = klines;
    }
    if (!klines.length) throw new Error('no kline');
    const v = IND.technicalView(klines);
    const sigs = IND.signals(v);
    $('#watch-detail-signals').innerHTML = sigs.map(s =>
      `<span class="chip ${s.c}"><b>${esc(s.t)}</b></span>`).join('');
    const dates = klines.map(k => k.date);
    const closes = v.closes;
    chart('watch-detail-chart', {
      animation: false,
      tooltip: tooltipFixed({ axisPointer: { type: 'cross' } }),
      grid: [{ left: 56, right: 14, top: 14, height: '62%' }, { left: 56, right: 14, top: '80%', height: '14%' }],
      xAxis: [
        Object.assign({ type: 'category', data: dates }, AXIS, { axisLabel: { show: false } }),
        Object.assign({ type: 'category', data: dates, gridIndex: 1 }, AXIS),
      ],
      yAxis: [
        Object.assign({ type: 'value', scale: true }, AXIS),
        Object.assign({ type: 'value', gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } }, AXIS),
      ],
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 60, end: 100 }],
      series: [
        { type: 'candlestick', data: klines.map(k => [k.open, k.close, k.low, k.high]),
          itemStyle: { color: '#f04a5a', color0: '#2ec27e', borderColor: '#f04a5a', borderColor0: '#2ec27e' } },
        { name: 'MA5', type: 'line', symbol: 'none', data: IND.smaSeries(closes, 5), lineStyle: { width: 1, color: '#e6a23c' } },
        { name: 'MA10', type: 'line', symbol: 'none', data: IND.smaSeries(closes, 10), lineStyle: { width: 1, color: '#5b8cff' } },
        { name: 'MA20', type: 'line', symbol: 'none', data: IND.smaSeries(closes, 20), lineStyle: { width: 1, color: '#c678dd' } },
        { type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: klines.map(k => ({ value: +(k.amt / 1e8).toFixed(1),
          itemStyle: { color: k.close >= k.open ? 'rgba(240,74,90,.7)' : 'rgba(46,194,126,.7)' } })) },
      ],
    });
  } catch (e) {
    $('#watch-detail-signals').innerHTML = '<span class="chip neg"><b>K线加载失败(实时接口不可用)</b></span>';
  }
}
$('#watch-detail-close').onclick = () => {
  $('#watch-detail').style.display = 'none';
  expandedCode = null;
};

/* ---------------- 实时刷新 ---------------- */
let liveLoaded = false;
async function liveRefresh(manual) {
  const trading = isTradingTime();
  if (liveLoaded && !trading && !manual) return;   // 非交易时段核对一次收盘数据即可
  try {
    const url = 'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=' + watchSecids().join(',') +
      '&fields=f2,f3,f4,f5,f6,f8,f10,f12,f13,f14,f18,f62,f104,f105,f106';
    const j = await jsonp(url);
    const diff = (j.data && j.data.diff) || [];
    for (const d of diff) {
      const secid = d.f13 + '.' + d.f12;
      liveQuoteMap[secid] = {
        name: d.f14, price: d.f2, pct: d.f3, chg: d.f4,
        amount: d.f6, main_net: d.f62,
        turnover: d.f8, vol_ratio: d.f10,
        up: d.f104, down: d.f105, flat: d.f106,
      };
    }
    liveLoaded = true;
    const bj = beijingNow();
    const hhmm = String(bj.getHours()).padStart(2, '0') + ':' + String(bj.getMinutes()).padStart(2, '0');
    if (trading) setBadge('live', `实时刷新 ${hhmm}`);
    else setBadge('', `收盘快照(已核对) · ${(DATA.meta && DATA.meta.date) || ''}`);
    renderIndexCards();
    renderWatch();
    if (expandedCode) refreshExpandedName(expandedCode);
  } catch (e) {
    setBadge('err', '实时不可用 · 显示快照');
    if (manual) console.warn('live refresh failed', e);
  }
}
function refreshExpandedName(code) {
  const name = (liveQuoteMap[secidOf(code)] && liveQuoteMap[secidOf(code)].name);
  if (name) $('#watch-detail-name').textContent = `${name} (${code}) 日K与信号`;
}

/* ---------------- 标签页 ---------------- */
function switchTab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + name));
  setTimeout(() => Object.values(charts).forEach(c => c.resize()), 50);
}

/* ---------------- 启动 ---------------- */
async function main() {
  await loadAll();
  renderMeta();
  renderIndexCards();
  renderGauge();
  renderTempComponents();
  renderHistory();
  renderKline();
  renderPools();
  renderBrief();
  renderSectorFlow();
  renderMainFlow();
  renderStockFlow();
  renderMargin();
  renderSectors();
  renderReport();
  renderWatch();
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => switchTab(b.dataset.tab));
  $('#watch-add-btn').onclick = addWatch;
  $('#watch-input').addEventListener('keydown', e => { if (e.key === 'Enter') addWatch(); });

  await liveRefresh(false);
  liveTimer = setInterval(() => liveRefresh(false), 30000);
}
main();
