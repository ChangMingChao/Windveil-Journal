# delta — core-01-architecture-overview.md（notification-channels）

## ADDED — 5.7 提醒通道自控与投递通道选择（notification-channels，S10）

```text
开关模型
  users.push_enabled / email_enabled（既有列），PATCH /me/notification-channels
  读写；切换立即生效（无冷静期、无确认）。全部关闭 = 完全静默。

投递侧通道选择（Scheduler 每轮投递时读取最新开关）
  push 开                    → 走 Push（410 失效 → 删订阅 → 转邮件，若邮件开）
  push 关 + email 开         → 直接走邮件（不对已关闭通道做无谓调用）
  全关                       → 跳过该 pending 记录：不投递、不计失败、不改退避、
                               不累加统计——保持 pending，下一轮再查；
                               用户重开任一通道后自然恢复（受周预算约束）
  「已确认的时机不因关通道丢失」由此保证：pending 记录永不因开关被删除。

并发语义
  开关在投递的同一事务/同一时刻读取，避免「读开关 → 用户切换 → 按旧值投递」
  的竞态错配；最坏情况是一条提醒在切换后 5 分钟内按旧通道投出——可接受。
```

## MODIFIED — 四、组件职责与代码结构

```text
frontend/                      React 19 + Vite（纯静态产物）
  src/pages/                   /、/welcome、/garden、/wish/:id、/book、/book/:id、/me
  src/components/              愿望卡、状态徽标、半屏、时间线、记忆页、建议卡（S08）、
                               轻事件区（S09）、提醒通道开关区（S10）
  src/theme/tokens.css         由 design-system.json 生成，禁止手改
  src/api/                     由后端 OpenAPI 生成的类型与客户端
backend/
  app/api/v1/                  路由层：仅做参数校验与调用 service
  app/services/                业务层：愿望状态机、提醒预算、记忆页组装、
                               偏好与可用时段、时机建议四层链路（S08）、
                               轻事件（S09）、通道开关与投递通道选择（S10）
  app/agent/                   LLMProvider 抽象、提示词、结构化输出模型、降级策略
  app/repositories/            数据访问，统一注入 owner_id
  app/models/                  SQLAlchemy 模型
  app/scheduler/               独立入口：扫描到期时机 → 写 outbox → 投递
                               （投递前按最新开关选择通道，S10）；
                               低频任务：提议过期扫描、偏好摘要生成（S08）。
                               轻事件不在任何扫描集合中（S09）
  migrations/                  Alembic
```

## MODIFIED — 九、场景清单（作为 Phase 3 Step 1 的输入）

| 编号 | 名称 | 优先级 | 参与方 |
|------|------|--------|--------|
| S01 | 新用户建立自己的未发生之地 | P0 | PWA、API、PG、LLM |
| S02 | 随手种下一个愿望并被理解 | P0 | PWA、API、PG、对象存储、ASR、LLM |
| S03 | 为一个愿望约定属于它的时机 | P0 | PWA、API、PG、Scheduler、Push、邮件 |
| S04 | 风来了，开始第一小步 | P0 | PWA、API、PG、LLM、Scheduler |
| S05 | 回看未发生之地并重新整理（S05.1 浏览 / S05.2 整理） | P1 | PWA、API、PG |
| S06 | 把发生过的事写成一页记忆 | P0 | PWA、API、PG、对象存储、LLM |
| S07 | 唤回一个被安静放下的愿望 | P2 | PWA、API、PG |
| S08 | 管理偏好与可用时段 | P1 | PWA、API、PG、LLM、Scheduler |
| S09 | 先记一下并随手划掉 | P1 | PWA、API、PG |
| S10 | 管理提醒通道 | P1 | PWA、API、PG、Scheduler |
