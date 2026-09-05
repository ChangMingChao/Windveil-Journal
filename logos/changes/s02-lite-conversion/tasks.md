# 实现任务

## [delta] 规格变更
- [ ] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` — S02 增补验收条件（2 条）与 5.3 条目修订
- [ ] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-06-lite-events-design.md` — S09 增补：来自 S02 转换的轻事件
- [ ] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — S09 范围说明更新
- [ ] 产出 delta 到 `deltas/api/wishes.yaml` — actions 枚举扩展 `save_as_lite` + 新增 convert-to-lite 端点
- [ ] 产出 delta 到 `deltas/test/core-S02-test-cases.md` — EX-18.2 第三选项的 UT/ST 增量
- [ ] 产出 delta 到 `deltas/scenario/core-S02-seed-wish.json` — 新增 1 个 flow
- [ ] 产出 delta 到 `deltas/scenario/core-00-orchestration-index.json` — 更新 coverage
- [ ] 验证 `logos/resources/api/` 下所有 YAML 有效且符合 OpenAPI 3.x

## [code] 代码实现
（本段在 plan 阶段留空：需要实现 convert-to-lite 端点（同事务删除 wish + 新建 lite_event）、actions 枚举扩展与 OpenLogos reporter；具体切片由 merge 后的 slice-planner 基于已合并规格与真实 UT/ST ID 规划。）

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging（无数据库迁移）
- [ ] 确认 near_term_todo mock 模式下第三选项的完整链路，应用回滚点可用
