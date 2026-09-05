# S02: 随手种下一个愿望并被理解 — 测试用例

> 模块：core｜上游：`../prd/3-technical-plan/2-scenario-implementation/core-S02-seed-wish.md`（27 Steps / 8 EX）
> API：`../api/media.yaml`、`../api/wishes.yaml`｜DB：`../database/schema.sql`（media、wishes、wish_photos、pending_agent_jobs）

## 一、单元测试用例

### 1.1 API 字段约束（来源：media.yaml、wishes.yaml）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S02-01 | kind 非枚举值被拒 | `media.yaml → createMediaUploadUrl → kind.enum` | 已认证 | `{"kind":"video",...}` | 422 `VALIDATION_FAILED` |
| UT-S02-02 | kind 与 content_type 不匹配被拒 | 同上 → content_type 白名单 | 已认证 | `kind=audio, content_type=image/png` | 422 `MEDIA_INVALID` |
| UT-S02-03 | 音频大小边界：10485760 通过 / 10485761 拒绝 | `size_bytes` 上限 + `media_size_within_limit` | 已认证 | 两个边界值 | 201 / 422 `MEDIA_INVALID` |
| UT-S02-04 | 图片大小边界：8388608 通过 / 8388609 拒绝 | 同上 | 已认证 | 两个边界值 | 201 / 422 `MEDIA_INVALID` |
| UT-S02-05 | size_bytes 为 0 或负数被拒 | `size_bytes.minimum: 1` | 已认证 | `0` / `-1` | 422 `VALIDATION_FAILED` |
| UT-S02-06 | 预签名 URL 有效期为 10 分钟 | `createMediaUploadUrl → expires_at` | 已认证 | 调用一次 | `expires_at - now ≈ 600s`（±5s） |
| UT-S02-07 | source=voice 时缺 media_id 被拒 | `wishes.yaml → seedWish` + `wishes_voice_requires_audio CHECK` | 已认证 | `{"source":"voice"}` | 422 `VALIDATION_FAILED` |
| UT-S02-08 | 引用 status≠ready 的媒体被拒 | `seedWish → 422 MEDIA_INVALID` | media 处于 pending | `{"source":"voice","media_id":<pending>}` | 422 `MEDIA_INVALID` |
| UT-S02-09 | photo_media_ids 边界：9 张通过 / 10 张拒绝 | `photo_media_ids.maxItems: 9` | 已认证 | 9 / 10 个 uuid | 201 / 422 `VALIDATION_FAILED` |
| UT-S02-10 | media_id 非 uuid 格式被拒 | `format: uuid` | 已认证 | `"abc"` | 422 `VALIDATION_FAILED` |
| UT-S02-11 | 引用他人的 media_id 返回 404 | `completeMediaUpload → 404 MEDIA_NOT_FOUND` + RLS | 用户 B 的 media | 用户 A 引用它 | 404 `MEDIA_NOT_FOUND`（非 403） |

### 1.2 DB 约束（来源：schema.sql）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S02-12 | object_key 唯一 | `media.object_key UNIQUE` | 已存在某 key | 插入同 key | 唯一冲突 |
| UT-S02-13 | media.status 只接受三个枚举值 | `media.status CHECK` | — | `status='uploading'` | 违反 CHECK |
| UT-S02-14 | media.status 默认 pending | `DEFAULT 'pending'` | — | 插入不指定 status | `status='pending'` |
| UT-S02-15 | source=voice 必须有 audio_media_id | `wishes_voice_requires_audio CHECK` | — | `source='voice', audio_media_id=NULL` | 违反 CHECK |
| UT-S02-16 | degraded_reason 只接受三个枚举值 | `wishes.degraded_reason CHECK` | — | `degraded_reason='unknown'` | 违反 CHECK |
| UT-S02-17 | wish_photos 复合主键防重复引用 | `wish_photos PRIMARY KEY (wish_id, media_id)` | 已关联 | 再次关联同一对 | 主键冲突 |
| UT-S02-18 | 被愿望引用的音频不可单独删除 | `ON DELETE RESTRICT` + `wishes_voice_requires_audio` | 愿望关联音频 | 删除该 media 行 | 违反外键约束，删除失败；愿望与音频均完好——这正是「原始音频永久保留」的结构性保证 |
| UT-S02-19 | pending_agent_jobs 去重索引生效 | `idx_pending_agent_jobs_dedup UNIQUE` | 已有同类待办 | 再次入队同 (job_kind, wish_id) | 唯一冲突 → 幂等不新增 |

### 1.3 业务规则（来源：时序图 Step 说明）

