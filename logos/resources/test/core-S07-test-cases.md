# S07 唤回一个被安静放下的愿望 — 测试用例

> 模块：core｜功能分组：F03 未发生之地浏览与整理｜阶段：Phase 3 Step 4a
> 上游：`../prd/1-product-requirements/core-01-requirements.md` S07、`../prd/2-product-design/1-feature-specs/core-02-unhappened-place-design.md` S07、`../prd/3-technical-plan/2-scenario-implementation/core-S07-recall-let-go-wish.md`

所有自动化测试必须通过 OpenLogos reporter 追加写入 `logos/resources/verify/test-results.jsonl`，格式遵循 `logos/spec/test-results.md`；`case_id` 使用本文件中的 UT / ST ID，不另建平行 ID。

## 一、单元测试用例

| ID | 描述 | 对象 | 前置条件 | 输入 | 预期结果 |
|----|------|------|---------|------|---------|
| UT-S07-01 | `recallWish` 端点已在 OpenAPI 中注册 | `wishes.yaml` | API schema loaded | 查找 `POST /wishes/{wish_id}/recall` | 存在 `operationId=recallWish`，200/404/409 响应齐全 |
| UT-S07-02 | `WishCard` 暴露 `let_go_at` 可空字段 | OpenAPI schema | schema loaded | 读取 `WishCard.properties` | `let_go_at` 为 `string|null` 且 `format=date-time` |
| UT-S07-03 | `wishes.let_go_at` 为可空列 | DB schema | 迁移后数据库 | introspect `wishes` | 存在可空 `let_go_at`，旧数据无需回填 |
| UT-S07-04 | 非 `let_go` 状态不得保留 `let_go_at` | DB constraint | 已有 seeded 记录 | 写入 `state='seeded'` 且 `let_go_at` 非空 | 违反 `wishes_let_go_timestamp_matches_state` |
| UT-S07-05 | 安静放下时记录 `let_go_at` | repository/service | state=brewing | 调用 `letGoWish` | `state='let_go'`，`let_go_at` 为服务端当前时间，pending outbox 清零 |
| UT-S07-06 | 安静放下区按 `let_go_at` 倒序 | repository | 3 条 let_go，放下时间不同 | `listWishes(state=let_go)` | 按 `let_go_at DESC` 返回，无统计字段 |
| UT-S07-07 | 历史兼容数据排序 | repository | 1 条 let_go 的 `let_go_at=NULL` | `listWishes(state=let_go)` | 该条不阻塞展示，排在同批有 `let_go_at` 记录之后 |
| UT-S07-08 | 重新种下只允许 `let_go` 状态 | domain service | state=brewing | `recallWish` | 返回 `STATE_TRANSITION_NOT_ALLOWED`，数据不变 |
| UT-S07-09 | 重新种下回到 `seeded` | domain service | state=let_go | `recallWish` | `state='seeded'`，`let_go_at=NULL`，`version+1` |
| UT-S07-10 | 重新种下清空旧时机 | domain service | let_go 记录残留 timing 字段 | `recallWish` | `timing_type/timing_value/timing_set_at/next_trigger_at/timing_occurrence` 均为 null，`trigger_kind='none'`，`soft_deferred=0` |
| UT-S07-11 | 重新种下保留内容 | domain service | let_go 愿望含原话、照片、理解结果、时间线、修订记录 | `recallWish` | `seeded_at`、标题、原话、照片、理解结果、时间线、修订记录均不变 |
| UT-S07-12 | 重新种下不创建提醒 | repository/service | let_go 且无 pending outbox | `recallWish` | `reminder_outbox` 未新增记录 |
| UT-S07-13 | 重新种下清除残留 pending 提醒 | repository/service | let_go 且存在 pending outbox | `recallWish` | 该 wish 的 pending outbox 为 0 |
| UT-S07-14 | 重新种下不调用 Agent | service with mock client | mock LLM/ASR stats=0 | `recallWish` | LLM 与 ASR 调用数仍为 0 |
| UT-S07-15 | 跨用户访问返回 404 | route/repository | 用户 B 有 let_go 愿望 | 用户 A 调用 `recallWish` | 返回 `WISH_NOT_FOUND`，不暴露权限差异 |
| UT-S07-16 | 重复重新种下返回状态冲突 | route/service | 第一次已成功，状态为 seeded | 第二次 `recallWish` | 409 `STATE_TRANSITION_NOT_ALLOWED`，状态保持 seeded |
| UT-S07-17 | `recallWish` 无 request body | OpenAPI schema | schema loaded | 检查 operation | 不定义 required requestBody |
| UT-S07-18 | 前端仅在 `let_go` 展示重新种下动作 | UI state helper | 6 种状态 | 渲染动作列表 | 只有 `let_go` 含「重新种下」 |
| UT-S07-19 | 「再放一会儿」无副作用 | UI handler | recall sheet open | click secondary action | 不调用写 API，只关闭半屏 |
| UT-S07-20 | 成功文案不含禁用词 | UI copy lint | S07 文案集 | 扫描禁用词 | 不含「放弃」「未完成」「失败」「逾期」「完成率」 |

