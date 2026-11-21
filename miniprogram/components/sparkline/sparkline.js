// 单序列迷你走势图（Canvas 2D，零依赖）
// values: number[] ; color: 线条颜色
Component({
  properties: {
    values: { type: Array, value: [] },
    color: { type: String, value: "#333333" },
    height: { type: Number, value: 60 },
  },
  data: { _ready: false },
  lifetimes: {
    attached() { this._ctx = null; },
    ready() { this.initCanvas(); },
  },
  observers: {
    "values,color,height": function () {
      if (this.data._ready) this.draw();
    },
  },
  methods: {
    initCanvas() {
      const q = this.createSelectorQuery ? this.createSelectorQuery() : wx.createSelectorQuery().in(this);
      q.select("#spark").fields({ node: true, size: true }).exec((res) => {
        if (!res || !res[0] || !res[0].node) return;
        const canvas = res[0].node;
        const ctx = canvas.getContext("2d");
        const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        const dpr = info.pixelRatio || 2;
        canvas.width = res[0].width * dpr;
        canvas.height = res[0].height * dpr;
        ctx.scale(dpr, dpr);
        this._ctx = ctx;
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
      const vals = (this.properties.values || []).filter((v) => typeof v === "number" && isFinite(v));
      ctx.clearRect(0, 0, W, H);
      if (vals.length < 2) return;
      const min = Math.min(...vals), max = Math.max(...vals);
      const pad = Math.max((max - min) * 0.08, 0.5);
      const yMin = min - pad, yMax = max + pad;
      const x = (i) => 6 + (i / Math.max(1, vals.length - 1)) * (W - 12);
      const y = (v) => 6 + ((yMax - v) / (yMax - yMin)) * (H - 12);
      ctx.beginPath();
      vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
      ctx.lineTo(x(vals.length - 1), H - 6);
      ctx.lineTo(x(0), H - 6);
      ctx.closePath();
      ctx.fillStyle = this.properties.color + "18";
      ctx.fill();
      ctx.beginPath();
      vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
      ctx.strokeStyle = this.properties.color;
      ctx.lineWidth = 1.5;
      ctx.lineJoin = "round";
      ctx.stroke();
    },
  },
});
