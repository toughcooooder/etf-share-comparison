from __future__ import annotations

import calendar
import concurrent.futures
import datetime as dt
import io
import json
import random
import threading
import time
import warnings
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


START_DATE = dt.date(2015, 2, 12)
# Every run advances the query window automatically. The recent-period refreshes
# below also replace cached empty responses collected before exchange settlement.
END_DATE = dt.date.today()
OUTPUT_DIR = Path(__file__).resolve().parent
HTML_PATH = OUTPUT_DIR / "16只ETF基金份额变化汇总.html"
SSE_CACHE_PATH = OUTPUT_DIR / "sse_target_funds_cache.json"
SZSE_CACHE_PATH = OUTPUT_DIR / "szse_target_funds_cache.json"
MAX_SSE_WORKERS = 16
MAX_SZSE_WORKERS = 4

FUNDS = [
    {"code": "512100", "name": "南方中证1000ETF", "exchange": "SSE", "group": "中证1000", "color": "#b4232d"},
    {"code": "560010", "name": "广发中证1000ETF", "exchange": "SSE", "group": "中证1000", "color": "#d97706"},
    {"code": "512500", "name": "华夏中证500ETF", "exchange": "SSE", "group": "中证500", "color": "#a16207"},
    {"code": "510180", "name": "华安上证180ETF", "exchange": "SSE", "group": "上证180", "color": "#7c3aed"},
    {"code": "159919", "name": "嘉实沪深300ETF", "exchange": "SZSE", "group": "沪深300", "color": "#2563eb"},
    {"code": "159845", "name": "华夏中证1000ETF", "exchange": "SZSE", "group": "中证1000", "color": "#ea580c"},
    {"code": "159629", "name": "富国中证1000ETF", "exchange": "SZSE", "group": "中证1000", "color": "#c2410c"},
    {"code": "159915", "name": "易方达创业板ETF", "exchange": "SZSE", "group": "创业板指", "color": "#059669"},
    {"code": "159977", "name": "天弘创业板ETF", "exchange": "SZSE", "group": "创业板指", "color": "#0d9488"},
    {"code": "510330", "name": "华夏沪深300ETF", "exchange": "SSE", "group": "沪深300", "color": "#1d4ed8"},
    {"code": "510050", "name": "华夏上证50ETF", "exchange": "SSE", "group": "上证50", "color": "#be123c"},
    {"code": "510310", "name": "易方达沪深300ETF发起式", "exchange": "SSE", "group": "沪深300", "color": "#4f46e5"},
    {"code": "588080", "name": "易方达上证科创板50ETF", "exchange": "SSE", "group": "科创50", "color": "#9333ea"},
    {"code": "510500", "name": "南方中证500ETF", "exchange": "SSE", "group": "中证500", "color": "#ca8a04"},
    {"code": "588000", "name": "华夏上证科创板50ETF", "exchange": "SSE", "group": "科创50", "color": "#c026d3"},
    {"code": "510300", "name": "华泰柏瑞沪深300ETF", "exchange": "SSE", "group": "沪深300", "color": "#0369a1"},
]

SSE_CODES = {item["code"] for item in FUNDS if item["exchange"] == "SSE"}
SZSE_CODES = {item["code"] for item in FUNDS if item["exchange"] == "SZSE"}
THREAD_LOCAL = threading.local()


def get_session() -> requests.Session:
    if not hasattr(THREAD_LOCAL, "session"):
        session = requests.Session()
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
                ),
                "Connection": "keep-alive",
            }
        )
        THREAD_LOCAL.session = session
    return THREAD_LOCAL.session


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def weekdays(start: dt.date, end: dt.date) -> list[str]:
    result: list[str] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += dt.timedelta(days=1)
    return result


def fetch_sse_date(date_text: str) -> dict[str, float]:
    response = get_session().get(
        "https://query.sse.com.cn/commonQuery.do",
        params={
            "isPagination": "true",
            "pageHelp.pageSize": "10000",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "1",
            "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
            "STAT_DATE": date_text,
        },
        headers={"Referer": "https://www.sse.com.cn/"},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json().get("result") or []
    result: dict[str, float] = {}
    for row in rows:
        code = str(row.get("SEC_CODE", "")).zfill(6)
        if code in SSE_CODES and row.get("TOT_VOL") not in (None, ""):
            # SSE field TOT_VOL is in 10,000 shares. Normalize to 100m shares.
            result[code] = round(float(row["TOT_VOL"]) / 10000, 8)
    return result


def collect_sse() -> dict[str, list[dict[str, object]]]:
    cache = load_json(SSE_CACHE_PATH)
    dates = weekdays(START_DATE, END_DATE)
    refresh_start = END_DATE - dt.timedelta(days=10)
    missing = [
        date_text
        for date_text in dates
        if date_text not in cache
        or dt.date.fromisoformat(date_text) >= refresh_start
    ]
    if missing:
        started = time.monotonic()
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SSE_WORKERS) as executor:
            futures = {
                executor.submit(fetch_sse_date, date_text): date_text
                for date_text in missing
            }
            for future in concurrent.futures.as_completed(futures):
                date_text = futures[future]
                try:
                    cache[date_text] = future.result()
                except Exception as exc:
                    print(f"[SSE retry later] {date_text}: {exc}")
                    continue
                completed += 1
                if completed % 100 == 0:
                    save_json(SSE_CACHE_PATH, cache)
                    print(
                        f"SSE {completed}/{len(missing)} dates "
                        f"in {time.monotonic() - started:.1f}s"
                    )
        save_json(SSE_CACHE_PATH, cache)

    unresolved = [date_text for date_text in dates if date_text not in cache]
    if unresolved:
        raise RuntimeError(
            f"上交所仍有 {len(unresolved)} 个日期请求失败，请重新运行以继续补齐。"
        )

    output = {code: [] for code in SSE_CODES}
    for date_text in dates:
        for code, value in cache.get(date_text, {}).items():
            if code in output:
                output[code].append({"d": date_text, "v": value})
    return output


def month_ranges(start: dt.date, end: dt.date) -> list[tuple[str, dt.date, dt.date]]:
    ranges: list[tuple[str, dt.date, dt.date]] = []
    cursor = dt.date(start.year, start.month, 1)
    while cursor <= end:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = dt.date(cursor.year, cursor.month, last_day)
        range_start = max(start, cursor)
        range_end = min(end, month_end)
        ranges.append((cursor.strftime("%Y-%m"), range_start, range_end))
        cursor = month_end + dt.timedelta(days=1)
    return ranges


