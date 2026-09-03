# S03: 为一个愿望约定属于它的时机 — 测试用例

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md`（22 Steps / 9 EX）
> API：`../api/wishes.yaml`、`../api/system.yaml`｜DB：`../database/schema.sql`（wishes、reminder_outbox、reminder_weekly_counters、push_subscriptions）

## 一、单元测试用例

### 1.1 API 字段约束（来源：wishes.yaml → setWishTiming、deferWish）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-01 | type 为必填 | `TimingInput.required: [type]` | 已有愿望 | `{}` | 422 `TIMING_INVALID` |
| UT-S03-02 | type 非枚举值被拒 | `TimingInput.type.enum`（6 值） | 已有愿望 | `{"type":"weather"}` | 422 `TIMING_INVALID` |
| UT-S03-03 | type=season 缺 season 被拒 | 组合校验 | 已有愿望 | `{"type":"season"}` | 422 `TIMING_INVALID` |
| UT-S03-04 | season 非四季值被拒 | `season.enum` | 已有愿望 | `{"type":"season","season":"rainy"}` | 422 `TIMING_INVALID` |
| UT-S03-05 | month_day 格式校验 | `pattern: ^\d{4}-\d{2}(-\d{2})?$` | 已有愿望 | `"2027-3"` / `"2027-03"` / `"2027-03-15"` | 422 / 200 / 200 |
| UT-S03-06 | month_day 日期不存在被拒 | EX-4.2 | 已有愿望 | `"2027-02-30"` | 422 `TIMING_INVALID` |
| UT-S03-07 | after_months 非 {1,3,6,12} 被拒 | `after_months.enum` | 已有愿望 | `2` | 422 `TIMING_INVALID` |
| UT-S03-08 | defer 默认 after_months=3 | `deferWish → default: 3` | 状态 brewing | `POST /defer` 空 body | `next_trigger_at ≈ now + 3 月` |
| UT-S03-09 | 前端传入 next_trigger_at 被忽略 | S03 Step 5 说明 | 已有愿望 | body 额外带 `next_trigger_at` | 该字段被丢弃，服务端自算 |
| UT-S03-10 | 时机接口幂等 | `PUT` 语义 | 已设 season=winter | 重复提交同参数 | 200，`timing_occurrence` 不变，无副作用 |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-11 | trigger_kind 非 time 时禁止有 next_trigger_at | `wishes_signal_and_none_have_no_trigger_time CHECK` | — | `trigger_kind='signal', next_trigger_at=now()` | 违反 CHECK |
| UT-S03-12 | timing_type 只接受 6 个枚举值 | `wishes.timing_type CHECK` | — | `timing_type='weather'` | 违反 CHECK |
| UT-S03-13 | 同一时机只能入箱一次 | `idx_reminder_outbox_once UNIQUE` | 已入箱 | 再次 INSERT 同 (wish_id, kind, timing_occurrence) | 唯一冲突；`ON CONFLICT DO NOTHING` 时行数不变 |
| UT-S03-14 | 周计数上限被数据库强制为 3 | `delivered_count CHECK BETWEEN 0 AND 3` | 已 3 条 | `UPDATE ... delivered_count=4` | 违反 CHECK |
| UT-S03-15 | outbox status 枚举校验 | `reminder_outbox.status CHECK` | — | `status='sent'` | 违反 CHECK |
| UT-S03-16 | delivered 必须同时有 channel 与 delivered_at | `reminder_outbox_delivered_has_channel CHECK` | — | `status='delivered'` 但 channel NULL | 违反 CHECK |
| UT-S03-17 | 周计数复合主键防重复 | `PRIMARY KEY (owner_id, week_start)` | 已有本周行 | 再插同 (owner, week) | 主键冲突 → upsert 累加 |
| UT-S03-18 | push endpoint 唯一 | `push_subscriptions.endpoint UNIQUE` | 已订阅 | 同 endpoint 再订阅 | 唯一冲突 → 幂等更新 |

### 1.3 业务规则（来源：时序图 Step 说明与调度算法）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-19 | 季节触发按用户时区计算 | S03 Step 5 说明 | 用户 timezone=Asia/Shanghai，当前 9 月 | 设 season=winter | `next_trigger_at` 落在该时区的入冬日 |
| UT-S03-20 | when_tired 置 trigger_kind=signal 且不算时间 | EX-11.1 | — | 设 `type=when_tired` | `trigger_kind='signal'`，`next_trigger_at IS NULL` |
| UT-S03-21 | type=none 状态保持 seeded | EX-4.1 | 状态 seeded | 设 `type=none` | `state='seeded'`（不转 brewing），`trigger_kind='none'` |
| UT-S03-22 | 自然周起始按用户时区的周一 | S03 Step 13 | timezone=Asia/Shanghai | 计算 `week_start` | 返回该时区周一日期，非 UTC 周一 |
| UT-S03-23 | 顺延排序键为 timing_set_at 升序 | S03 Step 11 说明 | 3 张卡不同 timing_set_at | 排序 | 最早设定的排最前（先发） |
| UT-S03-24 | 投递失败不累加周计数 | EX-16.2 | 推送与邮件均失败 | 投递 1 条 | `delivered_count` 不变，outbox 保持 pending |
| UT-S03-25 | 退避序列为 5 分钟 / 30 分钟 / 2 小时 | EX-16.2 | attempts=0/1/2 | 计算 `next_attempt_at` | 依次 +300s / +1800s / +7200s；attempts=3 后置 failed |
| UT-S03-26 | 通知文案为模板拼接且不调 LLM | S03 Step 15 说明 | — | 生成文案 | 文案逐字包含用户原话摘要；LLM mock 调用次数为 0 |
| UT-S03-27 | 调度锁未获得时静默退出 | EX-9.1 | 锁被占用 | 运行一轮 | 立即返回，**不记 error 级日志** |
| UT-S03-28 | 库中不存在顺延次数字段 | EX-20.1 副作用 | — | 检查 `wishes` 列清单 | 无任何形如 `defer_count` / `overdue_days` 的列 |

### 1.4 时机提议（TimingProposal）单元测试

> 上游：`../prd/3-technical-plan/2-scenario-implementation/core-S03-set-timing.md` 时机提议分支（P1–P16 / EX-P.1–P.5）、`../database/schema.sql`（timing_proposals）

### 1.4.1 API 字段约束（来源：wishes.yaml → createTimingProposal / confirmTimingProposal）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S03-29 | 提议的 timing_type 只接受 4 种时间类 | `TimingProposal.timing_type.enum`、架构 5.4 | 已有 seeded 愿望 | LLM mock 返回 `when_tired` 草稿 | Pydantic 校验失败等同 None → `degraded=true`，不落库（EX-P.1） |
| UT-S03-30 | confidence 超界被拒 | `timing_proposals.confidence CHECK 0–100` | — | `confidence=101` 入库 | 违反 CHECK |
| UT-S03-31 | 提议状态只允许 4 个枚举值 | `timing_proposals.status CHECK` | — | `status='sent'` | 违反 CHECK |
| UT-S03-32 | decided_at 与状态配对 | `timing_proposals_decided_state_pairing CHECK` | — | `status='confirmed'` 且 `decided_at=NULL` | 违反 CHECK |
| UT-S03-33 | 同一愿望至多 1 条 pending | `idx_timing_proposals_single_pending` | 已有 pending 提议 | 再 INSERT 一条 pending | 唯一冲突；服务端事务内先置旧提议 expired 再插入（分支 P7） |
| UT-S03-34 | evidence 只存 ID 引用且默认 '[]' | `timing_proposals.evidence` 列约定 | — | 检查新提议行 | `evidence='[]'` 或 `[{"kind","id"}]`；不含任何内容文本 |
| UT-S03-35 | confirm 请求体必须为空 | EX-P.4 | 已有 valid pending 提议 | confirm body 携带 `next_trigger_at` | 422 `PROPOSAL_CONFIRM_BODY_FORBIDDEN` |
| UT-S03-36 | confirm 拒绝非 pending 或 invalid 提议 | EX-P.3 / EX-P.2 | 提议已 expired 或 `validation.valid=false` | confirm（空 body） | 409 `PROPOSAL_EXPIRED` / `PROPOSAL_NOT_CONFIRMABLE`；wishes 无任何变化 |
| UT-S03-37 | 校验失败的提议入库即 expired 并留审计 | 分支 P8 | LLM 返回 `month_day=2027-02-30` 草稿 | POST 生成提议 | 200；行 `status='expired'`、`validation_result={"valid":false,"reason_code":"TIMING_INVALID"}` |
| UT-S03-38 | free_weekend 提议要求有可用时段 | EX-P.2、`validation.reason_code` | 用户无任何 availability 行 | 生成 `free_weekend` 提议 | `valid=false`、`reason_code="PROPOSAL_NO_AVAILABILITY"`、status=expired |
| UT-S03-39 | expires_at 默认 7 天且扫描置 expired | 分支第 3 层、`idx_timing_proposals_expiry` | 已有 pending 提议 | 时钟推进 7 天 + 1 秒 → 触发过期扫描 | `status` 转 `expired`；confirm 返回 409 |
| UT-S03-40 | 确认后 next_trigger_at 由服务端计算 | 分支 P13、S03 Step 5 说明 | 已有 valid pending 提议 | confirm | `wishes.next_trigger_at` 为服务端按 timezone 计算值；`proposed_trigger_at` 未写入 wishes 任何列 |

## 二、场景测试用例

### 2.1 主路径

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S03-01 | 约定季节触发并在时机到达时收到通知 | Step 1→22 | 已有 seeded 愿望「学会滑雪」；当前 2026-09；已注册 push 订阅 | 设 season=winter → 时钟推进到入冬 → 触发一轮调度 → 点通知动作「我好像准备好了」 | `state` 依次 seeded→brewing→wind；卡面 `timing.label="正在等待合适的风：入冬"`；`reminder_outbox` 恰好 1 行 `status=delivered`、`channel=push`；文案含「你在九月说过」；`delivered_count=1` |
| ST-S03-02 | 约定「多久之后再想想」 | Step 1→8 | 已有 seeded 愿望 | 设 `after_months=3` | `state=brewing`；`next_trigger_at ≈ now+3 月`；`timing_occurrence` 非空 |
| ST-S03-03 | 信号类时机由对话触发 | Step 1→8 + EX-11.1 | 已设 `when_tired` | 调度扫描一轮（不应命中）→ 在 `POST /messages` 说「最近好累」 | 第一轮 `scanned` 不含该卡；对话后 `next_trigger_at=now()`；下一轮进入 outbox |

### 2.2 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S03-04 | 选择「不必提醒」 | EX-4.1 | seeded 愿望 | 设 `type=none` | 200；`state=seeded`；`next_trigger_at IS NULL`；调度永不命中该卡；卡面文案「你说你会自己想起它」 |
| ST-S03-05 | 时机参数非法 | EX-4.2 | seeded 愿望 | 提交 `month_day="2027-02-30"` 与缺 value 的 season | 均 422 `TIMING_INVALID`；`wishes` 的 timing 字段与状态均不变 |
| ST-S03-06 | 调度锁被占用 | EX-9.1 | 另一实例持锁 | 运行第二个实例一轮 | 静默退出；`reminder_outbox` 无新增；无 error 日志 |
| ST-S03-07 | 本周预算已满 | EX-14.1 | 同一用户本周已投递 3 条；第 4、5 张卡时机到达 | 触发一轮调度 | 仅前 3 条 delivered；第 4、5 张 `soft_deferred=true`、outbox 记录 `deferred_to_next_week`；`GET /wishes` 返回 `soft_deferred=true`；**无任何合并式通知** |
| ST-S03-08 | 同一时机被重复扫描 | EX-14.2 | 已投递该时机 | 连续触发两轮调度 | 第二轮 `enqueued=0`；outbox 仍 1 行；`delivered_count` 仍为 1 |
| ST-S03-09 | Push 订阅已失效 | EX-16.1 | push mock 返回 410 | 触发投递 | `push_subscriptions` 该行被删除；同一条改走邮件；`channel='email'`；仅送达 1 条（不双发） |
| ST-S03-10 | 推送与邮件均失败 | EX-16.2 | 两个通道都返回 5xx | 触发投递 3 轮 | outbox 保持 pending 并按退避重试；第 4 次置 `failed`；`delivered_count` 始终为 0 |
| ST-S03-11 | 用户选择「还不是现在」 | EX-20.1 | 时机已到达并已投递 | `POST /defer` | 200；`state` 仍为 brewing；`next_trigger_at` 重算为 +3 月；无逾期标记；`GET /wishes` 中排序位置不变 |
| ST-S03-12 | 排序键验证：顺延先顺延最近设定的 | EX-14.1 + Step 11 | 3 张卡 timing_set_at 分别为 6 个月前 / 1 个月前 / 昨天，本周预算剩 1 条 | 触发一轮调度 | 投递的是 6 个月前设定的那张；昨天设定的被顺延 |

### 2.3 边界用例

| ID | 描述 | 覆盖 | 前置条件 | 触发条件 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S03-15 | 无 push 订阅时走邮件兜底并断言文案 | Step 16 邮件兜底分支（与 EX-16.1 的 410 同一代码路径） | 账号已绑定邮箱、从未注册 push 订阅、时机已到达 | 触发一轮调度 | `channel='email'`；邮件正文逐字包含用户原话；不含「逾期」「任务」等禁用词 |

### 2.4 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S03-13 [manual] | 「风来了」状态圆点呈 2.4 秒呼吸光晕，reduced-motion 下为静态柔光 | Step 22 | 真实浏览器 + 系统开关对照 |
| ST-S03-14 [manual] | 真实设备（含 iOS Safari 添加主屏后）能收到 Web Push 通知并显示两个动作 | Step 18 | 真机验证 |

### 2.5 时机提议场景测试（S08 增量）

### 主路径与异常（编排可覆盖，LLM mock 支持 `propose_timing` 模式）

| ID | 描述 | 覆盖 | 前置条件 | 操作序列 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S03-16 | 生成→展示→确认→衔接既有提醒链路 | 分支 P1→P15 + 主图 Step 9→18 | seeded 愿望；用户已有可用时段；LLM mock 返回 `after_months=1` 草稿；已注册 push 订阅 | 生成提议 → 断言建议卡字段 → confirm → 时钟推进 → 触发一轮调度 | confirm 200；`state=brewing`；提议 `status=confirmed`；调度后 outbox 恰好 1 条 delivered；`delivered_count=1`——建议采纳后的提醒行为与手动约定完全一致 |
| ST-S03-17 | 拒绝建议不产生任何副作用 | EX-P.3 | seeded 愿望；已有 pending 提议 | reject | 200；`status=rejected`、`decided_at` 非空；`wishes` 的 state/timing 全部不变；outbox 无新增；再次生成需用户主动触发 |
| ST-S03-18 | 依据被撤回 → 建议立即失效 | EX-P.5、S08 Step 15 | pending 提议 evidence 引用某 availability 行 | `POST /me/availability/{id}` 删除该时段 → confirm | 删除后提议 `status=expired`；confirm 409 `PROPOSAL_EXPIRED`；wishes 无变化 |
| ST-S03-19 | LLM 降级：无落库、无错误码 | EX-P.1 | LLM mock 置为不可用 | POST 生成提议 | 200 `{proposal: null, degraded: true}`；`timing_proposals` 无新行；响应不含错误码；愿望数据零变化 |
| ST-S03-20 | 新提议替代旧 pending | 分支 P7 | 已有 pending 提议 | 再次 POST 生成 | 旧提议转 `expired`，新提议 `pending`；任意时刻 pending 行数 ≤ 1（部分唯一索引兜底） |
| ST-S03-21 | 通知文案仍为模板拼接 | 分支 P15 + 主图 Step 15 说明 | ST-S03-16 完成后 | 检查 outbox 文案与 mock 调用统计 | 文案逐字含用户原话摘要；确认与调度全链路 LLM `chat_completions` 调用次数为 0（`propose_timing` 除外） |

## 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：ST-S03-01、ST-S03-11
- [x] Phase 1 异常验收条件（2 条）：ST-S03-04、ST-S03-07
- [x] EX 异常用例（9 个）：EX-4.1→ST-04、EX-4.2→ST-05、EX-9.1→ST-06、EX-11.1→ST-03、EX-14.1→ST-07/12、EX-14.2→ST-08、EX-16.1→ST-09、EX-16.2→ST-10、EX-20.1→ST-11
- [x] API required 字段：`type`（UT-01）覆盖；组合必填（season/month_day/after_months）UT-03~07 覆盖
- [x] DB UNIQUE/CHECK 约束：`idx_reminder_outbox_once`（UT-13）、`delivered_count` CHECK（UT-14）、`status` CHECK（UT-15）、`delivered_has_channel`（UT-16）、周计数 PK（UT-17）、`endpoint` UNIQUE（UT-18）、两条 wishes CHECK（UT-11/12）全部覆盖
- [x] Phase 2 交互级验收条件（4 条）：ST-S03-01/04/07/11
- [x] S08 增量 EX 异常用例（5 个）：EX-P.1→ST-19、EX-P.2→UT-37/38、EX-P.3→ST-17、EX-P.4→UT-35、EX-P.5→ST-18
- [x] S08 增量 DB 约束：`idx_timing_proposals_single_pending`（UT-33）、`status` CHECK（UT-31）、`decided_state_pairing`（UT-32）、`confidence` CHECK（UT-30）全部覆盖
- [x] 四层边界断言：模型不落时间（UT-40）、确认不接受时间字段（UT-35）、调度器不读提议（UT-40 间接 + ST-21）

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S03） | 覆盖用例 |
|-------|------------------------|---------|
| S03-AC-01 | 正常：约定季节触发并在时机到达时收到通知 | ST-S03-01, UT-S03-19, UT-S03-26 |
| S03-AC-02 | 正常：时机到达但用户选择顺延 | ST-S03-11, UT-S03-28 |
| S03-AC-03 | 异常：用户选择不必提醒 | ST-S03-04, UT-S03-21 |
| S03-AC-04 | 异常：同一时间窗口内多张卡片同时触发 | ST-S03-07, ST-S03-12, UT-S03-23 |
| S08-AC-03 | 异常（S08 增补）：模型提议未经确认不会变成任何提醒 | ST-S03-16（确认前无副作用 + 确认后走既有预算）、ST-S03-17、UT-S03-35/36/40 |
| S08-AC-04（建议部分） | 异常（S08 增补）：建议依据被撤回/删除后不再引用 | ST-S03-18、UT-S03-37/38 |
