# 实现任务

## [delta] 规格变更
- [x] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` — 增加偏好、可用时段、TimingProposal 的范围、隐私边界与验收条件
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — 增加设置入口与时机提议确认态
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` — 增加提议卡片、确认/拒绝/过期交互
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-05-preferences-availability-design.md` — **（执行中补充）** S08 交互规格全文：proposal 原变更范围只改 core-00/core-02，但 P6「它记得我什么」管理区需要独立设计文档承载，与 core-05 原型同名配对
- [x] 产出 delta 到 `deltas/prd/2-product-design/2-page-design/core-05-preferences-availability-prototype.html` — 产出偏好设置与时机提议确认原型（5 屏）
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 增加模型提议、规则校验、用户确认、调度执行的边界与隐私分层
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md` — 增加 TimingProposal 确认分支时序图（P1–P16 / EX-P.1–P.5）
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-S08-preferences-availability.md` — 新增偏好与可用时段场景时序图（25 Steps + 摘要支线 D1–D4 / 6 EX）
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 增加三张新表的迁移、备份、回滚与 smoke 说明
- [x] 产出 delta 到 `deltas/api/auth.yaml` — 增加偏好与可用时段 API 契约
- [x] 产出 delta 到 `deltas/api/wishes.yaml` — 增加 TimingProposal API 契约与结构化字段
- [x] 验证 `logos/resources/api/` 下所有 YAML 有效且符合 OpenAPI 3.x — 5 个文件全部解析通过（auth 7 / media 2 / memories 4 / system 5 / wishes 15 paths）
- [x] 产出 delta 到 `deltas/database/schema.sql` — 新增三张表及 owner、加密、状态约束；已在内存 SQLite 实测：DDL 可执行，declared_is_certain、digest_never_revoked、availability_windows_ordered、decided_state_pairing、timing_type 枚举 CHECK 与 idx_timing_proposals_single_pending 部分唯一索引全部生效
- [x] 产出 delta 到 `deltas/test/core-S03-test-cases.md` — 增加提议校验、确认、拒绝、过期与调度隔离用例（UT-S03-29~40 / ST-S03-16~21）
- [x] 产出 delta 到 `deltas/test/core-S08-test-cases.md` — 新增偏好与可用时段 UT/ST 用例（UT-S08-01~20 / ST-S08-01~08，含 2 个 [manual]）
- [x] 产出 delta 到 `deltas/test/smoke/core-smoke-test-cases.md` — 增加设置基础链路 smoke 用例（SMOKE-core-19/20；SMOKE-core-07 表数量 17→20）
- [x] 产出 delta 到 `deltas/scenario/core-S03-timing.json` — 增加提议确认编排 flow（6 个：ST-S03-16~21）+ LLM mock 控制面扩展
- [x] 产出 delta 到 `deltas/scenario/core-S08-preferences-availability.json` — 新增 S08 编排 flow（4 个：ST-S08-01/04/05/06；ST-S08-02/03 依赖 inferred 行 fixture 留 code-level，已在 not_orchestrated 说明）
- [x] 产出 delta 到 `deltas/scenario/core-00-orchestration-index.json` — 登记 S08 并更新统计（files/coverage/mock 契约/OQ-3 部分关闭）；**（执行中补充）** 采用整文件新版本形态，与归档 delta 惯例一致

执行中的两处范围修正（均已落 delta，merge 时一并生效）：
1. 新增 `core-05-preferences-availability-design.md`（proposal 变更范围的遗漏，IA 引用它，不能悬空）。
2. S08 编排为 4 个 flow 而非原计划的 5 个：撤回联动（ST-S08-03）与声明推断并列（ST-S08-02）依赖 inferred 行 DB fixture，编排环境为纯 API 无此能力；同源联动「删除时段 → 建议失效」已由 ST-S03-18 以纯 API 路径覆盖。coverage 数字已按 105/78/14/13 自洽。

## [code] 代码实现
（原留空说明见 implementation-manifest.md「preferences-availability-timing 增量交付」一节；三批全部闭环，已提交。）

- [x] **Batch 8**：迁移 0008 + 三张新表模型 + `app/preferences.py` + 8 个偏好/时段端点 + UT-S08-01~16/18、ST-S08-01/04/05（20 测试全绿）
- [x] **Batch 9**：`app/proposals.py` 四层链路 + `app/agent.py` 两个新 Provider 方法 + 3 个提议端点 + WishDetail.timing_proposal 装配 + scheduler 低频任务（过期扫描/每日摘要）+ UT-S03-29~40、ST-S03-16~21、UT-S08-17/19/20、ST-S08-02/03/06（23 测试全绿）
- [x] **Batch 10**：`scripts/smoke-core.py` 扩至 20 项（SMOKE-core-19/20 + 表数量 20/36）+ 前端 Me.tsx「它记得我什么」+ WishDetail 建议确认卡 + /me 路由（构建 + 7 vitest 通过）
- [x] 全量回归：pytest 313 passed / 2 skipped / 0 failed；test-results.jsonl 304 个唯一 ID（303 pass / 1 skip / 0 fail）

实现中发现并修正的三处规格问题（详见 implementation-manifest）：
1. `user_preferences` 唯一索引与「声明不覆盖推断」冲突 → 索引加入 `source` 列（schema/迁移/模型/测试文档四处同步）。
2. auth.yaml「响应不回显 note 明文」与 AvailabilityOut 契约矛盾 → 修正描述（敏感值不回显的边界是日志/错误/跨用户）。
3. TickResult 新增统计字段导致 ST-S03-06 全量相等断言失效 → 逐字段断言。

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging
- [ ] 确认迁移前已备份数据库，三张新表迁移向后兼容，服务启动与回滚点可用
