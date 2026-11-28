# ETF 基金份额变化汇总

抓取上交所（SSE）与深交所（SZSE）16 只主流 ETF 的**基金份额**历史数据，计算每日份额增减，生成一份可交互的单文件 HTML 报告，并导出微信小程序可直接读取的结构化 JSON。

份额变化是观察资金申赎动向的高频指标：份额增加代表净申购（资金流入），份额减少代表净赎回（资金流出）。相比净值，份额不受价格波动干扰，更能反映真实资金行为。

## 目录

- [环境准备](#环境准备)
- [三步跑起来](#三步跑起来)
- [命令详解](#命令详解)
- [输出文件](#输出文件)
- [目录结构](#目录结构)
- [报告怎么看](#报告怎么看)
- [数据口径](#数据口径)
- [小程序端](#小程序端)
- [定时任务](#定时任务)
- [常见问题](#常见问题)

## 环境准备

需要 Python 3.9 及以上。Windows 上 `py` 命令由 Python 安装包自带；macOS / Linux 换成 `python3`。

```bash
pip install -r requirements.txt
```

核心依赖只有两个：`pandas`、`requests`。`is_trading_day.py` 可选依赖 `akshare` 或 `exchange_calendars`，没装也能跑——仓库已经带了 `trade_calendar_cache.json`，命中缓存时不联网。

> 网络要求：需要能访问 `sse.com.cn` 与 `szse.cn` 的公开数据接口。代理环境可能拦截，表现为长时间无输出或大量 retry 日志。

## 三步跑起来

```bash
# 1) 判断今天是不是 A 股交易日（0=交易，1=休市，2=无法判断）
py is_trading_day.py

# 2) 抓数据、算份额变化、生成 HTML 报告
py build_etf_share_comparison.py

# 3) 从 HTML 导出小程序用的 JSON
py miniprogram/scripts/export_summary_json.py
```

跑完直接双击同目录下的 `16只ETF基金份额变化汇总.html` 就能看，不需要起服务器。

首次运行会补齐全部历史（2015 年至今），视网络情况要几分钟；之后依靠两份 cache 增量抓取，通常十几秒完成。

## 命令详解

### is_trading_day.py — 交易日判定

```bash
py is_trading_day.py                # 判断今天
py is_trading_day.py 2026-11-23     # 判断指定日期
```

输出一行，取首词判断：

| 输出示例 | 含义 | 退出码 |
|---|---|---|
| `TRADING_DAY 2026-11-20 source=cache` | 交易日 | 0 |
| `NON_TRADING_DAY 2026-11-21 source=cache` | 休市（周末或法定节假日） | 1 |
| `UNKNOWN 2026-11-21 ...` | 日期格式错误等 | 2 |

`source` 是日历来源：`cache` 命中本地缓存，`akshare` / `exchange_calendars` 为联网或内置日历，`weekday-fallback` 是兜底（仅按周一到周五判断，不认节假日）。

### build_etf_share_comparison.py — 主脚本

无参数，直接运行。它做四件事：

1. 读两份 cache，只补抓缺失的日期区间（近期窗口会重抓，用于覆盖交易所晚间的空响应）；
2. 按各基金自身的交易日序列计算份额增减；
3. 生成单文件 HTML，数据以 JSON 内嵌、图表用 Canvas 绘制；
4. 在终端打印每只基金的记录数、起止日期和最新份额，方便核对。

```text
Built: ...\16只ETF基金份额变化汇总.html
510050 华夏上证50ETF: 2859 records, 2015-02-12 -> 2026-11-20, latest 241.3417 亿份
```

看到 `[SSE retry later]` / `[SZSE retry later]` 属正常重试——交易所接口会限流，脚本自动退避。

### export_summary_json.py — 导出小程序数据

必须在 HTML 所在目录执行（脚本用 `cwd` 找文件）：

```bash
py miniprogram/scripts/export_summary_json.py
# 或显式指定 HTML 路径
py miniprogram/scripts/export_summary_json.py path/to/16只ETF基金份额变化汇总.html
```

加 `--sample` 可额外导出一份降采样快照，给小程序内置预览：

```bash
py miniprogram/scripts/export_summary_json.py --sample miniprogram/assets/summary_sample.json
```

## 输出文件

| 文件 | 说明 |
|---|---|
| `16只ETF基金份额变化汇总.html` | 主报告，单文件、离线可看 |
| `etf_share_summary.json` | 结构化数据，结构为 `{funds, reportEnd, generatedAt}` |
| `sse_target_funds_cache.json` | 上交所份额缓存，`{日期: {代码: 份额}}` |
| `szse_target_funds_cache.json` | 深交所份额缓存，`{月份: {代码: [{d, v}]}}` |
| `trade_calendar_cache.json` | 交易日历缓存 |

两份 cache 是**增量抓取的基础**。删掉不会报错，但下次会退回全量抓取，慢很多，建议保留。

## 目录结构

```
.
├── build_etf_share_comparison.py   主脚本：抓取两市数据并生成 HTML
├── report/                        网页模板、样式和交互脚本，构建时内嵌进 HTML
├── is_trading_day.py               交易日判定
├── trade_calendar_cache.json       交易日历缓存
├── sse_target_funds_cache.json     上交所份额缓存
├── szse_target_funds_cache.json    深交所份额缓存
├── 16只ETF基金份额变化汇总.html      生成的报告
├── etf_share_summary.json          小程序用的结构化数据
├── automation/prompt.md            定时任务配置与提示词
├── 定时任务分享配置.md               迁移到另一台机器的说明
└── miniprogram/                    微信小程序端（云开发版）
    ├── pages/                      首页、详情、关于
    ├── components/                 折线图、迷你趋势图
    ├── cloudfunctions/getSummary/  读取云存储 JSON 的云函数
    └── scripts/                    导出脚本、部署脚本
```

## 报告怎么看

- **市场总览**展示跟踪基金的最新份额、单日合计变化和净申购 / 净赎回前五。点击排行中的基金可查看详情。
- **基金份额走势**支持 1 年、3 年、5 年和全部历史。点「配置对比」选择基金，或切换到区间起点为 100 的相对走势。悬停或聚焦图表后用左右方向键查看交易日数据。
- **指数分析**按跟踪指数汇总，并在同一张图上显示各成分基金的份额。
- **基金明细**支持按名称或代码搜索、按指数筛选和排序。点击基金名称可查看完整历史曲线、累计变化率、峰值和记录数。
- 份额增加为红色，减少为绿色。「单日变化」取各基金自身最近两个有效交易日之差。页面右上角可查看数据来源和统计口径，导出 CSV 包含全部基金的完整历史。

## 数据口径

几个必须知道的事实，否则容易读错数据：

1. **份额在收盘后很久才发布**，两市一般在当日 23:15 之后更新。23:15 之前跑，拿到的一定是 T-1 数据。
2. **两市发布节奏不同步**，深交所经常比上交所滞后一个交易日，跨源比较时不能假设同一天。
3. **上交所会写入当日空占位**，不过滤会把「暂无数据」算成「份额归零」，脚本已过滤。
4. **跨周末与补跑**：周一的「当日变化」实际是周五→周一；补跑缺失区间时，那几天会被合并成一段累计变化。

## 小程序端

`miniprogram/` 是微信小程序工程（云开发版），读取 `etf_share_summary.json`。

1. 用微信开发者工具导入 `miniprogram/` 目录；
2. 在 `miniprogram/utils/config.js` 填云开发环境 ID（`CLOUD_ENV`）；
3. 把 `etf_share_summary.json` 上传到云存储的 `etf_share/` 前缀下，云函数 `getSummary` 按这个路径读取；
4. 没有云环境也能预览：保持 `USE_CLOUD: true` + `CLOUD_ENV: ""`，会自动回退到 `assets/summary_sample.json` 的内置示例数据。

`project.config.json` 里的 appid 是 `touristappid`，正式发布前换成自己的。

## 定时任务

每个交易日 23:40 自动执行：先判交易日（休市直接退出），再跑主脚本与导出脚本，最后回报当日份额变化 TOP3。

完整配置与提示词见 [`automation/prompt.md`](automation/prompt.md)，迁移到另一台机器的步骤见 [`定时任务分享配置.md`](定时任务分享配置.md)。

## 常见问题

**跑起来特别慢或一直卡住**
首次全量抓取要遍历 2015 年至今，慢属正常。超过十分钟无输出多半是网络问题，看是否出现大量 retry。

**报 OpenBLAS 或内存错误**
部分 Windows 环境下 pandas 底层库会申请过多线程，在命令前限制线程数：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 py build_etf_share_comparison.py
```

**数据没更新到当天**
先确认运行时间是否在 23:15 之后。当天份额尚未发布时，脚本只能拿到前一交易日。

**HTML 打开是空白**
报告依赖内嵌 JSON 与 Canvas，请用较新的 Chrome / Edge / Safari 打开。

**中文乱码**
Windows 控制台默认 GBK，建议用 Windows Terminal 或 PowerShell 7，或先执行 `chcp 65001`。

## 许可

代码以 [MIT License](LICENSE) 开源。数据来源于上交所、深交所公开接口，其版权与使用条款归原机构所有，不在本许可范围内。

## 免责声明

仅供研究与学习使用，不构成任何投资建议。接口结构可能随时调整，脚本不保证长期可用。
