# S04: 风来了，开始第一小步 — 测试用例

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S04-first-small-step.md`（23 Steps / 7 EX）
> API：`../api/wishes.yaml`｜DB：`../database/schema.sql`（wishes、wish_steps、wish_messages、wish_amendments）

## 一、单元测试用例

### 1.1 API 字段约束（来源：wishes.yaml → requestNextStep、markStepDone、sendWishMessage）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S04-01 | rejected_step_id 非 uuid 被拒 | `requestNextStep → format: uuid` | 状态 wind | `"abc"` | 422 `VALIDATION_FAILED` |
| UT-S04-02 | rejected_step_id 指向他人步骤返回 404 | RLS + 404 约定 | 用户 B 的步骤 | 用户 A 引用 | 404（非 403） |
| UT-S04-03 | markStepDone 缺 If-Match 返回 412 | `markStepDone → 412 PRECONDITION_REQUIRED` | 存在 proposed 步骤 | 不带 If-Match | 412 `PRECONDITION_REQUIRED` |
| UT-S04-04 | If-Match 版本不匹配返回 409 | `409 STATE_CONFLICT` | version=3 | 传 If-Match=2 | 409 `STATE_CONFLICT` |
| UT-S04-05 | messages.text 为必填且非空 | `sendWishMessage → minLength: 1` | 已有愿望 | `{"text":""}` | 422 `VALIDATION_FAILED` |
| UT-S04-06 | messages.text 边界：1000 字通过 / 1001 字拒绝 | `maxLength: 1000` | 已有愿望 | 两个边界值 | 200 / 422 |
| UT-S04-07 | requestNextStep 在非 wind/going 状态返回 409 | `409 STATE_TRANSITION_NOT_ALLOWED` | 状态 seeded | 请求下一步 | 409 |
| UT-S04-08 | markWishReady 在 happened 终态返回 409 | `markWishReady → 409` | 状态 happened | `POST /ready` | 409 `STATE_TRANSITION_NOT_ALLOWED` |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S04-09 | 同一愿望只允许 1 个 proposed 步骤 | `idx_wish_steps_single_proposed UNIQUE` | 已有 proposed | 再插一条 proposed | 唯一冲突 |
| UT-S04-10 | est_minutes 上限 5 由数据库强制 | `wish_steps.est_minutes CHECK <= 5` | — | `est_minutes=10` | 违反 CHECK |
| UT-S04-11 | done 状态必须有 completed_at | `wish_steps_done_has_completed_at CHECK` | — | `status='done', completed_at=NULL` | 违反 CHECK |
| UT-S04-12 | proposed/rejected 状态不得有 completed_at | 同上（等价约束） | — | `status='rejected', completed_at=now()` | 违反 CHECK |
| UT-S04-13 | wish_steps.status 枚举校验 | `status CHECK` | — | `status='skipped'` | 违反 CHECK |
| UT-S04-14 | wish_steps.source 枚举校验 | `source CHECK (llm, fallback)` | — | `source='manual'` | 违反 CHECK |
| UT-S04-15 | wish_messages.role 与 intent 枚举校验 | 两条 CHECK | — | `role='system'` / `intent='delete'` | 均违反 CHECK |
| UT-S04-16 | 删除愿望时步骤与对话级联删除 | `ON DELETE CASCADE` | 有 3 步骤 2 消息 | 删除 wish | `wish_steps`、`wish_messages` 相关行均消失 |
| UT-S04-17 | wish_amendments.prev_title_enc 非空 | `NOT NULL` | — | 插入 NULL | 违反 NOT NULL |

### 1.3 业务规则（来源：时序图 Step 说明）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S04-18 | 步骤合规校验：involves_cost=true 触发重试 | EX-8.2 | LLM 首次返回 `involves_cost=true` | 请求下一步 | 服务端重新请求 1 次并在 prompt 指出违反项 |
| UT-S04-19 | 二次仍不合规则用内置兜底步骤 | EX-8.2 | LLM 两次均违规 | 请求下一步 | `source='fallback'`，文本来自兜底库且按 `understanding.feeling` 选取 |
| UT-S04-20 | 被拒步骤永不重复出现 | EX-13.1 | 已 rejected 一条 | 连续请求下一步 3 次 | 返回文本与被拒文本的相似度低于阈值；被拒文本不再出现 |
| UT-S04-21 | 连续 3 次拒绝后不再调用 LLM | EX-13.2 | 已有 3 条 rejected 且无 done | 请求下一步 | LLM mock 调用次数为 0；返回最轻一档兜底步骤 |
| UT-S04-22 | 一次只返回 1 个步骤 | Step 23 说明 | 状态 going | 请求下一步 | 响应中 `step` 为单对象；库中 proposed 计数为 1 |
| UT-S04-23 | 完成步骤刷新 last_activity_at | Step 15 | last_activity_at 为 30 天前 | 标记 done | `last_activity_at ≈ now()` |
| UT-S04-24 | 60 天停滞判定边界 | EX-15.2 | last_activity_at 为 59 天 / 60 天前 | 运行扫描 | 59 天不命中；60 天命中 |
| UT-S04-25 | 停滞关心每个愿望只发一次 | EX-15.2 | 已有 stale_notified_at | 再次扫描 | 不重复入箱 |
| UT-S04-26 | intent=amend 保留 seeded_at 与原话 | EX-23.1 | 愿望种下于 2026-09 | 对话「想改成和妹妹一起去」 | `title` 更新；`seeded_at` 不变；`wish_amendments` 新增 1 行；`timeline` 行数不变 |
| UT-S04-27 | intent=fatigue 批量回写 signal 类时机 | S03 EX-11.1 联动 | 该用户有 2 张 `trigger_kind=signal` 卡 | 对话「最近好累」 | 两张卡 `next_trigger_at=now()`；非 signal 卡不受影响 |

## 二、场景测试用例

### 2.1 主路径

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S04-01 | 完成第一小步并进入「正在发生」 | Step 1→23 | 状态 brewing 的愿望「去海边待两天」；LLM mock 正常 | `POST /ready` → 取下一步 → 带 If-Match 标记 done → 自动取下一步 | `state` 依次 brewing→wind→going；`wish_steps` 1 条 done + 1 条 proposed；`timeline` 新增 1 条含 completed_at；响应中无步骤清单、剩余数量或百分比；详情页无任何截止日期字段 |
| ST-S04-02 | 从通知动作直接进入并推进 | Step 1→18 | 时机已到达且已投递 | 通知动作「我好像准备好了」→ 取下一步 → done | 与 ST-S04-01 一致；`last_activity_at` 被刷新 |

### 2.2 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S04-03 | LLM 不可用 | EX-8.1 | LLM mock 超时 | `POST /ready` 后取下一步 | 200 `{step:null, degraded:true}`；`state` **保持 wind 不回退**；`pending_agent_jobs` 新增 `next_step`；无错误码外泄 |
| ST-S04-04 | LLM 返回违规步骤 | EX-8.2 | mock 返回 `involves_cost=true` 两次 | 取下一步 | 最终返回 `source='fallback'` 的步骤；`est_minutes<=5`、`involves_cost=false`、`involves_others=false`；降级计数被记录 |
| ST-S04-05 | 要求一个更小的开始 | EX-13.1 | 已有 proposed 步骤 | 带 `rejected_step_id` 请求 | 原步骤 `status='rejected'`；新步骤满足 ≤5 分钟 / 不花钱 / 不联系他人；被拒文本不再出现；响应中无拒绝次数计数 |
| ST-S04-06 | 连续 3 次要求更小 | EX-13.2 | 无 done 且已 3 条 rejected | 第 4 次请求 | 返回纯想象类兜底步骤 + 「不用现在做任何事也可以」；LLM 未被调用 |
| ST-S04-07 | 并发点击「做完了」 | EX-15.1 | 同一 proposed 步骤，version=3 | 两个请求同时带 If-Match=3 | 一个 200 一个 409 `STATE_CONFLICT`；`timeline` 只新增 1 条 |
| ST-S04-08 | 「正在发生」满 60 天无动作 | EX-15.2 | state=going，last_activity_at 60 天前 | 运行调度扫描 | `reminder_outbox` 新增 1 条 `kind=stale_care` 且计入周预算；`stale_notified_at` 被写入；再次扫描不重复；详情页给出三个动作；响应中无停滞天数与百分比 |
| ST-S04-09 | 推进过程中改变愿望本身 | EX-23.1 | state=going，timeline 已有 3 条 | 对话「想改成和妹妹一起去」 | 200 `intent=amend`；`title` 与 `understanding.conditions.companion` 更新；`amended_from` 返回原始表述；`seeded_at` 不变；3 条 timeline 完整保留；`state` 仍为 going |
| ST-S04-10 | 「先放回酝酿」保留时间线 | EX-15.2 三选项之一 | state=going，timeline 3 条 | `POST /back-to-brewing` | 200；`state='brewing'`；`wish_steps` 的 done 行全部保留 |

### 2.3 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S04-11 [manual] | 对话区任一时刻只呈现 1 个下一步卡，无计划清单与进度条 | Step 12、Step 23 | 人工目视 375 / 768px |

## 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：ST-S04-01、ST-S04-05
- [x] Phase 1 异常验收条件（2 条）：ST-S04-08、ST-S04-09
- [x] EX 异常用例（7 个）：EX-8.1→ST-03、EX-8.2→ST-04、EX-13.1→ST-05、EX-13.2→ST-06、EX-15.1→ST-07、EX-15.2→ST-08/10、EX-23.1→ST-09
- [x] API required 字段：`text`（UT-05/06）覆盖；`If-Match` 头必填（UT-03）覆盖
- [x] DB UNIQUE/CHECK 约束：单 proposed 唯一索引（UT-09）、`est_minutes` CHECK（UT-10）、`done_has_completed_at`（UT-11/12）、`status`/`source`/`role`/`intent` CHECK（UT-13~15）、级联删除（UT-16）、`prev_title_enc` NOT NULL（UT-17）全部覆盖
- [x] Phase 2 交互级验收条件（4 条）：ST-S04-01/05/08/09

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S04） | 覆盖用例 |
|-------|------------------------|---------|
| S04-AC-01 | 正常：完成第一小步并进入「正在发生」 | ST-S04-01, UT-S04-22, UT-S04-23 |
| S04-AC-02 | 正常：用户要求一个更小的开始 | ST-S04-05, UT-S04-20 |
| S04-AC-03 | 异常：进入「正在发生」后长期没有新动作 | ST-S04-08, UT-S04-24, UT-S04-25 |
| S04-AC-04 | 异常：用户在推进过程中改变了愿望本身 | ST-S04-09, UT-S04-26 |
