"""Batch 7 迁移：调度心跳单行表。

revision: 0006_batch7_scheduler_heartbeat
down_revision: 0005_batch6_memories

`id = 1` 的 CHECK 让「全表只有一行」成为结构性保证，而不是靠代码自觉。
健康检查读 `last_beat_at` 判断调度进程是否还活着（部署方案 §7-2：超过 900 秒告警）。

按部署方案第五节，这是全库唯一一条初始化数据。种子行的 `instance_id` 写
`'not-started-yet'`、`last_beat_at` 落在迁移时刻：这样调度进程从未启动过时，
心跳年龄会随时间自然增长并越过 900 秒阈值——健康检查会说实话，
而不是因为「表里没有行」而报一个 null 让人误以为这项检查不适用。
"""

from alembic import op

revision = "0006_batch7_scheduler_heartbeat"
down_revision = "0005_batch6_memories"
branch_labels = None
depends_on = None

TS = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

DDL = f"""
CREATE TABLE scheduler_heartbeat (
  id INTEGER PRIMARY KEY NOT NULL DEFAULT 1 CHECK (id = 1),
  instance_id TEXT NOT NULL,
  last_beat_at TEXT NOT NULL DEFAULT {TS}
);
INSERT INTO scheduler_heartbeat (id, instance_id) VALUES (1, 'not-started-yet');
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in DDL.split(";\n") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduler_heartbeat")
