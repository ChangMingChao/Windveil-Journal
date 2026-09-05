# delta — core-S02-test-cases.md（s02-lite-conversion）

## ADDED — 2.5 EX-18.2 第三选项场景测试（s02-lite-conversion 增量）

> 上游：需求 S02 增补验收条件、`../api/wishes.yaml` 的 convertWishToLiteEvent

| ID | 描述 | 覆盖 | 前置条件 | 操作序列 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S02-16 | 选择「先记一下」转为轻事件 | 需求 S02 增补-正常 | LLM mock 置 near_term_todo 模式；已登录 | `POST /wishes`（near_term_todo 输入）→ `POST /wishes/{id}/convert-to-lite` → `GET /lite-events` → `GET /wishes/{id}` | actions 含 save_as_lite；转换 201 返回 LiteEvent（同文本）；轻事件列表含该条；原 wish_id 访问 404；outbox 无记录 |
| ST-S02-17 | brewing 状态拒绝转换 | 需求 S02 增补-异常 | 同上但转换前已 `PUT timing`（brewing） | `POST /wishes/{id}/convert-to-lite` | 409 `STATE_TRANSITION_NOT_ALLOWED`；wish 数据不变 |
| UT-S02-26 | actions 枚举含 save_as_lite | `SeedWishResult.actions` | near_term_todo mock | 检查响应 actions | 含 keep_as_future / save_as_lite / delete 三值 |
| UT-S02-27 | 转换的轻事件归属同一用户且文本一致 | 转换语义 | 转换完成 | 查 lite_events | owner 为原用户；text 与原输入一致 |

## MODIFIED — 三、覆盖度校验

> 在原清单末尾追加：

- [x] s02-lite-conversion 增量（4 个）：EX-18.2 第三选项→ST-16、brewing 拒绝→ST-17、actions 枚举→UT-26、归属与文本→UT-27

## MODIFIED — 四、验收条件追溯

> 在原表末尾追加：

| AC ID | 验收条件（S02 增补） | 覆盖用例 |
|-------|---------------------|---------|
| S02-AC-05 | 正常（增补）：选择「先记一下」转为轻事件 | ST-S02-16, UT-S02-26/27 |
| S02-AC-06 | 异常（增补）：已约定时机的愿望不可转换 | ST-S02-17 |
