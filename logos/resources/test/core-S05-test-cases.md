# S05: 回看未发生之地并重新整理 — 测试用例

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S05-browse-and-tidy.md`（32 Steps / 8 EX，S05.1 Step 1–14、S05.2 Step 15–32）
> API：`../api/wishes.yaml`｜DB：`../database/schema.sql`（wishes、reminder_outbox、media、orphan_objects）

## 一、单元测试用例

### 1.1 API 字段约束（来源：wishes.yaml → listWishes、amendWish、deleteWishPermanently）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S05-01 | state 非枚举值被拒 | `listWishes → state.enum` | 已认证 | `?state=overdue` | 422 `VALIDATION_FAILED` |
| UT-S05-02 | state 缺省为 all | `state.default: all` | 有多状态卡 | 不传 state | 返回全部状态卡片 |
| UT-S05-03 | limit 边界：1 与 50 通过 / 0 与 51 拒绝 | `limit.minimum/maximum` | 已认证 | 四个边界值 | 200 / 200 / 422 / 422 |
| UT-S05-04 | limit 缺省为 20 | `limit.default: 20` | 有 30 张卡 | 不传 limit | 返回 20 条 + `next_cursor` 非空 |
| UT-S05-05 | 游标非法返回 400 | `400 CURSOR_INVALID` | 已认证 | `?cursor=!!!` | 400 `CURSOR_INVALID` |
| UT-S05-06 | 列表响应不含任何统计字段 | EX-6.1 副作用 | 有 5 张卡 | `GET /wishes` | 响应键集合仅 `items`、`next_cursor`；无 total/completed_count/overdue |
| UT-S05-07 | amendWish 至少改一个字段 | `minProperties: 1` | 已有愿望 | `{}` | 422 `VALIDATION_FAILED` |
| UT-S05-08 | title 边界：60 字通过 / 61 字拒绝 | `title.maxLength: 60` | 已有愿望 | 两个边界值 | 200 / 422 |
| UT-S05-09 | 彻底删除缺 confirm 返回 400 | `confirm` required + `400 CONFIRMATION_REQUIRED` | 已有愿望 | `DELETE /wishes/{id}` | 400 `CONFIRMATION_REQUIRED`；记录仍存在 |
| UT-S05-10 | confirm=false 同样被拒 | `confirm.const: true` | 已有愿望 | `?confirm=false` | 400 `CONFIRMATION_REQUIRED` |

### 1.2 DB 与隔离约束（来源：schema.sql；SQLite 无 RLS，隔离改为应用层守卫）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S05-11 | 未带 owner_id 的 owner 表查询被守卫拒绝 | `db.owner_guard` | 库中有数据 | 执行 `SELECT * FROM wishes`（无 WHERE） | 抛 `OwnerGuardError`，**不返回任何数据** |
| UT-S05-12 | 带他人 owner_id 查不到本人数据 | 仓储层注入 | A、B 各有愿望 | 以 B 的 owner_id 查 A 的 wish_id | 0 行 |
| UT-S05-13 | 关联表按父表主键限定才放行 | `db.ASSOC_TABLES` | A 的愿望有照片 | 查 wish_photos 不带 wish_id | 抛 `OwnerGuardError`；带 wish_id 时正常返回 |
| UT-S05-14 | wishes.state 枚举校验 | `state CHECK` | — | `state='archived'` | 违反 CHECK |
| UT-S05-15 | 彻底删除级联清空全部子表 | 多处 `ON DELETE CASCADE` | 愿望含步骤/对话/照片/修订/outbox | DELETE wishes 行 | 5 张子表相关行均为 0 |
| UT-S05-16 | orphan_objects.object_key 唯一 | `UNIQUE` | 已记录某 key | 再记同 key | 唯一冲突 → 幂等不新增 |
| UT-S05-17 | orphan_objects.reason 枚举校验 | `reason CHECK` | — | `reason='unknown'` | 违反 CHECK |

### 1.3 业务规则（来源：时序图 Step 说明）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S05-18 | 默认排序为 seeded_at 倒序 | S05.1 Step 3 | 3 张不同种下时间的卡 | `GET /wishes` | 最新种下的在最前 |
| UT-S05-19 | 河流视图排序键为 next_trigger_at 升序 | S05.1 Step 14 | 响应含 `timing.next_trigger_at` | 前端重排函数 | 时机最近的在最前；`next_trigger_at` 为 null 的排最后 |
| UT-S05-20 | 视图切换不触发新请求 | S05.1 Step 14 说明 | 已加载列表 | 调用视图切换 | HTTP 请求计数不增加 |
| UT-S05-21 | 放下时同事务清空 pending 提醒 | S05.2 Step 19 | 该愿望有 2 条 pending outbox | `POST /let-go` | `reminder_outbox` 中该愿望 pending 行为 0；已 delivered 行保留 |
| UT-S05-22 | 放下不改 seeded_at 与原话 | S05.2 Step 18 | 种下于 2026-09 | `POST /let-go` | `seeded_at` 与 `original_text` 均不变 |
| UT-S05-23 | 响应与文案不含失败/放弃/未完成字样 | S05.2 Step 22 | — | `POST /let-go` 响应体 | 不含「失败」「放弃」「未完成」任一子串 |
| UT-S05-24 | 删除顺序为先对象后记录 | S05.2 步骤说明 | 愿望含 2 个媒体对象 | 执行彻底删除 | 调用顺序断言：DeleteObjects 先于 DELETE FROM wishes |
| UT-S05-25 | 对象删除部分失败仍删记录并登记孤儿 | EX-28.1 | 对象存储对 1 个 key 返回失败 | 执行彻底删除 | `wishes` 行已删；`orphan_objects` 新增 1 行 `reason='delete_failed'` |
| UT-S05-26 | 彻底删除幂等 | EX-30.1 | 已删除 | 再次 DELETE | 204（不是 404） |
| UT-S05-27 | pause 清空时机并回 seeded | S05.2 整理半屏第 2 项 | state=brewing | `POST /pause` | `state='seeded'`；`next_trigger_at IS NULL`；pending outbox 清零 |

## 二、场景测试用例

### 2.1 主路径（S05.1 浏览）

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S05-01 | 按状态浏览并深链 | Step 1→12 | 12 张卡分布在 4 种状态 | `GET /wishes` → `GET /wishes?state=brewing` | 首次返回全部 12 条按 seeded_at 倒序；筛选后仅返回 brewing 卡；每条含 `timing.label` 与 `state`；响应中无任何计数字段 |
| ST-S05-02 | 切换视图不丢失筛选 | Step 13→14 | 处于 `state=wind` | 切到河流视图 | 数据集不变（无新请求）；按 `next_trigger_at` 升序重排 |
| ST-S05-03 | 游标分页 | Step 2→5 | 30 张卡 | 取第一页 → 用 next_cursor 取第二页 | 两页无重叠无遗漏；第二页 `next_cursor` 为 null |

### 2.2 主路径（S05.2 整理）

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S05-04 | 安静放下一个愿望 | Step 15→22 | state=brewing 且有 2 条 pending 提醒 | `POST /let-go` | 200；`state='let_go'`；`next_trigger_at IS NULL`；pending outbox 清零；标题/原话/`seeded_at` 保留；`GET /wishes?state=let_go` 能查到 |
| ST-S05-05 | 改一改它 | Step 15 | 已有愿望「学会滑雪」 | `PATCH /wishes/{id} {title:"和朋友学会滑雪"}` | 200；标题更新；`seeded_at` 与 `original_text` 不变；`wish_amendments` 新增 1 行；无修改次数展示 |
| ST-S05-06 | 彻底删除完整链路 | Step 23→32 | 愿望含 2 媒体 + 3 步骤 + 2 对话 + 1 修订 + 1 outbox | `DELETE /wishes/{id}?confirm=true` | 204；对象存储 2 个对象不存在；5 张子表相关行为 0；`GET /wishes/{id}` 返回 404 |

### 2.3 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S05-07 | 分页游标失效 | EX-2.1 | — | `?cursor=<已删除记录的游标>` | 400 `CURSOR_INVALID`；客户端可丢弃游标重取第一页 |
| ST-S05-08 | 访问他人的愿望 | EX-3.1 | 用户 B 有愿望 | 用户 A 用其 id 请求详情 | **404** `WISH_NOT_FOUND`（不是 403）；产生一条安全审计日志（含 user_id 与被请求 id，不含内容） |
| ST-S05-09 | 花园为空 | EX-6.1 | 该用户无任何愿望 | `GET /wishes` | 200 `{items:[], next_cursor:null}`；响应无统计字段 |
| ST-S05-10 | 某状态下无卡片 | EX-9.1 | 无 going 状态卡 | `?state=going` | 200 `{items:[]}`；不自动回退为 all |
| ST-S05-11 | 在终态尝试放下 | EX-17.1 | state=happened | `POST /let-go` | 409 `STATE_TRANSITION_NOT_ALLOWED`；数据不变 |
| ST-S05-12 | 彻底删除缺少确认 | EX-25.1 | 已有愿望 | `DELETE` 不带 confirm | 400 `CONFIRMATION_REQUIRED`；记录仍在 |
| ST-S05-13 | 对象存储删除部分失败 | EX-28.1 | 对象存储对 1 个 key 超时 | 彻底删除 | 204；`wishes` 已删；`orphan_objects` 新增 1 行；每日清理任务重试后该 key 消失 |
| ST-S05-14 | 重复删除幂等 | EX-30.1 | 已删除 | 再次 DELETE | 204；无异常抛出 |

### 2.4 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S05-15 [manual] | 花园视图无完成率/进度条/逾期红字/数字角标/任何红色 | Step 6 | 人工目视 375 / 768 / 1024 / 1440px |
| ST-S05-16 [manual] | 彻底删除确认层默认焦点在「取消」，Tab 顺序与视觉顺序一致 | Step 23 | 键盘操作验证 |

## 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：ST-S05-01、ST-S05-04
- [x] Phase 1 异常验收条件（2 条）：ST-S05-12（彻底删除说明差别）、ST-S05-09（花园为空）
- [x] EX 异常用例（8 个）：EX-2.1→ST-07、EX-3.1→ST-08、EX-6.1→ST-09、EX-9.1→ST-10、EX-17.1→ST-11、EX-25.1→ST-12、EX-28.1→ST-13、EX-30.1→ST-14
- [x] API required 字段：`confirm`（UT-09/10）覆盖；`minProperties`（UT-07）覆盖
- [x] DB UNIQUE/CHECK 约束：`state` CHECK（UT-14）、级联删除（UT-15）、`orphan_objects` UNIQUE 与 CHECK（UT-16/17）全部覆盖；应用层隔离守卫 UT-11~13 覆盖
- [x] Phase 2 交互级验收条件（8 条，S05.1 与 S05.2 各 4）：ST-S05-01/02/09/10/04/05/11/12 逐条对应

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S05） | 覆盖用例 |
|-------|------------------------|---------|
| S05-AC-01 | 正常：按状态浏览愿望花园 | ST-S05-01, ST-S05-02, UT-S05-06, UT-S05-18 |
| S05-AC-02 | 正常：安静放下一个愿望 | ST-S05-04, UT-S05-21, UT-S05-22, UT-S05-23 |
| S05-AC-03 | 异常：用户尝试彻底删除一个愿望 | ST-S05-12, ST-S05-06, UT-S05-09 |
| S05-AC-04 | 异常：花园为空 | ST-S05-09, ST-S05-15 [manual] |
