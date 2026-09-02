# S01: 新用户建立自己的未发生之地 — 测试用例

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S01-onboarding-first-wish.md`（25 Steps / 6 EX）
> API：`../api/auth.yaml`、`../api/wishes.yaml`｜DB：`../database/schema.sql`（users、onboarding_answers、wishes）

## 一、单元测试用例

### 1.1 API 字段约束（来源：auth.yaml、wishes.yaml）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S01-01 | timezone 缺省时取默认值 | `auth.yaml → createAnonymousSpace → timezone.default` | 无 | `{}` | `users.timezone = 'Asia/Shanghai'` |
| UT-S01-02 | timezone 非法 IANA 名被拒 | 同上（应用层校验） | 无 | `{"timezone": "Mars/Olympus"}` | 422 `VALIDATION_FAILED` |
| UT-S01-03 | answers 为必填 | `auth.yaml → submitOnboardingAnswers → required` | 已认证 | `{}` | 422 `VALIDATION_FAILED` |
| UT-S01-04 | answers 空数组合法 | 同上（跳过全部问题的路径） | 已认证 | `{"answers": []}` | 204，`onboarding_answers` 无新增行 |
| UT-S01-05 | answers 超过 10 项被拒 | `submitOnboardingAnswers → maxItems: 10` | 已认证 | 11 项 | 422 `VALIDATION_FAILED` |
| UT-S01-06 | answer_text 边界：500 字通过 / 501 字拒绝 | `answer_text.maxLength: 500` | 已认证 | 500 字 / 501 字 | 204 / 422 |
| UT-S01-07 | answer_text 允许为 null（该题留空） | `answer_text: [string, null]` | 已认证 | `{"question_key":"q1","answer_text":null}` | 204，`answer_enc IS NULL` |
| UT-S01-08 | question_key 缺失被拒 | `answers.items.required: [question_key]` | 已认证 | `{"answer_text":"x"}` | 422 `VALIDATION_FAILED` |
| UT-S01-09 | source=text 时缺 text 被拒 | `wishes.yaml → seedWish` | 已认证 | `{"source":"text"}` | 422 `WISH_TEXT_INVALID` |
| UT-S01-10 | text 边界：1 字通过 / 纯空白拒绝 | `text.minLength: 1` + 去空白规则 | 已认证 | `"海"` / `"   "` | 201 / 422 `WISH_TEXT_INVALID` |
| UT-S01-11 | text 边界：500 字通过 / 501 字拒绝 | `text.maxLength: 500` | 已认证 | 500 字 / 501 字 | 201 / 422 `WISH_TEXT_INVALID` |
| UT-S01-12 | source 非枚举值被拒 | `source.enum: [text, voice]` | 已认证 | `{"source":"image"}` | 422 `VALIDATION_FAILED` |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S01-13 | 匿名用户不得带 email | `users_anonymous_has_no_email CHECK` | 无 | `is_anonymous=1, email='a@b.c'` | 违反 CHECK，插入失败 |
| UT-S01-14 | email 与 password_hash 必须同时存在 | `users_email_password_together CHECK` | 无 | 只给 email 不给 hash | 违反 CHECK，插入失败 |
| UT-S01-15 | email 唯一 | `users.email UNIQUE` | 已有用户绑定 `a@b.c` | 另一用户绑定同 email | 唯一冲突 → 409 `EMAIL_ALREADY_LINKED` |
| UT-S01-16 | onboarded_at 建号时即写入 | `users.onboarded_at` 语义（S01 Step 4） | 无 | 调 `POST /auth/anonymous` | `onboarded_at IS NOT NULL` |
| UT-S01-17 | 同一 (owner_id, question_key) 重复提交为覆盖而非报错 | `onboarding_answers_unique_per_question UNIQUE` | 已答 q1 | 再次提交 q1 | upsert 覆盖，行数不变，返回 204 |
| UT-S01-18 | wishes.title_enc 非空约束 | `wishes.title_enc NOT NULL` | — | 尝试插入 title_enc=NULL | 违反 NOT NULL |
| UT-S01-19 | wishes.state 默认 seeded | `wishes.state DEFAULT 'seeded'` | — | 插入不指定 state | `state='seeded'` |
| UT-S01-20 | 加密列写入后直接查库不是可读明文 | 应用层 AES-256-GCM 约定 | — | 加密「想去看海」后写入 | `title_enc`/`original_text_enc` 为 BLOB 密文、不含原文子串，解密后可还原 |

### 1.3 业务规则（来源：时序图 Step 说明与架构约束）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S01-21 | 未带 access token 访问业务端点返回 401 | `auth.yaml → 401 UNAUTHENTICATED` | 无 | `POST /wishes` 无 Authorization | 401 `UNAUTHENTICATED` |
| UT-S01-22 | LLM 超时上限硬编码为 5 秒 | S01 Step 16、`LLM_TIMEOUT_SECONDS` | mock 端点延迟 6 秒 | 调 `understand_wish` | 5 秒内返回 `None`，不抛异常 |
| UT-S01-23 | WishUnderstanding schema 校验失败等同不可用 | S01 EX-16.2 | — | 传入缺 `kind` 字段的 JSON | 返回 `None`，不写库 |
| UT-S01-24 | 降级时标题回退为原话前 20 字 | S01 EX-16.1 | LLM 返回 None | 原话 30 字 | `title` == 原话前 20 字 |
| UT-S01-25 | 降级不记录 LLM 响应内容 | S01 EX-16.2 副作用（隐私红线） | LLM 返回非法 JSON | 触发降级 | 日志含响应长度与错误类型，**不含**响应正文 |
| UT-S01-26 | 落库与调用 LLM 分属不同事务 | S01 Step 14 | LLM 必失败 | 种下一个愿望 | `wishes` 行已提交存在，`understanding IS NULL` |

## 二、场景测试用例

### 2.1 主路径

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S01-01 | 完整走完温柔问题并种下第一个愿望 | Step 1→25 | 无用户，LLM mock 正常返回 | 建号 → 提交 3 题答案 → 种下「等压力没这么大的时候，想去海边待两天」→ 回答追问 | 201；`users.onboarded_at` 非空；`onboarding_answers` 3 行；`wishes` 1 行 `state=seeded`、`understanding` 非空、`title` 为提炼短句；响应 `question` 恰好 1 句；`answer_enc` 已写入 |
| ST-S01-02 | 跳过温柔问题直接种下 | Step 2→7、跳过 Step 8→11、Step 12→25 | 无用户 | 建号 → 提交 `answers: []` → 种下 → 点「先不说」 | 201；`onboarding_answers` 0 行；`wishes` 1 行；`pending_question=true` 且本次响应不再返回追问 |

### 2.2 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S01-03 | 匿名建号失败 | EX-3.1 | DB 连接不可用 | `POST /auth/anonymous` | 503 `SPACE_CREATE_FAILED`；`users` 无新增行；响应不含堆栈或 SQL |
| ST-S01-04 | 初始记忆写入失败仍返回 204 | EX-10.1 | `onboarding_answers` 写入被强制失败 | 提交 3 题答案 | 204；`onboarding_answers` 0 行；服务端记 error 日志；后续种下流程不受影响 |
| ST-S01-05 | 跳过问题后未输入任何内容即离开 | EX-12.1 | 已建号，未调 `POST /wishes` | 重新调 `GET /me` | `onboarded_at` 非空 → 客户端应进 `/garden`；`GET /wishes` 返回 `items: []`、无任何计数字段 |
| ST-S01-06 | 提交内容为空或超长 | EX-13.1 | 已建号 | `POST /wishes` 传 `text: "   "` 与 501 字 | 均 422 `WISH_TEXT_INVALID`；`wishes` 无新增行 |
| ST-S01-07 | LLM 超时降级 | EX-16.1 | LLM mock 延迟 6 秒 | 种下一个 30 字愿望 | 201 `degraded=true`、`question=null`；`wishes` 行存在且 `original_text` 完整；`title` 为原话前 20 字；`pending_agent_jobs` 新增 1 行 `job_kind=wish_understanding` |
| ST-S01-08 | LLM 返回非法 JSON 降级 | EX-16.2 | LLM mock 返回 `not-json` | 种下一个愿望 | 与 ST-S01-07 完全一致的对外表现；`understanding IS NULL`（绝不写半结构化结果） |

### 2.3 边界用例

| ID | 描述 | 覆盖 | 前置条件 | 触发条件 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S01-11 | 认证与字段边界的 HTTP 层复核 | UT-S01-05/06/07/21 的编排层验证 | 已建号 | 无 token 调业务端点；answers 提交 11 项；`answer_text: null` | 401 `UNAUTHENTICATED`；422；204 且 `answer_enc IS NULL` |

### 2.4 人工验证用例（[manual]）

> 以下用例需要真实浏览器渲染或视觉判断，无法在 CI 无头环境稳定断言。

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S01-09 [manual] | W1 欢迎屏的灯渐亮动效在 600ms 内完成，`prefers-reduced-motion: reduce` 下直接呈现终态 | Step 1 | 真实浏览器 + 系统「减少动态效果」开关对照 |
| ST-S01-10 [manual] | W2 跳过后不出现红点、补答提示或进度条 | Step 8 | 人工目视三种视口（375 / 768 / 1024） |

## 三、覆盖度校验

- [x] Phase 1 正常验收条件（2 条）：全部覆盖（ST-S01-01、ST-S01-02）
- [x] Phase 1 异常验收条件（2 条）：全部覆盖（ST-S01-05、ST-S01-07/08）
- [x] EX 异常用例（6 个）：全部覆盖（EX-3.1→ST-03、EX-10.1→ST-04、EX-12.1→ST-05、EX-13.1→ST-06、EX-16.1→ST-07、EX-16.2→ST-08）
- [x] API required 字段：`answers`（UT-03）、`source`（UT-09/12）、`question_key`（UT-08）全部覆盖
- [x] DB UNIQUE/CHECK 约束：`users.email` UNIQUE（UT-15）、两条 users CHECK（UT-13/14）、`onboarding_answers` UNIQUE（UT-17）、`wishes.state` DEFAULT（UT-19）全部覆盖
- [x] Phase 2 交互级验收条件（4 条）：ST-S01-01/02/05/07 覆盖，按钮 `disabled` 等纯视觉部分由 ST-S01-10 [manual] 兜底

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S01） | 覆盖用例 |
|-------|------------------------|---------|
| S01-AC-01 | 正常：完整走完温柔问题并种下第一个愿望 | ST-S01-01 |
| S01-AC-02 | 正常：跳过温柔问题直接种下 | ST-S01-02 |
| S01-AC-03 | 异常：跳过问题后又不输入任何内容就退出 | ST-S01-05 |
| S01-AC-04 | 异常：Agent 理解服务不可用 | ST-S01-07, ST-S01-08, UT-S01-22, UT-S01-24 |
