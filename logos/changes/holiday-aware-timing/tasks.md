# 实现任务

## [delta] 规格变更
- [x] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` — S03 增补节假日感知验收条件（2 正常 2 异常）、5.1 数据源边界、「不做」清单修订
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` — 建议卡依据来源新增节假日条目的展示文案
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 内置节假日数据源（文件形态/年份粒度/缺年份降级）与更新机制
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md` — 时机提议分支 P3 组装上下文加入节假日事实 + free_weekend 触发日的节假日感知计算说明
- [x] 产出 delta 到 `deltas/api/wishes.yaml` — `TimingProposal.evidence[].kind` 枚举扩展 `calendar`
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 数据文件随镜像发布与年度数据更新运维项
- [x] 产出 delta 到 `deltas/test/core-S03-test-cases.md` — 节假日感知 UT（调休上班周六不命中 / 长周末命中 / 缺年份降级 / evidence 含 calendar）与建议依据 ST
- [x] 产出 delta 到 `deltas/scenario/core-S03-timing.json` — 新增 2 个编排 flow + LLM mock 控制面（propose_timing 的节假日依据模式）
- [x] 产出 delta 到 `deltas/scenario/core-00-orchestration-index.json` — 登记 S03 flow 数变化并更新 coverage
- [x] 验证 `logos/resources/api/` 下所有 YAML 有效且符合 OpenAPI 3.x
- [x] 节假日数据文件 schema — 已定义于架构 delta 5.5 节（年份 / source / updated_at / holidays / workdays 五字段契约）；`deltas/backend/` 非合法 delta 类别，不单设数据文件 delta，正式数据文件（以官方公告填充）随 [code] 阶段交付到 `backend/app/data/`

## [code] 代码实现
（本段在 plan 阶段留空：需要实现节假日数据加载器、free_weekend 计算的节假日感知、提议上下文组装扩展与 OpenLogos reporter；具体切片由 merge 后的 slice-planner 基于已合并规格与真实 UT/ST ID 规划。）

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging（数据文件随镜像发布；无数据库迁移）
- [ ] 确认节假日数据文件在镜像内、缺年份降级路径可验证，应用回滚点可用
