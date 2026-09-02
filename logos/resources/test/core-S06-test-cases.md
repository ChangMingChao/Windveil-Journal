# S06: 把发生过的事写成一页记忆 — 测试用例

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S06-write-memory-page.md`（20 Steps / 8 EX）
> API：`../api/memories.yaml`｜DB：`../database/schema.sql`（memories、memory_photos、wishes、reminder_outbox）

## 一、单元测试用例

### 1.1 API 字段约束（来源：memories.yaml）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S06-01 | happened_from 为必填 | `markWishHappened → required` | state=going | `{}` | 422 `VALIDATION_FAILED` |
| UT-S06-02 | happened_from 非 date 格式被拒 | `format: date` | state=going | `"2026/10/17"` | 422 `VALIDATION_FAILED` |
| UT-S06-03 | happened_to 允许为 null（单日） | `[string, null]` | state=going | `{"happened_from":"2026-10-17"}` | 201；`happened_to IS NULL` |
| UT-S06-04 | 未来日期被拒 | `422 HAPPENED_DATE_IN_FUTURE` | 今天为 2026-09-01 | `"2026-09-02"` | 422 `HAPPENED_DATE_IN_FUTURE` |
| UT-S06-05 | 今天通过（边界） | 同上 | 今天为 2026-09-01 | `"2026-09-01"` | 201 |
| UT-S06-06 | 区间倒置被拒 | `422 HAPPENED_RANGE_INVALID` | — | from=10-18, to=10-17 | 422 `HAPPENED_RANGE_INVALID` |
| UT-S06-07 | 区间相等通过（边界） | 同上 | — | from=to=10-17 | 201 |
| UT-S06-08 | mood 非枚举值被拒 | `updateMemory → mood.enum`（6 值 + null） | 有草稿 | `"excited"` | 422 `VALIDATION_FAILED` |
| UT-S06-09 | mood 允许为 null | 同上 | 有草稿 | `{"mood":null}` | 200；`mood IS NULL` |
| UT-S06-10 | 全字段为空仍可 PATCH | `所有字段可为 null` | 有草稿 | 全部置 null | 200；无非空校验错误 |
| UT-S06-11 | PATCH 至少一个字段 | `minProperties: 1` | 有草稿 | `{}` | 422 `VALIDATION_FAILED` |
| UT-S06-12 | 字段长度边界 | `title 80 / cause 2000 / process 4000 / last_line 300` | 有草稿 | 各边界与 +1 | 200 / 422 |
| UT-S06-13 | photo_media_ids 边界：9 通过 / 10 拒绝 | `maxItems: 9` | 有草稿 | 9 / 10 个 uuid | 200 / 422 `MEDIA_LIMIT_EXCEEDED` |
| UT-S06-14 | 引用他人 media 返回 404 | `404 MEDIA_NOT_FOUND` | B 的 media | A 引用 | 404 |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S06-15 | 一个愿望最多一页记忆 | `memories.wish_id UNIQUE` | 已有草稿 | 再次 `POST /happened` | 唯一冲突 → 返回既有草稿（幂等）而非新建 |
| UT-S06-16 | happened_to >= happened_from | `memories_range_ordered CHECK` | — | to < from | 违反 CHECK |
| UT-S06-17 | published 必须有 published_at | `memories_published_has_timestamp CHECK` | — | `status='published', published_at=NULL` | 违反 CHECK |
| UT-S06-18 | draft 不得有 published_at | 同上（等价约束） | — | `status='draft', published_at=now()` | 违反 CHECK |
| UT-S06-19 | mood CHECK 枚举 | `memories.mood CHECK` | — | `mood='excited'` | 违反 CHECK |
| UT-S06-20 | status CHECK 枚举 | `memories.status CHECK` | — | `status='archived'` | 违反 CHECK |
| UT-S06-21 | edited_fields 默认空数组 | `DEFAULT '[]'` | — | 插入不指定 | `edited_fields = '[]'` |
| UT-S06-22 | memory_photos 复合主键防重复 | `PRIMARY KEY (memory_id, media_id)` | 已关联 | 再关联同一对 | 主键冲突 |
| UT-S06-23 | 愿望删除时记忆页级联删除 | `wish_id ON DELETE CASCADE` | 有已发布记忆页 | 彻底删除愿望 | `memories` 与 `memory_photos` 相关行为 0 |

### 1.3 业务规则（来源：时序图 Step 说明）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S06-24 | 标记已发生即停提醒但不转状态 | S06 Step 6 说明 | state=going 且有 2 条 pending 提醒 | `POST /happened` | `next_trigger_at IS NULL`；pending outbox 清零；`wishes.state` **仍为 going** |
| UT-S06-25 | 发布时才转 happened 终态 | S06 Step 17 | 有草稿 | `POST /publish` | `wishes.state='happened'`；`memories.status='published'` |
| UT-S06-26 | 早于种下日期时返回 warning 而非错误 | EX-3.1 | 种下于 2026-09 | `happened_from=2026-07-12` 且不带 ack | 201 且 `warning.code='HAPPENED_BEFORE_SEEDED'`；`note_before_seeded=false` |
| UT-S06-27 | 携带 ack 后写入注记 | EX-3.1 | 同上 | 带 `acknowledged_before_seeded=true` | 201；`warning` 为 null；`note_before_seeded=true` |
| UT-S06-28 | 无时间线时 process 为空占位 | EX-4.1 | state=seeded 无步骤 | `POST /happened` | `process IS NULL`；不报错 |
| UT-S06-29 | 用户编辑过的字段被记入 edited_fields | EX-7.1 | 有草稿 | PATCH title 与 cause | `edited_fields = ['title','cause']` |
| UT-S06-30 | 补草拟不覆盖用户编辑过的字段 | EX-7.1 | `edited_fields=['title']` | 运行 `memory_draft` 补草拟 | `title` 保持用户版本；`process` 被填充 |
| UT-S06-31 | lived_pages 只统计 published | `listMemories → lived_pages` | 2 published + 1 draft | `GET /memories` | `lived_pages=2`；`items` 2 条 |
| UT-S06-32 | 发布幂等不重复计数 | EX-17.1 | 已 published | 再次 publish | 200；`published_at` 不变；`lived_pages` 不变 |

## 二、场景测试用例

### 2.1 主路径

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S06-01 | 生成并补充一页记忆 | Step 1→20 | state=going，timeline 3 条；LLM mock 正常；已上传 2 张照片 | `POST /happened {from:2026-10-17,to:2026-10-18}` → PATCH 补心情与一句话 + 2 张照片 → `POST /publish` | 201 ≤5 秒返回草稿，含 LLM 草拟的标题/起因/经过；PATCH 后 `memory_photos` 2 行、`mood='relieved'`、`last_line_enc` 非空；publish 后 `wishes.state='happened'`、`memories.status='published'`、`lived_pages` +1；该愿望不再接收提醒 |
| ST-S06-02 | 跳过全部补充内容直接发布 | Step 1→10 + Step 15→20 | state=going | `POST /happened` → 直接 `POST /publish` | 200；记忆页仅含标题/日期/起因/经过；无「内容不完整」提示；发布后仍可 PATCH 继续补 |
| ST-S06-03 | 单日发生（非区间） | Step 2→10 | state=going | `{happened_from:"2026-10-17"}` | 201；`happened_to IS NULL` |
| ST-S06-04 | 书架按发生时间倒序 | Step 20 | 3 个 published 记忆页 | `GET /memories` | 按 `happened_from` 倒序；`lived_pages=3`；每条含 `cover_media_id`（无图时为 null） |

### 2.2 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S06-05 | 发生日期早于种下日期 | EX-3.1 | 种下于 2026-09 | `happened_from=2026-07-12`（先不带 ack，再带 ack 重提） | 首次 201 + `warning`；`note_before_seeded=false`；带 ack 后 `note_before_seeded=true`；两次均无 422、无校验红字 |
| ST-S06-06 | 发生日期在未来 | EX-3.2 | 今天 2026-09-01 | `happened_from=2026-12-01` | 422 `HAPPENED_DATE_IN_FUTURE`；不创建记忆页 |
| ST-S06-07 | 区间倒置 | EX-3.3 | — | from=10-18, to=10-17 | 422 `HAPPENED_RANGE_INVALID`；不创建记忆页 |
| ST-S06-08 | 未经历约定路径直接标记已发生 | EX-4.1 | state=seeded，无时机无步骤 | `POST /happened` | 201；`process IS NULL`；不出现「请先完成前序步骤」；可正常发布 |
| ST-S06-09 | LLM 草拟失败 | EX-7.1 | LLM mock 超时 | `POST /happened` | 201 `degraded=true`；`title` 回退为愿望原标题；`cause` 为原话引用；`process IS NULL`；`pending_agent_jobs` 新增 `memory_draft`；不阻塞发布 |
| ST-S06-10 | 补草拟不覆盖用户编辑 | EX-7.1 | 降级草稿 + 用户已改 title | 运行补草拟任务 | `title` 保持用户版本；`process` 被填充；`edited_fields` 含 `title` |
| ST-S06-11 | 照片数量超限 | EX-12.1 | 有草稿 | PATCH 10 个 media_id | 422 `MEDIA_LIMIT_EXCEEDED`；本次编辑不保存；多余对象由孤儿清理回收 |
| ST-S06-12 | 重复点击「收进书里」 | EX-17.1 | 已 published | 再次 publish | 200；`published_at` 不变；`lived_pages` 不变 |
| ST-S06-13 | 发布时愿望已在另一端被彻底删除 | EX-18.1 | 草稿存在后愿望被删 | `POST /publish` | 404 `WISH_NOT_FOUND`；事务回滚；草稿已随愿望级联删除 |

### 2.3 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S06-14 [manual] | 阅读态纸质背景与颗粒在浅色环境下对比度达标、照片带 alt 文本 | Step 20 | 人工目视 + 屏幕阅读器抽查 |
| ST-S06-15 [manual] | 「收进书里」后书页合起动效 600ms，reduced-motion 下无动效 | Step 20 | 真实浏览器 + 系统开关对照 |

## 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：ST-S06-01、ST-S06-02
- [x] Phase 1 异常验收条件（2 条）：ST-S06-08、ST-S06-05
- [x] EX 异常用例（8 个）：EX-3.1→ST-05、EX-3.2→ST-06、EX-3.3→ST-07、EX-4.1→ST-08、EX-7.1→ST-09/10、EX-12.1→ST-11、EX-17.1→ST-12、EX-18.1→ST-13
- [x] API required 字段：`happened_from`（UT-01）覆盖；`minProperties`（UT-11）覆盖
- [x] DB UNIQUE/CHECK 约束：`wish_id` UNIQUE（UT-15）、`range_ordered`（UT-16）、`published_has_timestamp`（UT-17/18）、`mood`/`status` CHECK（UT-19/20）、`edited_fields` DEFAULT（UT-21）、`memory_photos` PK（UT-22）、级联删除（UT-23）全部覆盖
- [x] Phase 2 交互级验收条件（5 条）：ST-S06-01/02/08/05 + ST-S06-09（Agent 草拟降级）

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S06） | 覆盖用例 |
|-------|------------------------|---------|
| S06-AC-01 | 正常：生成并补充一页记忆 | ST-S06-01, UT-S06-25, UT-S06-31 |
| S06-AC-02 | 正常：跳过全部补充内容 | ST-S06-02, UT-S06-10 |
| S06-AC-03 | 异常：未经历约定路径就直接标记已发生 | ST-S06-08, UT-S06-28 |
| S06-AC-04 | 异常：发生日期早于种下日期 | ST-S06-05, UT-S06-26, UT-S06-27 |
