"""从「16只ETF基金份额变化汇总.html」中提取结构化数据，导出为小程序可用的 JSON。

用法（在 HTML 所在目录执行，cwd 即 etf_share_comparison_16）：
    py export_summary_json.py            # 导出全量 summary.json（供上云）
    py export_summary_json.py --sample assets/summary_sample.json
                                       # 额外导出一份降采样快照（供小程序内置预览）

说明：
    - 页面 <script> 中内嵌了 const FUNDS = [...]; 结构，即 16 只 ETF 的
      {code,name,exchange,group,color,data:[{d:"日期",v:份额(亿份)}]}。
    - 全量导出保留每个交易日数据点；--sample 按约每 5 个交易日抽 1 点，
      并强制保留首/尾点，文件体积更小，便于内置到小程序资源目录。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HTML_NAME = "16只ETF基金份额变化汇总.html"


def extract_funds(html_path: Path) -> list[dict]:
    text = html_path.read_text(encoding="utf-8")
    m = re.search(r"const FUNDS = (\[.*?\]);", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"未能在 {html_path.name} 中找到内嵌的 FUNDS 数据")
    payload = json.loads(m.group(1))

    funds = []
    for fund in payload:
        rows = sorted(fund.get("data", []), key=lambda r: r["d"])
        if not rows:
            continue
        funds.append(
            {
                "code": fund["code"],
                "name": fund["name"],
                "exchange": fund["exchange"],
                "group": fund["group"],
                "color": fund["color"],
                "data": [{"d": r["d"], "v": round(float(r["v"]), 6)} for r in rows],
            }
        )
    if not funds:
        raise RuntimeError("提取到的 FUNDS 为空")
    return funds


def downsample(funds: list[dict], step: int = 5) -> list[dict]:
    out = []
    for fund in funds:
        rows = fund["data"]
        if len(rows) <= step * 2:
            out.append(fund)
            continue
        kept = rows[::step]
        if kept[-1] is not rows[-1]:
            kept.append(rows[-1])  # 保留最新点
        if kept[0] is not rows[0]:
            kept.insert(0, rows[0])  # 保留最早点
        out.append({**fund, "data": kept})
    return out


def derive_meta(funds: list[dict]) -> dict:
    report_end = max(f["data"][-1]["d"] for f in funds)
    generated_at = None  # 真实生成时间由定时任务写入，这里留空
    return {"reportEnd": report_end, "generatedAt": generated_at}


def main() -> int:
    cwd = Path.cwd()
    html_path = cwd / HTML_NAME
    if not html_path.exists():
        # 允许通过第一个位置参数指定 HTML 路径
        if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
            html_path = Path(sys.argv[1]).resolve()
    if not html_path.exists():
        raise SystemExit(f"未找到 {HTML_NAME}（cwd={cwd}）")

    funds = extract_funds(html_path)
    meta = derive_meta(funds)

    full = {"funds": funds, **meta}
    out_full = cwd / "etf_share_summary.json"
    out_full.write_text(
        json.dumps(full, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"导出全量: {out_full}  ({len(funds)} 只, {out_full.stat().st_size//1024} KB)")

    if "--sample" in sys.argv:
        idx = sys.argv.index("--sample")
        sample_target = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "summary_sample.json"
        sample = {"funds": downsample(funds), **meta}
        sample_path = cwd / sample_target
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text(
            json.dumps(sample, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"导出快照: {sample_path}  ({sample_path.stat().st_size//1024} KB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