| ID | 描述 | 来源 | 前置条件 | 输入 | 预期输出 |
|----|------|------|---------|------|---------|
| UT-S02-20 | ASR 超时上限为 15 秒 | S02 Step 15、`ASR_TIMEOUT_SECONDS` | mock 延迟 16 秒 | 调 `transcribe` | 15 秒内返回 `None` |
| UT-S02-21 | 转写成功后原始音频不被删除 | S02 Step 17 说明 | 转写成功 | 检查对象存储 | 音频对象仍存在，`media.status='ready'` |
| UT-S02-22 | 转写返回空白文本视为 asr_empty | S02 EX-15.2 | ASR 返回 `"  "` | 种下语音愿望 | `degraded_reason='asr_empty'`，与 `asr_failed` 区分 |
| UT-S02-23 | near_term_todo 判定不丢弃用户内容 | S02 EX-18.2 | LLM 返回 `kind=near_term_todo` | 提交「今天下午 3 点开会」 | 201；`wishes` 行存在；响应 `actions=[keep_as_future, delete]` |
| UT-S02-24 | 孤儿媒体判定：超过 24 小时未被引用 | S02 EX-13.1 | media `ready` 且无引用，created_at 为 25 小时前 | 运行清理任务 | 该 media 与对象被删除；23 小时前的不被删 |
| UT-S02-25 | 直传不经过 API 进程 | S02 Step 5 说明 | — | 检查 `POST /media/upload-url` 响应 | `upload_url` 指向对象存储主机，非 API 主机 |

## 二、场景测试用例

### 2.1 主路径

| ID | 描述 | 覆盖 Steps | 前置条件 | 操作序列 | 预期结果 |
|----|------|-----------|---------|---------|---------|
| ST-S02-01 | 语音路径完整种下并跳过追问 | Step 1→27 | 已建号；ASR/LLM mock 正常 | 申请上传地址 → PUT 音频 → complete → `POST /wishes {source:voice}` → 点「先不说」 | 201；`media.status=ready`；`wishes.original_text` 为转写文本；`understanding.conditions` 含隐含条件；音频可回放；`pending_question=true` |
| ST-S02-02 | 文字路径一句话种下 | Step 12→27（跳过 2→11） | 已建号；LLM mock 正常 | `POST /wishes {source:text,text:"想在冬天学会滑雪"}` | 201；≤5 秒返回；`title="学会滑雪"`；`understanding.conditions.season="winter"`；`understanding.smallest_step` 非空；`question` 恰好 1 句 |
| ST-S02-03 | 附加照片种下 | Step 3→11（image）+ Step 12→27 | 已建号 | 上传 2 张照片 → 种下并带 `photo_media_ids` | 201；`wish_photos` 2 行；照片 `alt_text` 默认取标题 |

### 2.2 异常路径

| ID | 描述 | 覆盖 EX | 前置条件 | 触发条件 | 预期结果 |
|----|------|--------|---------|---------|---------|
| ST-S02-04 | 音频直传失败或预签名过期 | EX-5.1 | 预签名已过期 | PUT 到过期 URL | 对象存储返回 4xx；`wishes` 无新增行；`media` 停留 `pending`，24 小时后由清理任务回收 |
| ST-S02-05 | 媒体校验不通过 | EX-8.1 | 上传 12MB 音频 | `POST /media/{id}/complete` | 422 `MEDIA_INVALID`；对象被删除；`media.status='rejected'` |
| ST-S02-06 | 转写失败 | EX-15.1 | ASR mock 返回 500 | 种下语音愿望 | 201；`title="一段还没被读懂的话"`；`original_text IS NULL`；`degraded_reason='asr_failed'`；音频保留；`POST /wishes/{id}/transcription` 可重试成功 |
| ST-S02-07 | 转写返回空文本 | EX-15.2 | ASR mock 返回空串 | 种下语音愿望 | 同上但 `degraded_reason='asr_empty'` |
| ST-S02-08 | LLM 理解失败 | EX-18.1 | LLM mock 超时 | 种下文字愿望 | 201 `degraded=true`；原话完整；`pending_agent_jobs` 新增 `wish_understanding` |
| ST-S02-09 | 输入是当下日程 | EX-18.2 | LLM 返回 `near_term_todo` | 提交「今天下午 3 点开会」 | 201；`question` 为确认句；`actions` 两项；选 `delete` 后 `DELETE /wishes/{id}?confirm=true` 硬删且无残留 |
| ST-S02-10 | 孤儿媒体清理 | EX-13.1 | media ready 无引用满 25 小时 | 运行每日清理 | 对象与 `media` 行均被删除；不产生任何用户可见通知 |
| ST-S02-11 | 麦克风权限被拒（服务端视角） | EX-2.1 | — | 前端不发任何请求 | 服务端无任何调用记录；该用例的用户可见部分由 ST-S02-12（人工验证）覆盖 |

### 2.3 边界用例

