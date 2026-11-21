// 云函数 getSummary：从云存储读取 etf_share/summary.json 并返回给小程序
const cloud = require("wx-server-sdk");
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

exports.main = async () => {
  const PREFIX = "etf_share/";
  try {
    const list = await cloud.storage().list({ prefix: PREFIX });
    const files = (list && list.files) || [];
    if (!files.length) {
      return { funds: [], reportEnd: "", generatedAt: "", _empty: true };
    }
    // 优先取 summary*.json，否则取目录下第一个 json
    const target =
      files.find((f) => /summary.*\.json$/i.test(f.fileID)) ||
      files.find((f) => /\.json$/i.test(f.fileID)) ||
      files[0];

    const dl = await cloud.downloadFile({ fileID: target.fileID });
    const text = dl.fileContent.toString("utf8");
    const data = JSON.parse(text);
    return {
      funds: Array.isArray(data.funds) ? data.funds : [],
      reportEnd: data.reportEnd || "",
      generatedAt: data.generatedAt || "",
    };
  } catch (e) {
    console.error("getSummary failed", e);
    return { funds: [], reportEnd: "", generatedAt: "", _error: String(e) };
  }
};
