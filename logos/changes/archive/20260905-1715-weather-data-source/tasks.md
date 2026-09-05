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
（单批闭环，已提交。）

- [x] `app/weather.py`（新增）：WeatherProvider 抽象 + OpenMeteoProvider（geocoding+forecast 两段，超时 5 秒静默降级）+ 城市级 6 小时缓存 + `WEATHER_BASE_URL` 未配置时能力整体静默
- [x] `app/config.py`：WEATHER_BASE_URL 环境变量（空 = 静默）
- [x] `app/proposals.py`：`_bounded_context` 注入天气事实（仅当用户声明 location 偏好）；不写 evidence
- [x] `app/schemas.py` + `app/models.py`：PreferenceKey 扩 `location`
- [x] 测试：UT-S03-49~53 + ST-S03-24（6 个，`tests/test_s03_weather.py`），FakeWeather fixed-value 注入
- [x] 全量回归 364 passed / 2 skipped / 0 failed
- [x] 实现修正（一处，影响 S10 既有代码）：`refresh_preference_digests` 在 run_tick 主事务内嵌套开写事务导致 `database is locked`（weather 测试暴露）——已将两个低频任务移出主事务、digest 函数自管事务

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging（配置 WEATHER_BASE_URL；无数据库迁移）
- [ ] 确认天气 API 探针可达（失败仅告警）、未声明城市时能力静默，应用回滚点可用
