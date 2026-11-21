"""判断指定日期是否为 A 股交易日（沪深交易所）。

用法:
    py is_trading_day.py                 # 判断今天
    py is_trading_day.py 2026-10-08      # 判断指定日期

输出（stdout 末行）:
    TRADING_DAY <date>      交易日
    NON_TRADING_DAY <date>  非交易日（周末或法定休市）
    UNKNOWN <date> <reason> 无法判断（仅日期格式非法时出现）

退出码:
    0 = 交易日   1 = 非交易日   2 = 无法判断

数据源（逐级降级）:
    1. akshare 新浪交易日历 tool_trade_date_hist_sina() —— 最权威，覆盖到次年
    2. exchange_calendars XSHG —— 本地内置日历，离线可用
    3. 星期判断（周一至周五视为交易日）—— 最后兜底

本地缓存: trade_calendar_cache.json，命中的日期无需联网。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_PATH = BASE_DIR / "trade_calendar_cache.json"
CACHE_MAX_AGE_DAYS = 30


def _load_cache() -> set[str]:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        fetched = dt.date.fromisoformat(data["fetched_at"])
        if (dt.date.today() - fetched).days > CACHE_MAX_AGE_DAYS:
            return set()
        return set(data["dates"])
    except Exception:
        return set()


def _save_cache(dates: set[str]) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(
                {"fetched_at": dt.date.today().isoformat(), "dates": sorted(dates)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _from_akshare() -> set[str]:
    import akshare as ak

    df = ak.tool_trade_date_hist_sina()
    return {str(v)[:10] for v in df["trade_date"].astype(str)}


def _from_exchange_calendars() -> set[str]:
    import exchange_calendars as xc

    cal = xc.get_calendar("XSHG")
    start = dt.date(dt.date.today().year - 1, 1, 1)
    end = dt.date(dt.date.today().year + 2, 12, 31)
    return {str(s.date()) for s in cal.sessions_in_range(str(start), str(end))}


def resolve_trading_dates() -> tuple[set[str], str, str | None]:
    """返回 (交易日集合, 数据源名称, 失败原因)。"""
    errors: list[str] = []

    cached = _load_cache()
    if cached:
        return cached, "cache", None

    for name, loader in (("akshare", _from_akshare), ("exchange_calendars", _from_exchange_calendars)):
        try:
            dates = loader()
            if dates:
                _save_cache(dates)
                return dates, name, None
        except Exception as exc:  # noqa: BLE001 - 逐级降级，任一数据源失败都不致命
            errors.append(f"{name}: {type(exc).__name__}")

    return set(), "none", "; ".join(errors) or "no source available"


def is_trading_day(target: dt.date) -> tuple[bool | None, str]:
    """返回 (是否交易日 | None 表示未知, 说明)。"""
    dates, source, error = resolve_trading_dates()
    if dates:
        return target.isoformat() in dates, source
    # 最后兜底：周一至周五视为交易日
    return target.weekday() < 5, f"weekday-fallback({error})"


def main() -> int:
    if len(sys.argv) > 1:
        try:
            target = dt.date.fromisoformat(sys.argv[1].strip())
        except ValueError:
            print(f"UNKNOWN {sys.argv[1]} invalid-date-format")
            return 2
    else:
        target = dt.date.today()

    result, source = is_trading_day(target)
    if result is True:
        print(f"TRADING_DAY {target.isoformat()} source={source}")
        return 0
    if result is False:
        print(f"NON_TRADING_DAY {target.isoformat()} source={source}")
        return 1
    print(f"UNKNOWN {target.isoformat()} {source}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
