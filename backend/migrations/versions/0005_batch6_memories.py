"""Batch 6 迁移：记忆页与记忆页照片。

revision: 0005_batch6_memories
down_revision: 0004_batch5_orphans

加表属于向后兼容变更。两处结构性保证值得单独说明：

  `memories.wish_id UNIQUE`      —— 一事一页，「重复点击它已经发生了」在数据库层就
                                    不可能建出第二页（S06 UT-S06-15）
  `memories_published_has_timestamp` —— status 与 published_at 必须同时成立或同时不成立，
                                    把「已入册却没有入册时间」这种半状态排除掉

`idx_memories_owner_published` 是部分索引，只覆盖 published——书架查询与
`lived_pages` 计数都只看已发生的事，草稿不该进入这个索引。

`pending_agent_jobs.memory_id` 在 0001 里没有带 FK（当时 memories 表还不存在，
而 SQLite 无法事后 ALTER 添加外键）。这与 schema.sql 的设计存在一处已知偏差：
删除记忆页不会级联清除它的 memory_draft 补草拟任务。补草拟任务在执行时会
校验目标记忆页是否仍存在，因此不会因此产生错误行为。
"""

from alembic import op

revision = "0005_batch6_memories"
down_revision = "0004_batch5_orphans"
branch_labels = None
depends_on = None

TS = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"

DDL = f"""
CREATE TABLE memories (
  id TEXT PRIMARY KEY NOT NULL,
  wish_id TEXT NOT NULL UNIQUE REFERENCES wishes(id) ON DELETE CASCADE,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title_enc BLOB NOT NULL,
  cause_enc BLOB,
  process_enc BLOB,
  mood TEXT CHECK (mood IS NULL OR mood IN
    ('relieved','healed','tearful','calm','proud','unspeakable')),
  last_line_enc BLOB,
  voice_media_id TEXT REFERENCES media(id) ON DELETE SET NULL,
  happened_from TEXT NOT NULL,
  happened_to TEXT,
  note_before_seeded INTEGER NOT NULL DEFAULT 0 CHECK (note_before_seeded IN (0, 1)),
  edited_fields TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  published_at TEXT,
  created_at TEXT NOT NULL DEFAULT {TS},
  updated_at TEXT NOT NULL DEFAULT {TS},
  CONSTRAINT memories_range_ordered
    CHECK (happened_to IS NULL OR happened_to >= happened_from),
  CONSTRAINT memories_published_has_timestamp
    CHECK ((status = 'published' AND published_at IS NOT NULL)
        OR (status <> 'published' AND published_at IS NULL))
);
CREATE INDEX idx_memories_owner_published ON memories(owner_id, happened_from DESC, id)
  WHERE status = 'published';
CREATE INDEX idx_memories_draft ON memories(owner_id) WHERE status = 'draft';
CREATE INDEX idx_memories_voice_media ON memories(voice_media_id) WHERE voice_media_id IS NOT NULL;
CREATE TABLE memory_photos (
  memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (memory_id, media_id)
);
CREATE INDEX idx_memory_photos_media ON memory_photos(media_id);
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in DDL.split(";\n") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_photos")
    op.execute("DROP TABLE IF EXISTS memories")
