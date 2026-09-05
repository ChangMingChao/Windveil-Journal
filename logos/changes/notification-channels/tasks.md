# 实现任务

## [delta] 规格变更
- [x] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` — 新增 S10 场景与 3 条验收条件、5.1 静默通道细化、追溯表更新
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — 场景映射加 S10、P6 描述细化、追溯表加行
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-07-notification-channels-design.md` — 新增 P6 提醒通道区交互规格全文
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-S10-channels.md` — 新增 S10 场景时序图
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 投递通道选择逻辑与场景清单加 S10
- [x] 产出 delta 到 `deltas/api/auth.yaml` — 新增 `PATCH /me/notification-channels` 与 UserProfile 扩展字段
- [x] 产出 delta 到 `deltas/test/core-S10-test-cases.md` — 新增 S10 测试用例
- [x] 产出 delta 到 `deltas/scenario/core-S10-channels.json` — 新增 S10 编排文件
- [x] 产出 delta 到 `deltas/scenario/core-00-orchestration-index.json` — 登记 S10 并更新 coverage，OQ-3 标记 fully_resolved
- [x] 验证 `logos/resources/api/` 下所有 YAML 有效且符合 OpenAPI 3.x

## [code] 代码实现
（本段在 plan 阶段留空：需要实现通道开关端点与投递通道选择逻辑、P6 前端开关区、测试与 OpenLogos reporter；具体切片由 merge 后的 slice-planner 基于已合并规格与真实 UT/ST ID 规划。）

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging（无数据库迁移）
- [ ] 确认投递通道选择逻辑在开关组合下的行为（push 关走邮件 / 全关顺延），应用回滚点可用
