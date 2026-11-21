const { getSummary } = require("../../utils/cloud");
const fmt = require("../../utils/format");
const { metrics, aggregateIndex, inRange, downsample } = require("../../utils/metrics");

const DEFAULT_CODES = ["510050", "510300", "510500", "512100", "159915", "588000"];
const INDEX_GROUPS = ["沪深300", "中证500", "中证1000", "创业板指", "科创50", "上证50", "上证180"];

// 通用降采样（保留端点），控制传给 canvas 的点数，避免 setData 过大
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
    loading: true,
    source: "",
    reportEnd: "",
    generatedAt: "",
    // KPIs
    kpiCount: 0,
    kpiTotal: "",
    kpiDaily: "",
    kpiDailyCls: "",
    kpiLargest: "",
    kpiLargestMeta: "",
    // 多基金对比
    compMode: "absolute",
    compRange: "all",
    selected: DEFAULT_CODES.slice(),
    selectable: [],
    compSeries: [],
    // 同指数汇总
    indexGroups: INDEX_GROUPS,
    indexGroup: "沪深300",
    indexKpis: {},
    indexSeries: [],
    // 单基金卡片
    groups: ["全部"].concat(INDEX_GROUPS),
    group: "全部",
    cards: [],
    // 汇总表
    sort: "latest",
    tableRows: [],
  },

  onLoad() {
    getSummary().then((res) => {
      const funds = res.funds || [];
      this._funds = funds;
      this._fundMap = {};
      funds.forEach((f) => (this._fundMap[f.code] = f));
      getApp().globalData.summary = res;

      const selectable = funds.map((f) => ({
        code: f.code,
        name: f.name,
        color: f.color,
        checked: this.data.selected.includes(f.code),
      }));
      this.setData({
        loading: false,
        source: res._source,
        reportEnd: res.reportEnd,
        generatedAt: res.generatedAt || "",
        selectable,
      });
      this.buildKpis();
      this.buildCompSeries();
      this.buildIndex();
      this.buildCards();
      this.buildTable();
    });
  },

  buildKpis() {
    const ms = this._funds.map((f) => ({ f, m: metrics(f) }));
    const total = ms.reduce((s, x) => s + x.m.last.v, 0);
    const daily = ms.reduce((s, x) => s + x.m.dailyChange, 0);
    const largest = ms.reduce((a, b) => (b.m.last.v > a.m.last.v ? b : a));
    this.setData({
      kpiCount: this._funds.length,
      kpiTotal: fmt.fmtYi(total),
      kpiDaily: fmt.signedYi(daily),
      kpiDailyCls: fmt.clsOf(daily),
      kpiLargest: largest.f.code,
      kpiLargestMeta: `${largest.f.name} · ${fmt.fmtYi(largest.m.last.v)}`,
    });
  },

  buildCompSeries() {
    const { compRange, compMode, reportEnd } = this.data;
    const series = this.data.selected
      .map((code) => {
        const f = this._fundMap[code];
        if (!f) return null;
        const rows = inRange(f.data, compRange, reportEnd);
        const base = rows[0] ? rows[0].v : 1;
        const vals = rows.map((r) => ({
          d: r.d,
          v: compMode === "indexed" ? (r.v / base) * 100 : r.v,
        }));
        return { name: `${f.code} ${f.name}`, color: f.color, values: ds(vals, 400) };
      })
      .filter(Boolean);
    this.setData({ compSeries: series });
  },

  buildIndex() {
    const group = this.data.indexGroup;
    const funds = this._funds.filter((f) => f.group === group);
    const agg = aggregateIndex(funds);
    const total = agg.total;
    if (!total.length) {
      this.setData({ indexSeries: [], indexKpis: {} });
      return;
    }
    const series = [{ name: `${group}合计`, color: "#182026", isTotal: true, values: ds(total, 600) }];
    funds.forEach((f) => {
      const rows = f.data.filter((r) => r.d <= agg.commonEnd);
      series.push({ name: `${f.code} ${f.name}`, color: f.color, values: ds(rows, 400) });
    });
    const last = total[total.length - 1];
    const prev = total[total.length - 2] || last;
    const daily = last.v - prev.v;
    const comps = funds.map((f) => ({
      f,
      row: f.data.find((r) => r.d === agg.commonEnd) || f.data[f.data.length - 1],
    }));
    const largest = comps.reduce((a, b) => (b.row.v > a.row.v ? b : a));
    this.setData({
      indexSeries: series,
      indexKpis: {
        latest: fmt.fmtYi(last.v),
        latestDate: last.d,
        daily: fmt.signedYi(daily),
        dailyCls: fmt.clsOf(daily),
        count: funds.length,
        codes: funds.map((f) => f.code).join(" / "),
        largest: `${largest.f.code} · ${fmt.fmtYi(largest.row.v)}`,
      },
    });
  },

  buildCards() {
    const g = this.data.group;
    const funds = g === "全部" ? this._funds : this._funds.filter((f) => f.group === g);
    const cards = funds.map((f) => {
      const m = metrics(f);
      return {
        code: f.code,
        name: f.name,
        color: f.color,
        exchange: fmt.exchangeLabel(f.exchange),
        group: f.group,
        latest: fmt.fmtYi(m.last.v),
        latestDate: m.last.d,
        daily: fmt.signedYi(m.dailyChange),
        dailyCls: fmt.clsOf(m.dailyChange),
        dailyPct: fmt.signedPct(m.dailyPct),
        spark: downsample(f.data.map((r) => r.v), 120),
        sparkColor: f.color,
        count: m.count,
      };
    });
    this.setData({ cards });
  },

  buildTable() {
    const rows = this._funds.map((f) => {
      const m = metrics(f);
      return {
        code: f.code,
        name: f.name,
        exchange: fmt.exchangeLabel(f.exchange),
        group: f.group,
        lastDate: m.last.d,
        last: fmt.fmtNum(m.last.v),
        daily: fmt.signedYi(m.dailyChange),
        dailyCls: fmt.clsOf(m.dailyChange),
        dailyPct: fmt.signedPct(m.dailyPct),
        changePct: fmt.signedPct(m.pct),
        changeCls: fmt.clsOf(m.change),
        peak: fmt.fmtNum(m.peak.v),
        count: m.count,
      };
    });
    const num = (s) => parseFloat(String(s).replace(/,/g, ""));
    const sort = this.data.sort;
    if (sort === "latest") rows.sort((a, b) => num(b.last) - num(a.last));
    else if (sort === "daily") rows.sort((a, b) => num(b.daily) - num(a.daily));
    else if (sort === "change") rows.sort((a, b) => num(b.changePct) - num(a.changePct));
    else if (sort === "code") rows.sort((a, b) => a.code.localeCompare(b.code));
    this.setData({ tableRows: rows });
  },

  toggleFund(e) {
    const code = e.currentTarget.dataset.code;
    const selected = this.data.selected.includes(code)
      ? this.data.selected.filter((c) => c !== code)
      : this.data.selected.concat(code);
    const selectable = this.data.selectable.map((s) =>
      s.code === code ? Object.assign({}, s, { checked: !s.checked }) : s
    );
    this.setData({ selected, selectable });
    this.buildCompSeries();
  },
  selectAll() {
    const selected = this._funds.map((f) => f.code);
    const selectable = this.data.selectable.map((s) => Object.assign({}, s, { checked: true }));
    this.setData({ selected, selectable });
    this.buildCompSeries();
  },
  clearAll() {
    const selectable = this.data.selectable.map((s) => Object.assign({}, s, { checked: false }));
    this.setData({ selected: [], selectable });
    this.buildCompSeries();
  },
  setCompMode(e) {
    this.setData({ compMode: e.currentTarget.dataset.mode });
    this.buildCompSeries();
  },
  setCompRange(e) {
    this.setData({ compRange: e.currentTarget.dataset.range });
    this.buildCompSeries();
  },
  setIndexGroup(e) {
    this.setData({ indexGroup: e.currentTarget.dataset.group });
    this.buildIndex();
  },
  setGroup(e) {
    this.setData({ group: e.currentTarget.dataset.group });
    this.buildCards();
  },
  onSortChange(e) {
    this.setData({ sort: e.detail.value });
    this.buildTable();
  },
  goDetail(e) {
    const code = e.currentTarget.dataset.code;
    wx.navigateTo({ url: `/pages/detail/detail?code=${code}` });
  },
});
