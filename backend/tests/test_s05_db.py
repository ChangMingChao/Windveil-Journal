"""S05 的数据库约束、隔离守卫与服务层单元测试。"""

from __future__ import annotations

import sqlite3
import uuid

import pytest


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


def test_UT_S05_14_wish_state_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, state)"
            " VALUES (?, ?, ?, 'text', 'archived')",
            (str(uuid.uuid4()), uid, b"cipher"),
        )


def test_UT_S05_15_cascade_clears_all_child_tables(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    mid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO media (id, owner_id, kind, object_key, content_type)"
        " VALUES (?, ?, 'image', ?, 'image/jpeg')",
        (mid, uid, f"{uid}/image/{mid}.jpg"),
    )
    raw_db.execute("INSERT INTO wish_photos (wish_id, media_id) VALUES (?, ?)", (wid, mid))
    raw_db.execute(
        "INSERT INTO wish_steps (id, wish_id, owner_id, text_enc) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), wid, uid, b"c"),
    )
    raw_db.execute(
        "INSERT INTO wish_messages (id, wish_id, owner_id, role, text_enc)"
        " VALUES (?, ?, ?, 'user', ?)",
        (str(uuid.uuid4()), wid, uid, b"c"),
    )
    raw_db.execute(
        "INSERT INTO wish_amendments (id, wish_id, owner_id, prev_title_enc)"
        " VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), wid, uid, b"c"),
    )
    raw_db.execute(
        "INSERT INTO reminder_outbox (id, owner_id, wish_id, kind, timing_occurrence, body_enc)"
        " VALUES (?, ?, ?, 'timing', 'o1', ?)",
        (str(uuid.uuid4()), uid, wid, b"c"),
    )
    raw_db.execute("DELETE FROM wishes WHERE id = ?", (wid,))
    for table in ("wish_photos", "wish_steps", "wish_messages", "wish_amendments",
                  "reminder_outbox"):
        left = raw_db.execute(
            f"SELECT count(*) FROM {table} WHERE wish_id = ?", (wid,)  # noqa: S608
        ).fetchone()[0]
        assert left == 0, table


def test_UT_S05_16_orphan_object_key_unique(raw_db: sqlite3.Connection) -> None:
    sql = (
        "INSERT INTO orphan_objects (id, object_key, reason)"
        " VALUES (?, 'a/b/c.webm', 'delete_failed')"
    )
    raw_db.execute(sql, (str(uuid.uuid4()),))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(sql, (str(uuid.uuid4()),))


def test_UT_S05_17_orphan_reason_enum(raw_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO orphan_objects (id, object_key, reason)"
            " VALUES (?, 'x.webm', 'unknown')",
            (str(uuid.uuid4()),),
        )


# ---------------------------------------------------------------- 隔离守卫


@pytest.mark.asyncio
async def test_UT_S05_11_unscoped_query_is_rejected_by_guard(app_env: None) -> None:
    """未带 owner_id 的 owner 表查询被守卫拒绝，且不返回任何数据。"""
    from sqlalchemy import text

    from app.db import OwnerGuardError, dispose_engines, session_scope
    from app.services import create_anonymous_space

    async with session_scope() as s:
        await create_anonymous_space(s, "Asia/Shanghai")

    try:
        with pytest.raises(OwnerGuardError):
            async with session_scope() as s:
                await s.execute(text("SELECT * FROM wishes"))
    finally:
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_12_other_owner_sees_nothing(app_env: None) -> None:
    from app.db import dispose_engines, session_scope
    from app.services import create_anonymous_space, list_wishes_page, seed_wish

    try:
        async with session_scope() as s:
            a, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
            b, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
            a_id, b_id = a.id, b.id
        async with session_scope(a_id) as s:
            await seed_wish(
                s, a_id, source="text", text="只属于 A 的愿望", media_id=None, photo_media_ids=[]
            )
        async with session_scope(b_id) as s:
            page, cursor = await list_wishes_page(s, b_id)
            assert page == [] and cursor is None
        async with session_scope(a_id) as s:
            page, _ = await list_wishes_page(s, a_id)
            assert len(page) == 1
    finally:
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_13_assoc_table_requires_parent_key(app_env: None) -> None:
    """关联表按父表主键限定才放行，不带 wish_id 的查询被守卫拒绝。"""
    from sqlalchemy import text

    from app.db import OwnerGuardError, dispose_engines, session_scope

    try:
        with pytest.raises(OwnerGuardError):
            async with session_scope() as s:
                await s.execute(text("SELECT * FROM wish_photos"))
        # 带上父表主键即放行
        async with session_scope() as s:
            await s.execute(
                text("SELECT * FROM wish_photos WHERE wish_id = :w"), {"w": str(uuid.uuid4())}
            )
    finally:
        await dispose_engines()


# ---------------------------------------------------------------- 服务层


async def _two_wishes():  # noqa: ANN201
    from app.db import session_scope
    from app.services import create_anonymous_space, seed_wish

    async with session_scope() as s:
        user, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
        owner = user.id
    ids = []
    async with session_scope(owner) as s:
        for text in ("想去看海", "想学滑雪"):
            wish, _, _, _ = await seed_wish(
                s, owner, source="text", text=text, media_id=None, photo_media_ids=[]
            )
            ids.append(wish.id)
    return owner, ids


