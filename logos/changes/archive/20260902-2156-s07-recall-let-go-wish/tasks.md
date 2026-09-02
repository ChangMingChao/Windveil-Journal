# 实现任务

## [delta] 规格变更

一文件一任务，与 `deltas/` 下的目标路径一一对应。

- [x] 产出 delta 到 `deltas/prd/1-product-requirements/core-01-requirements.md` —
      补写 S07 的验收条件（当前为空），并给第五节待确认事项第 4 条写下结论
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md` —
      S07 行由「仅占位 / 设计文件暂缺」改为指向实际设计；状态机 `重新种下` 迁移补规则说明
- [x] 产出 delta 到 `deltas/prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` —
      新增 S07 小节：「安静放下」区、唤回半屏、交互级验收条件
- [x] 产出 delta 到 `deltas/prd/2-product-design/2-page-design/core-04-recall-let-go-prototype.html` —
      新增原型（4 个页面 / 状态，见 proposal 的 UI/UX 变更声明）
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-00-scenario-overview.md` —
      S07 行由「未建模」改为已建模，并登记 EX 用例数
- [x] 产出 delta 到 `deltas/prd/3-technical-plan/2-scenario-implementation/core-S07-recall-let-go-wish.md` —
      新增时序图（含异常用例）
- [x] 产出 delta 到 `deltas/api/wishes.yaml` — 新增「重新种下」端点；`WishCard` / `WishDetail`
      补「放下时间」字段
- [x] **验证 API YAML** — `logos/resources/api/` 下所有文件必须为有效 YAML 且符合
      OpenAPI 3.x；含 `:` 或特殊字符的 `description` / `summary` 必须用双引号包裹
- [x] 产出 delta 到 `deltas/database/schema.sql` — `wishes` 新增可空列记录「安静放下的时间」
- [x] 产出 delta 到 `deltas/test/core-S07-test-cases.md` — 新增 S07 的 UT / ST 用例
- [x] 产出 delta 到 `deltas/scenario/core-S07-recall.json` — 新增 S07 编排 flow
- [x] 产出 delta 到 `deltas/scenario/core-00-orchestration-index.json` — 登记 S07 flow

说明（非 delta 产出任务，故不作为 checkbox）：架构文档与 S02 时序图**仅在**
proposal 的 Q2 决定纳入「种下时命中相似已放下记录」时才需要 delta；本清单按
「只做手动唤回」拟定，Q2 若改为纳入，需回到本节补两条 delta 任务。
smoke 用例与部署方案本次不受影响，故无对应 delta（理由见 proposal「变更范围」）。

## [code] 代码实现

> 六维评分：影响范围 2、行为复杂度 2、契约变化 2、测试规模 2、风险等级 2、不确定性 1，合计 11 分，属于大任务。
>
> 删后续自检：候选拆分为后端状态迁移、前端唤回交互、编排闭环会形成横向按工种切分；且任一候选片单独执行全量 `openlogos verify` 都会留下另一侧的 S07 用例未覆盖，无法通过删后续证伪门。故合并为一个端到端自闭环切片，包含数据库兼容、仓储/领域服务、API、前端交互、UT/ST、编排校验与 OpenLogos reporter。

- [x] **切片 1：唤回被安静放下的愿望端到端闭环** — 实现 `let_go` 列表排序与详情字段、`POST /api/v1/wishes/{wish_id}/recall` 状态迁移、旧时机与 pending 提醒清理、内容与时间线保留、跨用户隔离及重复操作冲突；完成前端「重新种下 / 再放一会儿」交互与禁用词校验；补齐对应 UT/ST、S07 编排 flow 校验和 `logos/resources/verify/test-results.jsonl` reporter。覆盖 `UT-S07-01`～`UT-S07-20`、`ST-S07-01`～`ST-S07-08`；`ST-S07-09` 保留人工视觉验证，不纳入自动化代码覆盖。
## [deploy] 部署任务

- [x] 按部署方案 §4.3 部署到 staging（`ops/deploy.sh`，新 `IMAGE_TAG`）
- [x] 确认迁移前已备份 `.db`、加列为可空且向后兼容、服务启动与回滚点可用

## [delta] 追加修复：smoke 索引基线

- [x] 产出 delta 到 `deltas/test/smoke/core-smoke-test-cases.md` — 将 `SMOKE-core-07`
      的预期索引数量从 28 修正为 29，并说明 S07 迁移新增索引的来源

## [code] 追加修复：smoke runner

- [x] 更新 `scripts/smoke-core.py` 的 `SMOKE-core-07` 断言与错误文案，使其校验当前
      17 张表、29 个 `idx_` 索引；不改变运行时业务逻辑


