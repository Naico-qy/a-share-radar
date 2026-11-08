/* 技术指标(与 scripts/indicators.py 同口径):MA / EMA / MACD / RSI / 均线排列。
 * 用于自选股在浏览器本地基于日K计算信号。 */
'use strict';
const IND = {
  smaSeries(vals, n) {
    const out = [];
    for (let i = 0; i < vals.length; i++) {
      if (i + 1 >= n) {
        let s = 0;
        for (let j = i - n + 1; j <= i; j++) s += vals[j];
        out.push(s / n);
      } else out.push(null);
    }
    return out;
  },
  emaSeries(vals, n) {
    const k = 2 / (n + 1);
    const out = []; let e = null;
    for (const v of vals) { e = (e === null) ? v : (v - e) * k + e; out.push(e); }
    return out;
  },
  macd(closes, fast = 12, slow = 26, sig = 9) {
    if (closes.length < slow + sig) return null;
    const ef = this.emaSeries(closes, fast), es = this.emaSeries(closes, slow);
    const dif = closes.map((_, i) => ef[i] - es[i]);
    const dea = this.emaSeries(dif, sig);
    const hist = dif.map((d, i) => (d - dea[i]) * 2);
    const n = closes.length;
    let state;
    if (dif[n - 2] <= dea[n - 2] && dif[n - 1] > dea[n - 1]) state = '金叉';
    else if (dif[n - 2] >= dea[n - 2] && dif[n - 1] < dea[n - 1]) state = '死叉';
    else state = dif[n - 1] > dea[n - 1] ? '多头运行' : '空头运行';
    const momentum = Math.abs(hist[n - 1]) > Math.abs(hist[n - 2]) ? '增强' : '衰减';
    return { dif: dif[n - 1], dea: dea[n - 1], hist: hist[n - 1], state, momentum, histSeries: hist };
  },
  rsi(closes, n = 14) {
    if (closes.length < n + 1) return null;
    const gains = [], losses = [];
    for (let i = 1; i < closes.length; i++) {
      const d = closes[i] - closes[i - 1];
      gains.push(Math.max(d, 0)); losses.push(Math.max(-d, 0));
    }
    let ag = gains.slice(0, n).reduce((a, b) => a + b, 0) / n;
    let al = losses.slice(0, n).reduce((a, b) => a + b, 0) / n;
    for (let i = n; i < gains.length; i++) {
      ag = (ag * (n - 1) + gains[i]) / n;
      al = (al * (n - 1) + losses[i]) / n;
    }
    if (al === 0) return 100;
    return 100 - 100 / (1 + ag / al);
  },
  technicalView(klines) {
    const closes = klines.map(k => k.close);
    if (!closes.length) return null;
    const ma = {};
    [5, 10, 20, 60].forEach(n => {
      const s = this.smaSeries(closes, n);
      ma['ma' + n] = s[s.length - 1];
    });
    let align = 'mixed';
    if (ma.ma5 && ma.ma10 && ma.ma20) {
      if (ma.ma5 > ma.ma10 && ma.ma10 > ma.ma20) align = 'bullish';
      else if (ma.ma5 < ma.ma10 && ma.ma10 < ma.ma20) align = 'bearish';
    }
    const last = closes[closes.length - 1];
    const chg20 = closes.length >= 21 ? (last / closes[closes.length - 21] - 1) * 100 : null;
    const chg5 = closes.length >= 6 ? (last / closes[closes.length - 6] - 1) * 100 : null;
    const pos20 = ma.ma20 ? (last / ma.ma20 - 1) * 100 : null;
    return { last, ma, align, macd: this.macd(closes), rsi14: this.rsi(closes), chg5, chg20, pos20, closes };
  },
  signals(v) {
    if (!v) return [];
    const out = [];
    if (v.align === 'bullish') out.push({ t: '均线多头排列', c: 'pos' });
    else if (v.align === 'bearish') out.push({ t: '均线空头排列', c: 'neg' });
    else out.push({ t: '均线纠缠', c: '' });
    if (v.macd) out.push({ t: 'MACD ' + v.macd.state + '(' + v.macd.momentum + ')', c: v.macd.state === '金叉' ? 'pos' : (v.macd.state === '死叉' ? 'neg' : (v.macd.state === '多头运行' ? 'pos' : 'neg')) });
    if (v.rsi14 != null) {
      if (v.rsi14 > 70) out.push({ t: 'RSI ' + v.rsi14.toFixed(0) + ' 超买', c: 'neg' });
      else if (v.rsi14 < 30) out.push({ t: 'RSI ' + v.rsi14.toFixed(0) + ' 超卖', c: 'pos' });
      else out.push({ t: 'RSI ' + v.rsi14.toFixed(0), c: '' });
    }
    if (v.chg20 != null) out.push({ t: '近20日 ' + (v.chg20 > 0 ? '+' : '') + v.chg20.toFixed(1) + '%', c: v.chg20 >= 0 ? 'pos' : 'neg' });
    if (v.pos20 != null) out.push({ t: (v.pos20 >= 0 ? '站上' : '跌破') + 'MA20 ' + (v.pos20 > 0 ? '+' : '') + v.pos20.toFixed(1) + '%', c: v.pos20 >= 0 ? 'pos' : 'neg' });
    return out;
  }
};
window.IND = IND;
