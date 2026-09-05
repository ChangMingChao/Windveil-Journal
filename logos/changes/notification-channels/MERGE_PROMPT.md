# 合并指令

## 变更提案
- 提案名称：notification-channels
- 提案目录：logos/changes/notification-channels/

## 提案内容

# 变更提案：notification-channels

> module: core | created: 2026-09-05

## 变更原因
来自编排测试总索引的待确认项 OQ-3 剩余部分：IA 5.1「静默通道」与 5.4 要求用户可在 P6 关闭推送仅保留邮件、或全部关闭，`users.push_enabled / email_enabled` 两列自建表起就存在，但 **API 中没有任何写入端点**——用户目前无法关闭提醒通道。preferences-availability-timing 已关闭该条「用户无法管理自己的数据」部分，本次随 P6「我的」的完整建模关闭剩余缺口。

同时补齐 P6「我的」页面的场景建模：此前 P6 从未进入时序图（S01–S09 均未覆盖），是唯一没有场景归属的常驻页面。

### 2026-09-03 技术评估口径
OQ-3：「为 P6 补一个场景，走完 Step 1 → Step 2 → Step 4a/4b 的正常流程，而不是直接往 auth.yaml 里加端点。」

## 收敛决策（请重点确认）
| 决策点 | 本提案 | 理由 |
|--------|--------|------|
| 范围 | **提醒通道开关**（push_enabled / email_enabled 的读写）+ P6 场景建模（S10） | 这是 OQ-3 的明确剩余缺口，也是「不制造焦虑」原则的用户自控出口 |
| 端点形态 | `PATCH /me/notification-channels`（一个端点管两个开关）而非 PATCH /me 整体资料 | 两个开关语义独立且是 P6 唯一的可写字段；独立资源路径让部分更新语义清晰，也为后续 P6 扩展（导出、注销）留出各自端点 |
| 行为细节 | 关闭全部通道 = 完全静默（应用内也不再有催促标记）；切换立即生效；已入 outbox 的 pending 记录不删除——投递时按最新开关选择通道，全关则顺延到重开 | IA 5.1「关闭后不再有任何应用内催促标记」；pending 是用户已确认时机的产物，关通道不应吞掉它们 |
| 邮件兜底的边界 | push 关闭但 email 开启时：投递直接走邮件（不先试 push）；全部关闭时：outbox 保持 pending 且顺延 | 避免对已关闭通道的无谓调用；「全部关闭 = 完全静默」语义清晰 |
| 导出与注销 | **裁剪为后续提案** | 导出涉及全量数据组装与格式设计、注销涉及级联删除与冷静期，各自是独立提案的体量 |
| 新增场景 | **S10「管理提醒通道」**（P6 页面，`scenario_counter.next_id=10`） | OQ-3 的建议路径：走完整建模流程而非裸加端点 |

## 变更类型
接口级

一个新端点 + 投递通道选择逻辑微调 + P6 场景建模。不改数据表（两列已存在）、不影响愿望与轻事件链路。因涉及新场景与投递行为变化，按全链路处理但范围最小。

## 变更范围
- 影响的需求文档：
  - `prd/1-product-requirements/core-01-requirements.md` — 新增 S10 场景（3 条验收条件）、5.1 静默通道条目细化、追溯表更新
- 影响的功能规格：
  - `prd/2-product-design/1-feature-specs/core-07-notification-channels-design.md` — 新增：P6 提醒通道区交互规格
- 影响的信息架构：
  - `prd/2-product-design/1-feature-specs/core-00-information-architecture.md` — 场景映射加 S10、P6 描述细化、追溯表加行
- 影响的业务场景：
  - `S10` — 新增场景时序图（使用全局 `scenario_counter.next_id=10`）
- 影响的技术架构：
  - `prd/3-technical-plan/1-architecture/core-01-architecture-overview.md` — 投递的通道选择逻辑（按最新开关）、场景清单加 S10
- 影响的 API：
  - `api/auth.yaml` — 新增 `PATCH /me/notification-channels`；开关状态经 `GET /me` 的 UserProfile 扩展字段返回
- 影响的 DB 表：
  - 无（`users.push_enabled / email_enabled` 已存在）
- 影响的测试用例：
  - `test/core-S10-test-cases.md` — 新增：开关读写 / 投递通道选择 / 全关顺延 / 隔离
- 影响的编排测试：
  - `scenario/core-S10-channels.json` — 新增编排文件；`scenario/core-00-orchestration-index.json` — 登记 S10 并更新 coverage，**OQ-3 标记 fully_resolved**
- 影响的部署方案：
  - `prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` — 无迁移；smoke 不新增（开关行为属 ST 层）

## 明确不做（本提案边界）
- 不做数据导出与账号注销（各自独立提案）；
- 不做按愿望粒度的提醒开关（全局开关已满足 IA 5.1，愿望粒度会显著复杂化预算逻辑）；
- 不做定时免打扰（quiet hours）——与可用时段数据的关系需单独设计；
- pending outbox 记录不因关通道被删除——投递时按最新开关决定通道与时机。

