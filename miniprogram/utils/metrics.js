// 指标计算（移植自 HTML 报告的 metrics / aggregateIndex 逻辑）
function metrics(fund) {
  const data = fund.data || [];
  if (!data.length) return null;
  const first = data[0];
  const last = data[data.length - 1];
  const previous = data.length > 1 ? data[data.length - 2] : first;
  const change = last.v - first.v;
  const pct = first.v ? (change / first.v) * 100 : 0;
  const dailyChange = last.v - previous.v;
  const dailyPct = previous.v ? (dailyChange / previous.v) * 100 : 0;
  let peak = data[0];
  for (const r of data) if (r.v > peak.v) peak = r;
  return {
    first,
    last,
    previous,
    change,
    pct,
    dailyChange,
    dailyPct,
    peak,
    count: data.length,
  };
}

// 同指数 ETF 合计（与 HTML 的 aggregateIndex 对齐）
function aggregateIndex(funds) {
  if (!funds.length) return { total: [], commonEnd: null, funds };
  const ends = funds.map((f) => f.data[f.data.length - 1].d).sort();
  const commonEnd = ends[0];
  const totals = new Map();
  funds.forEach((f) =>
    (f.data || []).forEach((r) => {
      if (r.d <= commonEnd) totals.set(r.d, (totals.get(r.d) || 0) + r.v);
    })
  );
  const total = [...totals]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([d, v]) => ({ d, v }));
  return { total, commonEnd, funds };
}

// 对走势做轻量降采样，用于迷你图 / 长序列展示
function downsample(values, maxPoints = 120) {
  if (values.length <= maxPoints) return values.slice();
  const step = Math.ceil(values.length / maxPoints);
  const out = [];
  for (let i = 0; i < values.length; i += step) out.push(values[i]);
  if (out[out.length - 1] !== values[values.length - 1]) out.push(values[values.length - 1]);
  return out;
}

// 取某范围内的数据点（range: all|1y|3y|5y，endDate 形如 2026-10-23）
function rangeStart(range, endDate) {
  if (range === "all") return "2015-02-12";
  const n = Number(range[0]);
  const d = new Date(`${endDate}T00:00:00`);
  d.setFullYear(d.getFullYear() - n);
  return d.toISOString().slice(0, 10);
}

function inRange(data, range, endDate) {
  const start = rangeStart(range, endDate);
  const rows = data.filter((r) => r.d >= start);
  return rows.length ? rows : data.slice(-1);
}

module.exports = { metrics, aggregateIndex, downsample, rangeStart, inRange };