@pytest.mark.asyncio
async def test_UT_S05_18_default_order_is_seeded_at_desc(app_env: None) -> None:
    from datetime import timedelta

    from app.clock import clock
    from app.db import dispose_engines, session_scope
    from app.models import Wish
    from app.services import list_wishes_page

    try:
        owner, ids = await _two_wishes()
        base = clock.now()
        async with session_scope(owner) as s:
            (await s.get(Wish, ids[0])).seeded_at = base - timedelta(days=10)
            (await s.get(Wish, ids[1])).seeded_at = base
        async with session_scope(owner) as s:
            page, _ = await list_wishes_page(s, owner)
            assert [w.id for w in page] == [ids[1], ids[0]]
    finally:
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_21_let_go_clears_pending_reminders(app_env: None) -> None:
    from sqlalchemy import select

    from app.db import dispose_engines, session_scope
    from app.models import ReminderOutbox
    from app.services import let_go_wish, set_timing

    try:
        owner, ids = await _two_wishes()
        wid = ids[0]
        async with session_scope(owner) as s:
            await set_timing(s, owner, wid, {"type": "season", "season": "winter"})
        async with session_scope(owner) as s:
            for occ in ("o1", "o2"):
                s.add(
                    ReminderOutbox(
                        id=uuid.uuid4(), owner_id=owner, wish_id=wid, kind="timing",
                        timing_occurrence=occ, body_enc="body", status="pending",
                    )
                )
            s.add(
                ReminderOutbox(
                    id=uuid.uuid4(), owner_id=owner, wish_id=wid, kind="timing",
                    timing_occurrence="delivered-one", body_enc="body", status="delivered",
                    channel="push", delivered_at=__import__("app.clock", fromlist=["clock"]).clock.now(),
                )
            )
        async with session_scope(owner) as s:
            wish = await let_go_wish(s, owner, wid)
            assert wish.state == "let_go"
            assert wish.next_trigger_at is None
        async with session_scope(owner) as s:
            rows = list((await s.scalars(
                select(ReminderOutbox).where(ReminderOutbox.owner_id == owner)
            )).all())
            assert [r.status for r in rows] == ["delivered"]  # 已投递的保留，pending 清零
    finally:
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_22_let_go_keeps_seeded_at_and_original(app_env: None) -> None:
    from app.db import dispose_engines, session_scope
    from app.models import Wish
    from app.services import let_go_wish

    try:
        owner, ids = await _two_wishes()
        async with session_scope(owner) as s:
            wish = await s.get(Wish, ids[0])
            seeded_at, original = wish.seeded_at, wish.original_text_enc
        async with session_scope(owner) as s:
            wish = await let_go_wish(s, owner, ids[0])
            assert wish.seeded_at == seeded_at
            assert wish.original_text_enc == original
    finally:
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_25_partial_object_failure_registers_orphan(app_env: None) -> None:
    """对象存储部分失败：记录照删，残留 key 进 orphan_objects（EX-28.1）。"""
    from sqlalchemy import select

    from app.db import dispose_engines, session_scope
    from app.models import OrphanObject, Wish
    from app.services import create_upload_url, delete_wish_permanently
    from app.storage import get_storage, set_storage

    real = get_storage()

    class FlakyStorage:
        def presign_put(self, key, content_type, size_bytes):  # noqa: ANN001, ANN201
            return real.presign_put(key, content_type, size_bytes)

        def head(self, key):  # noqa: ANN001, ANN201
            return real.head(key)

        def delete_many(self, keys):  # noqa: ANN001, ANN201
            return list(keys[:1])  # 第一个 key 永远删不掉

    try:
        owner, ids = await _two_wishes()
        wid = ids[0]
        async with session_scope(owner) as s:
            media, _, _ = await create_upload_url(
                s, owner, kind="image", content_type="image/jpeg", size_bytes=2048
            )
            media.status = "ready"
            wish = await s.get(Wish, wid)
            from app.models import WishPhoto

            s.add(WishPhoto(wish_id=wish.id, media_id=media.id))
            key = media.object_key

        set_storage(FlakyStorage())
        async with session_scope(owner) as s:
            assert await delete_wish_permanently(s, owner, wid) is True
        async with session_scope(owner) as s:
            assert await s.get(Wish, wid) is None
            orphans = list((await s.scalars(select(OrphanObject))).all())
            assert [o.object_key for o in orphans] == [key]
            assert orphans[0].reason == "delete_failed"
    finally:
        set_storage(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_26_delete_is_idempotent(app_env: None) -> None:
    from app.db import dispose_engines, session_scope
    from app.services import delete_wish_permanently

    try:
        owner, ids = await _two_wishes()
        async with session_scope(owner) as s:
            assert await delete_wish_permanently(s, owner, ids[0]) is True
        async with session_scope(owner) as s:
            assert await delete_wish_permanently(s, owner, ids[0]) is False
    finally:
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S05_27_pause_clears_timing_and_returns_to_seeded(app_env: None) -> None:
    from app.db import dispose_engines, session_scope
    from app.services import pause_reminders, set_timing

    try:
        owner, ids = await _two_wishes()
        async with session_scope(owner) as s:
            wish = await set_timing(s, owner, ids[0], {"type": "season", "season": "winter"})
            assert wish.state == "brewing"
        async with session_scope(owner) as s:
            wish = await pause_reminders(s, owner, ids[0])
            assert wish.state == "seeded"
            assert wish.next_trigger_at is None
            assert wish.timing_type is None
    finally:
        await dispose_engines()
