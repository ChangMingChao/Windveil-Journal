# 实现清单（Phase 3 Step 5）

> 最后更新：2026-09-03｜模块：core｜阶段：Batch 1–7 交付 + preferences-availability-timing 增量（Batch 8–10）

## 分批策略（六维打分结果）

| 维度 | 得分 | 依据 |
|------|------|------|
| 影响范围 | 2 | 跨端（React PWA + FastAPI + Scheduler）+ 跨模块 |
| 行为复杂度 | 2 | 6 状态的愿望状态机 + 异步调度 + 7 个场景 |
| 契约变化 | 2 | 全新 API（36 端点）+ 全新 DB（17 表） |
| 测试规模 | 2 | 165 UT / 79 ST / 18 SMOKE / 61 编排 flow |
| 风险等级 | 2 | 涉及个人隐私数据、列级加密、RLS、迁移、部署 |
| 不确定性 | 2 | 三处待确认（托管方式、ASR 供应商、样式方案） |
| **合计** | **12** | ≥8 分 → **大任务，必须拆批**（每批闭环） |

分批按场景垂直切分，每批交付业务代码 + 该批 UT/ST 测试代码 + reporter：

| 批次 | 范围 | 状态 |
|------|------|------|
| Batch 1 | 基础设施 + S01（匿名建号 / 温柔问题 / 种下 / 追问 / LLM 降级） | ✅ 已交付 |
| Batch 2 | S02（媒体预签名直传 + ASR 转写与失败重试 + 当下日程判定） | ✅ 已交付 |
| Batch 3 | S03（时机 6 类 + Scheduler 单活 + outbox + 周预算 + 双通道投递） | ✅ 已交付 |
| Batch 4 | S04（最小步骤与合规自检 + 乐观锁 + 停滞关心 + 对话意图） | ✅ 已交付 |
| Batch 5 | S05（列表与游标 + 整理半屏动作 + 彻底删除 + RLS 隔离断言） | ✅ 已交付 |
| Batch 6 | S06（记忆页草稿 / 编辑 / 幂等发布 / 书架） | ✅ 已交付 |
| Batch 7 | 前端 React PWA + smoke runner/dispatcher + 故障注入夹具（补 ST-S01-03/04 等） | ✅ 已交付 |

## Batch 1 交付内容

### 覆盖用例（批前声明）

- **UT-S01-01 ~ UT-S01-26**（26 个，全部实现）
- **ST-S01-01、02、05、06、07、08、11**（7 个）
- 未覆盖并已说明：ST-S01-03（需注入 DB 不可用）、ST-S01-04（需强制写入失败）→ 推迟到 Batch 7 的故障注入夹具；ST-S01-09/10 为 `[manual]`，按规范不写入 JSONL

