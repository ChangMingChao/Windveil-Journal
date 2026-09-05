# 实现任务

## [delta] 规格变更
- [ ] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` — 5.1 数据源边界更新与 5.3 条目修订
- [ ] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-06-lite-events-design.md` — 不改（确认无涉，跳过说明）；改为 `deltas/prd/2-product-design/1-feature-specs/core-05-preferences-availability-design.md` — 「所在城市」偏好主题
- [ ] 产出 delta 到 `deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — WeatherProvider 抽象（第七节 + 5.8 节）
- [ ] 产出 delta 到 `deltas/test/core-S03-test-cases.md` — 天气事实 UT 与建议理由 ST
- [ ] 产出 delta 到 `deltas/scenario/core-S03-timing.json` — mock 控制面扩展
- [ ] 产出 delta 到 `deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — WEATHER_BASE_URL 与探针说明
- [ ] 验证 `logos/resources/api/` 下所有 YAML 有效且符合 OpenAPI 3.x

## [code] 代码实现
（本段在 plan 阶段留空：需要实现 WeatherProvider 抽象与 Open-Meteo 兼容实现、提议上下文天气注入、测试与 OpenLogos reporter；具体切片由 merge 后的 slice-planner 基于已合并规格与真实 UT/ST ID 规划。）

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging（配置 WEATHER_BASE_URL；无数据库迁移）
- [ ] 确认天气 API 探针可达（失败仅告警）、未声明城市时能力静默，应用回滚点可用
