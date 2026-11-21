// 数据获取：优先云函数 getSummary，失败/未配置则回退内置示例
const cfg = require("./config");
const sample = require("./sampleData");

function getSummary() {
  return new Promise((resolve) => {
    if (!cfg.USE_CLOUD || !cfg.CLOUD_ENV) {
      return resolve({ ...sample, _source: "sample" });
    }
    if (!wx.cloud) {
      return resolve({ ...sample, _source: "sample" });
    }
    wx.cloud
      .callFunction({ name: cfg.CLOUD_FUNC })
      .then((res) => {
        const r = res && res.result;
        if (r && Array.isArray(r.funds) && r.funds.length) {
          resolve({ ...r, _source: "cloud" });
        } else {
          console.warn("云函数返回为空，回退示例数据");
          resolve({ ...sample, _source: "sample" });
        }
      })
      .catch((err) => {
        console.warn("云函数调用失败，回退示例数据", err);
        resolve({ ...sample, _source: "sample" });
      });
  });
}

module.exports = { getSummary };
