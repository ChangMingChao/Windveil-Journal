"""Batch 4 迁移：步骤、对话、修订快照三张表。

revision: 0003_batch4_steps
down_revision: 0002_batch3_reminders

加表属于向后兼容变更。`idx_wish_steps_single_proposed` 是部分唯一索引，
把「任一时刻只存在 1 个待完成步骤」变成结构性保证而非代码判断。
"""

from alembic import op

revision = "0003_batch4_steps"
down_revision = "0002_batch3_reminders"
branch_labels = None
depends_on = None

TS = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

DDL = f"""
CREATE TABLE wish_amendments (
  id TEXT PRIMARY KEY NOT NULL,
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  prev_title_enc BLOB NOT NULL,
  prev_original_enc BLOB,
  prev_understanding TEXT,
  created_at TEXT NOT NULL DEFAULT {TS}
);
CREATE INDEX idx_wish_amendments_wish ON wish_amendments(wish_id, created_at);

CREATE TABLE wish_steps (
  id TEXT PRIMARY KEY NOT NULL,
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text_enc BLOB NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'done', 'rejected')),
  est_minutes INTEGER CHECK (est_minutes IS NULL OR est_minutes <= 5),
  involves_cost INTEGER NOT NULL DEFAULT 0 CHECK (involves_cost IN (0, 1)),
  involves_others INTEGER NOT NULL DEFAULT 0 CHECK (involves_others IN (0, 1)),
  source TEXT NOT NULL DEFAULT 'llm' CHECK (source IN ('llm', 'fallback')),
  completed_at TEXT,
  created_at TEXT NOT NULL DEFAULT {TS},
  CONSTRAINT wish_steps_done_has_completed_at
    CHECK ((status = 'done' AND completed_at IS NOT NULL)
        OR (status <> 'done' AND completed_at IS NULL))
);
CREATE UNIQUE INDEX idx_wish_steps_single_proposed ON wish_steps(wish_id) WHERE status = 'proposed';
CREATE INDEX idx_wish_steps_timeline ON wish_steps(wish_id, completed_at) WHERE status = 'done';
CREATE INDEX idx_wish_steps_rejected ON wish_steps(wish_id) WHERE status = 'rejected';

CREATE TABLE wish_messages (
  id TEXT PRIMARY KEY NOT NULL,
  wish_id TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'agent')),
  text_enc BLOB NOT NULL,
  intent TEXT CHECK (intent IS NULL OR intent IN ('chat', 'amend', 'assist', 'fatigue')),
  created_at TEXT NOT NULL DEFAULT {TS}
);
CREATE INDEX idx_wish_messages_wish ON wish_messages(wish_id, created_at);
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in DDL.split(";\n") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    for table in ("wish_messages", "wish_steps", "wish_amendments"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
