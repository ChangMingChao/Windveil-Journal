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
（单批闭环，已提交。）

- [x] `app/api.py`：`POST /wishes/{id}/convert-to-lite`（仅 seeded；同事务删 wish 建 lite_event）；actions 三选项
- [x] `app/lite_events.py`：`create_from_wish`（文本迁移，照片/理解不迁移）；`app/schemas.py` actions 枚举扩展
- [x] 既有 ST-S02-09 断言更新为三选项（枚举扩展的预期行为变化）
- [x] 测试：UT-S02-26/27 + ST-S02-16/17（4 个），全量回归 357 passed / 2 skipped（S04-07 为已知偶发抖动，单跑通过）

## [deploy] 部署任务
- [ ] 按合并后的部署方案部署到 staging（无数据库迁移）
- [ ] 确认 near_term_todo mock 模式下第三选项的完整链路，应用回滚点可用
