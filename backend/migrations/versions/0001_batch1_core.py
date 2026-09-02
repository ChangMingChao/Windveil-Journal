"""Alembic 初始迁移（Batch 1）— SQLite。

来源：logos/resources/database/schema.sql 的转写。按部署方案第五节，
生产不直接执行 schema.sql，而以此 revision 为准。

本 revision 只建 S01 所需的表；其余表在后续批次的 revision 中加入。

SQLite 的 ALTER TABLE 能力有限：后续 revision 若要改列，必须用
op.batch_alter_table()（Alembic 会自动走「建新表 → 拷数据 → 换名」）。

revision: 0001_batch1_core
"""

from alembic import op

revision = "0001_batch1_core"
down_revision = None
branch_labels = None
depends_on = None

TS_DEFAULT = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

DDL = f"""
CREATE TABLE users (
  id TEXT PRIMARY KEY NOT NULL,
  email TEXT UNIQUE,
  password_hash TEXT,
  is_anonymous INTEGER NOT NULL DEFAULT 1 CHECK (is_anonymous IN (0, 1)),
  onboarded_at TEXT,
  timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  push_enabled INTEGER NOT NULL DEFAULT 1 CHECK (push_enabled IN (0, 1)),
  email_enabled INTEGER NOT NULL DEFAULT 1 CHECK (email_enabled IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  updated_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  CONSTRAINT users_email_password_together
    CHECK ((email IS NULL AND password_hash IS NULL)
        OR (email IS NOT NULL AND password_hash IS NOT NULL)),
  CONSTRAINT users_anonymous_has_no_email
    CHECK (is_anonymous = (CASE WHEN email IS NULL THEN 1 ELSE 0 END))
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_hash TEXT NOT NULL UNIQUE,
  user_agent TEXT,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL DEFAULT {TS_DEFAULT}
);
CREATE INDEX idx_sessions_owner_active ON sessions(owner_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_sessions_expires ON sessions(expires_at) WHERE revoked_at IS NULL;

CREATE TABLE onboarding_answers (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_key TEXT NOT NULL,
  answer_enc BLOB,
  created_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  CONSTRAINT onboarding_answers_unique_per_question UNIQUE (owner_id, question_key)
);
CREATE INDEX idx_onboarding_answers_owner ON onboarding_answers(owner_id);

CREATE TABLE media (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('audio', 'image')),
  object_key TEXT NOT NULL UNIQUE,
  content_type TEXT NOT NULL,
  size_bytes INTEGER,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'rejected')),
  alt_text_enc BLOB,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  updated_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  CONSTRAINT media_size_within_limit
    CHECK (size_bytes IS NULL
        OR (kind = 'audio' AND size_bytes <= 10485760)
        OR (kind = 'image' AND size_bytes <= 8388608))
);
CREATE INDEX idx_media_orphan_scan ON media(created_at) WHERE status <> 'rejected';
CREATE INDEX idx_media_owner ON media(owner_id);

CREATE TABLE wishes (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title_enc BLOB NOT NULL,
  original_text_enc BLOB,
  source TEXT NOT NULL CHECK (source IN ('text', 'voice')),
  audio_media_id TEXT REFERENCES media(id) ON DELETE RESTRICT,
  state TEXT NOT NULL DEFAULT 'seeded'
    CHECK (state IN ('seeded','brewing','wind','going','happened','let_go')),
  understanding TEXT,
  pending_question INTEGER NOT NULL DEFAULT 0 CHECK (pending_question IN (0, 1)),
  question_enc BLOB,
  answer_enc BLOB,
  timing_type TEXT CHECK (timing_type IS NULL OR timing_type IN
    ('season','month_day','after_months','free_weekend','when_tired','none')),
  timing_value TEXT,
  trigger_kind TEXT NOT NULL DEFAULT 'none' CHECK (trigger_kind IN ('time','signal','none')),
  timing_set_at TEXT,
  next_trigger_at TEXT,
  timing_occurrence TEXT,
  soft_deferred INTEGER NOT NULL DEFAULT 0 CHECK (soft_deferred IN (0, 1)),
  let_go_at TEXT,
  degraded_reason TEXT
    CHECK (degraded_reason IS NULL OR degraded_reason IN ('llm_failed','asr_failed','asr_empty')),
  seeded_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  last_activity_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  stale_notified_at TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  updated_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  CONSTRAINT wishes_voice_requires_audio
    CHECK (source <> 'voice' OR audio_media_id IS NOT NULL),
  CONSTRAINT wishes_signal_and_none_have_no_trigger_time
    CHECK (trigger_kind = 'time' OR next_trigger_at IS NULL),
  CONSTRAINT wishes_let_go_timestamp_matches_state
    CHECK (state = 'let_go' OR let_go_at IS NULL)
);
CREATE INDEX idx_wishes_owner_state_seeded ON wishes(owner_id, state, seeded_at DESC);
CREATE INDEX idx_wishes_owner_seeded ON wishes(owner_id, seeded_at DESC, id);
CREATE INDEX idx_wishes_due_trigger ON wishes(next_trigger_at, timing_set_at)
  WHERE trigger_kind = 'time' AND next_trigger_at IS NOT NULL
    AND state IN ('seeded', 'brewing');
CREATE INDEX idx_wishes_stale_scan ON wishes(last_activity_at)
  WHERE state = 'going' AND stale_notified_at IS NULL;
CREATE INDEX idx_wishes_signal_trigger ON wishes(owner_id) WHERE trigger_kind = 'signal';
CREATE INDEX idx_wishes_audio_media ON wishes(audio_media_id) WHERE audio_media_id IS NOT NULL;
CREATE INDEX idx_wishes_owner_let_go_at ON wishes(owner_id, let_go_at DESC, seeded_at DESC, id);

CREATE TABLE wish_photos (
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (wish_id, media_id)
);
CREATE INDEX idx_wish_photos_media ON wish_photos(media_id);

CREATE TABLE pending_agent_jobs (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  wish_id TEXT REFERENCES wishes(id) ON DELETE CASCADE,
  memory_id TEXT,
  job_kind TEXT NOT NULL
    CHECK (job_kind IN ('wish_understanding','transcription','next_step','memory_draft')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  last_error_code TEXT,
  created_at TEXT NOT NULL DEFAULT {TS_DEFAULT},
  CONSTRAINT pending_agent_jobs_has_target
    CHECK (wish_id IS NOT NULL OR memory_id IS NOT NULL)
);
CREATE INDEX idx_pending_agent_jobs_due ON pending_agent_jobs(next_attempt_at);
CREATE UNIQUE INDEX idx_pending_agent_jobs_dedup
  ON pending_agent_jobs(job_kind, COALESCE(wish_id, memory_id));
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in DDL.split(";\n") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    for table in (
        "pending_agent_jobs",
        "wish_photos",
        "wishes",
        "media",
        "onboarding_answers",
        "sessions",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
