# 📈 A股市场雷达 (A-Share Radar)

> 资金监控 × 市场情绪 × 每日复盘 —— 部署在 GitHub Pages 上的 A 股每日自动分析网站。
> 数据层基于高星开源库 [akshare](https://github.com/akfamily/akshare),图表基于 [Apache ECharts](https://github.com/apache/echarts)。
>
> **⚠️ 免责声明:本项目仅供学习交流,所有内容(包括仓位建议、板块提示)均由固定规则自动生成,不构成任何投资建议。数据来自公开接口,可能有延迟或错误。股市有风险,入市需谨慎。**

---

## 功能一览

| 标签页 | 内容 |
|---|---|
| **总览** | 四大指数卡片(含主力资金、涨跌家数)、市场情绪温度计(0-100 分 + 六维明细)、温度走势、上证日K(MA5/10/20/60 + 成交额)、涨停/跌停/炸板统计与连板梯队、今日要点 |
| **资金** | 行业主力资金净流入排行、全市场主力资金近 60 日走势、个股主力净流入 Top20、融资余额(两融)趋势 |
| **板块** | 行业/概念板块涨幅榜(含资金与领涨股) |
| **自选股** | 本地保存自选名单,交易时段每 30 秒实时刷新;点击展开日K + 技术信号(均线排列 / MACD 金叉死叉 / RSI 超买超卖) |
| **每日报告** | 收盘后自动生成的完整复盘:大盘速览 → 温度计 → 资金面 → 涨停梯队 → 技术面 → 热点主线 → 明日参考与操作建议 |

**市场温度计打分规则**(透明可复核,参数在 `scripts/analyze.py`):基础分 50 分,叠加
① 涨跌家数广度 ② 涨停/跌停结构 ③ 量能(相对前5日均量,量价配合) ④ 全市场主力净流入
⑤ 融资余额5日变化 ⑥ 炸板率,各维度封顶,映射到 0~100 分:≤20 冰点 / ≤40 降温 / ≤60 中性 / ≤80 回暖 / >80 过热。

## 工作原理

```
GitHub Actions(每交易日 15:35 北京时间)
    └─> scripts/run_pipeline.py
          ├─ fetch_data.py   采集:行情快照 / 指数K线 / 大盘资金 / 板块资金 / 个股资金
          │                  / 涨跌停池 / 两融   (akshare 优先,失败自动降级东财直连)
          ├─ indicators.py   纯 Python 指标:MA / MACD / RSI / 均线排列
          ├─ analyze.py      市场温度计 + 仓位建议
          └─ report.py       生成 data/report.json(9 节 HTML 复盘报告)
    └─> git commit data/*.json  →  GitHub Pages 自动重新部署

浏览器(静态站,无需任何后端)
    ├─ 加载 data/*.json 快照渲染全站
    ├─ 交易时段:JSONP 直连东财行情接口,每 30 秒刷新指数与自选股
    └─ 自选股 K 线与指标在浏览器本地计算(assets/js/indicators.js)
```

## 部署到你自己的 GitHub(约 3 分钟)

> 仓库任意名字均可,下面以 `a-share-radar` 为例;GitHub Pages 免费版要求仓库为 **Public**。

1. **在 GitHub 上新建空仓库**:`New repository` → 名字如 `a-share-radar` → 选 **Public** → **不要**勾选任何初始化选项。

2. **推送本目录**(在 `a-share-radar` 目录下执行):

   ```bash
   git init -b main
   git add .
   git commit -m "init: A股市场雷达"
   git remote add origin https://github.com/<你的用户名>/a-share-radar.git
   git push -u origin main
   ```

3. **开启 GitHub Pages**:仓库 `Settings` → `Pages` → `Build and deployment` →
   Source 选 **Deploy from a branch** → Branch 选 **`main`**、目录 **`/(root)`** → Save。

4. 等待 1~2 分钟,访问 `https://<你的用户名>.github.io/a-share-radar/` 即可。

5. **确认定时任务**:仓库 `Actions` 页应已自动启用 `daily-data-update` 工作流
   (首次推送默认启用)。可点进该工作流 → `Run workflow` 手动触发一次验证。
   之后每个交易日 15:35(北京时间)自动更新数据并重新部署。

## 本地运行

```bash
# 1) 更新数据(可选,仓库已带最近交易日数据;akshare 可选,没有也能跑)
pip install -r scripts/requirements.txt
python scripts/run_pipeline.py

# 2) 本地预览(必须走 http,file:// 下无法加载 json)
python -m http.server 8080
# 打开 http://127.0.0.1:8080
```

## 项目结构

```
a-share-radar/
├── index.html                  # 单页站点(五个标签页)
├── assets/
│   ├── css/style.css           # 深色主题(红涨绿跌)
│   ├── js/app.js               # 渲染 / ECharts 图表 / 实时刷新 / 自选股
│   └── js/indicators.js        # 浏览器端指标(与 Python 同口径)
├── scripts/
│   ├── fetch_data.py           # 数据采集层(纯标准库,akshare 可选增强)
│   ├── indicators.py           # 指标:MA/MACD/RSI/均线排列
│   ├── analyze.py              # 市场温度计 + 仓位建议(参数集中在 CFG)
│   ├── report.py               # 每日复盘报告生成
│   ├── run_pipeline.py         # 流水线入口
│   └── requirements.txt
├── data/                       # 每日生成、随仓库提交(站点数据源)
├── .github/workflows/daily.yml # 每交易日 15:35 定时任务
└── README.md
```

## 自定义

| 想改什么 | 改哪里 |
|---|---|
| 更新时间 | `.github/workflows/daily.yml` 里的 `cron`(注意是 UTC,北京 = UTC+8) |
| 温度计灵敏度/各项权重 | `scripts/analyze.py` 的 `CFG` |
| 仓位建议话术 | `scripts/analyze.py` 的 `position_advice` |
| 报告内容/措辞 | `scripts/report.py` |
| 默认自选股 | `assets/js/app.js` 的 `WL_DEFAULT` |
| 监控的指数 | `scripts/fetch_data.py` 的 `fetch_index_quotes` 与 `index.html` |

## 常见问题

- **为什么没有北向资金?**
  2024 年 8 月起,港交所停止了陆股通盘中实时成交与净买入数据的逐日实时披露,盘中"北向资金净流入"已无官方数据源。本项目改用**全市场主力资金(东财口径)+ 两融余额**作为资金面替代,并在报告中注明两融为 T+1 披露。

- **盘中打开网站,数据是实时的吗?**
  指数卡片、涨跌家数、自选股行情是实时的(JSONP 直连,可能有几秒延迟);温度计、资金排行、涨停池、报告等为每日收盘后快照。

- **数据接口会失效吗?**
  采集层全部带重试与降级:akshare 失败自动直连东财同源接口;某一项失败不影响其他项;核心数据缺失时 Actions 会退出报错并在上一次数据上保持运行。

- **周末/节假日打开会怎样?**
  涨跌停池等接口自动回溯到最近一个交易日;顶部显示"收盘快照 · 数据日期"。

## 致谢 · 站在巨人的肩膀上

结合/借鉴了以下 GitHub 高星开源项目:

- [akfamily/akshare](https://github.com/akfamily/akshare) — 财经数据接口库,数据层首选,失败自动降级直连
- [apache/echarts](https://github.com/apache/echarts) — 全站图表
- [myhhub/stock](https://github.com/myhhub/stock)(InStock) — 指标体系与每日复盘思路参考
- [microsoft/qlib](https://github.com/microsoft/qlib) — 量化研究框架(Roadmap:信号回测)
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — LLM 多智能体分析(Roadmap:接入 LLM 生成更智能的每日解读)
- [vnpy/vnpy](https://github.com/vnpy/vnpy)、[rainx/pytdx](https://github.com/rainx/pytdx) — 量化交易/通达信数据生态

## Roadmap

- [ ] 接入 LLM(如 TradingAgents 思路)对每日报告做更自然的解读
- [ ] 温度计历史信号胜率统计(回测打分规则)
- [ ] 板块轮动热力图
- [ ] Server酱/邮件推送每日报告
