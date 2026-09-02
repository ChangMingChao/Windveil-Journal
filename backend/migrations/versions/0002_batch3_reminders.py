"""Batch 3 迁移：提醒相关三张表。

revision: 0002_batch3_reminders
down_revision: 0001_batch1_core

加表属于向后兼容变更（部署方案第五节的兼容要求）：旧版应用代码
在这些表存在的情况下也能正常运行。
"""

from alembic import op

revision = "0002_batch3_reminders"
down_revision = "0001_batch1_core"
branch_labels = None
depends_on = None

TS = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

DDL = f"""
CREATE TABLE push_subscriptions (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL UNIQUE,
  p256dh TEXT NOT NULL,
  auth_secret TEXT NOT NULL,
  user_agent TEXT,
  created_at TEXT NOT NULL DEFAULT {TS}
);
CREATE INDEX idx_push_subscriptions_owner ON push_subscriptions(owner_id);

CREATE TABLE reminder_outbox (
  id TEXT PRIMARY KEY NOT NULL,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('timing', 'stale_care')),
  timing_occurrence TEXT NOT NULL,
  body_enc BLOB NOT NULL,
  channel TEXT CHECK (channel IS NULL OR channel IN ('push', 'email')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','delivered','failed','deferred_to_next_week')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  delivered_at TEXT,
  last_error_code TEXT,
  created_at TEXT NOT NULL DEFAULT {TS},
  CONSTRAINT reminder_outbox_delivered_has_channel
    CHECK (status <> 'delivered' OR (delivered_at IS NOT NULL AND channel IS NOT NULL))
);
CREATE UNIQUE INDEX idx_reminder_outbox_once ON reminder_outbox(wish_id, kind, timing_occurrence);
CREATE INDEX idx_reminder_outbox_pending ON reminder_outbox(next_attempt_at) WHERE status = 'pending';
CREATE INDEX idx_reminder_outbox_owner ON reminder_outbox(owner_id, created_at DESC);

CREATE TABLE reminder_weekly_counters (
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_start TEXT NOT NULL,
  delivered_count INTEGER NOT NULL DEFAULT 0 CHECK (delivered_count BETWEEN 0 AND 3),
  updated_at TEXT NOT NULL DEFAULT {TS},
  PRIMARY KEY (owner_id, week_start)
);
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in DDL.split(";\n") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    for table in ("reminder_weekly_counters", "reminder_outbox", "push_subscriptions"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