def fetch_szse_month(start: dt.date, end: dt.date) -> dict[str, list[dict[str, object]]]:
    response = get_session().get(
        "https://www.szse.cn/api/report/ShowReport",
        params={
            "SHOWTYPE": "xlsx",
            "CATALOGID": "scsj_fund_jjgm",
            "TABKEY": "tab1",
            "txtStart": start.isoformat(),
            "txtEnd": end.isoformat(),
            "jjlb": "ETF",
            "random": str(random.random()),
        },
        headers={
            "Referer": "https://www.szse.cn/market/fund/volume/etf/index.html"
        },
        timeout=60,
    )
    response.raise_for_status()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frame = pd.read_excel(io.BytesIO(response.content), engine="openpyxl")

    output = {code: [] for code in SZSE_CODES}
    if frame.empty or len(frame.columns) < 4:
        return output

    date_values = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    code_values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    share_values = pd.to_numeric(
        frame.iloc[:, 3].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    for index in frame.index:
        if pd.isna(date_values[index]) or pd.isna(code_values[index]) or pd.isna(share_values[index]):
            continue
        code = str(int(code_values[index])).zfill(6)
        if code not in SZSE_CODES:
            continue
        output[code].append(
            {
                "d": date_values[index].date().isoformat(),
                # SZSE XLSX field is in shares. Normalize to 100m shares.
                "v": round(float(share_values[index]) / 100000000, 8),
            }
        )
    for rows in output.values():
        rows.sort(key=lambda row: row["d"])
    return output


def collect_szse() -> dict[str, list[dict[str, object]]]:
    cache = load_json(SZSE_CACHE_PATH)
    ranges = month_ranges(START_DATE, END_DATE)
    refresh_keys = {item[0] for item in ranges[-2:]}
    missing = [
        item
        for item in ranges
        if item[0] not in cache or item[0] in refresh_keys
    ]
    if missing:
        started = time.monotonic()
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SZSE_WORKERS) as executor:
            futures = {
                executor.submit(fetch_szse_month, start, end): key
                for key, start, end in missing
            }
            for future in concurrent.futures.as_completed(futures):
                key = futures[future]
                try:
                    cache[key] = future.result()
                except Exception as exc:
                    print(f"[SZSE retry later] {key}: {exc}")
                    continue
                completed += 1
                if completed % 12 == 0:
                    save_json(SZSE_CACHE_PATH, cache)
                    print(
                        f"SZSE {completed}/{len(missing)} months "
                        f"in {time.monotonic() - started:.1f}s"
                    )
        save_json(SZSE_CACHE_PATH, cache)

    unresolved = [key for key, _, _ in ranges if key not in cache]
    if unresolved:
        raise RuntimeError(
            f"深交所仍有 {len(unresolved)} 个月请求失败，请重新运行以继续补齐。"
        )

    output = {code: [] for code in SZSE_CODES}
    for key, _, _ in ranges:
        month_data = cache.get(key, {})
        for code in SZSE_CODES:
            output[code].extend(month_data.get(code, []))

    for code, rows in output.items():
        unique = {str(row["d"]): row for row in rows}
        output[code] = [unique[date_text] for date_text in sorted(unique)]
    return output


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>16只宽基ETF基金份额变化汇总</title>
  <style>
    :root {
      --bg: #f3f5f7;
      --surface: #ffffff;
      --ink: #182026;
      --muted: #67727c;
      --border: #d8dee3;
      --grid: #e8ecef;
      --red: #b4232d;
      --green: #087f5b;
      --blue: #2563eb;
      --shadow: 0 2px 12px rgba(24, 32, 38, 0.07);
    }

    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-variant-numeric: tabular-nums;
      letter-spacing: 0;
    }

    button, select, a { font: inherit; }
    .top-line { height: 5px; background: var(--red); }
    .page { width: min(1380px, calc(100% - 40px)); margin: 0 auto; padding: 28px 0 46px; }

    .header { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 20px; }
    .eyebrow { color: var(--red); font-size: 13px; font-weight: 700; margin-bottom: 7px; }
    h1 { margin: 0; font-size: 30px; line-height: 1.2; }
    .subtitle { margin: 8px 0 0; color: var(--muted); font-size: 13px; }
    .header-actions { display: flex; gap: 9px; flex: 0 0 auto; }
    .action {
      min-height: 36px; display: inline-flex; align-items: center; justify-content: center;
      padding: 0 13px; border: 1px solid var(--border); border-radius: 5px;
      background: var(--surface); color: var(--ink); text-decoration: none; font-size: 12px; cursor: pointer;
    }
    .action:hover { border-color: #aeb7bf; background: #fafbfc; }

    .kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .kpi { min-height: 108px; padding: 16px 18px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); }
    .kpi-label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 10px; }
    .kpi-value { display: block; font-size: 24px; line-height: 1.15; font-weight: 720; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .kpi-meta { display: block; margin-top: 8px; color: var(--muted); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); margin-bottom: 16px; }
    .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 17px 19px 14px; border-bottom: 1px solid var(--grid); }
    .panel-title { margin: 0; font-size: 17px; font-weight: 700; }
    .panel-note { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
    .control-row { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
    .segmented { display: inline-flex; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; background: #f7f8f9; }
    .segment { height: 32px; padding: 0 11px; border: 0; border-right: 1px solid var(--border); background: transparent; color: var(--muted); font-size: 12px; cursor: pointer; white-space: nowrap; }
    .segment:last-child { border-right: 0; }
    .segment:hover { background: #eef1f3; }
    .segment.active { color: #fff; background: var(--red); }

    .selector-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 19px 8px; }
    .selector-label { color: var(--muted); font-size: 12px; }
    .plain-button { border: 0; background: transparent; padding: 4px 6px; color: var(--blue); font-size: 12px; cursor: pointer; }
    .plain-button:hover { text-decoration: underline; }
    .fund-selector { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px 10px; padding: 0 19px 15px; }
    .fund-toggle { min-width: 0; display: grid; grid-template-columns: 16px 9px minmax(0, 1fr); align-items: center; gap: 7px; padding: 7px 8px; border: 1px solid var(--grid); border-radius: 4px; background: #fafbfc; cursor: pointer; }
    .fund-toggle:hover { border-color: #bdc5cc; }
    .fund-toggle input { width: 15px; height: 15px; margin: 0; accent-color: var(--red); }
    .swatch { width: 9px; height: 9px; border-radius: 2px; }
    .toggle-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
    .toggle-text strong { font-weight: 700; margin-right: 5px; }

    .chart-wrap { position: relative; width: 100%; height: 485px; padding: 10px 12px 5px; border-top: 1px solid var(--grid); }
    canvas { display: block; width: 100%; height: 100%; }
    .empty-chart { position: absolute; inset: 0; display: none; place-items: center; color: var(--muted); font-size: 13px; pointer-events: none; }
    .tooltip { position: absolute; z-index: 5; min-width: 230px; max-width: 340px; padding: 10px 12px; border: 1px solid #c8cfd5; border-radius: 5px; background: rgba(255,255,255,.97); box-shadow: 0 5px 18px rgba(24,32,38,.15); pointer-events: none; opacity: 0; font-size: 11px; }
    .tooltip.show { opacity: 1; }
    .tooltip-date { color: var(--muted); margin-bottom: 7px; }
    .tooltip-row { display: grid; grid-template-columns: 9px minmax(90px,1fr) auto; align-items: center; gap: 7px; margin-top: 4px; }
    .tooltip-row span:nth-child(2) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .index-tabs { display: flex; flex-wrap: wrap; gap: 6px; padding: 13px 19px; border-bottom: 1px solid var(--grid); }
    .index-button { height: 32px; padding: 0 11px; border: 1px solid var(--border); border-radius: 4px; background: #fff; color: var(--muted); font-size: 11px; cursor: pointer; }
    .index-button:hover { border-color: #aeb7bf; }
    .index-button.active { border-color: var(--ink); background: var(--ink); color: #fff; }
    .index-kpis { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); border-bottom: 1px solid var(--grid); }
    .index-stat { min-width: 0; padding: 13px 19px; border-right: 1px solid var(--grid); }
    .index-stat:last-child { border-right: 0; }
    .index-stat-label { display: block; color: var(--muted); font-size: 10px; margin-bottom: 5px; }
    .index-stat-value { display: block; font-size: 16px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .index-chart-wrap { position: relative; width: 100%; height: 390px; padding: 10px 12px 4px; }
    .index-legend { display: flex; flex-wrap: wrap; gap: 8px 18px; padding: 11px 19px 14px; border-top: 1px solid var(--grid); color: var(--muted); font-size: 10px; }
    .index-legend-item { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
    .index-total-line { width: 14px; height: 3px; background: var(--ink); border-radius: 2px; }

    .filter-band { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 24px 0 12px; }
    .section-title { margin: 0; font-size: 18px; }
    .group-filter { display: flex; flex-wrap: wrap; gap: 6px; }
    .filter-button { height: 31px; padding: 0 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); color: var(--muted); font-size: 11px; cursor: pointer; }
    .filter-button.active { color: #fff; border-color: var(--ink); background: var(--ink); }

    .fund-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .fund-card { min-width: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); overflow: hidden; }
    .fund-card-head { display: flex; justify-content: space-between; gap: 10px; padding: 14px 14px 7px; }
    .fund-code { font-size: 13px; font-weight: 750; }
    .fund-name { margin-top: 3px; color: var(--muted); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .exchange-badge { flex: 0 0 auto; align-self: flex-start; padding: 2px 5px; border: 1px solid var(--border); border-radius: 3px; color: var(--muted); font-size: 10px; }
    .spark-wrap { height: 92px; padding: 1px 10px 0; }
    .fund-card-stats { display: grid; grid-template-columns: 1fr 1fr; border-top: 1px solid var(--grid); }
    .fund-card-stat { min-width: 0; padding: 10px 13px 11px; }
    .fund-card-stat + .fund-card-stat { border-left: 1px solid var(--grid); }
    .mini-label { display: block; color: var(--muted); font-size: 10px; margin-bottom: 4px; }
    .mini-value { display: block; font-size: 14px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .coverage { padding: 8px 13px; border-top: 1px solid var(--grid); color: var(--muted); font-size: 10px; }
    .positive { color: var(--green) !important; }
    .negative { color: var(--red) !important; }

    .table-tools { display: flex; align-items: center; gap: 8px; }
    .table-tools label { color: var(--muted); font-size: 11px; }
    .sort-select { height: 32px; padding: 0 28px 0 9px; border: 1px solid var(--border); border-radius: 4px; background: #fff; color: var(--ink); font-size: 11px; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    th { padding: 10px 12px; background: #f5f7f8; color: var(--muted); text-align: right; font-weight: 650; border-bottom: 1px solid var(--border); white-space: nowrap; }
    th:first-child, th:nth-child(2), td:first-child, td:nth-child(2) { text-align: left; }
    td { padding: 10px 12px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
    tbody tr:hover { background: #f8f9fa; }
    tbody tr:last-child td { border-bottom: 0; }
    .table-code { font-weight: 700; }
    .source-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
    .source-note { padding: 14px 16px; border-left: 3px solid var(--red); background: #fff; color: var(--muted); font-size: 11px; line-height: 1.7; }
    .source-note.szse { border-left-color: var(--blue); }
    .source-note strong { color: var(--ink); }
    .source-note a { color: var(--blue); }
    .footer { display: flex; justify-content: space-between; gap: 20px; padding-top: 17px; color: var(--muted); font-size: 10px; }

    @media (max-width: 1100px) {
      .fund-selector, .fund-cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 820px) {
      .page { width: min(100% - 24px, 1380px); padding-top: 21px; }
      .header { flex-direction: column; align-items: flex-start; }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel-head { flex-direction: column; align-items: flex-start; }
      .control-row { justify-content: flex-start; }
      .fund-selector, .fund-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .chart-wrap { height: 420px; }
      .filter-band { align-items: flex-start; flex-direction: column; }
      .source-notes { grid-template-columns: 1fr; }
      .index-kpis { grid-template-columns: repeat(2, minmax(0,1fr)); }
      .index-stat:nth-child(2) { border-right: 0; }
      .index-stat:nth-child(-n+2) { border-bottom: 1px solid var(--grid); }
    }
    @media (max-width: 540px) {
      h1 { font-size: 25px; }
      .header-actions { width: 100%; flex-wrap: wrap; }
      .action { flex: 1 1 30%; padding: 0 8px; }
      .kpis, .fund-selector, .fund-cards { grid-template-columns: 1fr; }
      .selector-head { align-items: flex-start; }
      .chart-wrap { height: 370px; padding-left: 2px; padding-right: 2px; }
      .segmented { max-width: 100%; overflow-x: auto; }
      .segment { flex: 0 0 auto; padding: 0 9px; }
      .tooltip { min-width: 200px; max-width: calc(100% - 20px); }
      .index-chart-wrap { height: 340px; padding-left: 2px; padding-right: 2px; }
      .footer { flex-direction: column; }
    }
    @media print {
      body { background: #fff; }
      .page { width: 100%; padding: 10px; }
      .header-actions, .fund-selector, .selector-head, .control-row, .filter-band .group-filter { display: none; }
      .panel, .fund-card, .kpi { box-shadow: none; }
      .fund-cards { grid-template-columns: repeat(4, 1fr); }
    }
  </style>
</head>
<body>
  <div class="top-line"></div>
  <main class="page">
    <header class="header">
      <div>
        <div class="eyebrow">沪深两市 · 16只宽基ETF</div>
        <h1>基金总份额变化汇总</h1>
        <p class="subtitle">统计区间 2015-02-12 至 __REPORT_END__ · 单位统一为亿份</p>
      </div>
      <div class="header-actions">
        <a class="action" href="https://www.sse.com.cn/assortment/fund/etf/list/scale/" target="_blank" rel="noreferrer">上交所来源</a>
        <a class="action" href="https://www.szse.cn/market/fund/volume/etf/index.html" target="_blank" rel="noreferrer">深交所来源</a>
        <button class="action" id="downloadCsv" type="button">下载汇总 CSV</button>
      </div>
    </header>

    <section class="kpis" aria-label="汇总指标">
      <article class="kpi"><span class="kpi-label">纳入基金</span><strong class="kpi-value" id="fundCount">--</strong><span class="kpi-meta">11只沪市 · 5只深市</span></article>
      <article class="kpi"><span class="kpi-label">最新份额合计</span><strong class="kpi-value" id="latestTotal">--</strong><span class="kpi-meta">各基金最新有效记录汇总</span></article>
      <article class="kpi"><span class="kpi-label">最新一日合计变化</span><strong class="kpi-value" id="latestDailyChange">--</strong><span class="kpi-meta" id="latestDailyMeta">相对各自前一有效交易日</span></article>
      <article class="kpi"><span class="kpi-label">最新份额最大</span><strong class="kpi-value" id="largestFund">--</strong><span class="kpi-meta" id="largestFundMeta">--</span></article>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">多基金对比</h2>
          <p class="panel-note">勾选基金后比较绝对份额，或切换为各自区间起点=100的相对变化</p>
        </div>
        <div class="control-row">
          <div class="segmented" role="group" aria-label="图表口径">
            <button class="segment active" type="button" data-mode="absolute">份额（亿份）</button>
            <button class="segment" type="button" data-mode="indexed">相对起点（100）</button>
          </div>
          <div class="segmented" role="group" aria-label="时间范围">
            <button class="segment" type="button" data-range="1y">1年</button>
            <button class="segment" type="button" data-range="3y">3年</button>
            <button class="segment" type="button" data-range="5y">5年</button>
            <button class="segment active" type="button" data-range="all">全部</button>
          </div>
        </div>
      </div>
      <div class="selector-head">
        <span class="selector-label"><span id="selectedCount">6</span>只已选；全部勾选时线条较密，可用下方单基金卡片查看细节</span>
        <span><button class="plain-button" id="selectAll" type="button">全选</button><button class="plain-button" id="clearAll" type="button">清空</button></span>
      </div>
      <div class="fund-selector" id="fundSelector"></div>
      <div class="chart-wrap" id="comparisonWrap">
        <canvas id="comparisonChart" role="img" aria-label="16只ETF基金份额对比折线图"></canvas>
        <div class="empty-chart" id="emptyChart">请至少选择一只基金</div>
        <div class="tooltip" id="comparisonTooltip" aria-hidden="true"></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">同指数ETF汇总</h2>
          <p class="panel-note">粗线为同一指数下全部ETF份额之和，细线为各基金公司产品；新增基金从上市后纳入合计</p>
        </div>
      </div>
      <div class="index-tabs" id="indexTabs" role="group" aria-label="选择跟踪指数"></div>
      <div class="index-kpis" aria-label="所选指数汇总指标">
        <div class="index-stat"><span class="index-stat-label">合计最新份额</span><strong class="index-stat-value" id="indexLatest">--</strong></div>
        <div class="index-stat"><span class="index-stat-label">最新日合计变化</span><strong class="index-stat-value" id="indexDaily">--</strong></div>
        <div class="index-stat"><span class="index-stat-label">纳入ETF</span><strong class="index-stat-value" id="indexFundCount">--</strong></div>
        <div class="index-stat"><span class="index-stat-label">最大单只ETF</span><strong class="index-stat-value" id="indexLargest">--</strong></div>
      </div>
      <div class="index-chart-wrap" id="indexChartWrap">
        <canvas id="indexChart" role="img" aria-label="同指数ETF合计份额与成分基金走势图"></canvas>
        <div class="tooltip" id="indexTooltip" aria-hidden="true"></div>
      </div>
      <div class="index-legend" id="indexLegend"></div>
    </section>

    <div class="filter-band">
      <h2 class="section-title">单基金概览</h2>
      <div class="group-filter" id="groupFilter"></div>
    </div>
    <section class="fund-cards" id="fundCards" aria-label="单基金份额概览"></section>

    <section class="panel">
      <div class="panel-head">
        <div><h2 class="panel-title">基金份额汇总表</h2><p class="panel-note">最新日变化按相邻两个有效交易日计算；累计变化从各基金首个可用记录起计算</p></div>
        <div class="table-tools"><label for="sortSelect">排序</label><select class="sort-select" id="sortSelect"><option value="latest">最新份额从高到低</option><option value="daily">最新日变化从高到低</option><option value="change">累计变化率从高到低</option><option value="code">基金代码</option></select></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>代码</th><th>基金名称</th><th>市场</th><th>类别</th><th>最新数据日</th><th>最新份额</th><th>最新日变化</th><th>日变化率</th><th>累计变化率</th><th>区间峰值</th><th>记录数</th></tr></thead>
          <tbody id="summaryTable"></tbody>
        </table>
      </div>
    </section>

    <section class="source-notes">
      <div class="source-note"><strong>沪市口径：</strong>使用上海证券交易所基金规模接口，原始 <code>TOT_VOL</code> 单位为万份，页面除以10,000换算为亿份。基金尚未上市的日期保持空白，不做前向填充。</div>
      <div class="source-note szse"><strong>深市口径：</strong>使用深圳证券交易所基金规模日频公开报表，原始单位为份，页面除以1亿换算为亿份。该公开接口在本区间内最早可用数据日为2016-08-08，因此深市基金在此前区间不补值。</div>
    </section>

    <footer class="footer"><span>数据为交易日清算后基金份额，不等同于基金资产净值或规模金额。</span><span>页面生成时间：__GENERATED_AT__</span></footer>
  </main>

  <script>
    "use strict";
    const FUNDS = __FUNDS_JSON__;
    const REPORT_END = "__REPORT_END__";
    const DEFAULT_CODES = ["510050","510300","510500","512100","159915","588000"];
    const INDEX_GROUPS = ["沪深300","中证500","中证1000","创业板指","科创50","上证50","上证180"];
    const GROUPS = ["全部", ...INDEX_GROUPS];
    const state = { selected: new Set(DEFAULT_CODES), mode: "absolute", range: "all", group: "全部", indexGroup: "沪深300", sort: "latest", hoverTime: null, indexHoverTime: null };
    const chart = document.getElementById("comparisonChart");
    const chartWrap = document.getElementById("comparisonWrap");
    const tooltip = document.getElementById("comparisonTooltip");
    const indexChart = document.getElementById("indexChart");
    const indexTooltip = document.getElementById("indexTooltip");
    const dateMs = (text) => new Date(`${text}T00:00:00`).getTime();
    const formatNumber = (value, digits=2) => value.toLocaleString("zh-CN", {minimumFractionDigits:digits, maximumFractionDigits:digits});
    const formatYi = (value, digits=2) => `${formatNumber(value,digits)} 亿份`;
    const signedYi = (value) => `${value > 0 ? "+" : ""}${formatNumber(value,2)} 亿份`;
    const signedPct = (value) => `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
    const shortDate = (value) => value.replaceAll("-", ".");

    function metrics(fund) {
      const first = fund.data[0]; const last = fund.data.at(-1); const previous = fund.data.at(-2) || first;
      const change = last.v - first.v; const pct = change / first.v * 100;
      const dailyChange = last.v - previous.v; const dailyPct = dailyChange / previous.v * 100;
      const peak = fund.data.reduce((a,b) => b.v > a.v ? b : a);
      return {first,last,previous,change,pct,dailyChange,dailyPct,peak,count:fund.data.length};
    }

    function setupCanvas(canvas) {
      const rect = canvas.getBoundingClientRect(); const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(rect.width*dpr); canvas.height = Math.round(rect.height*dpr);
      const ctx = canvas.getContext("2d"); ctx.setTransform(dpr,0,0,dpr,0,0);
      return {ctx,width:rect.width,height:rect.height};
    }

    function rangeStart() {
      if (state.range === "all") return dateMs("2015-02-12");
      const end = new Date(`${REPORT_END}T00:00:00`); end.setFullYear(end.getFullYear()-Number(state.range[0]));
      return end.getTime();
    }

    function visibleRows(fund) {
      const start = rangeStart(); const rows = fund.data.filter(row => dateMs(row.d) >= start);
      return rows.length ? rows : [];
    }

    function niceStep(raw) {
      if (!Number.isFinite(raw) || raw <= 0) return 1;
      const p = 10 ** Math.floor(Math.log10(raw)); const n = raw/p;
      return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10)*p;
    }

    function nearestRow(rows, target) {
      if (!rows.length) return null; let low=0, high=rows.length-1;
      while(low<high){const mid=Math.floor((low+high)/2); if(dateMs(rows[mid].d)<target) low=mid+1; else high=mid;}
      if(low>0 && Math.abs(dateMs(rows[low-1].d)-target)<Math.abs(dateMs(rows[low].d)-target)) return rows[low-1];
      return rows[low];
    }

    function selectedSeries() {
      return FUNDS.filter(fund => state.selected.has(fund.code)).map(fund => {
        const rows=visibleRows(fund); const base=rows[0]?.v || 1;
        return {fund,rows,points:rows.map(row => ({d:row.d,v:state.mode==="indexed" ? row.v/base*100 : row.v,raw:row.v}))};
      }).filter(series => series.rows.length);
    }

    function drawComparison() {
      const {ctx,width,height}=setupCanvas(chart); const compact=width<600;
      const plot={left:compact?53:70,right:18,top:22,bottom:43}; const pw=Math.max(1,width-plot.left-plot.right); const ph=Math.max(1,height-plot.top-plot.bottom);
      const series=selectedSeries(); document.getElementById("emptyChart").style.display=series.length?"none":"grid";
      ctx.clearRect(0,0,width,height); if(!series.length){state.geometry=null;return;}
      const allPoints=series.flatMap(item=>item.points); const minT=Math.min(...allPoints.map(p=>dateMs(p.d))); const maxT=Math.max(...allPoints.map(p=>dateMs(p.d)));
      const vals=allPoints.map(p=>p.v); const rawMin=Math.min(...vals), rawMax=Math.max(...vals); const pad=Math.max((rawMax-rawMin)*.08,state.mode==="indexed"?3:1);
      const step=niceStep((rawMax-rawMin+pad*2)/5); const yMin=Math.max(0,Math.floor((rawMin-pad)/step)*step); const yMax=Math.ceil((rawMax+pad)/step)*step;
      const xOf=t=>plot.left+(t-minT)/Math.max(1,maxT-minT)*pw; const yOf=v=>plot.top+(yMax-v)/Math.max(1,yMax-yMin)*ph;
      ctx.font=`${compact?10:11}px "Segoe UI","Microsoft YaHei",sans-serif`; ctx.textBaseline="middle";
      const ticks=Math.round((yMax-yMin)/step); for(let i=0;i<=ticks;i++){const v=yMin+i*step,y=yOf(v);ctx.strokeStyle="#e7ebee";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(plot.left,y);ctx.lineTo(width-plot.right,y);ctx.stroke();ctx.fillStyle="#67727c";ctx.textAlign="right";ctx.fillText(v.toLocaleString("zh-CN",{maximumFractionDigits:1}),plot.left-9,y);}
      const xCount=compact?4:7; for(let i=0;i<xCount;i++){const r=i/(xCount-1),d=new Date(minT+(maxT-minT)*r),label=state.range==="1y"?`${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,"0")}`:String(d.getFullYear());ctx.fillStyle="#67727c";ctx.textAlign=i===0?"left":i===xCount-1?"right":"center";ctx.fillText(label,plot.left+r*pw,height-17);}
      ctx.save();ctx.beginPath();ctx.rect(plot.left,plot.top,pw,ph);ctx.clip();
      series.forEach(item=>{ctx.beginPath();item.points.forEach((p,i)=>{const x=xOf(dateMs(p.d)),y=yOf(p.v);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.strokeStyle=item.fund.color;ctx.lineWidth=state.selected.size>10?1.25:1.8;ctx.lineJoin="round";ctx.stroke();});
      if(state.hoverTime!==null){const x=xOf(state.hoverTime);ctx.strokeStyle="rgba(103,114,124,.55)";ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x,plot.top);ctx.lineTo(x,plot.top+ph);ctx.stroke();ctx.setLineDash([]);}
      ctx.restore(); state.geometry={plot,pw,ph,minT,maxT,xOf,yOf,series};
    }

    function handlePointer(event) {
      const g=state.geometry;if(!g)return;const rect=chart.getBoundingClientRect();const clientX=event.touches?event.touches[0].clientX:event.clientX;const x=clientX-rect.left;
      if(x<g.plot.left||x>rect.width-g.plot.right){hideTooltip();return;} const ratio=(x-g.plot.left)/g.pw;state.hoverTime=g.minT+ratio*(g.maxT-g.minT);drawComparison();
      const entries=g.series.map(item=>{const row=nearestRow(item.rows,state.hoverTime);return row?{fund:item.fund,row}:null;}).filter(Boolean);
      if(!entries.length)return; const shownDate=nearestRow(entries[0].fund.data,state.hoverTime)?.d || entries[0].row.d;
      tooltip.innerHTML=`<div class="tooltip-date">${shownDate}</div>`+entries.map(item=>`<div class="tooltip-row"><i class="swatch" style="background:${item.fund.color}"></i><span>${item.fund.code} ${item.fund.name}</span><strong>${state.mode==="absolute"?formatNumber(item.row.v,2):formatNumber(item.row.v/visibleRows(item.fund)[0].v*100,1)}</strong></div>`).join("");
      tooltip.classList.add("show");tooltip.setAttribute("aria-hidden","false");const tw=330;tooltip.style.left=`${x+tw+20>rect.width?Math.max(6,x-tw-12):x+10}px`;tooltip.style.top="48px";
    }
    function hideTooltip(){state.hoverTime=null;tooltip.classList.remove("show");tooltip.setAttribute("aria-hidden","true");drawComparison();}

    function aggregateIndex(groupName) {
      const funds = FUNDS.filter(fund => fund.group === groupName);
      const commonEnd = funds.map(fund => fund.data.at(-1).d).sort()[0];
      const totals = new Map();
      funds.forEach(fund => fund.data.forEach(row => {
        if (row.d <= commonEnd) totals.set(row.d, (totals.get(row.d) || 0) + row.v);
      }));
      const total = [...totals].sort((a,b) => a[0].localeCompare(b[0])).map(([d,v]) => ({d,v}));
      return {funds,total,commonEnd};
    }

    function renderIndexTabs() {
      const host = document.getElementById("indexTabs");
      host.innerHTML = INDEX_GROUPS.map(group => {
        const count = FUNDS.filter(fund => fund.group === group).length;
        return `<button class="index-button ${state.indexGroup===group?"active":""}" type="button" data-index-group="${group}">${group} · ${count}只</button>`;
      }).join("");
      host.querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
        state.indexGroup = button.dataset.indexGroup;
        state.indexHoverTime = null;
        renderIndexTabs();
        renderIndexPanel();
      }));
    }

    function renderIndexPanel() {
      const aggregate = aggregateIndex(state.indexGroup);
      const last = aggregate.total.at(-1);
      const previous = aggregate.total.at(-2) || last;
      const daily = last.v - previous.v;
      const latestComponents = aggregate.funds.map(fund => {
        const row = fund.data.find(item => item.d === aggregate.commonEnd) || fund.data.at(-1);
        return {fund,row};
      });
      const largest = latestComponents.reduce((a,b) => b.row.v > a.row.v ? b : a);
      document.getElementById("indexLatest").textContent = `${formatYi(last.v)} · ${last.d}`;
      const dailyElement = document.getElementById("indexDaily");
      dailyElement.textContent = `${signedYi(daily)} · 较 ${previous.d}`;
      dailyElement.classList.toggle("positive", daily > 0);
      dailyElement.classList.toggle("negative", daily < 0);
      document.getElementById("indexFundCount").textContent = `${aggregate.funds.length}只 · ${aggregate.funds.map(f=>f.code).join(" / ")}`;
      document.getElementById("indexLargest").textContent = `${largest.fund.code} · ${formatYi(largest.row.v)}`;
      document.getElementById("indexLegend").innerHTML = `<span class="index-legend-item"><i class="index-total-line"></i><strong>${state.indexGroup}合计</strong></span>` + aggregate.funds.map(fund => `<span class="index-legend-item"><i class="swatch" style="background:${fund.color}"></i>${fund.code} ${fund.name}</span>`).join("");
      drawIndexChart(aggregate);
    }

    function drawIndexChart(aggregate = aggregateIndex(state.indexGroup)) {
      const {ctx,width,height} = setupCanvas(indexChart);
      const compact = width < 600;
      const plot = {left:compact?53:70,right:18,top:20,bottom:42};
      const pw = Math.max(1,width-plot.left-plot.right), ph = Math.max(1,height-plot.top-plot.bottom);
      const total = aggregate.total;
      const minT = dateMs(total[0].d), maxT = dateMs(total.at(-1).d);
      const rawMax = Math.max(...total.map(row=>row.v));
      const step = niceStep(rawMax/5), yMin = 0, yMax = Math.ceil(rawMax/step)*step;
      const xOf = value => plot.left+(value-minT)/Math.max(1,maxT-minT)*pw;
      const yOf = value => plot.top+(yMax-value)/Math.max(1,yMax-yMin)*ph;
      ctx.clearRect(0,0,width,height);
      ctx.font = `${compact?10:11}px "Segoe UI","Microsoft YaHei",sans-serif`;
      ctx.textBaseline = "middle";
      const ticks = Math.round(yMax/step);
      for(let i=0;i<=ticks;i++){
        const value=i*step,y=yOf(value);ctx.strokeStyle="#e7ebee";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(plot.left,y);ctx.lineTo(width-plot.right,y);ctx.stroke();ctx.fillStyle="#67727c";ctx.textAlign="right";ctx.fillText(value.toLocaleString("zh-CN",{maximumFractionDigits:1}),plot.left-9,y);
      }
      const xCount=compact?4:7;
      for(let i=0;i<xCount;i++){
        const ratio=i/(xCount-1),value=minT+(maxT-minT)*ratio,d=new Date(value);ctx.fillStyle="#67727c";ctx.textAlign=i===0?"left":i===xCount-1?"right":"center";ctx.fillText(String(d.getFullYear()),plot.left+ratio*pw,height-17);
      }
      ctx.save();ctx.beginPath();ctx.rect(plot.left,plot.top,pw,ph);ctx.clip();
      aggregate.funds.forEach(fund=>{
        const rows=fund.data.filter(row=>row.d<=aggregate.commonEnd);ctx.beginPath();rows.forEach((row,index)=>{const x=xOf(dateMs(row.d)),y=yOf(row.v);if(index===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.strokeStyle=fund.color;ctx.globalAlpha=.72;ctx.lineWidth=1.25;ctx.lineJoin="round";ctx.stroke();ctx.globalAlpha=1;
      });
      ctx.beginPath();total.forEach((row,index)=>{const x=xOf(dateMs(row.d)),y=yOf(row.v);if(index===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.lineTo(xOf(dateMs(total.at(-1).d)),yOf(0));ctx.lineTo(xOf(dateMs(total[0].d)),yOf(0));ctx.closePath();ctx.fillStyle="rgba(24,32,38,.06)";ctx.fill();
      ctx.beginPath();total.forEach((row,index)=>{const x=xOf(dateMs(row.d)),y=yOf(row.v);if(index===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.strokeStyle="#182026";ctx.lineWidth=2.6;ctx.lineJoin="round";ctx.stroke();
      if(state.indexHoverTime!==null){const x=xOf(state.indexHoverTime);ctx.strokeStyle="rgba(103,114,124,.55)";ctx.lineWidth=1;ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x,plot.top);ctx.lineTo(x,plot.top+ph);ctx.stroke();ctx.setLineDash([]);}
      ctx.restore();
      state.indexGeometry={plot,pw,ph,minT,maxT,xOf,yOf,aggregate};
    }

    function handleIndexPointer(event) {
      const geometry=state.indexGeometry;if(!geometry)return;const rect=indexChart.getBoundingClientRect();const clientX=event.touches?event.touches[0].clientX:event.clientX;const x=clientX-rect.left;
      if(x<geometry.plot.left||x>rect.width-geometry.plot.right){hideIndexTooltip();return;}
      const ratio=(x-geometry.plot.left)/geometry.pw;const target=geometry.minT+ratio*(geometry.maxT-geometry.minT);const totalRow=nearestRow(geometry.aggregate.total,target);state.indexHoverTime=dateMs(totalRow.d);drawIndexChart(geometry.aggregate);
      const componentRows=geometry.aggregate.funds.map(fund=>({fund,row:fund.data.find(item=>item.d===totalRow.d)}));
      indexTooltip.innerHTML=`<div class="tooltip-date">${totalRow.d}</div><div class="tooltip-row"><i class="index-total-line"></i><span>${state.indexGroup}合计</span><strong>${formatNumber(totalRow.v,2)}</strong></div>`+componentRows.map(item=>`<div class="tooltip-row"><i class="swatch" style="background:${item.fund.color}"></i><span>${item.fund.code} ${item.fund.name}</span><strong>${item.row?formatNumber(item.row.v,2):"--"}</strong></div>`).join("");
      indexTooltip.classList.add("show");indexTooltip.setAttribute("aria-hidden","false");const tw=330;indexTooltip.style.left=`${x+tw+20>rect.width?Math.max(6,x-tw-12):x+10}px`;indexTooltip.style.top="42px";
    }

    function hideIndexTooltip(){state.indexHoverTime=null;indexTooltip.classList.remove("show");indexTooltip.setAttribute("aria-hidden","true");drawIndexChart();}

    function renderSelector(){const host=document.getElementById("fundSelector");host.innerHTML=FUNDS.map(f=>`<label class="fund-toggle"><input type="checkbox" data-code="${f.code}" ${state.selected.has(f.code)?"checked":""}><i class="swatch" style="background:${f.color}"></i><span class="toggle-text"><strong>${f.code}</strong>${f.name}</span></label>`).join("");host.querySelectorAll("input").forEach(input=>input.addEventListener("change",()=>{input.checked?state.selected.add(input.dataset.code):state.selected.delete(input.dataset.code);document.getElementById("selectedCount").textContent=state.selected.size;drawComparison();}));document.getElementById("selectedCount").textContent=state.selected.size;}

    function drawSpark(canvas,fund){const {ctx,width,height}=setupCanvas(canvas);const vals=fund.data.map(r=>r.v);const min=Math.min(...vals),max=Math.max(...vals),pad=Math.max((max-min)*.08,.2);const yMin=min-pad,yMax=max+pad;const x=i=>8+i/Math.max(1,fund.data.length-1)*(width-16),y=v=>7+(yMax-v)/(yMax-yMin)*(height-14);ctx.clearRect(0,0,width,height);ctx.beginPath();fund.data.forEach((r,i)=>{if(i===0)ctx.moveTo(x(i),y(r.v));else ctx.lineTo(x(i),y(r.v));});ctx.strokeStyle=fund.color;ctx.lineWidth=1.6;ctx.lineJoin="round";ctx.stroke();ctx.lineTo(x(fund.data.length-1),height-7);ctx.lineTo(8,height-7);ctx.closePath();ctx.fillStyle=fund.color+"12";ctx.fill();}

    function renderCards(){const funds=state.group==="全部"?FUNDS:FUNDS.filter(f=>f.group===state.group);const host=document.getElementById("fundCards");host.innerHTML=funds.map(f=>{const m=metrics(f),cls=m.dailyChange>0?"positive":m.dailyChange<0?"negative":"";return `<article class="fund-card"><div class="fund-card-head"><div style="min-width:0"><div class="fund-code" style="color:${f.color}">${f.code}</div><div class="fund-name">${f.name}</div></div><span class="exchange-badge">${f.exchange==="SSE"?"沪":"深"} · ${f.group}</span></div><div class="spark-wrap"><canvas id="spark-${f.code}" role="img" aria-label="${f.code}${f.name}份额走势图"></canvas></div><div class="fund-card-stats"><div class="fund-card-stat"><span class="mini-label">最新份额</span><strong class="mini-value">${formatYi(m.last.v)}</strong></div><div class="fund-card-stat"><span class="mini-label">最新日变化</span><strong class="mini-value ${cls}">${signedYi(m.dailyChange)}</strong></div></div><div class="coverage">${m.last.d} · 较 ${m.previous.d} ${signedPct(m.dailyPct)} · 共${m.count.toLocaleString("zh-CN")}日</div></article>`;}).join("");funds.forEach(f=>drawSpark(document.getElementById(`spark-${f.code}`),f));}

    function renderFilters(){const host=document.getElementById("groupFilter");host.innerHTML=GROUPS.map(g=>`<button class="filter-button ${state.group===g?"active":""}" type="button" data-group="${g}">${g}</button>`).join("");host.querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{state.group=b.dataset.group;renderFilters();renderCards();}));}

    function renderTable(){let rows=FUNDS.map(f=>({fund:f,m:metrics(f)}));if(state.sort==="latest")rows.sort((a,b)=>b.m.last.v-a.m.last.v);if(state.sort==="daily")rows.sort((a,b)=>b.m.dailyChange-a.m.dailyChange);if(state.sort==="change")rows.sort((a,b)=>b.m.pct-a.m.pct);if(state.sort==="code")rows.sort((a,b)=>a.fund.code.localeCompare(b.fund.code));document.getElementById("summaryTable").innerHTML=rows.map(({fund:f,m})=>{const dayCls=m.dailyChange>0?"positive":m.dailyChange<0?"negative":"",totalCls=m.change>0?"positive":m.change<0?"negative":"";return `<tr><td class="table-code" style="color:${f.color}">${f.code}</td><td>${f.name}</td><td>${f.exchange==="SSE"?"沪市":"深市"}</td><td>${f.group}</td><td>${m.last.d}</td><td>${formatNumber(m.last.v,2)}</td><td class="${dayCls}">${signedYi(m.dailyChange).replace(" 亿份","")}</td><td class="${dayCls}">${signedPct(m.dailyPct)}</td><td class="${totalCls}">${signedPct(m.pct)}</td><td>${formatNumber(m.peak.v,2)}</td><td>${m.count.toLocaleString("zh-CN")}</td></tr>`;}).join("");}

    function renderKpis(){const ms=FUNDS.map(f=>({f,m:metrics(f)}));const total=ms.reduce((s,x)=>s+x.m.last.v,0),daily=ms.reduce((s,x)=>s+x.m.dailyChange,0);const largest=ms.reduce((a,b)=>b.m.last.v>a.m.last.v?b:a);document.getElementById("fundCount").textContent=`${FUNDS.length} 只`;document.getElementById("latestTotal").textContent=formatYi(total);const dailyElement=document.getElementById("latestDailyChange");dailyElement.textContent=signedYi(daily);dailyElement.classList.toggle("positive",daily>0);dailyElement.classList.toggle("negative",daily<0);document.getElementById("latestDailyMeta").textContent=`截至接口最新有效日 ${REPORT_END}`;document.getElementById("largestFund").textContent=largest.f.code;document.getElementById("largestFundMeta").textContent=`${largest.f.name} · ${formatYi(largest.m.last.v)}`;}

    function downloadCsv(){const dates=[...new Set(FUNDS.flatMap(f=>f.data.map(r=>r.d)))].sort();const maps=new Map(FUNDS.map(f=>[f.code,new Map(f.data.map(r=>[r.d,r.v]))]));const lines=[["日期",...FUNDS.map(f=>`${f.code} ${f.name}(亿份)`)].join(",")];dates.forEach(d=>lines.push([d,...FUNDS.map(f=>maps.get(f.code).get(d)??"")].join(",")));const blob=new Blob(["\ufeff"+lines.join("\r\n")],{type:"text/csv;charset=utf-8"});const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=`16只ETF基金份额_20150212_${REPORT_END.replaceAll("-","")}.csv`;a.click();URL.revokeObjectURL(url);}

    document.querySelectorAll("[data-mode]").forEach(b=>b.addEventListener("click",()=>{state.mode=b.dataset.mode;document.querySelectorAll("[data-mode]").forEach(x=>x.classList.toggle("active",x===b));drawComparison();}));
    document.querySelectorAll("[data-range]").forEach(b=>b.addEventListener("click",()=>{state.range=b.dataset.range;document.querySelectorAll("[data-range]").forEach(x=>x.classList.toggle("active",x===b));drawComparison();}));
    document.getElementById("selectAll").addEventListener("click",()=>{state.selected=new Set(FUNDS.map(f=>f.code));renderSelector();drawComparison();});
    document.getElementById("clearAll").addEventListener("click",()=>{state.selected.clear();renderSelector();drawComparison();});
    document.getElementById("sortSelect").addEventListener("change",e=>{state.sort=e.target.value;renderTable();});
    document.getElementById("downloadCsv").addEventListener("click",downloadCsv);
    chart.addEventListener("mousemove",handlePointer);chart.addEventListener("mouseleave",hideTooltip);chart.addEventListener("touchmove",handlePointer,{passive:true});chart.addEventListener("touchend",hideTooltip);
    indexChart.addEventListener("mousemove",handleIndexPointer);indexChart.addEventListener("mouseleave",hideIndexTooltip);indexChart.addEventListener("touchmove",handleIndexPointer,{passive:true});indexChart.addEventListener("touchend",hideIndexTooltip);
    let resizeTimer;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{drawComparison();drawIndexChart();renderCards();},120);});
    renderKpis();renderSelector();renderIndexTabs();renderIndexPanel();renderFilters();renderCards();renderTable();drawComparison();
  </script>
</body>
</html>
'''


def build_html(sse_data: dict[str, list[dict]], szse_data: dict[str, list[dict]]) -> None:
    merged = {**sse_data, **szse_data}
    payload: list[dict[str, object]] = []
    for fund in FUNDS:
        rows = merged.get(fund["code"], [])
        if not rows:
            raise RuntimeError(f"基金 {fund['code']} 没有获取到份额数据。")
        payload.append({**fund, "data": rows})

    report_end = max(str(fund["data"][-1]["d"]) for fund in payload)
    generated_at = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    html = HTML_TEMPLATE.replace(
        "__FUNDS_JSON__",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    ).replace("__REPORT_END__", report_end).replace("__GENERATED_AT__", generated_at)
    HTML_PATH.write_text(html, encoding="utf-8")

    print(f"Built: {HTML_PATH}")
    for fund in payload:
        rows = fund["data"]
        print(
            f"{fund['code']} {fund['name']}: {len(rows)} records, "
            f"{rows[0]['d']} -> {rows[-1]['d']}, latest {rows[-1]['v']:.4f} 亿份"
        )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sse_data = collect_sse()
    szse_data = collect_szse()
    build_html(sse_data, szse_data)


if __name__ == "__main__":
    main()