## 二、场景测试用例

### 2.1 主路径

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S07-01 | 浏览安静放下区 | Step 1→6 | 3 条 let_go，2 条有 `let_go_at` | `GET /wishes?state=let_go` | 200；仅返回 let_go；按 `let_go_at DESC NULLS LAST, seeded_at DESC`；响应无统计字段 |
| ST-S07-02 | 打开唤回半屏 | Step 7→12 | state=let_go | `GET /wishes/{id}` | 200；详情含原话、`seeded_at`、`let_go_at`、时间线；前端展示「重新种下」「再放一会儿」 |
| ST-S07-03 | 重新种下 | Step 13→19 | state=let_go 且有 pending 提醒残留 | `POST /wishes/{id}/recall` | 200；`state='seeded'`；`let_go_at IS NULL`；旧时机字段清空；pending outbox 清零；内容与 `seeded_at` 保留 |
| ST-S07-04 | 唤回后重新约定时机 | Step 20→23 | ST-S07-03 产出的 seeded 愿望 | `PUT /wishes/{id}/timing` | 复用 S03 返回；季节/月/几个月后等路径进入 brewing，none 保持 seeded 且无提醒 |

### 2.2 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S07-05 | 安静放下区为空 | EX-6.1 | 该用户无 let_go | `GET /wishes?state=let_go` | 200 `{items:[], next_cursor:null}`；前端空态不显示 0 或计数 |
| ST-S07-06 | 访问他人的安静放下愿望 | EX-8.1 | 用户 B 有 let_go | 用户 A `GET` 或 `POST /recall` | 404 `WISH_NOT_FOUND`；安全日志不含愿望内容 |
| ST-S07-07 | 卡片状态已变化 | EX-10.1 | 列表加载后该卡已被另一端重新种下 | 再次 `POST /recall` | 409 `STATE_TRANSITION_NOT_ALLOWED`；前端重取并展示 seeded |
| ST-S07-08 | 再放一会儿 | EX-12.1 | recall sheet open | 点击「再放一会儿」 | 不发写请求；愿望仍为 let_go；`let_go_at` 不变 |

### 2.3 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S07-09 [manual] | S07 四屏在 375 / 768 / 1024 / 1440px 下不出现计数压力、红色警示、完成率、逾期或「放弃」文案 | Step 6 / Step 12 / Step 19 / EX-6.1 | 人工目视 `core-04-recall-let-go-prototype.html` |

## 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：ST-S07-03、ST-S07-04
- [x] Phase 1 异常验收条件（2 条）：ST-S07-07、ST-S07-06
- [x] Phase 2 交互级验收条件（5 条）：ST-S07-01、ST-S07-02、ST-S07-03、ST-S07-08、ST-S07-09 [manual]
- [x] EX 异常用例（4 个）：EX-6.1→ST-S07-05、EX-8.1→ST-S07-06、EX-10.1→ST-S07-07、EX-12.1→ST-S07-08
- [x] API required 字段：`recallWish` 无 request body（UT-S07-17）；响应复用 `WishDetail`（UT-S07-01/02）
- [x] DB 约束与索引：`let_go_at` 可空列（UT-S07-03）、状态约束（UT-S07-04）、排序索引行为（UT-S07-06/07）覆盖

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S07） | 覆盖用例 |
|-------|------------------------|---------|
| S07-AC-01 | 正常：从安静放下区重新种下 | ST-S07-03, UT-S07-09, UT-S07-10, UT-S07-11, UT-S07-13 |
| S07-AC-02 | 正常：唤回后重新约定时机 | ST-S07-04, UT-S07-12, UT-S07-14 |
| S07-AC-03 | 异常：从非安静放下状态尝试重新种下 | ST-S07-07, UT-S07-08, UT-S07-16 |
| S07-AC-04 | 异常：访问他人的安静放下愿望 | ST-S07-06, UT-S07-15 |
