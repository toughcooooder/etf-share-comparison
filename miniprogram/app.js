const cfg = require("./utils/config");

App({
  globalData: {
    env: cfg.CLOUD_ENV,
    useCloud: cfg.USE_CLOUD && !!cfg.CLOUD_ENV,
    summary: null, // 首次拉取后缓存，detail 页复用
  },
  onLaunch() {
    if (cfg.USE_CLOUD && cfg.CLOUD_ENV) {
      try {
        if (wx.cloud) {
          wx.cloud.init({ env: cfg.CLOUD_ENV, traceUser: true });
        }
      } catch (e) {
        console.warn("cloud init failed", e);
      }
    }
  },
});