| ID | 描述 | 覆盖 | 前置条件 | 触发条件 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S02-14 | 媒体字段边界与跨用户引用的 HTTP 层复核 | UT-S02-01~05、09~11 | 已建号 A 与 B | kind/content_type 不匹配；音频 10485760 与 10485761；photo_media_ids 10 个；B 引用 A 的 media | 422 `MEDIA_INVALID`；201 / 422；422；404 `MEDIA_NOT_FOUND` |

### 2.4 人工验证用例（[manual]）

| ID | 描述 | 覆盖 Steps | 验证方式 |
|----|------|-----------|---------|
| ST-S02-12 [manual] | 麦克风权限被拒时展示一次授权引导，已输入文字不清空，本会话不再弹出 | EX-2.1 | 真实浏览器拒绝权限后目视 |
| ST-S02-13 [manual] | 录音中显示波形与剩余秒数，到 60 秒自动停止 | Step 2 | 真实设备录音观察 |

> 上游：需求 S02 增补验收条件、`../api/wishes.yaml` 的 convertWishToLiteEvent

| ID | 描述 | 覆盖 | 前置条件 | 操作序列 | 预期结果 |
|----|------|------|---------|---------|---------|
| ST-S02-16 | 选择「先记一下」转为轻事件 | 需求 S02 增补-正常 | LLM mock 置 near_term_todo 模式；已登录 | `POST /wishes`（near_term_todo 输入）→ `POST /wishes/{id}/convert-to-lite` → `GET /lite-events` → `GET /wishes/{id}` | actions 含 save_as_lite；转换 201 返回 LiteEvent（同文本）；轻事件列表含该条；原 wish_id 访问 404；outbox 无记录 |
| ST-S02-17 | brewing 状态拒绝转换 | 需求 S02 增补-异常 | 同上但转换前已 `PUT timing`（brewing） | `POST /wishes/{id}/convert-to-lite` | 409 `STATE_TRANSITION_NOT_ALLOWED`；wish 数据不变 |
| UT-S02-26 | actions 枚举含 save_as_lite | `SeedWishResult.actions` | near_term_todo mock | 检查响应 actions | 含 keep_as_future / save_as_lite / delete 三值 |
| UT-S02-27 | 转换的轻事件归属同一用户且文本一致 | 转换语义 | 转换完成 | 查 lite_events | owner 为原用户；text 与原输入一致 |

## 三、覆盖度校验
- [x] s02-lite-conversion 增量（4 个）：EX-18.2 第三选项→ST-16、brewing 拒绝→ST-17、actions 枚举→UT-26、归属与文本→UT-27


- [x] Phase 1 正常验收条件（2 条）：ST-S02-02（文字）、ST-S02-01（语音跳过追问）
- [x] Phase 1 异常验收条件（2 条）：ST-S02-09（当下日程）、ST-S02-06/07 + ST-S02-12（转写失败与权限）
- [x] EX 异常用例（8 个）：EX-2.1→ST-11/12、EX-5.1→ST-04、EX-8.1→ST-05、EX-15.1→ST-06、EX-15.2→ST-07、EX-18.1→ST-08、EX-18.2→ST-09、EX-13.1→ST-10
- [x] API required 字段：`kind`/`content_type`/`size_bytes`（UT-01~05）、`source`+`media_id`（UT-07）全部覆盖
- [x] DB UNIQUE/CHECK 约束：`object_key` UNIQUE（UT-12）、`media.status` CHECK（UT-13）、`media_size_within_limit`（UT-03/04）、`wishes_voice_requires_audio`（UT-15）、`degraded_reason` CHECK（UT-16）、`wish_photos` PK（UT-17）、`pending_agent_jobs` 去重（UT-19）全部覆盖
- [x] Phase 2 交互级验收条件（4 条）：ST-S02-01/02/09 + ST-S02-12 [manual]

## 四、验收条件追溯

| AC ID | 验收条件（Phase 1 S02） | 覆盖用例 |
|-------|------------------------|---------|
| S02-AC-01 | 正常：一句话文字输入生成愿望卡 | ST-S02-02 |
| S02-AC-02 | 正常：语音输入并跳过追问 | ST-S02-01, UT-S02-21 |
| S02-AC-03 | 异常：输入内容不构成一件未来想做的事 | ST-S02-09, UT-S02-23 |
| S02-AC-04 | 异常：语音转写失败或权限被拒绝 | ST-S02-06, ST-S02-07, ST-S02-12 [manual], UT-S02-22 |

| AC ID | 验收条件（S02 增补） | 覆盖用例 |
|-------|---------------------|---------|
| S02-AC-05 | 正常（增补）：选择「先记一下」转为轻事件 | ST-S02-16, UT-S02-26/27 |
| S02-AC-06 | 异常（增补）：已约定时机的愿望不可转换 | ST-S02-17 |
