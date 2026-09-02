-- =============================================================================
-- 未发生事件管理局 — 数据库 Schema（SQLite 3.40+）
-- 来源：logos/resources/api/*.yaml（auth / media / wishes / memories / system）
--       与 logos/resources/prd/3-technical-plan/1-architecture/core-01-architecture-overview.md
-- 生成阶段：Phase 3 Step 2（db-designer）｜方言变更：PostgreSQL → SQLite
--
-- 连接时必须执行（SQLite 默认不开外键，且默认日志模式不适合并发读）：
--   PRAGMA foreign_keys = ON;
--   PRAGMA journal_mode = WAL;
--   PRAGMA busy_timeout = 5000;
--
-- 三条贯穿全库的设计约束（来自需求与场景，不是通用最佳实践）：
--   1. 隐私：所有「用户自己说的话」以 *_enc BLOB 存储，**加密在应用层完成**
--      （AES-256-GCM，密钥来自环境变量 ENCRYPTION_KEY）。数据库只见密文，
--      因此明文不会作为 SQL 参数出现，也不会落进任何数据库日志。
--      代价：这些列不可用于 WHERE / ORDER BY / JOIN，无法建全文索引。
--   2. 隔离：SQLite 没有行级安全。「仅本人可见」由两道应用层防线保证：
--      仓储层统一注入 owner_id（第一道）+ 会话级运行时守卫（第二道，见文末）。
--      **这是相对 PostgreSQL 方案的实质性弱化，已在架构文档 5.3 记录。**
--   3. 不制造焦虑：库中刻意不存在 顺延次数 / 完成率 / 连续天数 / 逾期天数 等任何列，
--      使 UI 在结构上无法显示压迫性指标（见 S03 EX-20.1）。
--
-- 类型约定（SQLite 无原生 UUID / 布尔 / 时间类型）：
--   主键与外键  TEXT，存 UUID v4 字符串，由应用层生成
--   时间        TEXT，ISO 8601 UTC，如 2026-09-01T12:00:00.000Z
--   布尔        INTEGER，仅 0 / 1，均带 CHECK
--   JSON        TEXT，存 JSON 字符串，由应用层序列化
--   加密内容    BLOB
--   updated_at  由应用层刷新，不使用触发器
-- =============================================================================

-- -----------------------------------------------------------------------------
-- users（来源：auth.yaml → createAnonymousSpace, linkEmail, login, getMe）
-- -----------------------------------------------------------------------------
CREATE TABLE users (
  -- @comment 用户唯一标识（UUID v4 字符串），同时是全库 owner 主体
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 邮箱，已归一化为小写；未绑定时为 NULL。绑定后才可跨设备登录
  email TEXT UNIQUE,
  -- @comment Argon2id 密码哈希，仅存哈希，永不返回给客户端
  password_hash TEXT,
  -- @comment 1 表示尚未绑定邮箱，换设备后无法找回其愿望
  is_anonymous INTEGER NOT NULL DEFAULT 1 CHECK (is_anonymous IN (0, 1)),
  -- @comment 首次体验完成时间。建号时即写入，使「跳过问题后未输入即离开」不会重复首次体验（S01 EX-12.1）
  onboarded_at TEXT,
  -- @comment IANA 时区名。提醒周预算按该时区的自然周计算，季节触发也依赖它
  timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  -- @comment 用户可在 /me 关闭推送；关闭后不再有任何应用内催促标记
  push_enabled INTEGER NOT NULL DEFAULT 1 CHECK (push_enabled IN (0, 1)),
  -- @comment 邮件兜底通道开关。iOS Safari 未添加主屏时这是唯一可用通道
  email_enabled INTEGER NOT NULL DEFAULT 1 CHECK (email_enabled IN (0, 1)),
  -- @comment 创建时间，ISO 8601 UTC
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间，由应用层刷新
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT users_email_password_together
    CHECK ((email IS NULL AND password_hash IS NULL)
        OR (email IS NOT NULL AND password_hash IS NOT NULL)),
  CONSTRAINT users_anonymous_has_no_email
    CHECK (is_anonymous = (CASE WHEN email IS NULL THEN 1 ELSE 0 END))
);
-- @table-comment users 用户表。首次体验以匿名主体建号（is_anonymous=1, email 为 NULL），邮箱绑定为后置可选动作

-- -----------------------------------------------------------------------------
-- sessions（来源：auth.yaml → refreshToken, logout）
-- -----------------------------------------------------------------------------
CREATE TABLE sessions (
  -- @comment 会话唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户，用户删除时级联清除
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment refresh token 的 SHA-256 哈希，明文只存在于 httpOnly Cookie 中
  refresh_hash TEXT NOT NULL UNIQUE,
  -- @comment 登录设备标识，仅用于用户自查设备列表
  user_agent TEXT,
  -- @comment 过期时间，签发后 30 天
  expires_at TEXT NOT NULL,
  -- @comment 撤销时间。登出或轮换后置值，非 NULL 即失效
  revoked_at TEXT,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- @table-comment sessions refresh token 记录表。存哈希以支持撤销与轮换

-- 按用户查活跃会话（登出全部设备、轮换时校验）
CREATE INDEX idx_sessions_owner_active ON sessions(owner_id) WHERE revoked_at IS NULL;
-- 过期会话清理任务扫描用
CREATE INDEX idx_sessions_expires ON sessions(expires_at) WHERE revoked_at IS NULL;

-- -----------------------------------------------------------------------------
-- onboarding_answers（来源：auth.yaml → submitOnboardingAnswers）
-- -----------------------------------------------------------------------------
CREATE TABLE onboarding_answers (
  -- @comment 回答唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 问题标识，如 wanted_but_not_done
  question_key TEXT NOT NULL,
  -- @comment 用户回答，应用层 AES-256-GCM 加密；NULL 表示该题留空
  answer_enc BLOB,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT onboarding_answers_unique_per_question UNIQUE (owner_id, question_key)
);
-- @table-comment onboarding_answers 温柔问题的回答，作为 Agent 的初始记忆语料。写入失败不影响首次体验（S01 EX-10.1）

CREATE INDEX idx_onboarding_answers_owner ON onboarding_answers(owner_id);

-- -----------------------------------------------------------------------------
-- media（来源：media.yaml → createMediaUploadUrl, completeMediaUpload）
-- 先于 wishes 建表：wishes.audio_media_id 引用它
-- -----------------------------------------------------------------------------
CREATE TABLE media (
  -- @comment 媒体唯一标识，即 API 中的 media_id
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment audio 为愿望语音或记忆页录音，image 为照片
  kind TEXT NOT NULL CHECK (kind IN ('audio', 'image')),
  -- @comment 对象存储中的键。彻底删除时先按此键删对象再删数据库记录（S05.2 步骤说明）
  object_key TEXT NOT NULL UNIQUE,
  -- @comment MIME 类型，白名单校验后写入
  content_type TEXT NOT NULL,
  -- @comment 字节数。audio 上限 10MB，image 上限 8MB（S02 EX-8.1）
  size_bytes INTEGER,
  -- @comment pending 已签发未确认；ready 校验通过可被引用；rejected 校验失败且对象已删
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'rejected')),
  -- @comment 图片替代文本，默认取愿望或记忆页标题，应用层加密
  alt_text_enc BLOB,
  -- @comment 记忆页内照片排序，用户可长按调整
  sort_order INTEGER NOT NULL DEFAULT 0,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT media_size_within_limit
    CHECK (size_bytes IS NULL
        OR (kind = 'audio' AND size_bytes <= 10485760)
        OR (kind = 'image' AND size_bytes <= 8388608))
);
-- @table-comment media 媒体元数据。对象本身在 S3 兼容存储中，由前端直传；本表只存元数据与状态

-- 孤儿媒体清理任务：超过 24 小时未被引用（S02 EX-13.1）
CREATE INDEX idx_media_orphan_scan ON media(created_at) WHERE status <> 'rejected';
CREATE INDEX idx_media_owner ON media(owner_id);

-- -----------------------------------------------------------------------------
-- wishes（来源：wishes.yaml → seedWish, listWishes, getWish, setWishTiming,
--         markWishReady, deferWish, pauseWishReminders, moveWishBackToBrewing,
--         letGoWish, amendWish, deleteWishPermanently）
-- -----------------------------------------------------------------------------
CREATE TABLE wishes (
  -- @comment 愿望唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户。SQLite 无 RLS，隔离由仓储层注入 + 运行时守卫保证（见文末）
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 标题，应用层加密。LLM 提炼的短句，降级时回退为原话前 20 字（S01 EX-16.1）
  title_enc BLOB NOT NULL,
  -- @comment 用户原话或语音转写文本，应用层加密。ASR 失败时为 NULL 但音频保留（S02 EX-15.1）
  original_text_enc BLOB,
  -- @comment text 为文字输入，voice 为语音输入
  source TEXT NOT NULL CHECK (source IN ('text', 'voice')),
  -- @comment 原始音频。永久保留以支持重试转写。用 RESTRICT 而非 SET NULL：被愿望引用的音频不允许被单独删除，否则会与 wishes_voice_requires_audio 约束互相矛盾（该冲突由 UT-S02-18 发现）
  audio_media_id TEXT REFERENCES media(id) ON DELETE RESTRICT,
  -- @comment 刚种下 / 正在酝酿 / 风来了 / 正在发生 / 已经发生 / 安静放下
  state TEXT NOT NULL DEFAULT 'seeded'
    CHECK (state IN ('seeded','brewing','wind','going','happened','let_go')),
  -- @comment LLM 结构化理解结果的 JSON 字符串（kind/feeling/conditions/smallest_step）。Pydantic 校验失败时保持 NULL，绝不写入半结构化结果（S01 EX-16.2）
  understanding TEXT,
  -- @comment 1 表示有一句「待未来再问」的追问，本次已被用户跳过
  pending_question INTEGER NOT NULL DEFAULT 0 CHECK (pending_question IN (0, 1)),
  -- @comment Agent 的一句追问原文，加密存储
  question_enc BLOB,
  -- @comment 用户对追问的回答，加密存储；跳过时为 NULL
  answer_enc BLOB,
  -- @comment 6 种时机类型之一，none 表示「不必提醒，我自己会想起」
  timing_type TEXT CHECK (timing_type IS NULL OR timing_type IN
    ('season','month_day','after_months','free_weekend','when_tired','none')),
  -- @comment 时机参数：season 存 winter，month_day 存 2027-03 或 2027-03-15，after_months 存 3
  timing_value TEXT,
  -- @comment time 由时间触发；signal 为 when_tired，须由对话检出疲惫后回写触发时间（S03 EX-11.1）；none 永不提醒
  trigger_kind TEXT NOT NULL DEFAULT 'none' CHECK (trigger_kind IN ('time','signal','none')),
  -- @comment 用户定下该时机的时刻。周预算不足时的顺延排序键——先顺延最近才随手设的（S03 Step 11）
  timing_set_at TEXT,
  -- @comment 下次触发时刻，一律由服务端按 users.timezone 计算，禁止前端传入
  next_trigger_at TEXT,
  -- @comment 本次时机的唯一标识（如 season:winter:2026）。与 reminder_outbox 的唯一索引配合保证同一时机只发一条
  timing_occurrence TEXT,
  -- @comment 1 表示本周提醒被预算顺延，卡面显示「本周先不打扰你」（S03 EX-14.1）
  soft_deferred INTEGER NOT NULL DEFAULT 0 CHECK (soft_deferred IN (0, 1)),
  -- @comment 降级原因；asr_empty 与 asr_failed 分开是因为「没听清」和「服务坏了」对用户是两件事
  degraded_reason TEXT
    CHECK (degraded_reason IS NULL OR degraded_reason IN ('llm_failed','asr_failed','asr_empty')),
  -- @comment 首次种下时间。修改愿望、唤回被放下的愿望时均不变
  seeded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 安静放下时间。仅 state='let_go' 时展示；历史数据和重新种下后可为 NULL（S07）
  let_go_at TEXT,
  -- @comment 最后一次用户动作时间。going 状态下距今 60 天触发一次关心（S04 EX-15.2）
  last_activity_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 停滞关心已发送时间，用于保证每个愿望只发 1 次
  stale_notified_at TEXT,
  -- @comment 乐观锁版本号，随 If-Match 头校验并发提交（S04 EX-15.1）
  version INTEGER NOT NULL DEFAULT 1,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT wishes_voice_requires_audio
    CHECK (source <> 'voice' OR audio_media_id IS NOT NULL),
  CONSTRAINT wishes_signal_and_none_have_no_trigger_time
    CHECK (trigger_kind = 'time' OR next_trigger_at IS NULL),
  CONSTRAINT wishes_let_go_timestamp_matches_state
    CHECK (state = 'let_go' OR let_go_at IS NULL)
);
-- @table-comment wishes 愿望表，产品核心实体。状态机见架构概要第四节；happened 为终态不可回退；let_go_at 用于 S07 安静放下区排序与展示

-- 花园列表：按 owner + 状态过滤后按种下时间倒序（listWishes，S05.1 Step 3）
CREATE INDEX idx_wishes_owner_state_seeded ON wishes(owner_id, state, seeded_at DESC);
-- 花园「全部」视图与游标分页（listWishes 默认参数）
CREATE INDEX idx_wishes_owner_seeded ON wishes(owner_id, seeded_at DESC, id);
-- Scheduler 扫描到期时机：只索引真正可能被触发的行（S03 Step 11）
CREATE INDEX idx_wishes_due_trigger ON wishes(next_trigger_at, timing_set_at)
  WHERE trigger_kind = 'time' AND next_trigger_at IS NOT NULL
    AND state IN ('seeded', 'brewing');
-- Scheduler 扫描 60 天停滞（S04 EX-15.2），只索引尚未通知过的 going 行
CREATE INDEX idx_wishes_stale_scan ON wishes(last_activity_at)
  WHERE state = 'going' AND stale_notified_at IS NULL;
-- 疲惫信号命中时批量回写 next_trigger_at（S03 EX-11.1）
CREATE INDEX idx_wishes_signal_trigger ON wishes(owner_id) WHERE trigger_kind = 'signal';
-- 外键索引，避免删除媒体时全表扫描
CREATE INDEX idx_wishes_audio_media ON wishes(audio_media_id) WHERE audio_media_id IS NOT NULL;
-- S07 安静放下区：按放下时间倒序，历史兼容数据再按首次种下时间倒序
CREATE INDEX idx_wishes_owner_let_go_at ON wishes(owner_id, let_go_at DESC, seeded_at DESC, id)
  WHERE state = 'let_go';
-- 说明：understanding 改为 TEXT 后不再有 GIN 索引。按 feeling 选兜底步骤（S04 EX-8.2）
-- 改为应用层解析，因为该查询只在单条记录上发生，不需要索引支持。

-- -----------------------------------------------------------------------------
-- wish_amendments（来源：wishes.yaml → amendWish、sendWishMessage 的 intent=amend）
-- -----------------------------------------------------------------------------
CREATE TABLE wish_amendments (
  -- @comment 快照唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属愿望，愿望删除时级联清除
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment 所属用户，冗余存储以便守卫层直接过滤而不必 JOIN
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 修改前的标题，加密存储
  prev_title_enc BLOB NOT NULL,
  -- @comment 修改前的用户原话，加密存储
  prev_original_enc BLOB,
  -- @comment 修改前的结构化理解结果（JSON 字符串）
  prev_understanding TEXT,
  -- @comment 修订时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- @table-comment wish_amendments 愿望修订快照。支撑详情页的「最初你说的是……」（S04 EX-23.1），最早一条即原始表述

CREATE INDEX idx_wish_amendments_wish ON wish_amendments(wish_id, created_at);

-- -----------------------------------------------------------------------------
-- wish_steps（来源：wishes.yaml → requestNextStep, markStepDone）
-- -----------------------------------------------------------------------------
CREATE TABLE wish_steps (
  -- @comment 步骤唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属愿望
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment 所属用户，冗余存储供守卫层使用
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 步骤文本，加密存储
  text_enc BLOB NOT NULL,
  -- @comment proposed 待完成；done 已完成并进入时间线；rejected 被用户拒绝且永不再出现（S04 EX-13.1）
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'done', 'rejected')),
  -- @comment 模型自报的预计耗时，服务端强制 ≤5 分钟（S04 EX-8.2）
  est_minutes INTEGER CHECK (est_minutes IS NULL OR est_minutes <= 5),
  -- @comment 模型自报是否涉及花钱，为 1 时服务端拒绝并重新生成
  involves_cost INTEGER NOT NULL DEFAULT 0 CHECK (involves_cost IN (0, 1)),
  -- @comment 模型自报是否需要联系他人，为 1 时服务端拒绝并重新生成
  involves_others INTEGER NOT NULL DEFAULT 0 CHECK (involves_others IN (0, 1)),
  -- @comment llm 由模型生成；fallback 为内置兜底步骤
  source TEXT NOT NULL DEFAULT 'llm' CHECK (source IN ('llm', 'fallback')),
  -- @comment 完成时间，即时间线上显示的时间
  completed_at TEXT,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT wish_steps_done_has_completed_at
    CHECK ((status = 'done' AND completed_at IS NOT NULL)
        OR (status <> 'done' AND completed_at IS NULL))
);
-- @table-comment wish_steps 最小下一步与准备过程时间线。同一愿望在任一时刻只允许 1 条 proposed（由下方部分唯一索引强制）

-- 强制「任一时刻只存在 1 个 proposed 步骤」——结构性保证，不依赖代码判断
CREATE UNIQUE INDEX idx_wish_steps_single_proposed ON wish_steps(wish_id) WHERE status = 'proposed';
CREATE INDEX idx_wish_steps_timeline ON wish_steps(wish_id, completed_at) WHERE status = 'done';
CREATE INDEX idx_wish_steps_rejected ON wish_steps(wish_id) WHERE status = 'rejected';

-- -----------------------------------------------------------------------------
-- wish_messages（来源：wishes.yaml → sendWishMessage）
-- -----------------------------------------------------------------------------
CREATE TABLE wish_messages (
  -- @comment 消息唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属愿望
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment 所属用户，冗余存储供守卫层使用
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment user 为用户发言，agent 为 Agent 回复
  role TEXT NOT NULL CHECK (role IN ('user', 'agent')),
  -- @comment 消息正文，加密存储
  text_enc BLOB NOT NULL,
  -- @comment LLM 判定的意图：chat 闲聊 / amend 修改愿望 / assist 推进协助 / fatigue 疲惫信号
  intent TEXT CHECK (intent IS NULL OR intent IN ('chat', 'amend', 'assist', 'fatigue')),
  -- @comment 发送时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- @table-comment wish_messages 愿望详情页的往来对话。同一通道承载多种意图，由 intent 分类

CREATE INDEX idx_wish_messages_wish ON wish_messages(wish_id, created_at);

-- -----------------------------------------------------------------------------
-- wish_photos / memory_photos（有序关联表）
-- -----------------------------------------------------------------------------
CREATE TABLE wish_photos (
  -- @comment 所属愿望
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment 照片媒体
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  -- @comment 展示顺序
  sort_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (wish_id, media_id)
);
-- @table-comment wish_photos 愿望与照片的有序关联，每个愿望最多 9 张（应用层校验）

CREATE INDEX idx_wish_photos_media ON wish_photos(media_id);

-- -----------------------------------------------------------------------------
-- memories（来源：memories.yaml → markWishHappened, updateMemory, publishMemory,
--           listMemories, getMemory）
-- -----------------------------------------------------------------------------
CREATE TABLE memories (
  -- @comment 记忆页唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 来源愿望，唯一约束保证一事一页；愿望彻底删除时草稿一并失效（S06 EX-18.1）
  wish_id TEXT NOT NULL UNIQUE REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment 所属用户，冗余存储供守卫层使用
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 标题，加密存储。LLM 草拟，降级时回退为愿望原标题（S06 EX-7.1）
  title_enc BLOB NOT NULL,
  -- @comment 起因，引用原始期待；降级时回退为直接引用用户原话
  cause_enc BLOB,
  -- @comment 经过，依据准备过程时间线草拟；无时间线时为 NULL，前端渲染占位（S06 EX-4.1）
  process_enc BLOB,
  -- @comment 6 个低饱和心情词之一，可为 NULL 表示不选；不使用 emoji
  mood TEXT CHECK (mood IS NULL OR mood IN
    ('relieved','healed','tearful','calm','proud','unspeakable')),
  -- @comment 「如果只留一句话」，加密存储
  last_line_enc BLOB,
  -- @comment 可选的一段不超过 60 秒录音
  voice_media_id TEXT REFERENCES media(id) ON DELETE SET NULL,
  -- @comment 发生日期（YYYY-MM-DD），或区间起始。允许早于 wishes.seeded_at（S06 EX-3.1）
  happened_from TEXT NOT NULL,
  -- @comment 区间结束；单日时为 NULL
  happened_to TEXT,
  -- @comment 1 时阅读态注明「你是在它发生之后才写下它的」
  note_before_seeded INTEGER NOT NULL DEFAULT 0 CHECK (note_before_seeded IN (0, 1)),
  -- @comment 用户手动改过的字段名，JSON 数组字符串。Scheduler 补草拟时跳过这些字段（S06 EX-7.1）
  edited_fields TEXT NOT NULL DEFAULT '[]',
  -- @comment draft 草稿，未入册；published 已收进书里
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  -- @comment 入册时间。重复发布时保持不变以保证幂等（S06 EX-17.1）
  published_at TEXT,
  -- @comment 创建时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后更新时间
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT memories_range_ordered
    CHECK (happened_to IS NULL OR happened_to >= happened_from),
  CONSTRAINT memories_published_has_timestamp
    CHECK ((status = 'published' AND published_at IS NOT NULL)
        OR (status <> 'published' AND published_at IS NULL))
);
-- @table-comment memories 记忆页。一个愿望最多一页（wish_id 唯一）。全部内容字段均可为空——「跳过全部补充内容」是明确的验收条件

CREATE INDEX idx_memories_owner_published ON memories(owner_id, happened_from DESC, id)
  WHERE status = 'published';
CREATE INDEX idx_memories_draft ON memories(owner_id) WHERE status = 'draft';
CREATE INDEX idx_memories_voice_media ON memories(voice_media_id) WHERE voice_media_id IS NOT NULL;

CREATE TABLE memory_photos (
  -- @comment 所属记忆页
  memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  -- @comment 照片媒体
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  -- @comment 展示顺序，用户可长按调整
  sort_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (memory_id, media_id)
);
-- @table-comment memory_photos 记忆页与照片的有序关联，每页最多 9 张（应用层校验，S06 EX-12.1）

CREATE INDEX idx_memory_photos_media ON memory_photos(media_id);

-- -----------------------------------------------------------------------------
-- push_subscriptions（来源：架构概要 Web Push 依赖；S03 EX-16.1）
-- -----------------------------------------------------------------------------
CREATE TABLE push_subscriptions (
  -- @comment 订阅唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 推送服务端点 URL，全局唯一
  endpoint TEXT NOT NULL UNIQUE,
  -- @comment Web Push 加密公钥
  p256dh TEXT NOT NULL,
  -- @comment Web Push 认证密钥
  auth_secret TEXT NOT NULL,
  -- @comment 订阅设备标识，用于用户自查
  user_agent TEXT,
  -- @comment 订阅时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- @table-comment push_subscriptions 浏览器推送订阅。收到 404/410 即删除该行并改走邮件（S03 EX-16.1）

CREATE INDEX idx_push_subscriptions_owner ON push_subscriptions(owner_id);

-- -----------------------------------------------------------------------------
-- reminder_outbox（来源：system.yaml → testReadOutbox；S03 Step 14 → Step 17）
-- -----------------------------------------------------------------------------
CREATE TABLE reminder_outbox (
  -- @comment 记录唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 收件用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 关联愿望。放下或标记已发生时，pending 记录会被同事务删除（S05.2 Step 19、S06 Step 6）
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment timing 为时机提醒；stale_care 为 60 天停滞关心，两者共用同一份周预算
  kind TEXT NOT NULL CHECK (kind IN ('timing', 'stale_care')),
  -- @comment 本次时机的唯一标识，与 wish_id、kind 组成唯一索引以拦截重复扫描（S03 EX-14.2）
  timing_occurrence TEXT NOT NULL,
  -- @comment 通知正文，加密存储。由模板拼接而成，不调用 LLM
  body_enc BLOB NOT NULL,
  -- @comment 实际投递通道。push 优先，订阅失效或 iOS 未添加主屏时为 email
  channel TEXT CHECK (channel IS NULL OR channel IN ('push', 'email')),
  -- @comment pending 待投递；delivered 已送达并计入周预算；failed 重试耗尽；deferred_to_next_week 被周预算顺延
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','delivered','failed','deferred_to_next_week')),
  -- @comment 投递尝试次数，上限 3（5 分钟 / 30 分钟 / 2 小时退避）
  attempts INTEGER NOT NULL DEFAULT 0,
  -- @comment 下次重试时刻
  next_attempt_at TEXT,
  -- @comment 送达时间
  delivered_at TEXT,
  -- @comment 最后一次失败的错误码，仅用于排查，不含通知内容
  last_error_code TEXT,
  -- @comment 入箱时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT reminder_outbox_delivered_has_channel
    CHECK (status <> 'delivered' OR (delivered_at IS NOT NULL AND channel IS NOT NULL))
);
-- @table-comment reminder_outbox 提醒发件箱。是「同一时机只发一条」与「每周不超过 3 条」两条产品规则的落地点

-- 结构性保证「同一时机只发一条」（S03 EX-14.2），配合 INSERT OR IGNORE
CREATE UNIQUE INDEX idx_reminder_outbox_once ON reminder_outbox(wish_id, kind, timing_occurrence);
CREATE INDEX idx_reminder_outbox_pending ON reminder_outbox(next_attempt_at) WHERE status = 'pending';
CREATE INDEX idx_reminder_outbox_owner ON reminder_outbox(owner_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- reminder_weekly_counters（来源：S03 Step 13；system.yaml → testReadOutbox）
-- -----------------------------------------------------------------------------
CREATE TABLE reminder_weekly_counters (
  -- @comment 用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 自然周起始日（按 users.timezone 的周一，YYYY-MM-DD）
  week_start TEXT NOT NULL,
  -- @comment 本周已成功投递条数。投递失败不累加（S03 EX-16.2）
  delivered_count INTEGER NOT NULL DEFAULT 0 CHECK (delivered_count BETWEEN 0 AND 3),
  -- @comment 最后更新时间
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (owner_id, week_start)
);
-- @table-comment reminder_weekly_counters 每周提醒计数。CHECK 上限 3 把产品指标写进约束——即使调度代码写错，数据库也不会让第 4 条被记为已投递

-- -----------------------------------------------------------------------------
-- pending_agent_jobs（来源：S01 EX-16.1、S02 EX-15.1、S04 EX-8.1、S06 EX-7.1）
-- -----------------------------------------------------------------------------
CREATE TABLE pending_agent_jobs (
  -- @comment 任务唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 目标愿望，memory_draft 之外的任务都指向它
  wish_id TEXT REFERENCES wishes(id) ON DELETE CASCADE,
  -- @comment 目标记忆页，仅 memory_draft 使用
  memory_id TEXT REFERENCES memories(id) ON DELETE CASCADE,
  -- @comment wish_understanding 补理解 / transcription 补转写 / next_step 补步骤 / memory_draft 补记忆草拟
  job_kind TEXT NOT NULL
    CHECK (job_kind IN ('wish_understanding','transcription','next_step','memory_draft')),
  -- @comment 重试次数，低频退避，避免外部服务长期故障时放大成本
  attempts INTEGER NOT NULL DEFAULT 0,
  -- @comment 下次重试时刻
  next_attempt_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 最后一次失败的错误码；不记录响应内容（隐私红线）
  last_error_code TEXT,
  -- @comment 入队时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CONSTRAINT pending_agent_jobs_has_target
    CHECK (wish_id IS NOT NULL OR memory_id IS NOT NULL)
);
-- @table-comment pending_agent_jobs 待补的 Agent 工作。承接「先替你收好了，我稍后再慢慢读它」这句承诺——降级不是丢弃，而是入队

CREATE INDEX idx_pending_agent_jobs_due ON pending_agent_jobs(next_attempt_at);
CREATE UNIQUE INDEX idx_pending_agent_jobs_dedup
  ON pending_agent_jobs(job_kind, COALESCE(wish_id, memory_id));

-- -----------------------------------------------------------------------------
-- orphan_objects（来源：S05.2 EX-28.1、S02 EX-13.1）
-- -----------------------------------------------------------------------------
CREATE TABLE orphan_objects (
  -- @comment 记录唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 对象存储键。此表不含 owner_id——记录已从业务表删除，无所属用户可言
  object_key TEXT NOT NULL UNIQUE,
  -- @comment delete_failed 删除失败残留；unreferenced 上传后 24 小时未被引用
  reason TEXT NOT NULL CHECK (reason IN ('delete_failed', 'unreferenced')),
  -- @comment 清理重试次数
  attempts INTEGER NOT NULL DEFAULT 0,
  -- @comment 记录时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- @table-comment orphan_objects 待清理的存储对象。彻底删除时对象存储失败不阻塞用户的删除意图，残留在此收敛（S05.2 EX-28.1）

CREATE INDEX idx_orphan_objects_pending ON orphan_objects(created_at);

-- -----------------------------------------------------------------------------
-- scheduler_heartbeat（来源：system.yaml → healthCheck）
-- -----------------------------------------------------------------------------
CREATE TABLE scheduler_heartbeat (
  -- @comment 固定为 1，CHECK 约束保证全表只有一行
  id INTEGER PRIMARY KEY NOT NULL DEFAULT 1 CHECK (id = 1),
  -- @comment 当前持有调度锁的实例标识
  instance_id TEXT NOT NULL,
  -- @comment 最后一次心跳时间，每轮扫描结束时刷新
  last_beat_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- @table-comment scheduler_heartbeat 单行表，用于判断调度进程存活。健康检查读取 last_beat_at，超过 900 秒应告警

-- =============================================================================
-- 数据隔离：应用层两道防线（SQLite 无 RLS）
--
-- PostgreSQL 方案里第二道防线是行级安全策略：漏写 owner_id 条件时数据库返回空集。
-- 换到 SQLite 后这一层不存在，因此改为：
--
--   第一道：仓储层统一注入 owner_id。禁止在路由层手写 WHERE，代码审查检查项。
--   第二道：会话级运行时守卫。所有对 owner 表的 SELECT / UPDATE / DELETE
--           必须经由 OwnedSession 包装器发出；包装器在语句执行前断言
--           WHERE 中含 owner_id 绑定参数，否则直接抛异常（而不是返回错误数据）。
--           实现见 backend/app/db.py 的 owner_guard 事件钩子。
--
-- 受守卫保护的表（等价于原 RLS 策略集合）：
--   users, sessions, onboarding_answers, media, wishes, wish_amendments,
--   wish_steps, wish_messages, wish_photos, memories, memory_photos,
--   push_subscriptions, reminder_outbox, reminder_weekly_counters,
--   pending_agent_jobs
-- 不受保护（无 owner_id，仅服务进程访问）：orphan_objects, scheduler_heartbeat
--
-- **诚实记录代价**：守卫是进程内断言，绕过 ORM 直接开 sqlite3 连接即可绕过它；
-- 而 RLS 是数据库强制的。这是选择 SQLite 必然付出的代价，已在架构 5.3 与
-- 部署方案的风险清单中标注。越权访问仍统一返回 404 而非 403（S05 EX-3.1）。
-- =============================================================================

-- =============================================================================
-- 加密列读写约定（应用层 AES-256-GCM）
--
-- 所有 *_enc BLOB 列由应用层加解密，密钥来自环境变量 ENCRYPTION_KEY：
--   写：aes_gcm_encrypt(plaintext, key) -> nonce || ciphertext || tag
--   读：aes_gcm_decrypt(blob, key)
-- 应用层用 SQLAlchemy TypeDecorator 封装，业务代码看到的是普通 str。
--
-- 相对 pgcrypto 方案的两个变化：
--   1. **更安全**：明文不再作为 SQL 参数传输，因此不存在「打开语句日志就泄露原文」
--      的风险，部署方案 3.4 关于 log_statement 的强制要求随之取消。
--   2. 代价不变：这些列仍不可用于 WHERE / ORDER BY / JOIN，无法建全文索引。
--
-- 密钥轮换需要一次全表重写，不在 MVP 范围。ENCRYPTION_KEY 丢失即所有用户内容
-- 永久不可读 —— 必须与数据库文件分开存放并离线冷备。
--
-- 明文保留的列及理由：
--   state / timing_type / trigger_kind / next_trigger_at / seeded_at 等——
--   调度与筛选必须依赖它们；它们只暴露「有一件事在等某个时机」，不暴露那件事是什么。
-- =============================================================================

-- =============================================================================
-- 追溯汇总：API 端点 → 表
--
--   auth.yaml       createAnonymousSpace / linkEmail / login / refreshToken / logout / getMe
--                     → users, sessions
--                   submitOnboardingAnswers → onboarding_answers
--   media.yaml      createMediaUploadUrl / completeMediaUpload → media
--   wishes.yaml     seedWish / listWishes / getWish / amendWish / deleteWishPermanently
--                     → wishes, wish_photos, wish_amendments, media
--                   answerWishQuestion / retryWishUnderstanding / retryTranscription
--                     → wishes, pending_agent_jobs
--                   setWishTiming / markWishReady / deferWish / pauseWishReminders
--                   / moveWishBackToBrewing / letGoWish / recallWish
--                     → wishes, reminder_outbox
--                   requestNextStep / markStepDone → wish_steps, wishes
--                   sendWishMessage → wish_messages, wishes, wish_amendments
--   memories.yaml   markWishHappened / updateMemory / publishMemory / listMemories
--                   / getMemory → memories, memory_photos, media, wishes, reminder_outbox
--   system.yaml     healthCheck → scheduler_heartbeat
--                   testReadOutbox → reminder_outbox, reminder_weekly_counters
--                   testTriggerSchedulerTick → wishes, reminder_outbox, pending_agent_jobs
--
-- 无对应 API 端点的表（仅供服务进程使用，刻意如此）：
--   orphan_objects（清理队列）、scheduler_heartbeat（仅由 healthCheck 读取）
-- =============================================================================






