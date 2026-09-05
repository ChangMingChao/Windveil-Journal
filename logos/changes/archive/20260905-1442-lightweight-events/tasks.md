# 实现任务

## [delta] 规格变更
- [x] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` — 新增 S09 场景与 4 条验收条件、5.3「不做」清单修订、5.1 轻事件边界、追溯表更新
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — 场景映射加 S09、P1 页面描述更新、追溯表加行
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-01-seeding-design.md` — P1「先记一下」次级入口与轻事件区交互
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-06-lite-events-design.md` — 新增 S09 交互规格全文
- [x] 产出 delta 到 `deltas/prd/2-product-design/2-page-design/core-06-lite-events-prototype.html` — P1 入口与轻事件列表原型
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 轻事件组件职责、「结构上无提醒路径」说明、场景清单加 S09
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-S09-lite-events.md` — 新增 S09 场景时序图
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-00-scenario-overview.md` — 场景地图加 S09
- [x] 产出 delta 到 `deltas/api/lite-events.yaml` — 新增 lite-events API 规格（4 端点）
- [x] 产出 delta 到 `deltas/database/schema.sql` — 新增 `lite_events` 表与索引
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 迁移 0009 与 smoke 清单更新
- [x] 产出 delta 到 `deltas/test/core-S09-test-cases.md` — 新增 S09 测试用例
- [x] 产出 delta 到 `deltas/test/smoke/core-smoke-test-cases.md` — SMOKE-core-21（先记一下链路）
- [x] 产出 delta 到 `deltas/scenario/core-S09-lite-events.json` — 新增 S09 编排文件
- [x] 产出 delta 到 `deltas/scenario/core-00-orchestration-index.json` — 登记 S09 并更新 coverage
- [x] 验证 `logos/resources/api/` 下所有 YAML 有效且符合 OpenAPI 3.x

## [code] 代码实现
（单批闭环，已提交。）

- [x] `app/models.py`：LiteEvent（open/done 两态 + closed 配对 CHECK）；迁移 `0009_lightweight_events.py`（exec_driver_sql 逐条，含部分索引）
- [x] `app/lite_events.py`（新增）：create（strip + 1–200 校验）/ list（默认 open）/ mark_done（409 幂等保护）/ delete（硬删）——模块内无任何提醒相关分支
- [x] `app/api.py`：4 端点（tag: lite-events）；`app/schemas.py`：LiteEventCreate/Out/ListResponse
- [x] `db.py` 守卫清单 + conftest MIGRATIONS 加 0009
- [x] 前端：`components/LiteEvents.tsx`（P1 展开区：记录/划掉/收走/空态，无计数）+ `Welcome.tsx` 挂载 + `api/types.ts` LiteEvent
- [x] smoke：SMOKE-core-21（先记一下链路 + outbox 无轻事件行断言）；表数量断言 20→21、索引 36→37
- [x] 测试：UT-S09-01~12 + ST-S09-01~04（16 个），全量回归 340 passed / 2 skipped / 0 failed

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging
- [ ] 确认迁移前已备份数据库，lite_events 迁移向后兼容，服务启动与回滚点可用
