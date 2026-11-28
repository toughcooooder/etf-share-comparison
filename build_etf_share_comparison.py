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


REPORT_DIR = OUTPUT_DIR / "report"


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
    template = (REPORT_DIR / "template.html").read_text(encoding="utf-8")
    template = template.replace("__REPORT_CSS__", (REPORT_DIR / "dashboard.css").read_text(encoding="utf-8"))
    template = template.replace("__REPORT_JS__", (REPORT_DIR / "dashboard.js").read_text(encoding="utf-8"))
    html = template.replace(
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
