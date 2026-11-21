// 小程序运行配置
// 1) 在微信公众平台拿到 AppID，在开发者工具里开通「云开发」，得到环境 ID；
// 2) 把环境 ID 填到下面的 CLOUD_ENV，并把 USE_CLOUD 设为 true；
// 3) 若暂时不接云端，保持 USE_CLOUD=true 但 CLOUD_ENV 留空，会自动回退到内置示例数据。
module.exports = {
  // 云开发环境 ID（留空则使用内置示例）
  CLOUD_ENV: "",
  // 是否优先从云函数拉取实时数据
  USE_CLOUD: true,
  // 云函数名称（见 cloudfunctions/getSummary）
  CLOUD_FUNC: "getSummary",
  // 云存储中汇总 JSON 的前缀
  STORAGE_PREFIX: "etf_share/",
};
