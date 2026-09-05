# delta — core-smoke-test-cases.md（lightweight-events）

## MODIFIED — 二、冒烟测试用例 > 2.2 数据库迁移与隔离

### 2.2 数据库迁移与隔离

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-06 | 迁移版本与本次发布一致 | §7-3 | local / staging / production | 迁移已执行 | `alembic current` | 等于目标 revision |
| SMOKE-core-07 | 关键表齐备 | §8.2 迁移项 | staging / production | — | 查 `sqlite_master` 中 21 张表与全部索引是否存在 | 21 张表（20 张既有 + `lite_events`）与索引全部存在（不再有扩展检查——加密在应用层） |
| SMOKE-core-08 | 数据隔离守卫生效 | §7-7 | staging / production | 已建两个 smoke 账号 A、B | 用 B 的 token 请求 A 的愿望详情与列表 | 均 404 / 空列表；启动日志含 `owner_guard installed` |

## ADDED — 二、冒烟测试用例 > 2.6 增补（S09 基础链路）

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-21 | 先记一下 → 划掉 → 收走 → 无残留 | 部署方案 §8.2 关键链路（S09 增补） | local / staging / production | 已有 smoke 账号 | `POST /api/v1/lite-events {text:"smoke：今晚吃火锅"}` → `GET /lite-events` → `POST /{id}/done` → `DELETE /{id}` → 查 `reminder_outbox` | 201 且回显 text → 列表含该条（status=open）→ done 200 → 204；重复 DELETE 404；**`reminder_outbox` 中无任何轻事件相关行**（结构上无提醒路径的 smoke 级体现）；直查 `lite_events.text_enc` 为 BLOB 且不含「火锅」子串 |

## MODIFIED — 三、覆盖度校验

- [x] 健康检查：SMOKE-core-01、02
- [x] 核心入口：SMOKE-core-09
- [x] 数据库迁移：SMOKE-core-06、07
- [x] 静态资源：SMOKE-core-16
- [x] 配置与密钥：SMOKE-core-03、04、05
- [x] 关键链路：SMOKE-core-10、11、12、13、15、19、20、21
- [x] 日志与监控：SMOKE-core-18
- [x] S09 基础链路：SMOKE-core-21
- [x] 表数量断言联动：SMOKE-core-07 更新为 21 张表
- [x] 部署方案 §7 的 12 项检查：1→01、2→02、3→06、4→16、5→17、6→04、7→08、8→05、9→15、10→10（仅告警）、11→03、12→18
- [x] 部署方案 §8.2 的 15 项清单（含 S08/S09 增补）：逐项映射至上表，无遗漏

## MODIFIED — 四、给 code 阶段的要求（本轮新增 18 个 SMOKE-*，必须闭环）

> 锚沿用主文档原标题（18）；本节内容将总数由 20 更新为 21（新增 SMOKE-core-21）。

1. 实现 `scripts/smoke-core.sh`（或等效 runner），**覆盖全部 21 个 `SMOKE-core-*` ID**（含本轮新增的 SMOKE-core-21），ID 原样使用不得改写。
2. runner 必须把每条结果写入 `logos/resources/verify/smoke-results.jsonl`，格式见 `logos/spec/test-results.md`。
3. `logos.config.json → smoke.command` 必须能执行该 runner；推荐接入统一 `scripts/run-smoke.js` dispatcher 自动发现 `scripts/smoke-*`。
4. SMOKE-core-10 必须实现**分层断言**：链路通过即 PASS，`degraded==true` 只写 warning 字段，不改判 FAIL。
5. SMOKE-core-19 必须断言**写响应不回显 value 明文**与 `value_enc` 密文落库两件事——这是 S08 隐私红线的 smoke 级体现。
6. SMOKE-core-21 必须断言**outbox 无轻事件相关行**——「结构上无提醒路径」的 smoke 级体现。
7. code 阶段完成前必须运行 smoke 覆盖预检，确认 21 个 ID 均不在 uncovered cases 中。
8. runner 结束时必须清理 smoke 账号的全部数据（含 SMOKE-core-19/20/21 产生的偏好、时段与轻事件），失败也要清理。
