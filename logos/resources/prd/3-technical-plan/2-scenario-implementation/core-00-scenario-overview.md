# 业务场景概览（技术实现）

> 最后更新：2026-09-01
> 模块：core｜阶段：Phase 3 Step 1 场景建模
> 上游：需求文档 S01–S07、Phase 2 交互规格、`../1-architecture/core-01-architecture-overview.md`

## 场景地图

| 编号 | 场景名称 | 分组 | 优先级 | Phase 1 | Phase 2 | Phase 3 时序图 | API 设计 | 编排测试 | 状态 |
|------|---------|------|--------|---------|---------|--------------|---------|---------|------|
| S01 | 新用户建立自己的未发生之地 | F01 | P0 | ✅ | ✅ | ✅ | 🔲 | 🔲 | 建模完成 |
| S02 | 随手种下一个愿望并被理解 | F01 | P0 | ✅ | ✅ | ✅ | 🔲 | 🔲 | 建模完成 |
| S03 | 为一个愿望约定属于它的时机 | F02 | P0 | ✅ | ✅ | ✅ | 🔲 | 🔲 | 建模完成 |
| S04 | 风来了，开始第一小步 | F02 | P0 | ✅ | ✅ | ✅ | 🔲 | 🔲 | 建模完成 |
| S05 | 回看未发生之地并重新整理 | F03 | P1 | ✅ | ✅ | ✅（S05.1 / S05.2 两图） | 🔲 | 🔲 | 建模完成 |
| S06 | 把发生过的事写成一页记忆 | F04 | P0 | ✅ | ✅ | ✅ | 🔲 | 🔲 | 建模完成 |
| S07 | 唤回一个被安静放下的愿望 | F03 | P2 | ✅ | ✅ | ✅ | 🔲 | 🔲 | 建模完成 |

本轮变更将 S07 从 P2 占位提升为 launched 后首个增量场景。S07 只覆盖「用户主动从安静放下区唤回」；种下新愿望时命中相似已放下记录不在本次建模范围。

## 功能分组

| 分组 | 名称 | 场景 | 对应 feature-specs |
|------|------|------|-------------------|
| F01 | 愿望记录与理解 | S01, S02 | `core-01-seeding-design.md` |
| F02 | 时机与陪伴推进 | S03, S04 | `core-02-unhappened-place-design.md` |
| F03 | 未发生之地浏览与整理 | S05, S07 | `core-02-unhappened-place-design.md` |
| F04 | 已发生之书 | S06 | `core-03-book-of-happened-design.md` |

## 场景依赖关系

```text
S01（建立个人空间 + 第一个愿望）
  └─ 是其余全部场景的前置：没有匿名主体就没有 owner_id，RLS 直接过滤掉一切

S02（种下愿望）
  └─ 产出「刚种下」状态的愿望，是 S03 的输入
       └─ S03（约定时机）产出「正在酝酿」+ next_trigger_at
            └─ S04（第一小步）由 S03 的提醒或用户主动触发，产出「正在发生」
                 └─ S06（写成记忆）从「正在发生」进入终态「已经发生」

S05.1（浏览）无前置依赖，空状态也可访问
S05.2（整理）可作用于除「已经发生」外的任意状态，是 S03/S04 的逃逸出口
S06 也可直接从「刚种下」进入（见 S06 的 EX-4.1，事情可能在产品之外自然发生）
S07（唤回）以 S05.2 产出的「安静放下」为前置
```

跨场景的两处强耦合，实现时必须一起改：

1. **提醒队列的生命周期**：S03 写入 `reminder_outbox`，S05.2（放下）与 S06（标记已发生）都必须清空它。任何新增的状态迁移都要检查这一点。
2. **周预算计数**：S03 的时机提醒、S04 的 60 天停滞关心共用同一份「每用户每周 ≤ 3 条」额度，投递失败不消耗额度。

## 从时序图浮现的 API 清单（Phase 3 Step 2 的输入）

