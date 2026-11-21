// 数字 / 单位格式化（与 HTML 报告口径一致：份额单位「亿份」）
function fmtNum(v, digits = 2) {
  if (v == null || isNaN(v)) return "--";
  return Number(v).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
function fmtYi(v, digits = 2) {
  return `${fmtNum(v, digits)} 亿份`;
}
function signedYi(v) {
  if (v == null || isNaN(v)) return "--";
  return `${v > 0 ? "+" : ""}${fmtNum(v, 2)} 亿份`;
}
function signedPct(v) {
  if (v == null || isNaN(v)) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}
function shortDate(d) {
  return String(d).replace(/-/g, ".");
}
function exchangeLabel(ex) {
  return ex === "SSE" ? "沪市" : "深市";
}
function clsOf(v) {
  if (v > 0) return "pos";
  if (v < 0) return "neg";
  return "";
}
module.exports = { fmtNum, fmtYi, signedYi, signedPct, shortDate, exchangeLabel, clsOf };
