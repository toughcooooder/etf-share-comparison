# ETF 基金份额变化汇总 · 微信小程序

把本地每日定时任务（`build_etf_share_comparison.py` 抓取沪深两市 ETF 基金份额）搬到微信里随时看。
基于**微信云开发**，无需自建服务器。

## 工程结构

```
etf_share_miniprogram/
├── app.js / app.json / app.wxss      # 小程序入口与全局配置
├── project.config.json               # 开发者工具工程配置
├── pages/
│   ├── index/                        # 汇总仪表盘（KPI / 对比图 / 同指数汇总 / 卡片 / 汇总表）
│   ├── detail/                       # 单只 ETF 明细
│   └── about/                        # 数据来源与接入说明
├── components/
│   ├── line-chart/                   # 多序列折线图（Canvas 2D，零依赖，支持触摸提示）
│   └── sparkline/                    # 卡片迷你走势图
├── utils/
│   ├── config.js                     # 云环境配置（填 CLOUD_ENV 即接入云端）
│   ├── cloud.js                      # 数据获取（云函数优先，失败回退内置示例）
│   ├── format.js / metrics.js        # 格式化与指标计算
│   └── sampleData.js                 # 引用内置示例
├── assets/summary_sample.json        # 内置示例数据（由最新报告导出，开发者工具直接预览）
├── cloudfunctions/getSummary/        # 云函数：读取云存储中的 summary.json
└── scripts/
    ├── export_summary_json.py        # 从 HTML 报告提取结构化 JSON
    └── deploy_to_cloud.js           # 把 JSON 上传到云存储
```

## 数据链路

```
本地定时任务(每日23:40,仅交易日)
  └─ build_etf_share_comparison.py → 16只ETF基金份额变化汇总.html
       └─ export_summary_json.py   → etf_share_summary.json
            └─ deploy_to_cloud.js  → 云存储 etf_share/summary.json
                 └─ 云函数 getSummary ← 小程序读取
```

## 快速开始（仅预览界面）

1. 微信开发者工具 → 导入项目 → 选择本目录（`etf_share_miniprogram`）。
2. AppID 选择「测试号」或你自己的 AppID。
3. 直接编译运行：未配置云环境时，自动使用 `assets/summary_sample.json` 内置示例，
   所有页面、图表、表格均可正常预览。

## 接入云端实时数据（6 步）

1. 微信公众平台拿到小程序 AppID（个人/企业均可）。
2. 开发者工具顶部「云开发」→ 开通环境，记录**环境 ID**。
3. 打开 `utils/config.js`，把环境 ID 填入 `CLOUD_ENV`，`USE_CLOUD` 保持 `true`。
4. 右键 `cloudfunctions/getSummary` → **上传并部署：云端安装依赖**。
5. 生成数据并上传：
   - 在 `etf_share_comparison_16` 目录执行 `py export_summary_json.py`（产出 `etf_share_summary.json`）；
   - 安装 CLI：`npm i -g @cloudbase/cli`，`tcb login`；
   - `set CLOUD_ENV=你的环境ID && node scripts/deploy_to_cloud.js`。
   - 也可在开发者工具「云开发 → 存储」手动上传该 JSON 到 `etf_share/` 目录。
6. 重新编译小程序，顶部状态应从「内置示例数据」变为「云端实时数据」。

## 让定时任务自动推送（可选）

原定时任务已新增一步：主脚本成功后执行 `export_summary_json.py` 产出 `etf_share_summary.json`。
再在定时任务末尾加一行调用 `deploy_to_cloud.js`（需环境已 `tcb login`）即可每日自动更新云端数据。

## 说明

- 份额单位统一为**亿份**；沪市原始 TOT_VOL 为万份（÷10000），深市原始为份（÷1亿）。
- 数据为交易日清算后基金份额，不等同于基金净值或规模金额，不构成投资建议。
- 图表用原生 Canvas 2D 绘制，无任何第三方图表库依赖。