时序图中每一个跨越系统边界的箭头对应一个接口。以下清单是 api-designer 的直接输入；**不在此表中的接口需要先回到时序图找出处**。

| 方法与路径 | 来源 | 用途 |
|-----------|------|------|
| `POST /api/v1/auth/anonymous` | S01 Step 3 | 无表单建立匿名个人空间 |
| `POST /api/v1/auth/link-email` | S01 待补设计 | 后置绑定邮箱以便换设备找回 |
| `GET /api/v1/me` | S01 EX-12.1 | 读 `onboarded_at` 判断是否已完成首次体验 |
| `POST /api/v1/onboarding/answers` | S01 Step 9 | 提交温柔问题答案，可为空数组 |
| `POST /api/v1/media/upload-url` | S02 Step 3 | 申请预签名 PUT |
| `POST /api/v1/media/{id}/complete` | S02 Step 7 | 声明上传完成并校验对象 |
| `POST /api/v1/wishes` | S01 Step 13 / S02 Step 12 | 种下愿望（text 或 voice） |
| `POST /api/v1/wishes/{id}/answer` | S01 Step 22 / S02 Step 24 | 回答或跳过 Agent 追问 |
| `POST /api/v1/wishes/{id}/understanding` | S01 EX-16.1 | 补做理解（用户重试 / Scheduler 重试） |
| `POST /api/v1/wishes/{id}/transcription` | S02 EX-15.1 | 重试语音转写 |
| `GET /api/v1/wishes` | S05.1 Step 2 / S07 Step 2 | 花园列表，支持 `state` 与游标分页；S07 使用 `state=let_go` |
| `GET /api/v1/wishes/{id}` | S03 Step 1 / S07 Step 7 | 详情页，S07 读取原话、首次种下时间与放下时间 |
| `PUT /api/v1/wishes/{id}/timing` | S03 Step 4 / S07 Step 14 | 约定时机（6 种 type）；S07 唤回后复用 |
| `POST /api/v1/wishes/{id}/ready` | S03 Step 20 / S04 Step 2 | 我好像准备好了 |
| `POST /api/v1/wishes/{id}/defer` | S03 EX-20.1 | 还不是现在 |
| `POST /api/v1/wishes/{id}/steps/next` | S04 Step 5 / Step 19 | 取下一个最小步骤（可带 `rejected_step_id`） |
| `POST /api/v1/wishes/{id}/steps/{step_id}/done` | S04 Step 14 | 标记步骤完成 |
| `POST /api/v1/wishes/{id}/messages` | S04 EX-23.1 | 与 Agent 对话（含修改愿望、疲惫信号） |
| `PATCH /api/v1/wishes/{id}` | S05.2 Step 15 | 改一改它 |
| `POST /api/v1/wishes/{id}/pause` | S05.2 Step 15 | 暂时不提醒 |
| `POST /api/v1/wishes/{id}/back-to-brewing` | S05.2 Step 15 | 先放回酝酿 |
| `POST /api/v1/wishes/{id}/let-go` | S05.2 Step 17 | 安静放下 |
| `POST /api/v1/wishes/{id}/recall` | S07 Step 10 | 重新种下一个已安静放下的愿望 |
| `DELETE /api/v1/wishes/{id}?confirm=true` | S05.2 Step 25 | 彻底删除（服务端强制确认） |
| `POST /api/v1/wishes/{id}/happened` | S06 Step 3 | 标记已发生并生成记忆草稿 |
| `PATCH /api/v1/memories/{id}` | S06 Step 12 | 保存记忆页编辑 |
| `POST /api/v1/memories/{id}/publish` | S06 Step 16 | 收进书里 |
| `GET /api/v1/memories` | S06 Step 20 | 已发生之书书架 |
| `GET /api/v1/memories/{id}` | S06 Step 20 | 单页记忆阅读态 |
| `GET /api/v1/health` | 架构文档 | 健康检查 |
| `GET /api/test/outbox` | 架构文档外部依赖表 | 仅 `APP_ENV=test` 注册，断言周预算与去重 |
| `GET /api/test/latest-email` | 架构文档外部依赖表 | 仅 `APP_ENV=test` 注册，断言邮件兜底 |

