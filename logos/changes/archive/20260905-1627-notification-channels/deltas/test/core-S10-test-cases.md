# delta — core-S10-test-cases.md（notification-channels，全新文件）

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S10-channels.md`（22 Steps + D 支线 / 2 EX）
> API：`../api/auth.yaml`（PATCH /me/notification-channels、GET /me 扩展）｜DB：users.push_enabled / email_enabled（既有列）

## ADDED — S10: 管理提醒通道测试用例

## 一、单元测试用例

### 1.1 API 行为（来源：auth.yaml → updateNotificationChannels）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S10-01 | 空请求体被拒 | `minProperties: 1` | 已登录 | `{}` | 422 `VALIDATION_FAILED` |
| UT-S10-02 | 只更新提交的字段 | S10 Step 8 | push=1, email=1 | `{push_enabled: false}` | 200 返回 push=false、email 不变 |
| UT-S10-03 | 开关状态随 GET /me 返回 | UserProfile 扩展 | 已登录 | `GET /me` | 响应含 push_enabled / email_enabled |
| UT-S10-04 | 未知字段被忽略或拒绝（以实现为准，拒绝更严格） | Pydantic 额外策略 | 已登录 | `{"foo": 1}` | 422 `VALIDATION_FAILED` |
| UT-S10-05 | 切换不影响愿望/轻事件/偏好数据 | S10 验收-异常 | 已有各数据 | PATCH 开关后逐项读取 | 全部不变 |

### 1.2 业务规则（投递侧通道选择，来源：S10 D 支线）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S10-06 | push 关 + email 开 → 直接走邮件（不试 push） | D2 | pending 记录；push 关 | 投递一轮 | `channel='email'`；push 尝试次数为 0 |
| UT-S10-07 | 全关 → 跳过且保持 pending | EX-D2.1 | pending 记录；两开关全关 | 投递一轮 | outbox 记录仍 pending、attempts 不变、未计入统计；用户重开后下一轮恢复 |
| UT-S10-08 | 恢复后受周预算约束 | EX-D2.1 | 全关期间到期多条；重开 email；本周已 3 条 | 重开后投递一轮 | 顺延语义不变，`deferred_to_next_week` 行为与既有一致 |
| UT-S10-09 | 投递成功才置 delivered 与累加计数 | D3 | 跳过场景 | 检查 delivered_count | 跳过不计入任何统计 |
| UT-S10-10 | 开关在投递同一时刻读取 | 架构 5.7 并发语义 | pending + 全关 | 投递中途切换开关（时钟窗口内） | 最坏情况按旧通道投出一条，无竞态崩溃 |

## 二、场景测试用例

### 2.1 主路径与异常

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S10-01 | 关闭推送保留邮件，投递直接走邮件 | Step 1→10 + D2 | 已有即将到期愿望与 push 订阅；push/email 均开 | PATCH 关 push → 时钟推进 → 投递一轮 | `channel='email'`；push_subscriptions 行保留；重开 push 后恢复双通道 |
| ST-S10-02 | 全关 = 完全静默、重开恢复且不丢时机 | 验收-正常2 + EX-D2.1 | 已有到期愿望与 pending 记录 | 全关 → 投递两轮（均跳过）→ 重开 email → 再投递一轮 | 全关期间 outbox pending 保持、attempts 不变；重开后 delivered 且文案完整 |
| ST-S10-03 | 快速连续切换互不牵连 | 验收-异常 | 已登录 | 连续 PATCH 只改 push / 只改 email 交替三次 | 每次响应仅目标开关变化；另一开关与愿望/轻事件/偏好数据全部不变 |
| ST-S10-04 | 跨用户无法修改他人开关 | S05 EX-3.1 同策略 | 两个账号 | B 用 A 的会话语义不可达——开关只作用于当前 token 用户；B PATCH 后 A 的开关不变 | B 只改自己的；A 的开关保持 |

### 2.2 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S10-05 [manual] | 全关文案「先安静一段时间，想听的时候随时打开」与开关触控区（44px）走查 | Step 5→6 | 真实浏览器对照 core-07 规格 |

## 三、覆盖度校验

- [x] 需求 S10 正常验收条件（2 条）：AC-01（关推送走邮件）→ ST-S10-01、AC-02（全关静默不丢时机）→ ST-S10-02
- [x] 需求 S10 异常验收条件（1 条）：AC-03（切换立即生效互不牵连）→ ST-S10-03、UT-S10-02/05
- [x] EX 异常用例（2 个）：EX-7.1→（保存失败回滚，前端行为，服务端 5xx 语义由 UT 覆盖）、EX-D2.1→UT-S10-07/ST-S10-02
- [x] 投递侧：通道选择（UT-06）、跳过不计数（UT-09）、预算约束（UT-08）、并发读（UT-10）
- [x] 隔离：开关只作用于当前 token 用户（UT-S10-04 的 token 语义 + ST-04）

## 四、验收条件追溯

| AC ID | 验收条件（需求 S10） | 覆盖用例 |
|-------|---------------------|---------|
| S10-AC-01 | 正常：关闭推送、保留邮件 | ST-S10-01, UT-S10-06 |
| S10-AC-02 | 正常：全部关闭 = 完全静默，已确认的时机不丢失 | ST-S10-02, UT-S10-07/08 |
| S10-AC-03 | 异常：开关切换立即生效且互不牵连 | ST-S10-03, UT-S10-02/05 |