## 部署影响
- 是否需要部署：是
- 部署原因：新端点 + 投递通道选择逻辑变化
- 影响环境：本地 / 测试 / 预发 / 生产（生产部署仍需单独授权）
- 是否涉及数据迁移：否（两列已存在）
- 是否需要回滚预案：是——应用回滚沿用上一镜像；开关数据由既有列承载，无兼容风险
- 是否需要 smoke：不新增——通道开关行为属 ST 层；既有 SMOKE-core-12（调度投递）在默认开关下行为不变

## UI/UX 变更声明

```yaml
ui_impact: true
design_system_mode: generated
design_system_fallback_reason: ""
pages: []
description: 无新增屏幕。P6「我的」页（已有锚点区）新增「提醒通道」开关区（推送 / 邮件两个开关），复用既有设计令牌；关闭全部时的文案为「先安静一段时间，想听的时候随时打开」。
```

## 变更概述
为 P6「我的」补齐提醒通道管理：`PATCH /me/notification-channels` 读写 `users.push_enabled / email_enabled`，新场景 S10 建模 P6 页面的通道开关交互，开关状态经 `GET /me` 一并返回。投递逻辑同步微调：Scheduler 投递时读取最新开关——推送关闭则直接走邮件；全部关闭则 outbox 记录保持 pending 并顺延（用户重开后自然恢复），用户已确认的时机不丢失。切换立即生效、无冷静期、无确认弹层——安静是用户的选择，不是需要确认的操作。

## 后续提案路线（本提案不做）
1. **数据导出**：全量数据组装（愿望/记忆/偏好/轻事件）与格式设计。
2. **账号注销**：级联删除 + 冷静期 + 邮件确认。
3. **按愿望粒度的提醒开关**：单卡静音（当前只有全局开关）。


## 需要合并的 Delta 文件

### 1. deltas/api/auth.yaml

- Delta 文件：`logos\changes\notification-channels\deltas\api\auth.yaml`
- 目标目录：`logos\resources\api/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 2. deltas/prd/1-product-requirements/core-01-requirements.md

- Delta 文件：`logos\changes\notification-channels\deltas\prd\1-product-requirements\core-01-requirements.md`
- 目标目录：`logos\resources\prd\1-product-requirements/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 3. deltas/prd/2-product-design/1-feature-specs/core-00-information-architecture.md

- Delta 文件：`logos\changes\notification-channels\deltas\prd\2-product-design\1-feature-specs\core-00-information-architecture.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 4. deltas/prd/2-product-design/1-feature-specs/core-07-notification-channels-design.md

- Delta 文件：`logos\changes\notification-channels\deltas\prd\2-product-design\1-feature-specs\core-07-notification-channels-design.md`
- 目标目录：`logos\resources\prd\2-product-design\1-feature-specs/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 5. deltas/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md

- Delta 文件：`logos\changes\notification-channels\deltas\prd\3-technical-plan\1-architecture\core-01-architecture-overview.md`
- 目标目录：`logos\resources\prd\3-technical-plan\1-architecture/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 6. deltas/prd/3-technical-plan/2-scenario-implementation/core-S10-channels.md

- Delta 文件：`logos\changes\notification-channels\deltas\prd\3-technical-plan\2-scenario-implementation\core-S10-channels.md`
- 目标目录：`logos\resources\prd\3-technical-plan\2-scenario-implementation/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 7. deltas/scenario/core-00-orchestration-index.json

- Delta 文件：`logos\changes\notification-channels\deltas\scenario\core-00-orchestration-index.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 8. deltas/scenario/core-S10-channels.json

- Delta 文件：`logos\changes\notification-channels\deltas\scenario\core-S10-channels.json`
- 目标目录：`logos\resources\scenario/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

### 9. deltas/test/core-S10-test-cases.md

- Delta 文件：`logos\changes\notification-channels\deltas\test\core-S10-test-cases.md`
- 目标目录：`logos\resources\test/`
- 操作：读取 delta 中的 ADDED / MODIFIED / REMOVED 标记，合并到目标目录中对应的主文档

## 执行要求

1. 逐个 Delta 文件处理，每处理完一个报告修改摘要
2. 对于 ADDED 标记：在主文档的指定位置插入新内容
3. 对于 MODIFIED 标记：替换主文档中同名章节的内容
4. 对于 REMOVED 标记：从主文档中删除对应章节
5. 保持主文档的原有格式和风格
6. 如果主文档有"最后更新"时间戳，同步更新
7. 所有变更完成后，列出修改清单
8. 所有变更合并完成后，自动执行 git commit（告知用户，无需确认）：
   git add -A && git commit -m "docs(notification-channels): merge spec deltas"
   然后提示用户：按更新后的规格实现代码，代码完成后运行 `openlogos verify` 验收，验收通过后明确授权执行 `openlogos archive notification-channels`。
