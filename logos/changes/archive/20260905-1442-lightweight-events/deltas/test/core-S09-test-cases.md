# delta — core-S09-test-cases.md（lightweight-events，全新文件）

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S09-lite-events.md`（22 Steps / 4 EX）
> API：`../api/lite-events.yaml`｜DB：`../database/schema.sql`（lite_events）

## ADDED — S09: 先记一下并随手划掉测试用例

## 一、单元测试用例

### 1.1 API 字段约束（来源：lite-events.yaml → createLiteEvent 等）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S09-01 | text 必填且 1–200 字 | `createLiteEvent.text` | 已登录 | 空 / 201 字 / 200 字 | 422 / 422 / 201 |
| UT-S09-02 | 全空白文本被拒 | S09 验收-异常3 | 已登录 | `"   "` | 422 `VALIDATION_FAILED`（服务端双层防御） |
| UT-S09-03 | 默认列表只含 open 状态 | `listLiteEvents.include_done` | 已有 open + done 各 1 条 | `GET /lite-events` | 默认仅 open；`include_done=true` 时 done 也返回且 closed_at 非空 |
| UT-S09-04 | POST 响应回显保存确认 | S09 Step 12 | 已登录 | 记下「今晚吃火锅」 | 201 且 `text` 与提交一致（轻事件是当下事项，与偏好 value 的不回显策略不同） |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S09-05 | status 只允许 open/done | `lite_events.status CHECK` | — | `status='sent'` | 违反 CHECK |
| UT-S09-06 | done 与 closed_at 配对 | `lite_events_closed_state_pairing CHECK` | — | `status='done'` 且 `closed_at=NULL`；`status='open'` 且 `closed_at` 非空 | 均违反 CHECK |
| UT-S09-07 | open 列表部分索引 | `idx_lite_events_owner_open` | 已有 open 与 done 各若干 | 直查索引使用 | 索引仅覆盖 `status='open'` 行 |
| UT-S09-08 | 三重无提醒路径（结构性） | 架构 5.6 | 建表后检查 | 检查 `lite_events` 列清单与 Scheduler 扫描 SQL | 无任何触发时间/提醒字段；调度扫描不引用该表；`reminder_outbox` 无关联路径 |

### 1.3 业务规则（来源：时序图步骤说明）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S09-09 | 划掉置 done 并记 closed_at | S09 Step 15→17 | 已有 open 行 | POST done | 200；status=done、closed_at 非空 |
| UT-S09-10 | 对已划掉的事件重复 done → 409 | EX-14.1 | 已 done 行 | 再次 POST done | 409 `LITE_EVENT_ALREADY_CLOSED`（幂等保护而非静默重放） |
| UT-S09-11 | 删除为硬删除 | S09 Step 21、EX-22.1 | 已删除一行 | 直查表 + include_done | 行不存在；重复 DELETE 404；无任何计数 |
| UT-S09-12 | 跨用户访问一律 404 | EX-22.1、S05 EX-3.1 同策略 | 用户 B 的 token | 读写用户 A 的轻事件 | 全部 404；审计日志只含标识符 |

## 二、场景测试用例

### 2.1 主路径与异常

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S09-01 | 记下 → 列表 → 划掉 → 收走全链路 | Step 1→22 | 已登录 | 记两条 → 划掉一条 → 收走另一条 | 列表按最近在上；划掉后默认列表不含；收走后 include_done 也不含；重复收走 404；outbox 全程无轻事件记录 |
| ST-S09-02 | 空内容与超长内容双层拒绝 | EX-9.1 | 已登录 | POST 空 / 全空白 / 201 字 | 均 422 且无写入行 |
| ST-S09-03 | 轻事件与愿望互不干扰 | S09 验收-正常2 | 已有愿望提醒（outbox 有 wish 相关行）与轻事件 | 任意轻事件操作后查 outbox 与愿望列表 | 轻事件操作不改变 outbox 与愿望；轻事件无提醒路径 |
| ST-S09-04 | 跨用户隔离 | EX-22.1 | 两个账号 | B 访问 A 的轻事件详情/划掉/收走 | 全部 404，不暴露存在性 |
| ST-S09-05 [manual] | P1「先记一下」展开/收起与空态文案走查 | Step 1→7 / EX-7.1 | 真实浏览器对照 `core-06` 原型 | 目视检查 | 无条数统计、无时间戳、无升格按钮；空态只有引导句 |

## 三、覆盖度校验

- [x] 需求 S09 正常验收条件（2 条）：AC-01（记下并划掉）→ ST-S09-01、AC-02（结构上无提醒）→ ST-S09-03、UT-S09-08
- [x] 需求 S09 异常验收条件（2 条）：AC-03（空内容）→ ST-S09-02、UT-S09-01/02、AC-04（收走无影子）→ ST-S09-01、UT-S09-11
- [x] EX 异常用例（4 个）：EX-7.1→ST-S09-05（人工）/UT-03、EX-9.1→ST-02、EX-14.1→UT-10、EX-22.1→ST-04/UT-11/12
- [x] DB CHECK：status 枚举（UT-05）、closed 配对（UT-06）、部分索引（UT-07）
- [x] 隐私红线：text_enc 加密（部署方案加密落地 smoke 项覆盖）、跨用户 404（UT-12）

## 四、验收条件追溯

| AC ID | 验收条件（需求 S09） | 覆盖用例 |
|-------|---------------------|---------|
| S09-AC-01 | 正常：记下并划掉 | ST-S09-01 |
| S09-AC-02 | 正常：轻事件在结构上不产生提醒 | ST-S09-03, UT-S09-08 |
| S09-AC-03 | 异常：空内容不保存 | ST-S09-02, UT-S09-01/02 |
| S09-AC-04 | 异常：收走是彻底的，不留影子 | ST-S09-01, UT-S09-11/12 |
