## MODIFIED — CREATE TABLE wishes

CREATE TABLE wishes (
  -- @comment 愿望唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户，所有查询必须带 owner_id 守卫
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 输入来源：文本或语音
  source TEXT NOT NULL CHECK (source IN ('text','voice')),
  -- @comment 用户原话，加密存储
  original_text_enc BLOB,
  -- @comment 语音原始文件，ASR 失败后可重试
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

## ADDED — idx_wishes_owner_let_go_at

-- S07 安静放下区：按放下时间倒序，历史兼容数据再按首次种下时间倒序
CREATE INDEX idx_wishes_owner_let_go_at ON wishes(owner_id, let_go_at DESC, seeded_at DESC, id)
  WHERE state = 'let_go';

## MODIFIED — 追溯汇总：API 端点 → 表

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
