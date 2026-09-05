# delta — core-01-deployment-plan.md（weather-data-source）

## ADDED — 五·增补：本次变更（weather-data-source）的部署说明

| 项 | 内容 |
|----|------|
| 新增表 | 无。位置偏好走既有 `user_preferences` 表（pref_key='location'） |
| 新增环境变量 | `WEATHER_BASE_URL`（Open-Meteo 兼容端点，默认官方地址；探针失败仅告警不阻断——部署后检查第 10 项既有约定） |
| 降级 | 供应商不可用 / 超时 5 秒 / 用户未声明城市 → 天气能力整体静默；回滚镜像即移除 Provider，双向安全 |
| smoke | 不新增。外部依赖探针沿用 §7-10；天气事实注入属 ST 层 |
