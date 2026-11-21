#!/usr/bin/env node
/**
 * 把本地生成的 etf_share_summary.json 上传到微信云开发存储 etf_share/ 目录。
 *
 * 前置：
 *   1) npm i -g @cloudbase/cli
 *   2) tcb login            （浏览器授权一次）
 *   3) 在小程序后台记录云开发环境 ID，通过环境变量传入：
 *      set CLOUD_ENV=你的环境ID   (Windows)
 *      export CLOUD_ENV=你的环境ID (mac/Linux)
 *
 * 用法：
 *   node deploy_to_cloud.js [本地summary.json路径]
 *   不传路径时，默认读取原定时任务输出目录里的 etf_share_summary.json。
 */
const { execSync } = require("child_process");
const path = require("path");

const ENV = process.env.CLOUD_ENV || "";
if (!ENV) {
  console.error("请先设置环境变量 CLOUD_ENV 为你的云开发环境 ID，例如：");
  console.error("  set CLOUD_ENV=xxx-env-id");
  process.exit(1);
}

const defaultPath = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "output",
  "etf_share_comparison_16",
  "etf_share_summary.json"
);
const local = process.argv[2] || defaultPath;

if (!require("fs").existsSync(local)) {
  console.error(`未找到本地文件：${local}`);
  console.error("请先运行 scripts/export_summary_json.py 生成 etf_share_summary.json");
  process.exit(1);
}

const cloudPath = "etf_share/summary.json";
const cmd = `npx -y @cloudbase/cli storage upload "${local}" "${cloudPath}" -e ${ENV}`;

console.log(`上传 ${local} -> 云存储 ${cloudPath} (env=${ENV})`);
try {
  execSync(cmd, { stdio: "inherit" });
  console.log("上传完成。小程序端的 getSummary 云函数现在可读取最新数据。");
} catch (e) {
  console.error("上传失败，请确认已执行 tcb login 且环境 ID 正确。");
  console.error("也可在微信开发者工具「云开发 → 存储」里手动上传该 JSON 到 etf_share/ 目录。");
  process.exit(1);
}
