# delta — core-smoke-test-cases.md（preferences-availability-timing）

## MODIFIED — 二、冒烟测试用例 > 2.2 数据库迁移与隔离

### 2.2 数据库迁移与隔离

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-06 | 迁移版本与本次发布一致 | §7-3 | local / staging / production | 迁移已执行 | `alembic current` | 等于目标 revision |
| SMOKE-core-07 | 关键表齐备 | §8.2 迁移项 | staging / production | — | 查 `sqlite_master` 中 20 张表与全部索引是否存在 | 20 张表（17 张既有 + `user_preferences` / `availability_windows` / `timing_proposals`）与索引全部存在（不再有扩展检查——加密在应用层） |
| SMOKE-core-08 | 数据隔离守卫生效 | §7-7 | staging / production | 已建两个 smoke 账号 A、B | 用 B 的 token 请求 A 的愿望详情与列表 | 均 404 / 空列表；启动日志含 `owner_guard installed` |

## ADDED — 二、冒烟测试用例 > 2.3 增补（S08 基础链路）

| ID | 描述 | 来源 | 目标环境 | 前置条件 | 操作 | 预期结果 |
|----|------|------|----------|----------|------|----------|
| SMOKE-core-19 | 偏好声明与读取（含不回显断言） | 部署方案 §8.2 关键链路（S08 增补） | local / staging / production | 已有 smoke 账号 | `PUT /api/v1/me/preferences {pref_key:"companion", value:"smoke：更想和朋友一起"}` → `GET /api/v1/me/preferences` | PUT 200 且响应**不含 value 明文**；GET 返回该条 `source="declared"`、`confidence=100`、value 与提交一致；直查 `user_preferences.value_enc` 为 BLOB 且不含「smoke：」子串（与 SMOKE-core-18 同型的加密抽查） |
| SMOKE-core-20 | 可用时段保存与读取 | 部署方案 §8.2 关键链路（S08 增补） | local / staging / production | 已有 smoke 账号 | `POST /api/v1/me/availability {weekday:5, start_minute:540, end_minute:720}` → `GET /api/v1/me/availability` → `DELETE /api/v1/me/availability/{id}` | 201 → 列表含该条（`weekday=5`）→ 204；重复 DELETE 返回 404；清理后无残留（并入 smoke 数据自清理） |

## MODIFIED — 三、覆盖度校验

- [x] 健康检查：SMOKE-core-01、02
- [x] 核心入口：SMOKE-core-09
- [x] 数据库迁移：SMOKE-core-06、07
- [x] 静态资源：SMOKE-core-16
- [x] 配置与密钥：SMOKE-core-03、04、05
- [x] 关键链路：SMOKE-core-10、11、12、13、15、19、20
- [x] 日志与监控：SMOKE-core-18
- [x] S08 基础链路：SMOKE-core-19、SMOKE-core-20
- [x] 表数量断言联动：SMOKE-core-07 更新为 20 张表
- [x] 部署方案 §7 的 12 项检查：1→01、2→02、3→06、4→16、5→17、6→04、7→08、8→05、9→15、10→10（仅告警）、11→03、12→18
- [x] 部署方案 §8.2 的 14 项清单（含 S08 增补的关键链路与隔离/加密扩展）：逐项映射至上表，无遗漏

## MODIFIED — 四、给 code 阶段的要求（本轮新增 18 个 SMOKE-*，必须闭环）

> 锚沿用主文档原标题（18）；本节内容将总数由 18 更新为 20（新增 SMOKE-core-19/20）。

1. 实现 `scripts/smoke-core.sh`（或等效 runner），**覆盖全部 20 个 `SMOKE-core-*` ID**（含本轮新增的 SMOKE-core-19、SMOKE-core-20），ID 原样使用不得改写。
2. runner 必须把每条结果写入 `logos/resources/verify/smoke-results.jsonl`，格式见 `logos/spec/test-results.md`。
3. `logos.config.json → smoke.command` 必须能执行该 runner；推荐接入统一 `scripts/run-smoke.js` dispatcher 自动发现 `scripts/smoke-*`。
4. SMOKE-core-10 必须实现**分层断言**：链路通过即 PASS，`degraded==true` 只写 warning 字段，不改判 FAIL。
5. SMOKE-core-19 必须断言**写响应不回显 value 明文**与 `value_enc` 密文落库两件事——这是 S08 隐私红线的 smoke 级体现。
6. code 阶段完成前必须运行 smoke 覆盖预检，确认 20 个 ID 均不在 uncovered cases 中。
7. runner 结束时必须清理 smoke 账号的全部数据（含 SMOKE-core-19/20 产生的偏好与时段），失败也要清理。
