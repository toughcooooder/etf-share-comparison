const $ = (id) => document.getElementById(id);
const iconPaths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  layers: '<path d="m3 7 9-5 9 5-9 5zM3 12l9 5 9-5M3 17l9 5 9-5"/>',
  list: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 9v11m3-7h6m-6 3h5"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v13c0 4 16 4 16 0V5M4 11c0 4 16 4 16 0"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
  stack: '<path d="m3 9 9-5 9 5-9 5zM3 13l9 5 9-5M3 17l9 5 9-5"/>',
  pulse: '<path d="M2 13h5l3-8 4 14 3-8h5"/>',
  trophy: '<path d="M7 3h10v5c0 5-2 8-5 8s-5-3-5-8zM7 5H3c0 5 1 7 5 7m9-7h4c0 5-1 7-5 7m-4 4v4m-4 1h8"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  sliders: '<path d="M3 7h8m4 0h6M3 17h3m4 0h11"/><circle cx="13" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  bars: '<path d="M4 20V12m5 8V8m5 12V4m5 16v-9"/>',
  upRight: '<path d="m4 17 6-6 4 3 6-9m-6 0h6v6"/>',
  downRight: '<path d="m4 7 6 6 4-3 6 9m-6 0h6v-6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  x: '<path d="m6 6 12 12M18 6 6 18"/>'
};
document.querySelectorAll("[data-icon]").forEach(host => {
  host.outerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${iconPaths[host.dataset.icon]}</svg>`;
});

const colors = {
  "588000": "#c5f277", "510300": "#a998ff", "159915": "#65d5cf", "512100": "#ffb380",
  "560010": "#82b6ff", "512500": "#f3cf68", "510180": "#e89fea", "159919": "#7ad0a0",
  "159845": "#fb8b9e", "159629": "#9ca9e6", "159977": "#54b8de", "510330": "#ff9190",
  "510050": "#d1bb77", "510310": "#e4a2bf", "588080": "#7eb9aa", "510500": "#a1bdff"
};
const colorOf = fund => colors[fund.code] || fund.color;
const numbers = new Intl.NumberFormat("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt = value => numbers.format(value);
const signed = value => (value > 0 ? "+" : "") + fmt(value);
const signClass = value => value > 0 ? "positive" : value < 0 ? "negative" : "";
const market = fund => fund.exchange === "SSE" ? "沪市" : "深市";
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const totalOf = (items, metric) => items.reduce((total, item) => total + metric(item), 0);
const groups = [...new Set(FUNDS.map(fund => fund.group))].sort((a,b) => a.localeCompare(b, "zh-CN"));
const defaultCodes = ["588000", "510300", "159915"];
const state = {
  selected: new Set(defaultCodes.filter(code => FUNDS.some(fund => fund.code === code))),
  mode: "absolute", range: "1y", ranking: "up", group: groups.includes("沪深300") ? "沪深300" : groups[0]
};
function metrics(fund) {
  const first = fund.data[0], last = fund.data.at(-1), previous = fund.data.at(-2) || first;
  const daily = last.v - previous.v;
  return { first, last, previous, daily,
    dailyPct: previous.v ? daily / previous.v * 100 : null,
    changePct: first.v ? (last.v / first.v - 1) * 100 : null,
    peak: fund.data.reduce((best, row) => row.v > best.v ? row : best)
  };
}
const stats = new Map(FUNDS.map(fund => [fund.code, metrics(fund)]));
const fundsByCode = new Map(FUNDS.map(fund => [fund.code, fund]));
const pct = value => value == null ? "—" : signed(value) + "%";
const times = new Map();
function dateMs(day) {
  if (!times.has(day)) times.set(day, Date.parse(day + "T00:00:00Z"));
  return times.get(day);
}
function datesBack(range) {
  if (range === "all") return "";
  const date = new Date(dateMs(REPORT_END));
  date.setUTCFullYear(date.getUTCFullYear() - parseInt(range, 10));
  return date.toISOString().slice(0, 10);
}
function press(selector, key, value) {
  document.querySelectorAll(selector).forEach(button => button.setAttribute("aria-pressed", String(button.dataset[key] === value)));
}
function spark(values, color, bars = false) {
  if (!values.length) return "";
  const width = 88, height = 24;
  const lo = Math.min(...values, ...(bars ? [0] : [])), hi = Math.max(...values, ...(bars ? [0] : []));
  const y = v => height - 2 - (v-lo) / (hi-lo || 1) * (height-4);
  let marks;
  if (bars) {
    const step = width / values.length;
    marks = values.map((v,i) => `<rect x="${(i*step).toFixed(1)}" y="${Math.min(y(v),y(0)).toFixed(1)}" width="${Math.max(1,step-1)}" height="${Math.max(1,Math.abs(y(v)-y(0))).toFixed(1)}" fill="${v>=0?"#ff9689":"#68d9b2"}" opacity=".8"/>`).join("");
  } else {
    const points = values.map((v,i) => `${(1+i*(width-2)/Math.max(1,values.length-1)).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    marks = `<polygon points="1,${height} ${points} ${width-1},${height}" fill="${color}" opacity=".06"/><polyline points="${points}" stroke="${color}" fill="none" stroke-width="1.55" stroke-linejoin="round" stroke-linecap="round"/>`;
  }
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">${marks}</svg>`;
}
// Sum only available records. A complete-date series is used for the market miniatures.
function aggregate(funds, end, completeOnly = false) {
  const days = new Map();
  funds.forEach(fund => fund.data.forEach(row => {
    if (row.d > end) return;
    const current = days.get(row.d) || {d: row.d, v: 0, count: 0};
    current.v += row.v;
    current.count++;
    days.set(row.d, current);
  }));
  return [...days.values()].filter(row => !completeOnly || row.count === funds.length).sort((a,b) => a.d.localeCompare(b.d));
}
function renderKpis() {
  const all = [...stats.values()];
  const total = totalOf(all, m => m.last.v), daily = totalOf(all, m => m.daily);
  const largest = FUNDS.reduce((a,b) => stats.get(a.code).last.v > stats.get(b.code).last.v ? a : b);
  const sse = FUNDS.filter(fund => fund.exchange === "SSE").length;
  $("latestTotal").textContent = fmt(total);
  $("totalMeta").textContent = "各基金最新有效份额合计";
  $("latestDailyChange").textContent = signed(daily);
  $("latestDailyChange").className = signClass(daily);
  $("dailyMeta").innerHTML = `较上次合计 <em class="${signClass(daily)}">${pct(total-daily ? daily/(total-daily)*100 : null)}</em>`;
  $("fundCount").textContent = FUNDS.length;
  $("exchangeCounts").textContent = `沪市 ${sse} 只 · 深市 ${FUNDS.length-sse} 只`;
  $("exchangeBars").innerHTML = FUNDS.map((_,i) => `<i class="${i<sse?"":"sz"}"></i>`).join("");
  $("largestValue").textContent = fmt(stats.get(largest.code).last.v);
  $("largestFundMeta").textContent = largest.name;
  const totals = aggregate(FUNDS, REPORT_END, true).slice(-61);
  $("totalSpark").innerHTML = spark(totals.map(row=>row.v), "#c5f277");
  $("dailySpark").innerHTML = spark(totals.slice(1).map((row,i)=>row.v-totals[i].v).slice(-18), "", true);
  $("largestSpark").innerHTML = spark(largest.data.slice(-60).map(row=>row.v), "#ac9bff");
}

function itemSeries(fund, rows = fund.data) { return {name: fund.name, color: colorOf(fund), rows}; }
function renderLegend(id, series) {
  $(id).innerHTML = series.map(s => `<span class="legend-item"><i class="dot" style="--dot:${s.color}"></i>${escapeHtml(s.name)}</span>`).join("");
}
const charts = new Map();
function niceStep(rough) {
  const unit = 10 ** Math.floor(Math.log10(rough || 1));
  return ([1, 2, 2.5, 5, 10].find(n => n * unit >= rough) || 10) * unit;
}
function nearestIndex(days, target) {
  let low = 0, high = days.length-1;
  while (low < high) {
    const mid = (low+high) >> 1;
    if (dateMs(days[mid]) < target) low = mid+1;
    else high = mid;
  }
  if (low && Math.abs(dateMs(days[low-1])-target) < Math.abs(dateMs(days[low])-target)) return low-1;
  return low;
}
function prepareChart(id, series, indexed = false) {
  const canvas = $(id);
  const lines = series.filter(s => s.rows.length).map(s => {
    const base = s.rows[0].v;
    const rows = s.rows.map((row,i) => ({
      d: row.d, t: dateMs(row.d), raw: row.v, v: indexed && base ? row.v/base*100 : row.v,
      delta: i ? row.v-s.rows[i-1].v : null
    }));
    return {...s, rows, byDay: new Map(rows.map(row=>[row.d,row]))};
  });
  const days = [...new Set(lines.flatMap(line=>line.rows.map(row=>row.d)))].sort();
  const model = {lines, days, indexed, hover: null};
  charts.set(id, model);
  const empty = canvas.parentElement.querySelector(".chart-empty");
  if (empty) empty.hidden = lines.length > 0;
  const tip = canvas.parentElement.querySelector(".chart-tip");
  if (tip) tip.hidden = true;
  paintChart(canvas, model);
}
function paintChart(canvas, model) {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(w*dpr) || canvas.height !== Math.round(h*dpr)) {
    canvas.width = Math.round(w*dpr);
    canvas.height = Math.round(h*dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,w,h);
  if (!model.lines.length) return;
  const left = w < 390 ? 36 : 43, right = w-8, top = 10, bottom = h-27;
  const first = dateMs(model.days[0]), last = dateMs(model.days.at(-1));
  if (model.min == null) {
    let min = Infinity, max = -Infinity;
    model.lines.forEach(s => s.rows.forEach(row => {min = Math.min(min,row.v); max = Math.max(max,row.v);}));
    model.min = min;
    model.max = max;
  }
  const step = niceStep(Math.max(model.max-model.min, model.max*.05, 1)/4.8);
  const ymin = Math.max(0, Math.floor(model.min/step)*step);
  const ymax = Math.max(ymin+step, Math.ceil((model.max || 1)/step)*step);
  const x = time => left+(time-first)/(last-first || 1)*(right-left);
  const y = value => bottom-(value-ymin)/(ymax-ymin)*(bottom-top);
  model.plot = {left,right,first,last};
  ctx.font = '11px Consolas, monospace';
  ctx.lineWidth = 1;
  ctx.textBaseline = "middle";
  ctx.textAlign = "right";
  for (let value=ymin; value<=ymax+step*.01; value+=step) {
    const py = y(value);
    ctx.setLineDash([3,4]); ctx.strokeStyle = "#343b43";
    ctx.beginPath(); ctx.moveTo(left,py); ctx.lineTo(right,py); ctx.stroke();
    ctx.fillStyle = "#929eac";
    ctx.fillText(value.toLocaleString("en-US",{maximumFractionDigits:2}),left-8,py);
  }
  const ticks = w < 400 ? 4 : w < 760 ? 6 : 8;
  const fullYear = last-first > 5*365.25*86400000;
  for (let i=0;i<ticks;i++) {
    const ratio = i/(ticks-1), t = first + ratio*(last-first), px = left+ratio*(right-left);
    ctx.beginPath(); ctx.strokeStyle = "#2a3036"; ctx.moveTo(px,top); ctx.lineTo(px,bottom); ctx.stroke();
    ctx.textAlign = i===0 ? "left" : i===ticks-1 ? "right" : "center";
    ctx.fillStyle = "#929eac";
    ctx.fillText(new Date(t).toISOString().slice(0,fullYear?4:7).replace("-","."),px,h-9);
  }
  ctx.setLineDash([]);
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  model.lines.forEach((line,i) => {
    const path = new Path2D();
    line.rows.forEach((row,j) => j ? path.lineTo(x(row.t),y(row.v)) : path.moveTo(x(row.t),y(row.v)));
    if (i === 0) {
      const area = new Path2D(path);
      area.lineTo(x(line.rows.at(-1).t),bottom); area.lineTo(x(line.rows[0].t),bottom); area.closePath();
      const fade = ctx.createLinearGradient(0,top,0,bottom);
      fade.addColorStop(0,line.color+"26"); fade.addColorStop(1,line.color+"01");
      ctx.fillStyle = fade; ctx.fill(area);
    }
    ctx.strokeStyle = line.color;
    ctx.lineWidth = model.lines.length > 6 ? 1.35 : i === 0 ? 2.4 : 1.95;
    ctx.stroke(path);
    const end = line.rows.at(-1);
    ctx.beginPath(); ctx.arc(x(end.t),y(end.v),2.7,0,Math.PI*2); ctx.fillStyle = line.color; ctx.fill();
  });
  if (model.hover != null) {
    const day = model.days[model.hover], px = x(dateMs(day));
    ctx.setLineDash([3,4]); ctx.strokeStyle = "#8a95a0"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(px,top); ctx.lineTo(px,bottom); ctx.stroke(); ctx.setLineDash([]);
    model.lines.forEach(line => {
      const row = line.byDay.get(day);
      if (!row) return;
      ctx.beginPath(); ctx.arc(px,y(row.v),3.4,0,Math.PI*2); ctx.fillStyle = line.color; ctx.fill();
    });
  }
}
function wireChart(canvas) {
  canvas.tabIndex = 0;
  const tip = document.createElement("div");
  tip.className = "chart-tip"; tip.hidden = true;
  canvas.parentElement.append(tip);
  function hide() {
    const model = charts.get(canvas.id);
    tip.hidden = true;
    if (model && model.hover != null) { model.hover = null; paintChart(canvas,model); }
  }
  function inspect(model, index) {
    if (model.hover === index && !tip.hidden) return;
    model.hover = index;
    paintChart(canvas,model);
    const day = model.days[index];
    const entries = model.lines.filter(line=>line.byDay.has(day));
    tip.innerHTML = `<strong>${day}</strong>` + entries.slice(0,7).map(line => {
      const row = line.byDay.get(day);
      const change = !model.indexed && row.delta != null ? ` <span class="${signClass(row.delta)}">(${signed(row.delta)})</span>` : "";
      return `<div class="tip-row"><i class="dot" style="--dot:${line.color}"></i>${escapeHtml(line.name)}<b>${fmt(row.v)}${change}</b></div>`;
    }).join("") + (entries.length>7 ? `<small>另有 ${entries.length-7} 只基金</small>` : "");
    tip.hidden = false;
    const {left,right,first,last} = model.plot;
    const px = left+(dateMs(day)-first)/(last-first || 1)*(right-left);
    tip.style.left = Math.max(3,Math.min(canvas.clientWidth-tip.offsetWidth-3,px>canvas.clientWidth/2 ? px-tip.offsetWidth-9 : px+9))+"px";
    tip.style.top = "8px";
  }
  function inspectPointer(event) {
    const model = charts.get(canvas.id);
    if (!model?.plot) return;
    const px = event.clientX-canvas.getBoundingClientRect().left;
    const {left,right,first,last} = model.plot;
    if (px<left || px>right) { hide(); return; }
    inspect(model,nearestIndex(model.days,first+(px-left)/(right-left)*(last-first)));
  }
  canvas.addEventListener("pointermove",inspectPointer);
  canvas.addEventListener("pointerdown",inspectPointer);
  canvas.addEventListener("pointerleave",event=>{ if (event.pointerType !== "touch") hide(); });
  document.addEventListener("pointerdown",event=>{ if (event.target !== canvas) hide(); });
  canvas.addEventListener("pointercancel",hide);
  canvas.addEventListener("blur",hide);
  canvas.addEventListener("keydown",event=>{
    const model = charts.get(canvas.id);
    if (!model?.days.length) return;
    if (event.key === "Escape") hide();
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const at = model.hover ?? model.days.length-1;
    inspect(model,Math.max(0,Math.min(model.days.length-1,at+(event.key==="ArrowLeft"?-1:1))));
  });
  new ResizeObserver(()=>{ const model = charts.get(canvas.id); if (model) { hide(); paintChart(canvas,model); } }).observe(canvas);
}


function renderComparison() {
  const start = datesBack(state.range);
  const series = [...state.selected].map(code=>fundsByCode.get(code)).map(fund => itemSeries(fund,fund.data.filter(row=>row.d>=start)));
  $("trendSub").textContent = state.mode === "indexed" ? "相对走势 · 区间首个有效记录 = 100" : "历史交易日 · 绝对份额（亿份）";
  renderLegend("comparisonLegend",series);
  $("selectedCount").textContent = `已选 ${state.selected.size} / ${FUNDS.length} 只`;
  press("[data-range]","range",state.range);
  press("[data-mode]","mode",state.mode);
  prepareChart("comparisonChart",series,state.mode==="indexed");
}
function renderSelector() {
  $("fundSelector").innerHTML = FUNDS.map(fund => `<label><input type="checkbox" value="${fund.code}" ${state.selected.has(fund.code)?"checked":""}><span><small>${fund.code}</small>${escapeHtml(fund.name)}</span></label>`).join("");
}
function renderRanking() {
  const direction = state.ranking === "up" ? 1 : -1;
  const rows = FUNDS.filter(fund=>direction*stats.get(fund.code).daily>0)
    .sort((a,b)=>direction*(stats.get(b.code).daily-stats.get(a.code).daily)).slice(0,5);
  press("[data-rank]","rank",state.ranking);
  $("rankRows").innerHTML = rows.map((fund,i)=>{
    const value = stats.get(fund.code).daily;
    const share = Math.abs(value/stats.get(rows[0].code).daily)*100;
    return `<li><button class="rank-row" data-detail="${fund.code}"><span class="rank-num">${String(i+1).padStart(2,"0")}</span>
      <span><span class="rank-name">${escapeHtml(fund.name)}</span><span class="rank-code">${fund.code}</span></span>
      <span class="rank-value ${signClass(value)}">${signed(value)}<i style="--pct:${share}%" aria-hidden="true"></i></span></button></li>`;
  }).join("") || '<li class="list-empty">当期暂无此方向的变化</li>';
}
function renderTable() {
  const query = $("fundSearch").value.trim().toLowerCase();
  const group = $("groupFilter").value, order = $("sortSelect").value;
  const funds = FUNDS.filter(fund => (!group || fund.group===group) && (fund.code+fund.name).toLowerCase().includes(query));
  funds.sort((a,b) => {
    if (order === "code") return a.code.localeCompare(b.code);
    const m = stats.get(a.code), n = stats.get(b.code);
    if (order === "daily") return n.daily-m.daily;
    if (order === "change") return (n.changePct ?? -Infinity)-(m.changePct ?? -Infinity);
    return n.last.v-m.last.v;
  });
  $("listCount").textContent = funds.length+" 只";
  $("listEmpty").hidden = funds.length>0;
  $("summaryTable").innerHTML = funds.map(fund => {
    const m = stats.get(fund.code);
    const series = fund.data.slice(-60).map(row=>row.v);
    const trendColor = series.at(-1)>=series[0] ? "#ff9689" : "#68d9b2";
    const sse = fund.exchange==="SSE";
    return `<tr><td><button class="fund-link" data-detail="${fund.code}" title="查看基金详情">
      <span class="exchange-mark ${sse?"":"sz"}" aria-label="${market(fund)}">${sse?"SH":"SZ"}</span>
      <span><span class="fund-name">${escapeHtml(fund.name)}</span><span class="fund-code">${fund.code}</span></span></button></td>
      <td><span class="index-tag">${escapeHtml(fund.group)}</span></td><td>${fmt(m.last.v)}</td>
      <td class="${signClass(m.daily)}">${signed(m.daily)}</td><td class="${signClass(m.daily)}">${pct(m.dailyPct)}</td>
      <td><span class="table-spark" role="img" aria-label="近 ${series.length} 个有效日份额从 ${fmt(series[0])} 至 ${fmt(series.at(-1))} 亿份">${spark(series,trendColor)}</span></td>
      <td class="table-date">${m.last.d}</td></tr>`;
  }).join("");
}
function dataStat(label,value,sub,cls="") {
  return `<div class="data-stat"><small>${label}</small><strong class="${cls}">${escapeHtml(value)}</strong><span>${escapeHtml(sub)}</span></div>`;
}
function showDetail(code) {
  const fund = fundsByCode.get(code);
  if (!fund) return;
  const m = stats.get(code);
  $("detailId").textContent = `${code}　·　${market(fund)}　·　${fund.group}`;
  $("detailTitle").textContent = fund.name;
  $("detailStats").innerHTML = [
    dataStat("最新份额 · 亿份",fmt(m.last.v),m.last.d),
    dataStat("单日变化 · 亿份",signed(m.daily),"较 "+m.previous.d,signClass(m.daily)),
    dataStat("单日变化率",pct(m.dailyPct),"相邻有效记录",signClass(m.daily)),
    dataStat("累计变化率",pct(m.changePct),"自 "+m.first.d,signClass(m.changePct)),
    dataStat("历史峰值 · 亿份",fmt(m.peak.v),m.peak.d),
    dataStat("有效记录",fund.data.length.toLocaleString("zh-CN"),"个交易日")
  ].join("");
  $("detailDates").textContent = `${m.first.d} — ${m.last.d}`;
  $("detailDialog").showModal();
  prepareChart("detailChart",[itemSeries(fund)]);
}
function renderIndex() {
  const funds = FUNDS.filter(fund=>fund.group===state.group);
  const commonEnd = funds.map(fund=>stats.get(fund.code).last.d).sort()[0];
  const totals = aggregate(funds,commonEnd);
  const last = totals.at(-1), previous = totals.at(-2) || last, delta = last.v-previous.v;
  const series = funds.map(fund=>itemSeries(fund,fund.data.filter(row=>row.d<=commonEnd)));
  const latest = series.filter(line=>line.rows.at(-1)?.d===last.d).sort((a,b)=>b.rows.at(-1).v-a.rows.at(-1).v)[0];
  $("indexStats").innerHTML = [
    dataStat("合计份额 · 亿份",fmt(last.v),last.d),
    dataStat("单日变化 · 亿份",signed(delta),"较 "+previous.d,signClass(delta)),
    dataStat("成分基金",String(funds.length)+" 只",state.group),
    dataStat("最大单只 · 亿份",fmt(latest.rows.at(-1).v),latest.name)
  ].join("");
  const totalLine = {name: state.group+"合计",color:"#f4f5e2",rows:totals};
  press("[data-index]","index",state.group);
  renderLegend("indexLegend",[totalLine,...series]);
  prepareChart("indexChart",[totalLine,...series]);
}
function downloadCsv() {
  const days = [...new Set(FUNDS.flatMap(fund=>fund.data.map(row=>row.d)))].sort();
  const maps = FUNDS.map(fund=>new Map(fund.data.map(row=>[row.d,row.v])));
  const csvCell = value => '"'+String(value).replaceAll('"','""')+'"';
  const lines = [["日期",...FUNDS.map(fund=>`${fund.code} ${fund.name}(亿份)`)].map(csvCell).join(",")];
  days.forEach(day=>lines.push([day,...maps.map(map=>map.get(day) ?? "")].join(",")));
  const blob = new Blob(["\ufeff",lines.join("\r\n")],{type:"text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = `${FUNDS.length}只ETF基金份额_${days[0].replaceAll("-","")}_${REPORT_END.replaceAll("-","")}.csv`;
  link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function showPage() {
  const page = ["indices","funds"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  const titles = {
    overview: ["ETF 份额监测","沪深宽基 ETF 的份额走势与申赎动向"],
    indices: ["指数份额分析","按跟踪指数比较成分基金与合计份额"],
    funds: ["基金份额明细","检索基金并查看历史份额、区间峰值与累计变化"]
  };
  [$("pageTitle").textContent,$("pageSubtitle").textContent] = titles[page];
  $("overviewBody").hidden = page !== "overview";
  $("fundPanel").hidden = page === "indices";
  $("indexPanel").hidden = page !== "indices";
  document.querySelectorAll("[data-page]").forEach(link=>{
    if (link.dataset.page===page) link.setAttribute("aria-current","page");
    else link.removeAttribute("aria-current");
  });
  if (page==="indices") renderIndex();
  if (page==="overview") renderComparison();
  window.scrollTo(0,0);
}

document.querySelector(".skip").addEventListener("click",event=>{
  event.preventDefault();
  $("workspace").focus();
});
document.querySelectorAll(".chart-frame canvas").forEach(wireChart);
$("groupFilter").add(new Option("全部指数",""));
groups.forEach(group=>$("groupFilter").add(new Option(group,group)));
$("indexTabs").innerHTML = groups.map(group=>`<button data-index="${escapeHtml(group)}">${escapeHtml(group)}</button>`).join("");
$("groupFilter").addEventListener("change",renderTable);
$("sortSelect").addEventListener("change",renderTable);
$("fundSearch").addEventListener("input",renderTable);
$("downloadCsv").addEventListener("click",downloadCsv);
$("clearSearch").addEventListener("click",()=>{
  $("fundSearch").value = ""; $("groupFilter").value = ""; renderTable(); $("fundSearch").focus();
});
$("pickFunds").addEventListener("click",()=>{ renderSelector(); $("configDialog").showModal(); });
$("fundSelector").addEventListener("change",event=>{
  const input = event.target;
  if (input.checked) state.selected.add(input.value); else state.selected.delete(input.value);
  renderComparison();
});
$("selectAll").addEventListener("click",()=>{ state.selected = new Set(FUNDS.map(fund=>fund.code)); renderSelector(); renderComparison(); });
$("clearAll").addEventListener("click",()=>{ state.selected.clear(); renderSelector(); renderComparison(); });
$("showSources").addEventListener("click",()=>$("sourceDialog").showModal());
$("footerSources").addEventListener("click",()=>$("sourceDialog").showModal());
document.querySelectorAll("dialog").forEach(dialog=>{
  dialog.querySelectorAll(".close").forEach(button=>button.addEventListener("click",()=>dialog.close()));
  dialog.addEventListener("click",event=>{
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX<box.left || event.clientX>box.right || event.clientY<box.top || event.clientY>box.bottom) dialog.close();
  });
});
document.addEventListener("click",event=>{
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.range) { state.range = button.dataset.range; renderComparison(); }
  if (button.dataset.mode) { state.mode = button.dataset.mode; renderComparison(); }
  if (button.dataset.rank) { state.ranking = button.dataset.rank; renderRanking(); }
  if (button.dataset.detail) showDetail(button.dataset.detail);
  if (button.dataset.index) { state.group = button.dataset.index; renderIndex(); }
});
window.addEventListener("hashchange",showPage);
renderKpis();
renderTable();
renderRanking();
showPage();
