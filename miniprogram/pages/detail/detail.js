const fmt = require("../../utils/format");
const { metrics, inRange } = require("../../utils/metrics");
const { getSummary } = require("../../utils/cloud");

function ds(arr, max) {
  if (!arr || arr.length <= max) return arr.slice();
  const step = Math.ceil(arr.length / max);
  const out = [];
  for (let i = 0; i < arr.length; i += step) out.push(arr[i]);
  if (out[out.length - 1] !== arr[arr.length - 1]) out.push(arr[arr.length - 1]);
  return out;
}

Page({
  data: {
    code: "",
    notFound: false,
    name: "",
    exchange: "",
    group: "",
    latest: "",
    latestDate: "",
    daily: "",
    dailyCls: "",
    dailyPct: "",
    changePct: "",
    changeCls: "",
    peak: "",
    peakDate: "",
    first: "",
    firstDate: "",
    count: 0,
    mode: "absolute",
    range: "all",
    series: [],
  },

  onLoad(q) {
    this.code = q.code;
    const app = getApp();
    const res = app.globalData.summary;
    if (res && res.funds) {
      this.use(res);
    } else {
      getSummary().then((r) => {
        app.globalData.summary = r;
        this.use(r);
      });
    }
  },

  use(res) {
    const f = (res.funds || []).find((x) => x.code === this.code);
    if (!f) {
      this.setData({ notFound: true });
      return;
    }
    this._fund = f;
    this._end = res.reportEnd;
    const m = metrics(f);
    this.setData({
      code: f.code,
      name: f.name,
      exchange: fmt.exchangeLabel(f.exchange),
      group: f.group,
      latest: fmt.fmtYi(m.last.v),
      latestDate: m.last.d,
      daily: fmt.signedYi(m.dailyChange),
      dailyCls: fmt.clsOf(m.dailyChange),
      dailyPct: fmt.signedPct(m.dailyPct),
      changePct: fmt.signedPct(m.pct),
      changeCls: fmt.clsOf(m.change),
      peak: fmt.fmtYi(m.peak.v),
      peakDate: m.peak.d,
      first: fmt.fmtYi(m.first.v),
      firstDate: m.first.d,
      count: m.count,
    });
    this.buildSeries();
  },

  buildSeries() {
    const f = this._fund;
    if (!f) return;
    const rows = inRange(f.data, this.data.range, this._end);
    const base = rows[0] ? rows[0].v : 1;
    const vals = rows.map((r) => ({
      d: r.d,
      v: this.data.mode === "indexed" ? (r.v / base) * 100 : r.v,
    }));
    this.setData({
      series: [{ name: `${f.code} ${f.name}`, color: f.color, values: ds(vals, 700) }],
    });
  },

  setMode(e) {
    this.setData({ mode: e.currentTarget.dataset.mode });
    this.buildSeries();
  },
  setRange(e) {
    this.setData({ range: e.currentTarget.dataset.range });
    this.buildSeries();
  },
});
