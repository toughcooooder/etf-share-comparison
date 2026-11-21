Page({
  data: {
    steps: [
      "在微信公众平台注册并拿到小程序 AppID（个人或企业均可）。",
      "用微信开发者工具打开本工程，顶部「云开发」→ 开通环境，记录环境 ID。",
      "把环境 ID 填入 utils/config.js 的 CLOUD_ENV，并将 USE_CLOUD 设为 true。",
      "右键 cloudfunctions/getSummary → 上传并部署（云端安装依赖）。",
      "运行 scripts/export_summary_json.py 生成 etf_share_summary.json，再用 deploy_to_cloud.js 上传到云存储 etf_share/ 目录。",
      "（可选）把导出+上传两步加进你原来的每日定时任务，实现自动更新。",
    ],
    sse: "https://www.sse.com.cn/assortment/fund/etf/list/scale/",
    szse: "https://www.szse.cn/market/fund/volume/etf/index.html",
  },
  copy(e) {
    const key = e.currentTarget.dataset.key;
    wx.setClipboardData({ data: this.data[key] });
  },
});
