"""lightweight-events 迁移：新增 lite_events（S09）。

加表类迁移：一张表一个部分索引，不改动既有表的任何列。
DDL 与 logos/resources/database/schema.sql 逐字节一致（由脚本从 schema.sql 提取生成）。
"""

from alembic import op

revision = "0009_lightweight_events"
down_revision = "0008_preferences_availability_timing"
branch_labels = None
depends_on = None

DDL = """
-- -----------------------------------------------------------------------------
-- lite_events（来源：lite-events.yaml → createLiteEvent, listLiteEvents,
--              markLiteEventDone, deleteLiteEvent；S09）
-- -----------------------------------------------------------------------------
CREATE TABLE lite_events (
  -- @comment 轻事件唯一标识
  id TEXT PRIMARY KEY NOT NULL,
  -- @comment 所属用户。SQLite 无 RLS，隔离由仓储层注入 + 运行时守卫保证
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- @comment 一句话轻意图（如「今晚吃火锅」），应用层 AES-256-GCM 加密。
  -- 它是「还不值得变成愿望的念头」：不调用 Agent、不进提醒队列、不占每周提醒额度
  text_enc BLOB NOT NULL,
  -- @comment open 已记下还在列表；done 已划掉（默认列表不含，保留行以备追溯）。
  -- 收走（硬删除）不留行。刻意没有 dismissed 状态：删除就是硬删，不留影子
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
  -- @comment 记下时间
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment 划掉时间；open 时必须为 NULL（配对约束见下）
  closed_at TEXT,
  -- @comment 最后更新时间，由应用层刷新
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  -- @comment done 必须有划掉时间；open 必须没有
  CONSTRAINT lite_events_closed_state_pairing
    CHECK ((status = 'done') = (closed_at IS NOT NULL))
);
-- @table-comment lite_events 轻量事件。设计核心：本表刻意没有任何触发时间 /
-- 提醒相关字段，Scheduler 的扫描集合与 reminder_outbox 的关联路径都不包含它——
-- 「轻事件不占用每周提醒额度」由数据结构保证，而非行为约定（架构 5.6）

-- 「先记一下」列表：open 状态按记下时间倒序（S09 Step 4）
CREATE INDEX idx_lite_events_owner_open
  ON lite_events(owner_id, created_at DESC) WHERE status = 'open';;
"""


def upgrade() -> None:
    # exec_driver_sql 原样下发，不做 text() 参数解析（与 0008 同理由）
    bind = op.get_bind()
    for stmt in [x.strip() for x in DDL.split(";\n") if x.strip()]:
        bind.exec_driver_sql(stmt)


def downgrade() -> None:
    op.exec_driver_sql(
        "DROP INDEX IF EXISTS idx_lite_events_owner_open; "
        "DROP TABLE IF EXISTS lite_events;"
    )