`Scheduler → PUSH / MAIL` 与 `API → LLM / ASR / OBJ` 都是出站调用，不产生对外 HTTP 接口。

> Phase 3 Step 2 实际产出 37 个端点：本表 32 项，加上 `POST /auth/login`、`/auth/refresh`、`/auth/logout`（「待补设计 1」邮箱绑定的必然配套）与 `POST /api/test/clock`、`/api/test/scheduler/tick`（架构第七节的 `fixed-value` 时钟注入与 smoke 手动触发）。详见 `logos/resources/api/`。

## 异常用例编号约定

Skill 规定的格式是 `EX-{步骤编号}.{序号}`，因此同一编号会在不同场景文件中重复出现（如 S01 的 `EX-16.1` 与 S02 的 `EX-18.1` 是两回事）。**跨文档引用时必须带场景前缀**，写作 `S01 EX-16.1`。本轮共设计 50 个异常用例：

| 场景 | 异常用例数 | 其中来自 Phase 1/2 验收条件 | 其中为新增技术异常 |
|------|-----------|---------------------------|------------------|
| S01 | 6 | 2 | 4 |
| S02 | 8 | 4 | 4 |
| S03 | 9 | 3 | 6 |
| S04 | 7 | 4 | 3 |
| S05 | 8 | 3 | 5 |
| S06 | 8 | 3 | 5 |
| S07 | 4 | 2 | 2 |
| 合计 | 50 | 21 | 29 |

每一条涉及外部调用的步骤（LLM、ASR、对象存储、推送、邮件、数据库）都至少有 1 个异常用例覆盖。S07 不新增外部依赖，重点覆盖状态迁移、幂等边界与 owner 隔离。

## 待补设计（建模过程中发现的缺口）

1. **账号从哪来（影响 S01，需回填 Phase 2）**：Phase 2 的 W1–W4 原型里没有任何注册表单，但需求文档 S01 要求「建立仅该用户可见的个人空间」。建模时按「点『开始』即建立匿名主体、邮箱绑定后置到 `/me`」处理——这是与「≤90 秒种下第一个愿望」唯一相容的方案。**需要在 Phase 2 补一屏 `/me` 的邮箱绑定交互**，否则用户换设备后会永久失去自己的愿望。
2. **「当我主动提到很累时」的触发通路（影响 S03）**：这不是时间条件，Scheduler 扫不到。已设计为由 S04 的对话链路检出疲惫信号后回写 `next_trigger_at`（见 S03 EX-11.1），但该交互在 Phase 2 没有对应界面表达。
3. **草稿期的状态表达（影响 S06）**：记忆页处于 `draft` 时，愿望状态仍是「正在发生」而提醒已停。Phase 2 未定义这个中间态在 `/garden` 卡面上如何显示。

## 场景索引

| 场景 | Phase 1 | Phase 2 | Phase 3 时序图 |
|------|---------|---------|--------------|
| S01 | `../../1-product-requirements/core-01-requirements.md` | `../../2-product-design/1-feature-specs/core-01-seeding-design.md` | `core-S01-onboarding-first-wish.md` |
| S02 | 同上 | 同上 | `core-S02-seed-wish.md` |
| S03 | 同上 | `../../2-product-design/1-feature-specs/core-02-unhappened-place-design.md` | `core-S03-set-timing.md` |
| S04 | 同上 | 同上 | `core-S04-first-small-step.md` |
| S05 | 同上 | 同上 | `core-S05-browse-and-tidy.md` |
| S06 | 同上 | `../../2-product-design/1-feature-specs/core-03-book-of-happened-design.md` | `core-S06-write-memory-page.md` |
| S07 | 同上 | `../../2-product-design/1-feature-specs/core-02-unhappened-place-design.md` | `core-S07-recall-let-go-wish.md` |
