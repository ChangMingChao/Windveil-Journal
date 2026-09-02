"""S06 的数据库约束与业务规则单元测试。

覆盖 UT-S06-16 ~ UT-S06-23（schema.sql 的 CHECK / UNIQUE / DEFAULT / 级联）
与 UT-S06-24 ~ UT-S06-32（时序图 Step 说明里的业务规则）。
UT-S06-01 ~ 15 是 HTTP 层断言，在 test_s06_scenarios.py。
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone

import pytest

MEMORY_SQL = (
    "INSERT INTO memories (id, wish_id, owner_id, title_enc, happened_from, happened_to,"
    " status, published_at, mood)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


class FakeDraftLLM:
    """只实现 S06 需要的 draft_memory；mode 控制降级与内容。"""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.calls = 0

    async def draft_memory(self, *, original_text, feeling, timeline):  # noqa: ANN001, ANN201
        from app.agent import MemoryDraft

        self.calls += 1
        if self.mode == "down":
            return None
        return MemoryDraft(
            title="那两天你真的去了海边",
            cause=f"你原本想{feeling or '喘口气'}。",
            # 没有时间线就不编造经过——与 MEMORY_PROMPT 里对模型的要求一致（EX-4.1）
            process="；".join(timeline) if timeline else None,
        )

    async def next_step(self, *, original_text, feeling, rejected):  # noqa: ANN001, ANN201, ARG002
        from app.agent import StepSuggestion

        return StepSuggestion(
            text="只是想一想那片海", est_minutes=2, involves_cost=False, involves_others=False
        )


FIXED_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture
async def llm(app_env: None) -> AsyncIterator[FakeDraftLLM]:
    from app.agent import set_llm_provider
    from app.clock import clock
    from app.db import dispose_engines

    provider = FakeDraftLLM()
    set_llm_provider(provider)
    clock.set_fixed(FIXED_NOW)
    yield provider
    clock.set_fixed(None)
    set_llm_provider(None)
    await dispose_engines()


async def _wish_going(owner_timezone: str = "Asia/Shanghai"):  # noqa: ANN202
    """建号 → 种下 → 设时机 → ready → 完成 1 步（state=going），返回 (owner_id, wish_id)。"""
    from app.db import session_scope
    from app.models import Wish
    from app.services import (
        create_anonymous_space,
        mark_ready,
        mark_step_done,
        request_next_step,
        seed_wish,
        set_timing,
    )

    async with session_scope() as s:
        user, _, _ = await create_anonymous_space(s, owner_timezone)
        owner = user.id
    async with session_scope(owner) as s:
        wish, _, _, _ = await seed_wish(
            s, owner, source="text", text="想一个人去海边待两天", media_id=None, photo_media_ids=[]
        )
        wish_id = wish.id
    async with session_scope(owner) as s:
        await set_timing(s, owner, wish_id, {"type": "season", "season": "winter"})
    async with session_scope(owner) as s:
        await mark_ready(s, owner, wish_id)
    async with session_scope(owner) as s:
        step, _ = await request_next_step(s, owner, wish_id)
        step_id = step.id
        version = (await s.get(Wish, wish_id)).version
    async with session_scope(owner) as s:
        await mark_step_done(s, owner, wish_id, step_id, version)
    return owner, wish_id



async def _wish_seeded():  # noqa: ANN202
    """只种下，不设时机、不留任何准备过程（EX-4.1 的前置）。"""
    from app.db import session_scope
    from app.services import create_anonymous_space, seed_wish

    async with session_scope() as s:
        user, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
        owner = user.id
    async with session_scope(owner) as s:
        wish, _, _, _ = await seed_wish(
            s, owner, source="text", text="想学会滑雪", media_id=None, photo_media_ids=[]
        )
        return owner, wish.id


# ---------------------------------------------------------------- DB 约束（raw sqlite3）


def _user(db: sqlite3.Connection) -> str:
    uid = str(uuid.uuid4())
    db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    return uid


def _wish(db: sqlite3.Connection, owner: str) -> str:
    wid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, ?, 'text')",
        (wid, owner, b"cipher"),
    )
    return wid


def _insert_memory(
    db: sqlite3.Connection,
    owner: str,
    wid: str,
    *,
    happened_from: str = "2026-10-17",
    happened_to: str | None = None,
    status: str = "draft",
    published_at: str | None = None,
    mood: str | None = None,
) -> str:
    mid = str(uuid.uuid4())
    db.execute(
        MEMORY_SQL,
        (mid, wid, owner, b"cipher", happened_from, happened_to, status, published_at, mood),
    )
    return mid


def test_UT_S06_16_range_must_be_ordered(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_memory(raw_db, uid, wid, happened_from="2026-10-18", happened_to="2026-10-17")


def test_UT_S06_17_published_requires_timestamp(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_memory(raw_db, uid, wid, status="published", published_at=None)


def test_UT_S06_18_draft_must_not_have_timestamp(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_memory(raw_db, uid, wid, status="draft", published_at="2026-10-19T02:00:00.000Z")


def test_UT_S06_19_mood_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_memory(raw_db, uid, wid, mood="excited")


def test_UT_S06_20_status_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_memory(raw_db, uid, wid, status="archived")


def test_UT_S06_21_edited_fields_defaults_to_empty_array(raw_db: sqlite3.Connection) -> None:
    """DDL 的默认值是 JSON 空数组 `'[]'`。

    测试用例文档里写的 `DEFAULT '{}'` 是 PostgreSQL 时期的 `text[]` 空数组字面量，
    改用 SQLite + JSON 字符串后应为 `'[]'`；已同步修正该文档的来源标注。
    """
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    mid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO memories (id, wish_id, owner_id, title_enc, happened_from)"
        " VALUES (?, ?, ?, ?, '2026-10-17')",
        (mid, wid, uid, b"cipher"),
    )
    row = raw_db.execute("SELECT edited_fields FROM memories WHERE id = ?", (mid,)).fetchone()
    assert row[0] == "[]"


def _media(db: sqlite3.Connection, owner: str) -> str:
    mid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO media (id, owner_id, kind, object_key, content_type)"
        " VALUES (?, ?, 'image', ?, 'image/jpeg')",
        (mid, owner, f"{owner}/image/{mid}.jpg"),
    )
    return mid


def test_UT_S06_22_memory_photos_composite_pk(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    memory_id = _insert_memory(raw_db, uid, wid)
    media_id = _media(raw_db, uid)
    sql = "INSERT INTO memory_photos (memory_id, media_id) VALUES (?, ?)"
    raw_db.execute(sql, (memory_id, media_id))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(sql, (memory_id, media_id))


def test_UT_S06_23_wish_delete_cascades_memory(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    memory_id = _insert_memory(
        raw_db, uid, wid, status="published", published_at="2026-10-19T02:00:00.000Z"
    )
    raw_db.execute(
        "INSERT INTO memory_photos (memory_id, media_id) VALUES (?, ?)",
        (memory_id, _media(raw_db, uid)),
    )
    raw_db.execute("DELETE FROM wishes WHERE id = ?", (wid,))
    assert raw_db.execute(
        "SELECT count(*) FROM memories WHERE wish_id = ?", (wid,)
    ).fetchone()[0] == 0
    assert raw_db.execute(
        "SELECT count(*) FROM memory_photos WHERE memory_id = ?", (memory_id,)
    ).fetchone()[0] == 0


# ---------------------------------------------------------------- 业务规则（服务层）


async def _add_pending(owner, wish_id, count: int) -> None:  # noqa: ANN001
    from app.db import session_scope
    from app.models import ReminderOutbox

    async with session_scope(owner) as s:
        for n in range(count):
            s.add(
                ReminderOutbox(
                    id=uuid.uuid4(),
                    owner_id=owner,
                    wish_id=wish_id,
                    kind="timing",
                    timing_occurrence=f"pending-{n}",
                    body_enc="到了那个时候",
                    status="pending",
                )
            )


async def _pending_count(owner, wish_id) -> int:  # noqa: ANN001
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models import ReminderOutbox

    async with session_scope(owner) as s:
        return await s.scalar(
            select(func.count())
            .select_from(ReminderOutbox)
            .where(
                ReminderOutbox.owner_id == owner,
                ReminderOutbox.wish_id == wish_id,
                ReminderOutbox.status == "pending",
            )
        )


async def test_UT_S06_24_happened_stops_reminders_without_state_change(
    llm: FakeDraftLLM,
) -> None:
    """Step 6 说明：提醒立刻停，但状态要到 Step 17 才转 happened。"""
    from app.db import session_scope
    from app.models import Wish
    from app.services import mark_wish_happened

    owner, wid = await _wish_going()
    await _add_pending(owner, wid, 2)
    assert await _pending_count(owner, wid) == 2

    async with session_scope(owner) as s:
        _, degraded, warning = await mark_wish_happened(
            s, owner, wid, happened_from=date(2026, 9, 1)
        )
        assert degraded is False
        assert warning is None
    async with session_scope(owner) as s:
        wish = await s.get(Wish, wid)
        assert wish.next_trigger_at is None
        assert wish.state == "going"  # 关键：还没有转 happened
    assert await _pending_count(owner, wid) == 0


async def test_UT_S06_25_publish_moves_wish_to_happened(llm: FakeDraftLLM) -> None:
    from app.db import session_scope
    from app.models import Wish
    from app.services import mark_wish_happened, publish_memory

    owner, wid = await _wish_going()
    async with session_scope(owner) as s:
        memory, _, _ = await mark_wish_happened(s, owner, wid, happened_from=date(2026, 9, 1))
        memory_id = memory.id
    async with session_scope(owner) as s:
        memory = await publish_memory(s, owner, memory_id)
        assert memory.status == "published"
        assert memory.published_at is not None
    async with session_scope(owner) as s:
        assert (await s.get(Wish, wid)).state == "happened"


async def test_UT_S06_26_before_seeded_returns_warning_not_error(llm: FakeDraftLLM) -> None:
    """EX-3.1：早于种下日期不是错误，只是一件需要确认的事。"""
    from app.db import session_scope
    from app.services import mark_wish_happened

    owner, wid = await _wish_going()
    async with session_scope(owner) as s:
        memory, _, warning = await mark_wish_happened(
            s, owner, wid, happened_from=date(2026, 7, 12)
        )
        assert warning is not None
        assert warning["code"] == "HAPPENED_BEFORE_SEEDED"
        assert memory.note_before_seeded is False


async def test_UT_S06_27_acknowledged_before_seeded_writes_note(llm: FakeDraftLLM) -> None:
    from app.db import session_scope
    from app.services import mark_wish_happened

    owner, wid = await _wish_going()
    async with session_scope(owner) as s:
        memory, _, warning = await mark_wish_happened(
            s,
            owner,
            wid,
            happened_from=date(2026, 7, 12),
            acknowledged_before_seeded=True,
        )
        assert warning is None
        assert memory.note_before_seeded is True


async def test_UT_S06_28_no_timeline_leaves_process_empty(llm: FakeDraftLLM) -> None:
    """EX-4.1：事情本来就可能在这个产品之外自然发生，不强制补齐中间状态。"""
    from app.db import session_scope
    from app.services import mark_wish_happened

    owner, wid = await _wish_seeded()
    async with session_scope(owner) as s:
        memory, degraded, _ = await mark_wish_happened(
            s, owner, wid, happened_from=date(2026, 9, 1)
        )
        assert degraded is False
        assert memory.process_enc is None
        assert memory.title_enc  # 标题照样有


async def test_UT_S06_29_patch_records_edited_fields(llm: FakeDraftLLM) -> None:
    from app.db import session_scope
    from app.services import mark_wish_happened, update_memory

    owner, wid = await _wish_going()
    async with session_scope(owner) as s:
        memory, _, _ = await mark_wish_happened(s, owner, wid, happened_from=date(2026, 9, 1))
        memory_id = memory.id
    async with session_scope(owner) as s:
        memory = await update_memory(
            s, owner, memory_id, {"title": "我自己写的标题", "cause": "我自己写的起因"}
        )
        assert memory.edited_fields == ["title", "cause"]


async def test_UT_S06_30_redraft_never_overwrites_user_edits(llm: FakeDraftLLM) -> None:
    """EX-7.1：补草拟晚于用户编辑发生，如果它有权覆盖，修改就会在某个夜里悄悄消失。"""
    from app.db import session_scope
    from app.services import mark_wish_happened, redraft_memory, update_memory

    owner, wid = await _wish_going()
    llm.mode = "down"
    async with session_scope(owner) as s:
        memory, degraded, _ = await mark_wish_happened(
            s, owner, wid, happened_from=date(2026, 9, 1)
        )
        assert degraded is True
        memory_id = memory.id
    async with session_scope(owner) as s:
        await update_memory(s, owner, memory_id, {"title": "我自己写的标题"})

    llm.mode = "ok"
    async with session_scope(owner) as s:
        assert await redraft_memory(s, owner, memory_id) is True
    async with session_scope(owner) as s:
        from app.models import Memory

        memory = await s.get(Memory, memory_id)
        assert memory.title_enc == "我自己写的标题"  # 用户版本原样保留
        assert memory.process_enc  # 未被编辑过的段落被补上
        assert memory.edited_fields == ["title"]


async def test_UT_S06_31_lived_pages_counts_published_only(llm: FakeDraftLLM) -> None:
    """listMemories → lived_pages。这个产品里唯一允许的计数，只数已经发生的事。"""
    from app.db import session_scope
    from app.services import list_memories, mark_wish_happened, publish_memory, seed_wish

    owner, first = await _wish_going()
    ids = [first]
    async with session_scope(owner) as s:
        for text in ("想去看一次雪", "想学会做面包"):
            wish, _, _, _ = await seed_wish(
                s, owner, source="text", text=text, media_id=None, photo_media_ids=[]
            )
            ids.append(wish.id)

    memory_ids = []
    for n, wish_id in enumerate(ids):
        async with session_scope(owner) as s:
            memory, _, _ = await mark_wish_happened(
                s, owner, wish_id, happened_from=date(2026, 8, 10 + n)
            )
            memory_ids.append(memory.id)
    for memory_id in memory_ids[:2]:  # 只发布 2 页，第 3 页留作草稿
        async with session_scope(owner) as s:
            await publish_memory(s, owner, memory_id)

    async with session_scope(owner) as s:
        page, cursor, lived = await list_memories(s, owner)
        assert lived == 2
        assert len(page) == 2
        assert cursor is None
        assert {m.status for m in page} == {"published"}


async def test_UT_S06_32_publish_is_idempotent(llm: FakeDraftLLM) -> None:
    """EX-17.1：/book 的页数不会因重复提交而虚增。"""
    from app.db import session_scope
    from app.services import list_memories, mark_wish_happened, publish_memory

    owner, wid = await _wish_going()
    async with session_scope(owner) as s:
        memory, _, _ = await mark_wish_happened(s, owner, wid, happened_from=date(2026, 9, 1))
        memory_id = memory.id
    async with session_scope(owner) as s:
        first = (await publish_memory(s, owner, memory_id)).published_at
    async with session_scope(owner) as s:
        again = await publish_memory(s, owner, memory_id)
        assert again.published_at == first
    async with session_scope(owner) as s:
        _, _, lived = await list_memories(s, owner)
        assert lived == 1