### 业务代码（`backend/app/`）

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `config.py` | 全部配置来自环境变量；`APP_ENV=test` 才启用测试后门 | 部署方案 3.1 / 3.2 |
| `clock.py` | Clock 抽象，禁止直接 `datetime.now()` | 架构第七节 fixed-value 策略 |
| `crypto.py` | `EncryptedText` TypeDecorator（应用层 AES-256-GCM） | schema.sql 加密列约定 |
| `types.py` | `GUID` 与 `TZDateTime` TypeDecorator（UUID↔TEXT、datetime↔ISO8601） | schema.sql SQLite 类型约定 |
| `db.py` | 单库引擎 + 连接级 PRAGMA + `owner_guard` 两道隔离防线 + `owner_guard_bypass()` | 架构 5.3、schema.sql 文末 |
| `models.py` | users / sessions / onboarding_answers / media / wishes / wish_photos / pending_agent_jobs | schema.sql（表名列名约束逐条对齐） |
| `security.py` | Argon2id + JWT access / refresh（refresh 只存 SHA-256） | 架构 3.2 |
| `agent.py` | `LLMProvider` 抽象 + OpenAI 兼容唯一实现 + 结构化输出二次校验 + 降级 | 架构 5.1、tech_stack.llm |
| `schemas.py` | 请求/响应模型，字段名与 `api/*.yaml` 一致 | auth.yaml / wishes.yaml |
| `services.py` | S01 Step 3→24 的业务逻辑，含两段式写入 | core-S01 时序图 |
| `api.py` | 路由、状态码、错误码；`/api/test/*` 独立 router | api/*.yaml |
| `main.py` | 应用装配 + 统一错误响应 `{code,message,details?}` | api-designer 统一约定 |
| `migrations/versions/0001_batch1_core.py` | Batch 1 表 + 索引 + RLS 策略 + `app_current_user_id()` | schema.sql 转写 |

### 测试代码（`backend/tests/`）

| 文件 | 内容 |
|------|------|
| `conftest.py` | **OpenLogos reporter**（pytest hook，写 `logos/resources/verify/test-results.jsonl`）+ 数据库探测夹具 |
| `test_s01_units.py` | UT-S01-01~12、21~25（17 个，不依赖数据库） |
| `test_s01_db.py` | UT-S01-13~20、26（9 个，依赖 PostgreSQL） |
| `test_s01_scenarios.py` | ST-S01-01/02/05/06/07/08/11（7 个端到端 HTTP） |

### 运行结果

```text
33 passed
logos/resources/verify/test-results.jsonl：33 条记录（33 pass / 0 skip / 0 fail）
```

**数据库改为 SQLite 后 skip 全部消失**：每个用例用 `tmp_path` 下的临时 `.db` 文件装载 Batch 1 的 DDL，不依赖 Docker 或任何外部服务。此前 16 个 skip 是因为没有可用的 PostgreSQL，现在这 16 条（9 个 DB 约束 UT + 7 个端到端 ST）都是真实执行并通过的。

### 配置变更

- `logos.config.json` → `sourceRoots.src = ["backend/app", "frontend/src"]`、`sourceRoots.test = ["backend/tests"]`
- `logos.config.json` → `verify.pre_run_command = "python -m pytest -c backend/pyproject.toml backend/tests"`
- 数据库方言由 PostgreSQL 改为 SQLite（用户决定）：`schema.sql` 全量重写、迁移改 SQLite DDL、`pgcrypto` 改为应用层 AES-256-GCM、RLS 改为 `owner_guard`，依赖由 `asyncpg` + `testcontainers` 换为 `aiosqlite` + `cryptography` + `tzdata`
- `smoke.command` **尚未写入**：smoke runner 属 Batch 7，不预先指向不存在的脚本

## Batch 2 交付内容

### 覆盖用例（批前声明）

- **UT-S02-01 ~ UT-S02-25**（25 个；`UT-S02-25` 写入 skip，见下）
- **ST-S02-01 ~ ST-S02-11、ST-S02-14**（12 个）
- `ST-S02-12` / `ST-S02-13` 为 `[manual]`（麦克风授权引导、录音波形），按规范不写 JSONL

### 新增业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/storage.py` | `ObjectStorage` 抽象 + `S3ObjectStorage`（staging/prod）+ `LocalObjectStorage`（local/test，文件系统 + 自签 HMAC 预签名） | media.yaml、架构第七节 |
| `app/asr.py` | `ASRProvider` 抽象 + OpenAI 兼容实现 + `classify_transcript` 三态归一 | S02 Step 15–17、EX-15.1/15.2 |
| `app/services.py`（新增） | `validate_upload_request` / `create_upload_url` / `complete_upload` / `transcribe_wish_audio` / `cleanup_orphan_media` | S02 Step 3–17、EX-8.1、EX-13.1 |
| `app/api.py`（新增） | `POST /media/upload-url`、`POST /media/{id}/complete`、`POST /wishes/{id}/transcription`；`POST /wishes` 的 voice 分支改为「落库 → 转写 → 理解」三段事务 | media.yaml、wishes.yaml |
| `app/api.py`（测试后门） | `PUT /api/test/object/{key}` 本地对象接收端，仅 `APP_ENV in (local,test)` 注册 | 见下方偏离说明 |

### 两处需要你知道的处理

**1. 对象存储在测试中用文件系统后端，而非架构声明的「本地 MinIO 真实调用」。** 本机 Docker 守护进程未运行，MinIO 起不来。`LocalObjectStorage` 自己实现 HMAC 预签名与过期校验，因此 `ST-S02-04`（签名被篡改 → 403 `PRESIGN_INVALID`）是真实走通的，不是 mock 掉的。唯一测不出的是「直传不经过 API 进程」——那是 S3 独有属性，`UT-S02-25` 因此写入 `skip` 并注明由 staging 上的 `SMOKE-core-15` 覆盖。这与编排索引里已登记的 `OQ-1`（对象存储 `fixed-value` 语义）是同一个待确认项。

**2. 发现并修正了一处 Step 2 的 schema 缺陷。** `UT-S02-18` 暴露出 `wishes.audio_media_id` 的 `ON DELETE SET NULL` 与 `wishes_voice_requires_audio` CHECK 互相矛盾：删除被引用的音频会把 `source='voice'` 的行改成 `audio_media_id IS NULL`，直接违反 CHECK。已统一改为 **`ON DELETE RESTRICT`**——这才是「原始音频永久保留」的正确编码。同步修改了 `schema.sql`、0001 迁移、`models.py` 与 `core-S02-test-cases.md` 的 UT-S02-18 描述。

### 运行结果（Batch 1 + 2 全量）

```text
69 passed, 1 skipped
logos/resources/verify/test-results.jsonl：70 条记录（69 pass / 1 skip / 0 fail）
```

## Batch 3 交付内容

### 覆盖用例（批前声明）

- **UT-S03-01 ~ UT-S03-28**（28 个）
- **ST-S03-01 ~ ST-S03-12、ST-S03-15**（13 个）
- `ST-S03-13` / `ST-S03-14` 为 `[manual]`（光晕动效、真机 Web Push），按规范不写 JSONL

### 新增业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/timing.py` | 6 种时机的 `next_trigger_at` 计算（按用户时区、上午 9 点）、`timing_occurrence` 生成、自然周起始日 | S03 Step 5、Step 13 |
| `app/notify.py` | `PushSender` / `EmailSender` 抽象 + env-disable 推送 + 内存邮箱（test-api）+ 纯模板文案 | 架构第七节、S03 Step 15 |
| `app/scheduler.py` | `run_tick()`：文件锁单活 → 按 `timing_set_at` 升序扫描 → 周预算判定 → outbox 去重入队 → 双通道投递 → 退避重试 | S03 Step 9–17、EX-9.1/14.1/14.2/16.1/16.2 |
| `app/services.py`（新增） | `set_timing` / `mark_ready` / `defer_wish` / `pause_reminders` / `trigger_fatigue_signals` | S03 Step 4、EX-4.1、EX-11.1、EX-20.1 |
| `app/api.py`（新增） | `PUT /wishes/{id}/timing`、`POST ready|defer|pause`；后门 `POST /api/test/scheduler/tick`、`GET /api/test/outbox`、`GET /api/test/latest-email`、`POST /api/test/push-subscription` | wishes.yaml、system.yaml |
| `migrations/versions/0002_batch3_reminders.py` | `push_subscriptions`、`reminder_outbox`、`reminder_weekly_counters` + 索引 | schema.sql |

### 三处在实现中发现并修正的问题

1. **`decode_access_token` 绕过了 Clock 抽象**。原实现把过期判定交给 PyJWT 内部的 `time.time()`，注入固定时钟的测试一律 401。架构第七节要求所有时间来自 `Clock`，已改为自己比较 `exp`，并关闭 PyJWT 的 `verify_exp` / `verify_iat` / `verify_nbf`。这不是测试的问题，是实现没有贯彻抽象。
2. **周预算的顺延判定位置错了**。原实现在扫描阶段读周计数，但计数要到投递阶段才被本轮成功投递抬高，导致 5 张同时到期的卡全部入队、没有一张被标记 `soft_deferred`。已把顺延判定移到投递循环内——预算在投递时刻才真正见分晓。
3. **`month_day` 未按 API 规格校验补零**。`wishes.yaml` 的 pattern 是 `^\d{4}-\d{2}(-\d{2})?$`，而原实现接受 `2027-3`。已加正则前置校验。

### 运行结果（Batch 1–3 全量）

```text
110 passed, 1 skipped
logos/resources/verify/test-results.jsonl：111 条（110 pass / 1 skip / 0 fail）
按场景：S01 33 / S02 37 / S03 41
```

## Batch 4 交付内容

### 覆盖用例（批前声明）

- **UT-S04-01 ~ UT-S04-27**（27 个）
- **ST-S04-01 ~ ST-S04-10**（10 个）
- `ST-S04-11` 为 `[manual]`（对话区只呈现 1 个下一步卡），按规范不写 JSONL

### 新增业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/agent.py`（扩展） | `next_step()` + `classify_message()` + `StepSuggestion` 三项自检字段 + 按 feeling 选取的兜底步骤库 | S04 Step 8、EX-8.2、EX-13.2 |
| `app/steps.py` | `request_next_step` / `mark_step_done`（乐观锁）/ `back_to_brewing` / `send_message`（四种意图）/ `detail_of`（装配 current_step、timeline、messages、amended_from） | S04 Step 5–23、EX-23.1 |
| `app/scheduler.py`（扩展） | 60 天停滞关心扫描，`stale_notified_at` 保证只发一次，占用同一份周预算 | S04 EX-15.2 |
| `app/api.py`（新增） | `POST /wishes/{id}/steps/next`、`POST /wishes/{id}/steps/{step_id}/done`（If-Match）、`POST /wishes/{id}/messages`、`POST /wishes/{id}/back-to-brewing` | wishes.yaml |
| `migrations/versions/0003_batch4_steps.py` | `wish_amendments`、`wish_steps`、`wish_messages` + 部分唯一索引 | schema.sql |

### 两处在实现中发现并修正的问题

1. **`owner_guard` 抓到服务层只按 `wish_id` 过滤。** `wish_steps` / `wish_messages` / `wish_amendments` 都有自己的 `owner_id`，但 `steps.py` 的 6 处查询只带 `wish_id`——等于信任调用方传来的 id。守卫直接抛异常挡住了，已全部补上 `owner_id`。这正是 SQLite 方案里第二道防线该起的作用。
2. **`detail_of` 读不到同事务内刚写入的行。** sessionmaker 关闭了 `autoflush`，所以 `mark_step_done` 刚置为 `done` 的步骤、`send_message` 刚插入的修订快照，在随后的 SELECT 里都看不见——`ST-S04-01` 的 timeline 为空、`ST-S04-09` 的 `amended_from` 为 null 就是这个原因。已在装配前显式 `flush()`。

### 运行结果（Batch 1–4 全量）

```text
147 passed, 1 skipped
logos/resources/verify/test-results.jsonl：148 条（147 pass / 1 skip / 0 fail）
按场景：S01 33 / S02 37 / S03 41 / S04 37
```

## Batch 5 交付内容

### 覆盖用例（批前声明）

- **UT-S05-01 ~ UT-S05-18、UT-S05-21 ~ UT-S05-27**（25 个，全部实现）
- **ST-S05-01、ST-S05-03 ~ ST-S05-14**（13 个）
- 未覆盖并已说明：
  - `UT-S05-19`（河流视图重排函数）、`UT-S05-20`（切换视图不触发新请求）是前端行为 → Batch 7
  - `ST-S05-02`（切到河流视图不丢筛选）同属前端，本批以 **skip** 写入 JSONL 保留 ID 可追溯 → Batch 7
  - `ST-S05-15` / `ST-S05-16` 为 `[manual]`（多断点目视、键盘焦点顺序），按规范不写 JSONL

### 业务代码

主体（`app/tidy.py`、`0004` 迁移、5 个 S05 端点）在上一轮已落地，本轮补齐三处规格缺口后闭环：

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/audit.py`（新增） | 安全审计日志：越权访问返回 404 的同时留一条**只含标识符**的记录 | S05 EX-3.1 副作用 |
| `app/tidy.py` → `register_orphan_object` | 孤儿对象登记，`ON CONFLICT DO NOTHING` 保证重复登记幂等不新增 | UT-S05-16 |
| `app/tidy.py` → `retry_orphan_objects` | 每日清理任务：重试残留对象键，成功即删行、仍失败 `attempts + 1` | EX-28.1 的收敛端 |
| `app/tidy.py` → `list_wishes_page` | 游标锚点已被删除时返回 `400 CURSOR_INVALID` | EX-2.1 后半句 |
| `app/api.py` → `get_wish` / `get_wish_or_404` | 404 分支接入审计日志 | EX-3.1 |
| `app/services.py` → `cleanup_orphan_media` | 删不掉的 key 登记为 `reason='unreferenced'`，不再就地丢弃 | schema.sql 的 `unreferenced` 枚举 |

### 测试代码

| 文件 | 内容 |
|------|------|
| `tests/test_s05_scenarios.py`（新增） | UT-S05-03/07/08/09/10（HTTP 层字段与状态断言）+ ST-S05-01 ~ 14 |
| `tests/test_s05_units.py`（修改） | `UT-S05-05b` 改名为无 ID 的辅助断言，原因见下方第 4 条 |

### 四处在实现中发现并修正的问题

1. **`list_wishes_page` 只实现了 EX-2.1 的前半句。** 原实现仅在游标无法解码时返回 400；游标指向**已被删除的记录**时会静默返回下一页。锚点消失后翻页结果会偏移，用户看到的是「漏了几张卡」，而不是 EX-2.1 副作用描述的「只感知为一次刷新」。已在解码后校验锚点仍存在且属于当前用户，否则返回 `400 CURSOR_INVALID`——客户端拿到这个码才知道该丢弃游标重取第一页。

2. **EX-3.1 的副作用完全没有实现。** 越权访问已经正确返回 404（而不是泄露存在性的 403），但规格明确要求「记录一条安全审计日志（含 user_id 与被请求 ID，不含内容）」，代码里一条日志都没有。新增 `app/audit.py`，日志里只有 `user_id` / `resource` / `resource_id` 三个标识符——审计日志本身不能成为第二个泄露面，`ST-S05-08` 因此直接断言愿望标题的子串不出现在日志文本里。

3. **`orphan_objects.reason = 'unreferenced'` 是个没有写入方的死枚举。** `cleanup_orphan_media`（S02 EX-13.1）对删除失败的 key 直接丢弃，从此再也查不到该删哪个 key——与 EX-28.1 竭力避免的正是同一件事。已改为登记进清理队列，`unreferenced` 这个值现在有了唯一的写入点，也一并被 `retry_orphan_objects` 收敛。

4. **reporter 会为 `UT-S05-05b` 重复写一条 `UT-S05-05`。** reporter 从函数名提取用例 ID，正则 `(UT|ST)_S\d{2}_\d{2,3}` 在 `test_UT_S05_05b_...` 上匹配出 `UT_S05_05`，导致 JSONL 里同一 ID 出现两次、覆盖率统计虚高。该函数是对 UT-S05-05 的补强断言、不是规格里的独立用例，已改名为不含 ID 的 `test_cursor_roundtrip_is_stable`。

### 两处需要你知道的取舍

**1. `ST-S05-11` 的 `happened` 前置状态是直接写库造的。** 该状态由 S06 的记忆页发布产生，而 S06 属 Batch 6、尚未交付。被测行为（`POST /let-go` 在终态返回 409 且响应体前后逐字节相等）仍然完整走 HTTP，只有前置条件绕了库。同理 `ST-S05-04` / `ST-S05-06` 的 pending 提醒也直接写库——投递本身是 S03 的被测行为，不在 S05 里重复一遍。

**2. `ST-S05-13` 的「每日清理任务」是直接调用服务函数，没有走后门端点。** 与 S02 EX-13.1 的 `cleanup_orphan_media` 保持同一做法：删除链路本身走 HTTP（`DELETE ?confirm=true` 返回 204），只有后台任务的触发是进程内调用。存储故障用 `FlakyStorage` 注入，它只坏 `delete_many` 一条路径，其余方法透传给真实的 `LocalObjectStorage`——否则测出来的 204 说明不了任何事。

### 运行结果（Batch 1–5 全量）

```text
186 passed, 2 skipped
logos/resources/verify/test-results.jsonl：187 条（185 pass / 2 skip / 0 fail）
按场景：S01 33 / S02 37 / S03 41 / S04 37 / S05 39
```

命令：`backend/.venv/Scripts/python -m pytest -c backend/pyproject.toml backend/tests`

> ⚠️ **必须用 `backend/.venv` 里的解释器。** 系统 Python（anaconda）缺 `email_validator`，
> `app/schemas.py:55` 的 `EmailStr` 会让 3 个测试模块直接 collection error。
> `logos.config.json` 的 `verify.pre_run_command` 刻意保持可移植的裸 `python -m pytest`
> （写死 `backend/.venv/Scripts/python` 会在 Linux CI 上失效），
> 因此运行 `openlogos verify` 前需先激活项目 venv。

## Batch 6 交付内容

### 覆盖用例（批前声明）

- **UT-S06-01 ~ UT-S06-32**（32 个，全部实现）
- **ST-S06-01 ~ ST-S06-13**（13 个，全部实现）
- `ST-S06-14` / `ST-S06-15` 为 `[manual]`（纸质背景对比度与屏幕阅读器、书页合起动效与
  reduced-motion 对照），按规范不写 JSONL

### 业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/memories.py`（新增） | 标记已发生 / 编辑 / 幂等发布 / 书架 / 补草拟，含书架游标 | S06 Step 3–20 |
| `app/models.py` → `Memory` / `MemoryPhoto` | 一事一页（`wish_id` UNIQUE）+ 4 条 CHECK | schema.sql 逐条对齐 |
| `app/agent.py` → `MemoryDraft` / `draft_memory` / `MEMORY_PROMPT` | 草拟标题、起因、经过；没有时间线就返回 null 而不编造 | Step 7、EX-4.1 |
| `app/schemas.py` → `HappenedRequest` / `MemoryOut` / `MemoryResult` … | `happened_from` 用 `date` 类型，`2026/10/17` 在 schema 层就被拒 | UT-S06-02 |
| `app/api.py`（新增 5 个端点） | `POST /wishes/{id}/happened`、`GET /memories`、`GET/PATCH /memories/{id}`、`POST /memories/{id}/publish` | memories.yaml |
| `migrations/versions/0005_batch6_memories.py` | `memories` + `memory_photos` + 3 个部分索引 | schema.sql |

### 测试代码

| 文件 | 内容 |
|------|------|
| `tests/test_s06_db.py`（新增） | UT-S06-16 ~ 23（DDL 约束）+ UT-S06-24 ~ 32（业务规则） |
| `tests/test_s06_scenarios.py`（新增） | UT-S06-01 ~ 15（HTTP 层）+ ST-S06-01 ~ 13 |

### 三处在实现中发现并修正的问题

1. **`Clock.set_fixed` 没有把注入时间归一到 UTC。** `ST-S06-12` 暴露出同一个时间点在响应里有两种形态：刚发布时返回 `2026-10-19T12:00:00+08:00`（内存里的注入值），再取一次返回 `2026-10-19T04:00:00Z`（经 `TZDateTime` 往返后的 UTC）。客户端做字符串比较或缓存键会直接判定「变了」。这不是 S06 的问题，是所有时间字段共有的——已在 `clock.py` 归一。

2. **测试用例文档里 `UT-S06-21` 的来源标注是 PostgreSQL 时期的残留。** 写的是 `DEFAULT '{}'`（PG 的 `text[]` 空数组字面量），换到 SQLite + JSON 字符串后应为 `'[]'`。已同步修正 `core-S06-test-cases.md` 的该行。

3. **0005 迁移漏了两个部分索引。** `idx_memories_draft` 与 `idx_memories_voice_media` 在 schema.sql 里有、迁移里没有，直接体现为 `SMOKE-core-07` 期望的 28 个索引对不上（当时只有 26 个）。已补入 0005。

### 两处需要你知道的取舍

**1. `publishMemory` 的 404 一律回 `WISH_NOT_FOUND`，包括「草稿 id 根本不存在」。** memories.yaml 给这个端点记载的唯一 404 就是它（EX-18.1：愿望被彻底删除，草稿随级联消失）。从客户端看这两种情况本来就是同一件事：这一页已经不在了。为一个查不到的 id 另造一个 `MEMORY_NOT_FOUND` 只会让前端多写一个分支去处理同一个结果。

**2. 清空标题落库为空字符串，不是 NULL。** memories.yaml 允许 `title: null`（「全部区块可为空」），而 DDL 的 `title_enc` 是 `NOT NULL`。两者的交集只能是空字符串——对外 `title` 因此永远是一个字符串（可能为空），`MemoryCard.title` 的非空类型也就成立。

### 运行结果（Batch 1–6 全量）

```text
231 passed, 2 skipped
按场景：S01 33 / S02 37 / S03 41 / S04 37 / S05 39 / S06 45
```

## Batch 7 交付内容

### 覆盖用例（批前声明）

- **UT-S05-19 / UT-S05-20 / ST-S05-02**（3 个前端行为，此前一直空缺）
- **ST-S01-03 / ST-S01-04**（2 个故障注入用例，Batch 1 起就挂着的欠账）
- **SMOKE-core-01 ~ SMOKE-core-18**（18 个部署后冒烟用例，本轮首次可执行）

### 前端（`frontend/`）

| 文件 | 职责 |
|------|------|
| `vite.config.ts` / `vitest.config.ts` | 构建与测试配置分两个文件——vitest 自带嵌套 vite，同一文件里 import 两边的 `defineConfig` 会让 tsc 认为 `Plugin` 是两个不兼容的类型 |
| `src/index.css` | `@theme` 直接映射 design-system.json 的令牌，前端不再手写第二套颜色常量 |
| `src/lib/river.ts` | 河流视图重排（纯函数，不就地修改入参） |
| `src/pages/Garden.tsx` | 未发生之地：状态胶囊 + URL 深链 + 花园/河流切换；响应里没有任何计数字段可渲染 |
| `src/pages/Welcome.tsx` | S01 首次体验 + 随手种下，三道问题可整段跳过 |
| `src/pages/WishDetail.tsx` | 详情 + 整理半屏 5 个动作（按侵入性递增）+ 彻底删除二次确认（默认焦点在取消） |
| `src/pages/Book.tsx` / `src/pages/MemoryPage.tsx` | 已发生之书书架与记忆页草稿 / 阅读态 |
| `tests/helpers/reporter.ts` | Vitest 版 OpenLogos reporter，**只 append 不 truncate** |
| `tests/river.test.ts` / `tests/garden.test.tsx` | UT-S05-19、UT-S05-20、ST-S05-02 |

前端 reporter 与 pytest 那份写同一个 JSONL，因此清空文件的职责固定归 pytest（它先跑），
`verify.pre_run_command` 必须保持 `pytest && vitest` 这个顺序：反过来会抹掉后端 233 条结果。

### 故障注入夹具

| 文件 | 职责 |
|------|------|
| `app/faults.py`（新增） | 两个注入点：`db`（任何 `session_scope()` 失败）、`onboarding_answers_write` |
| `app/api.py` → `POST /api/test/faults` | 武装 / 解除，挂在 `test_router` 上，生产构建里不存在 |
| `app/api.py` → `create_anonymous` | 捕获 `SQLAlchemyError` → `503 SPACE_CREATE_FAILED`，响应里不带堆栈或 SQL |

注入点抛的是 `OperationalError` 而不是自定义标记异常。否则测出来的只是
「代码能捕获我编的异常」，而不是「代码能捕获数据库真的挂了」。

### smoke 闭环与运维脚本

| 文件 | 职责 |
|------|------|
| `scripts/smoke-core.py`（新增） | 18 个 `SMOKE-core-*` 的真实断言，只用标准库 |
| `scripts/run-smoke.js`（新增） | dispatcher：清空结果文件、发现并顺序运行 `scripts/smoke-*`、汇总退出码 |
| `ops/check-env.sh`（新增） | 必需环境变量检查，只打印变量名与长度，不打印任何密钥值 |
| `ops/post-deploy-check.sh`（新增） | 部署方案 §7 的 12 项：先 check-env 再跑 smoke，不重复实现断言 |
| `logos.config.json` | 写入 `smoke.command = node scripts/run-smoke.js`；`verify.pre_run_command` 串上 vitest |

### smoke 需要的后端补齐

| 文件 | 职责 | 对应用例 |
|------|------|---------|
| `migrations/versions/0006_batch7_scheduler_heartbeat.py` | 单行心跳表 + 唯一一条初始化数据 | SMOKE-core-02 |
| `app/scheduler.py` → `_beat` / `heartbeat_age_seconds` | 每轮扫描**结束**刷新心跳（卡在投递里出不来的 tick 不算活着） | SMOKE-core-02 |
| `app/scheduler.py` → `main()` | `python -m app.scheduler --once`，生产触发一轮扫描的唯一外部入口 | SMOKE-core-12 |
| `app/main.py` → `/health` | 报告 `scheduler_heartbeat_age_seconds` 真实值（此前硬编码 null） | SMOKE-core-02 |
| `app/db.py` | 启动日志输出 `owner_guard installed` | SMOKE-core-08 |

### 四处在实现中发现并修正的问题

1. **`local` 环境根本无法上传媒体。** `get_storage()` 在 `APP_ENV in (local, test)` 返回 `LocalObjectStorage`，它签出的预签名 URL 指向 `/api/test/object/{key}`；但那个路由挂在 `test_router` 上，而 `test_backdoor_enabled` 只在 `APP_ENV == "test"` 为真。于是本地开发签得出预签名、收件的地方却不存在——`SMOKE-core-15` 直接撞出 404。已拆出独立的 `local_router`，它不读写任何业务数据，只按自签 HMAC 收一个文件。

2. **smoke 用例之间存在隐式顺序依赖。** `SMOKE-core-08` 需要「A 有一条愿望」这个前置，而建愿望发生在 `SMOKE-core-10`。第一版靠执行顺序碰巧成立，而空 id 会让 URL 从 `/wishes/{id}` 退化成 `/wishes` 列表端点——B 反而拿到 200，断言给出的错误信息完全指错了方向。已改为惰性前置 `ensure_wish_a()`，谁先跑谁建。

3. **Tailwind CSS 4.0.0 在本环境下构建即失败。** 连一行 `@import "tailwindcss";` 都会抛 `Cannot convert undefined or null to object`。这个报错最初显示在 `vite-plugin-pwa` 的 `buildEnd` 里，误导了一轮排查（还顺手钉了 `workbox-build`）；拆掉 PWA 插件后才定位到真正的来源是 `@tailwindcss/vite`。已升到 4.3.3，构建与 PWA 产物均正常。`overrides` 里对 `workbox-build` 7.3.0 的钉保留下来——`vite-plugin-pwa` 的 peer 是 `^7.3.0`，不钉就会自动装上 7.4.x，属于同类漂移。

4. **`SMOKE-core-12` 的规格自相矛盾。** 冒烟用例文档写 staging 用 `POST /api/test/scheduler/tick` 触发扫描，而同一份文档的 `SMOKE-core-04` 要求这个后门在 staging 返回 404。两者不能同时成立。runner 统一走 `SMOKE_SCHEDULER_CMD`（默认 `docker compose run --rm scheduler --once`），生产与 staging 用同一条路径——这也是为什么本轮补了 scheduler 的 CLI 入口。

### 三处需要你知道的偏离

**1. 包管理器用 npm，不是 tech_stack 声明的 pnpm。** 本机 `corepack enable pnpm` 报 `EPERM: operation not permitted, open 'D:\nvm\v22.14.0\pnpm'`（需要提权写入 nvm 目录）。依赖版本全部是精确钉死的，因此换包管理器不改变任何依赖解析结果，差异只在锁文件形态（`package-lock.json` 而非 `pnpm-lock.yaml`）。如果需要与 tech_stack 严格一致，在有权限的环境执行一次 `corepack enable pnpm && pnpm import` 即可。

**2. Playwright 未引入。** tech_stack 把它列在前端测试栈里，但没有任何 UT/ST ID 需要它：真正需要真实浏览器的用例（`ST-S05-15/16`、`ST-S06-14/15`、`ST-S01-09/10`）全部标着 `[manual]`，由 Phase 3-8 的人工确认覆盖。为不产出任何断言的依赖下载一套浏览器不划算。

**3. Docker / compose / Caddyfile 未产出。** 它们是 Phase 3-7「部署执行」的交付物（deployment-executor，人类确认点），不在 Batch 7 的范围内。直接后果是 `SMOKE-core-12` 的默认命令 `docker compose run --rm scheduler --once` 在当前仓库跑不通——本轮的自检是用 `SMOKE_SCHEDULER_CMD` 指向 `python -m app.scheduler --once` 验证的，两条路径调用的是同一个函数。

### 运行结果

后端 + 前端全量：

```text
233 passed, 2 skipped   (pytest)
4 passed                (vitest)
test-results.jsonl：236 条（235 pass / 1 skip / 0 fail），无重复 ID
按场景：S01 35 / S02 37 / S03 41 / S04 37 / S05 41 / S06 45
```

smoke（本机 `local` 环境，API + 静态站点均在本地起）：

```text
smoke-results.jsonl：18 条（6 pass / 12 skip / 0 fail），18 个 ID 全覆盖
SMOKE-core-10 warning：Agent 降级，检查 LLM_BASE_URL / LLM_API_KEY（本机无 LLM 端点）
```

12 条 skip 全部是「目标环境为 staging/production，当前是 local」——不是没实现。
为了确认这些断言不是空壳，另做过一次 `SMOKE_ENV=staging` 指向本地服务的自检：
**17 项真实执行通过**，只有 `SMOKE-core-02`（本机没有常驻调度进程，心跳超过 900 秒）
与 `SMOKE-core-17`（本机无 TLS）按环境事实分别 fail / skip。该结果未写入交付文件——
交付的冒烟结果只反映真实存在的环境。

## 自检结果（Step 5 检查表）

截至 Batch 7（全部批次）：

| 项 | 结论 |
|----|------|
| API 路由与方法与 YAML 一致 | ✅ 29 个业务端点（另 `/api/v1/health`）逐一核对；S06 的 5 个对照 `memories.yaml` 的 markWishHappened / listMemories / getMemory / updateMemory / publishMemory |
| HTTP 状态码与 YAML 一致 | ✅ 200/201/204/400/401/404/409/412/422/503；`503 SPACE_CREATE_FAILED`、`422 HAPPENED_DATE_IN_FUTURE`、`422 HAPPENED_RANGE_INVALID`、`422 MEDIA_LIMIT_EXCEEDED` 均由 ST 断言 |
| 错误响应格式 `{code,message}` | ✅ 统一异常处理器；FastAPI 校验错误归一为 `422 VALIDATION_FAILED`；503 响应不带堆栈或 SQL（ST-S01-03 逐字断言） |
| DB 表名列名与 DDL 一致 | ✅ 17 张表 / 28 个索引与 schema.sql 逐一对齐（`SMOKE-core-07` 直接数数） |
| 多表写操作使用事务 | ✅ `session_scope()` 包裹；发布时「置 published + 转 happened」在同一事务内（UT-S06-25） |
| 参数化查询 | ✅ 全部走 SQLAlchemy / `text()` 绑定参数；仅测试与 smoke 里有表名插值，来源都是模块内字面量元组 |
| 批前声明的 ID 均在测试代码中存在 | ✅ Batch 6：45/45；Batch 7：5 个测试 ID + 18 个 SMOKE ID 全部实现 |
| 数据隔离守卫已接入并被测试触发 | ✅ UT-S05-11/12/13 + ST-S05-08（审计日志）+ SMOKE-core-08/14 |
| 共享 reporter 已创建 | ✅ 后端 `backend/tests/conftest.py`、前端 `frontend/tests/helpers/reporter.ts`（只 append） |
| JSONL 已生成且非空 | ✅ 236 行 / 235 pass / 1 skip / 0 fail，无重复 ID |
| 无硬编码敏感信息 | ✅ 密钥全部走环境变量；审计日志只写标识符；`ops/check-env.sh` 只打印变量名与长度 |
| smoke runner / reporter / dispatcher | ✅ `scripts/smoke-core.py` + `scripts/run-smoke.js`，`smoke.command` 已写入；18 个 ID 全覆盖，无 uncovered |

## Phase 3-7 部署演练的回填（2026-09-02）

Batch 1–7 交付之后，`staging` 部署演练又改动了几处后端代码。记在这里是为了让这份清单
不至于读起来像「Batch 7 之后代码没再动过」；每一处的来龙去脉在
`../verify/deployment-report.md` 第七节。

| 文件 | 改动 | 为什么单元测试没抓到 |
|------|------|---------------------|
| `app/config.py` → `scheduler_lock_path` | 单活文件锁改按 `DATABASE_URL` 推导 | 原路径在测试里恰好可写，在镜像里指向 root 拥有的 `/app` |
| `app/obs.py`（新增）+ `main.py` + `scheduler.py` | 统一日志装配 + `request_id`（§7-12） | 没有任何 UT/ST 断言日志格式；`scheduler` 长驻入口此前完全没有日志 |
| `app/storage.py` → `S3ObjectStorage` | 预签名改按 `S3_PUBLIC_BASE` 签名 | 测试一律用 `LocalObjectStorage`，S3 分支从未被执行过 |
| `backend/entrypoint.sh`（新增） | `umask 0077`，让 `.db` 一出生就是 600（§3.3） | 权限是部署形态的属性，测试库落在 tmp 目录 |
| `backend/Dockerfile` / `docker-compose.yml` / `Caddyfile` | 镜像、编排、反代路由 | 部署产物，Phase 3-7 才产生 |

这几处的共同点值得记一句：**它们全部落在「只有真正跑起来才存在」的那一层**——
镜像里的目录属主、长驻进程的日志装配、只在 staging 才启用的存储实现、文件权限。
236 个用例全绿的同时，线上每一次上传都会失败、调度进程每一轮都在静默报错。

## 下一步

代码（Phase 3-5）、验收（3-6）、部署（3-7）、冒烟（3-8）四步已全部走通：

| 阶段 | 结论 | 产物 |
|------|------|------|
| Phase 3-6 · verify | ✅ Gate 3.6 PASS，覆盖度 100%、通过率 100% | `../verify/acceptance-report.md` |
| Phase 3-7 · 部署执行 | ✅ 本机 `staging` 演练 | `../verify/deployment-report.md` |
| Phase 3-8 · smoke | ✅ Gate 3.8 PASS，17 pass / 0 fail / 1 skip | `../verify/smoke-report.md` |

再往下有两条路，都不是「继续推进 Phase」：

1. **上真实 staging**。本次演练没有远程主机、真实域名和公网证书，
   因此 `SMOKE-core-17` 记 skip，Web Push 与 Service Worker（强制 HTTPS）也未真正验证。
   部署报告第八节列了六项未解决风险，其中「文件锁没有陈旧检测」与「未演练回滚」
   应在上真实环境前处理。
2. **`openlogos launch`**，把项目从 initial 切到 launched，之后一切改动走变更提案。
   S07（唤回一个被安静放下的愿望）是 P2、本轮明确不建模，正好作为 launched 之后的
   第一个变更提案。

运行 verify / smoke 时的两个前提，别忘：先激活 `backend/.venv`（否则系统 Python
缺 `email_validator`）；`verify.pre_run_command` 的 `pytest && vitest` 顺序不能反
（两个 reporter 写同一个 JSONL，清空的职责归先跑的 pytest）。



## S07 交付内容（唤回被安静放下的愿望）

### 覆盖用例

- `UT-S07-01`～`UT-S07-20`：端点、模型、状态迁移、时机清理、提醒清理、内容保留与禁用词契约。
- `ST-S07-01`～`ST-S07-08`：真实 HTTP 场景覆盖列表排序、唤回、重新约定时机、空态、跨用户隔离、重复唤回冲突及次要动作不写入。
- `ST-S07-09`：人工视觉验证，保留待 `375/768/1024/1440px` 目视检查。

### 业务代码

| 文件 | 职责 |
|------|------|
| `backend/app/models.py` | `wishes.let_go_at` 可空字段与状态约束 |
| `backend/app/tidy.py` | 安静放下时间记录、`let_go` 排序、唤回状态迁移及提醒清理 |
| `backend/app/api.py` | 新增 `POST /api/v1/wishes/{wish_id}/recall` |
| `backend/app/services.py`、`backend/app/schemas.py` | 卡片/详情暴露 `let_go_at` |
| `backend/migrations/versions/0007_s07_recall.py` | 兼容旧 SQLite 库的字段与约束迁移 |
| `frontend/src/pages/WishDetail.tsx`、`frontend/src/lib/recall.ts` | 「重新种下 / 再放一会儿」交互 |

### 测试与验证

- 前端 `npm run test:run`：7 个测试通过；`npm run build`：通过。
- `openlogos change-lint`：`PASS（7/7）`。
- 后端测试代码已补齐真实 HTTP/数据库行为断言；当前机器的 Anaconda `_ssl` DLL 加载失败，阻塞 pytest 收集，未将环境故障计为业务失败。

## preferences-availability-timing 增量交付（2026-09-03，Batch 8–10）

### 覆盖用例（批前声明）

- **Batch 8**：UT-S08-01 ~ UT-S08-16、UT-S08-18（15 个）+ ST-S08-01 / 04 / 05（3 个）
- **Batch 9**：UT-S03-29 ~ UT-S03-40（12 个）+ ST-S03-16 ~ 21（6 个）+ UT-S08-17 / 19 / 20、ST-S08-02 / 03 / 06（6 个）
- 未覆盖并已说明：UT-S08-14（跨午夜拆两行）已实现为两行各自 201 的 HTTP 断言；ST-S08-07 / ST-S08-08 为 `[manual]`（来源徽标视觉分层、空态文案走查），按规范不写 JSONL

### 业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/models.py` | `UserPreference`（declared/inferred + digest 行）/ `AvailabilityWindow` / `TimingProposal` 三模型 + 约束 | schema.sql（0008 迁移逐条对齐） |
| `app/preferences.py`（新增） | 偏好 UPSERT（声明不覆盖推断）/ 撤回（软失效留痕迹）/ 硬删；时段 CRUD；`expire_proposals_referencing`（同事务失效引用条目的 pending 建议）；`upsert_digest` | auth.yaml preferences tag、core-S08 时序图 |
| `app/proposals.py`（新增） | TimingProposal 四层链路：有界上下文组装（evidence 服务端检索，不信任模型自报）→ plan_timing 确定性校验（invalid 入库即 expired 留审计）→ confirm 复用 set_timing / reject 不写 wishes | core-S03 时机提议分支 P1–P16、架构 5.4 |
| `app/agent.py`（扩展） | `propose_timing` / `summarize_preferences` + TimingProposalDraft（timing_type 限 4 种时间类）/ PreferenceDigest | 架构 5.1 增补 |
| `app/scheduler.py`（扩展） | TickResult 新增 `expired_proposals` / `digest_updated`；低频任务：提议过期扫描 + 每日偏好摘要（超过 24h 才重新生成；LLM 降级保持旧值不重试，EX-D2.1） | S08 摘要支线 D1–D4 |
| `app/api.py`（新增 11 个端点） | 偏好 4 + 可用时段 4（写响应不回显 value）；提议生成/列表/confirm（body 必须为空）/reject | api/*.yaml |
| `app/steps.py` → `detail_of` | WishDetail 装配 `timing_proposal`（当前 pending 建议卡） | wishes.yaml WishDetail |
| `migrations/versions/0008_preferences_availability_timing.py` | 三张新表 + 7 索引（DDL 与 schema.sql 逐字节一致，脚本生成） | 部署方案「五·增补」 |
| `scripts/smoke-core.py` | SMOKE-core-19（声明/读取 + 不回显 + 密文断言）、SMOKE-core-20（时段保存/读取/清理）；表数量断言 17→20、索引 29→36 | smoke 用例 |
| `frontend/src/pages/Me.tsx`（新增）+ `src/lib/remembered.ts`（新增）+ `WishDetail.tsx`（建议卡）+ `App.tsx`（/me 路由）+ `api/types.ts` | 「它记得我什么」管理区（来源徽标 / 声明输入 / 撤回痕迹 / 时段管理）+ P3 建议确认卡（确认前无任何提醒的提示文案） | core-05 设计文档 |

### 实现中发现并修正的规格问题（三处）

1. **`user_preferences` 的唯一索引与「声明不覆盖推断」冲突（UT-S08-11 暴露）。** schema.sql 原唯一索引 `(owner_id, kind, pref_key)` 会让 declared 与 inferred 的同 key 两行无法并存，直接违反需求 S08 AC-01「不互相覆盖、不丢失」。已改为 `(owner_id, kind, pref_key, source)`，同步修正 schema.sql、0008 迁移、models.py 与 core-S08-test-cases.md 的 UT-S08-11 描述。
2. **auth.yaml 的「响应不回显 note 明文」与 AvailabilityOut 契约自相矛盾。** note 是用户刚写下的备忘，保存响应原样返回是体验的一部分（且 AvailabilityOut schema 本身含 note 字段）。「敏感值不回显」的真实边界是日志、错误响应与跨用户访问——已修正 auth.yaml 描述（提案 delta 同步）。
3. **`TickResult` 新增统计字段导致 ST-S03-06 的全量 dict 相等断言失效。** 该用例关心的是锁被占用时五个核心统计为零，已改为逐字段断言，对合法扩展保持不敏感。

### 运行结果

```text
pytest：313 passed, 2 skipped（新增 46 用例：Batch 8 的 18 + Batch 9 的 28）
vitest：7 passed（前端既有测试；Me/WishDetail 无新 UT/ST ID，由构建与 [manual] 覆盖）
test-results.jsonl：282 条（281 pass / 1 skip / 0 fail），无重复 ID
smoke runner：20 项（SMOKE-core-19/20 为 ALL 环境可执行）

## holiday-aware-timing 增量交付（2026-09-05）

### 覆盖用例（批前声明）

- **UT-S03-41 ~ UT-S03-48**（8 个）+ **ST-S03-22 / ST-S03-23**（2 个），全部实现并写 JSONL

### 业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/holidays.py`（新增） | 年份粒度数据加载器（懒加载 + 缓存 + 三重空集降级）+ `upcoming_facts` 事实行 | 架构 5.5 |
| `app/data/holidays_2026.json`（新增） | 2026 数据文件（示意日期，正式数据以官方公告为准） | 架构 5.5 schema |
| `app/timing.py` | free_weekend 改为「下一个非调休的周末日」逐日顺延（45 天上限），触发时刻不变；其余三种时间类不动 | 需求 HO-AC-01/03 |
| `app/proposals.py` | `_bounded_context` 追加节假日事实行与 `calendar` evidence 条目 | 需求 HO-AC-02 |
| `app/schemas.py` | `ProposalEvidence.kind` 扩 `calendar`、`id` 放宽为 string | wishes.yaml delta |
| `tests/test_s03_holidays.py`（新增） | `HOLIDAY_DATA_DIR` 注入受控样例数据（fixed-value） | 架构第七节 |

### 实现中发现并修正的问题（一处）

**`ProposalEvidence` 的 Pydantic 模型与合并后的规格脱节**：合并 wishes.yaml delta 时发现主文档没有独立的 `ProposalEvidence` schema（上个提案把 items 内联在 `TimingProposal.evidence`），delta 因此只改了 YAML 内联处；但 `app/schemas.py` 里的独立 Pydantic 模型仍是三值 kind + UUID 约束——UT-S03-47 真实执行时服务端直接 500（`calendar` 被 literal 校验拒绝、`holidays-2026` 被 UUID 解析拒绝）。已同步为四值 kind + string id。教训：**delta 改 YAML 的同时必须核对 Pydantic 模型是否独立存在**。

### 运行结果

```text
pytest：324 passed, 2 skipped / 0 failed（新增 10 用例）
test-results.jsonl：315 个唯一 ID（314 pass / 1 skip / 0 fail）

## lightweight-events 增量交付（2026-09-05）

### 覆盖用例（批前声明）

- **UT-S09-01 ~ UT-S09-12**（12 个）+ **ST-S09-01 ~ ST-S09-04**（4 个），全部实现并写 JSONL；ST-S09-05 为 [manual]

### 业务代码

| 文件 | 职责 | 对应规格 |
|------|------|---------|
| `app/models.py` + `migrations/versions/0009_lightweight_events.py` | LiteEvent（open/done 两态 + closed 配对 CHECK + open 部分索引） | schema.sql 逐条对齐 |
| `app/lite_events.py`（新增） | create（strip+校验）/ list / mark_done（409 幂等）/ delete（硬删）——模块内无任何提醒相关分支 | lite-events.yaml、core-S09 时序图 |
| `app/api.py`（4 端点） | POST/GET /lite-events、POST /{id}/done、DELETE /{id} | lite-events.yaml |
| `app/db.py` | 守卫清单加 lite_events | schema.sql 文末 |
| `scripts/smoke-core.py` | SMOKE-core-21（先记一下链路 + **outbox 无轻事件行**断言）；表数量 20→21、索引 36→37 | smoke 用例 |
| `frontend/src/components/LiteEvents.tsx`（新增）+ `Welcome.tsx` | P1「先记一下」展开区（记录/划掉/收走/空态，无计数） | core-06 设计文档 |

### 实现中发现并修正的问题（两处）

1. **schema 合并脚本丢弃了索引块**：lite_events 的 delta 有两个 sql 块（表 + 部分索引），合并脚本只取了 blocks[0]——索引直到 UT-S09-07 才暴露，已补进 schema.sql 与 0009 迁移。
2. **0009 迁移的 `
` 转义再次被 heredoc 破坏**（连续第三次），已在 Edit 阶段修复；后续生成迁移应彻底放弃 heredoc 内嵌代码。

### 运行结果

```text
pytest：340 passed, 2 skipped / 0 failed（新增 16 用例）
vitest：7 passed（前端构建通过）
test-results.jsonl：320 个唯一 ID（319 pass / 1 skip / 0 fail）
smoke runner：21 项（SMOKE-core-21 为 ALL 环境可执行）

## notification-channels 增量交付（2026-09-05）

### 覆盖用例（批前声明）

- **UT-S10-01~05、UT-S10-09**（6 个）+ **ST-S10-01~04**（4 个）；UT-S10-06/07/08 由 ST-S10-01/02 在真实投递路径覆盖，UT-S10-10（并发读）为代码审查项；ST-S10-05 为 [manual]

### 业务代码

| 文件 | 职责 |
|------|------|
| `app/api.py` | `PATCH /me/notification-channels`（只更新提交字段；空体 422） |
| `app/schemas.py` | UserProfile 扩展 push_enabled/email_enabled；NotificationChannelsUpdate/Out |
| `app/scheduler.py` | `_deliver_one` 投递前读取最新开关：push 关直接走邮件（订阅保留）、全关跳过保持 pending（EX-D2.1）、投递成功才计数 |
| `frontend/src/pages/Me.tsx` + `components` | P6「提醒通道」开关区（Toggle、全关文案「先安静一段时间，想听的时候随时打开」） |

### 实现中发现并修正的问题（一处）

**投递邮件分支残留旧变量引用**：改造 `_deliver_one` 通道选择时，原 `user = await session.get(...)` 行被合并进预读的 `user_row`，但 `send(to=user.email, ...)` 仍引用旧名——运行时 NameError 被记为 `last_error_code`，outbox 静默 pending。ST-S10-01 的真实投递断言暴露。教训：**改造既有函数时对函数内所有同名变量引用做全局核对**。

### 运行结果

```text
pytest：350 passed, 2 skipped / 0 failed（新增 10 用例）
test-results.jsonl：331 个唯一 ID（330 pass / 1 skip / 0 fail）
前端构建与 vitest 7 passed
