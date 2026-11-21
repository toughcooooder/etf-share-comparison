// 通用多序列折线图组件（Canvas 2D，零依赖）
// series: [{ name, color, values:[{d,v}], isTotal? }]
// 显示用的 v 已由页面按 份额/相对起点 与 时间范围 预处理好，组件只负责绘制。

const dateMs = (d) => new Date(`${d}T00:00:00`).getTime();

function niceStep(raw) {
  if (!isFinite(raw) || raw <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function unionDates(series) {
  const set = new Set();
  series.forEach((s) => s.values && s.values.forEach((p) => set.add(p.d)));
  return [...set].sort((a, b) => a.localeCompare(b));
}

function nearestRow(values, t) {
  if (!values || !values.length) return null;
  let lo = 0, hi = values.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dateMs(values[mid].d) < t) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(dateMs(values[lo - 1].d) - t) < Math.abs(dateMs(values[lo].d) - t)) lo--;
  return values[lo];
}

function nearestDate(dates, t) {
  if (!dates.length) return null;
  let lo = 0, hi = dates.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dateMs(dates[mid]) < t) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(dateMs(dates[lo - 1]) - t) < Math.abs(dateMs(dates[lo]) - t)) lo--;
  return dates[lo];
}

function drawTooltip(ctx, x, plot, entries, dateText, W) {
  if (!entries.length) return;
  const lineH = 16, padX = 8, padY = 6;
  const boxW = Math.min(230, W - plot.left - plot.right);
  const boxH = padY * 2 + lineH * (entries.length + 1);
  let bx = x + 10;
  if (bx + boxW > W - 4) bx = W - 4 - boxW;
  if (bx < 4) bx = 4;
  const by = plot.top + 4;
  ctx.fillStyle = "rgba(255,255,255,0.97)";
  ctx.strokeStyle = "#c8cfd5";
  ctx.lineWidth = 1;
  ctx.fillRect(bx, by, boxW, boxH);
  ctx.strokeRect(bx, by, boxW, boxH);
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#67727c";
  ctx.font = "10px sans-serif";
  ctx.fillText(dateText, bx + padX, by + padY + lineH / 2);
  entries.forEach((e, i) => {
    const y = by + padY + lineH * (i + 1) + lineH / 2;
    ctx.fillStyle = e.color || "#333";
    ctx.fillRect(bx + padX, y - 4, 8, 8);
    ctx.fillStyle = "#182026";
    ctx.font = "11px sans-serif";
    const text = `${e.name}  ${e.val.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
    ctx.fillText(text, bx + padX + 14, y);
  });
}

Component({
  properties: {
    series: { type: Array, value: [] },
    height: { type: Number, value: 240 },
    yMin: { type: Number, value: null },
    yMax: { type: Number, value: null },
    compact: { type: Boolean, value: false },
  },
  data: { _ready: false },
  lifetimes: {
    attached() {
      this._geo = null;
      this._hoverT = null;
      this._ctx = null;
    },
    ready() {
      this.initCanvas();
    },
  },
  observers: {
    "series,height,yMin,yMax,compact": function () {
      if (this.data._ready) this.draw();
    },
  },
  methods: {
    initCanvas() {
      const q = this.createSelectorQuery ? this.createSelectorQuery() : wx.createSelectorQuery().in(this);
      q.select("#chart").fields({ node: true, size: true }).exec((res) => {
        if (!res || !res[0] || !res[0].node) return;
        const canvas = res[0].node;
        const ctx = canvas.getContext("2d");
        const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        const dpr = info.pixelRatio || 2;
        canvas.width = res[0].width * dpr;
        canvas.height = res[0].height * dpr;
        ctx.scale(dpr, dpr);
        this._ctx = ctx;
        this._canvas = canvas;
        this._cssW = res[0].width;
        this._cssH = res[0].height;
        this.data._ready = true;
        this.draw();
      });
    },

    draw() {
      const ctx = this._ctx;
      if (!ctx) return;
      const W = this._cssW, H = this._cssH;
      const series = this.properties.series || [];
      ctx.clearRect(0, 0, W, H);
      if (!series.length) { this._geo = null; return; }

      const compact = this.properties.compact;
      const plot = { left: compact ? 46 : 60, right: 14, top: 18, bottom: 38 };
      const pw = Math.max(1, W - plot.left - plot.right);
      const ph = Math.max(1, H - plot.top - plot.bottom);

      const allDates = unionDates(series);
      const minT = dateMs(allDates[0]);
      const maxT = dateMs(allDates[allDates.length - 1]);

      const vals = [];
      series.forEach((s) => s.values && s.values.forEach((p) => vals.push(p.v)));
      const rawMin = Math.min(...vals);
      const rawMax = Math.max(...vals);

      let yMin = this.properties.yMin, yMax = this.properties.yMax;
      if (yMin == null || yMax == null) {
        const pad = Math.max((rawMax - rawMin) * 0.08, 1);
        let lo = rawMin - pad, hi = rawMax + pad;
        if (lo < 0 && rawMin >= 0) lo = 0;
        const step = niceStep((hi - lo) / 5);
        yMin = yMin != null ? yMin : Math.floor(lo / step) * step;
        yMax = yMax != null ? yMax : Math.ceil(hi / step) * step;
        if (yMin < 0 && rawMin >= 0) yMin = 0;
      }

      const xOf = (t) => plot.left + ((t - minT) / Math.max(1, maxT - minT)) * pw;
      const yOf = (v) => plot.top + ((yMax - v) / Math.max(1, yMax - yMin)) * ph;

      // grid + y labels
      const step = niceStep((yMax - yMin) / 5 || 1);
      const ticks = Math.round((yMax - yMin) / step);
      ctx.font = `${compact ? 10 : 11}px sans-serif`;
      ctx.textBaseline = "middle";
      for (let i = 0; i <= ticks; i++) {
        const v = yMin + i * step;
        const y = yOf(v);
        ctx.strokeStyle = "#e7ebee";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(plot.left, y);
        ctx.lineTo(W - plot.right, y);
        ctx.stroke();
        ctx.fillStyle = "#67727c";
        ctx.textAlign = "right";
        ctx.fillText(v.toLocaleString("zh-CN", { maximumFractionDigits: 1 }), plot.left - 8, y);
      }

      // x labels (years)
      const xCount = compact ? 4 : 7;
      for (let i = 0; i < xCount; i++) {
        const r = i / (xCount - 1);
        const d = new Date(minT + (maxT - minT) * r);
        const label = String(d.getFullYear());
        ctx.fillStyle = "#67727c";
        ctx.textAlign = i === 0 ? "left" : i === xCount - 1 ? "right" : "center";
        ctx.fillText(label, plot.left + r * pw, H - 17);
      }

      // clip to plot
      ctx.save();
      ctx.beginPath();
      ctx.rect(plot.left, plot.top, pw, ph);
      ctx.clip();

      series.forEach((s) => {
        const pts = (s.values || []).map((p) => ({ x: xOf(dateMs(p.d)), y: yOf(p.v) }));
        if (!pts.length) return;
        if (s.isTotal) {
          ctx.beginPath();
          pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
          ctx.lineTo(pts[pts.length - 1].x, yOf(yMin));
          ctx.lineTo(pts[0].x, yOf(yMin));
          ctx.closePath();
          ctx.fillStyle = "rgba(24,32,38,0.06)";
          ctx.fill();
        }
        ctx.beginPath();
        pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
        ctx.strokeStyle = s.color || "#333";
        ctx.lineWidth = s.isTotal ? 2.6 : series.length > 10 ? 1.2 : 1.7;
        ctx.lineJoin = "round";
        ctx.stroke();
      });

      if (this._hoverT != null) {
        const x = xOf(this._hoverT);
        ctx.strokeStyle = "rgba(103,114,124,0.55)";
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, plot.top);
        ctx.lineTo(x, plot.top + ph);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.restore();

      this._geo = { plot, pw, ph, minT, maxT };

      if (this._hoverT != null) {
        const near = nearestDate(allDates, this._hoverT);
        const nearMs = dateMs(near);
        const entries = series
          .map((s) => {
            const row = nearestRow(s.values, nearMs);
            return row ? { name: s.name, color: s.color, val: row.v } : null;
          })
          .filter(Boolean);
        drawTooltip(ctx, xOf(nearMs), plot, entries, near, W);
      }
    },

    onTouch(e) {
      if (!this._geo) return;
      const t = e.touches && e.touches[0];
      if (!t) return;
      const x = t.x != null ? t.x : t.clientX;
      const g = this._geo;
      if (x < g.plot.left || x > this._cssW - g.plot.right) {
        this._hoverT = null;
        this.draw();
        return;
      }
      const ratio = (x - g.plot.left) / g.pw;
      this._hoverT = g.minT + ratio * (g.maxT - g.minT);
      this.draw();
    },

    onTouchEnd() {
      this._hoverT = null;
      this.draw();
    },
  },
});
