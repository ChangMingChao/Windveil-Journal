"""Batch 5 迁移：孤儿对象清理队列。

revision: 0004_batch5_orphans
down_revision: 0003_batch4_steps

S05.2 EX-28.1：彻底删除时对象存储部分失败不阻塞用户的删除意图，
残留 key 转入此表由每日任务重试。此表不含 owner_id——记录已从业务表删除，
无所属用户可言，因此也不受 owner_guard 保护。
"""

from alembic import op

revision = "0004_batch5_orphans"
down_revision = "0003_batch4_steps"
branch_labels = None
depends_on = None

TS = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

DDL = f"""
CREATE TABLE orphan_objects (
  id TEXT PRIMARY KEY NOT NULL,
  object_key TEXT NOT NULL UNIQUE,
  reason TEXT NOT NULL CHECK (reason IN ('delete_failed', 'unreferenced')),
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT {TS}
);
CREATE INDEX idx_orphan_objects_pending ON orphan_objects(created_at);
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in DDL.split(";\n") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS orphan_objects")
