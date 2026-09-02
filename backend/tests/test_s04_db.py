"""S04 的数据库约束与服务层单元测试。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import timedelta

import pytest


def _user(db: sqlite3.Connection) -> str:
    uid = str(uuid.uuid4())
    db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    return uid


def _wish(db: sqlite3.Connection, owner: str, *, state: str = "going") -> str:
    wid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source, state)"
        " VALUES (?, ?, ?, 'text', ?)",
        (wid, owner, b"cipher", state),
    )
    return wid


def _step(db: sqlite3.Connection, owner: str, wish: str, **kw: object) -> str:
    sid = str(uuid.uuid4())
    cols = {"status": "proposed", "est_minutes": 2, "source": "llm", "completed_at": None}
    cols.update(kw)
    db.execute(
        "INSERT INTO wish_steps (id, wish_id, owner_id, text_enc, status, est_minutes,"
        " source, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sid, wish, owner, b"cipher", cols["status"], cols["est_minutes"],
         cols["source"], cols["completed_at"]),
    )
    return sid


def test_UT_S04_09_only_one_proposed_step_per_wish(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    _step(raw_db, uid, wid)
    with pytest.raises(sqlite3.IntegrityError):
        _step(raw_db, uid, wid)
    # 换成 rejected 后可以再有一个 proposed
    raw_db.execute("UPDATE wish_steps SET status = 'rejected' WHERE wish_id = ?", (wid,))
    _step(raw_db, uid, wid)


def test_UT_S04_10_est_minutes_capped_at_five(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _step(raw_db, uid, wid, est_minutes=10)


def test_UT_S04_11_done_requires_completed_at(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _step(raw_db, uid, wid, status="done", completed_at=None)


def test_UT_S04_12_non_done_must_not_have_completed_at(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _step(raw_db, uid, wid, status="rejected", completed_at="2026-09-01T00:00:00.000Z")


def test_UT_S04_13_step_status_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _step(raw_db, uid, wid, status="skipped")


def test_UT_S04_14_step_source_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _step(raw_db, uid, wid, source="manual")


def test_UT_S04_16_cascade_delete_removes_steps_and_messages(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    _step(raw_db, uid, wid)
    raw_db.execute(
        "INSERT INTO wish_messages (id, wish_id, owner_id, role, text_enc)"
        " VALUES (?, ?, ?, 'user', ?)",
        (str(uuid.uuid4()), wid, uid, b"hi"),
    )
    raw_db.execute(
        "INSERT INTO wish_amendments (id, wish_id, owner_id, prev_title_enc)"
        " VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), wid, uid, b"old"),
    )
    raw_db.execute("DELETE FROM wishes WHERE id = ?", (wid,))
    for table in ("wish_steps", "wish_messages", "wish_amendments"):
        left = raw_db.execute(
            f"SELECT count(*) FROM {table} WHERE wish_id = ?", (wid,)  # noqa: S608
        ).fetchone()[0]
        assert left == 0, table


def test_UT_S04_17_amendment_prev_title_not_null(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wish_amendments (id, wish_id, owner_id, prev_title_enc)"
            " VALUES (?, ?, ?, NULL)",
            (str(uuid.uuid4()), wid, uid),
        )


# ---------------------------------------------------------------- 服务层


class _Provider:
    """可控 LLM 替身：记录调用次数与收到的 rejected 列表。"""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.calls = 0
        self.seen_rejected: list[list[str]] = []

    async def understand_wish(self, text: str):  # noqa: ANN201, ARG002
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(
            {"understanding": {"kind": "future_wish", "feeling": "放松",
                               "conditions": {}, "smallest_step": None}, "question": None}
        )

    async def next_step(self, *, original_text, feeling, rejected):  # noqa: ANN001, ANN201, ARG002
        from app.agent import StepSuggestion

        self.calls += 1
        self.seen_rejected.append(list(rejected))
        if self.mode == "none":
            return None
        if self.mode == "violating":
            return StepSuggestion(
                text="先去订一张机票", est_minutes=30, involves_cost=True, involves_others=False
            )
        return StepSuggestion(
            text=f"第 {self.calls} 步：只是想一想", est_minutes=2,
            involves_cost=False, involves_others=False,
        )

    async def classify_message(self, *, text, original_text):  # noqa: ANN001, ANN201, ARG002
        from app.agent import MessageReply

        if self.mode == "amend":
            return MessageReply(
                intent="amend", reply="好，我记下来了",
                amended_title="和妹妹一起去海边", amended_conditions={"companion": "妹妹"},
            )
        if self.mode == "fatigue":
            return MessageReply(intent="fatigue", reply="那先歇一歇")
        return MessageReply(intent="chat", reply="嗯")


async def _prepare(owner_state: str = "wind"):  # noqa: ANN201
    """建号 + 种下 + 置目标状态，返回 (owner_id, wish_id)。"""
    from app.db import session_scope
    from app.services import create_anonymous_space, seed_wish

    async with session_scope() as s:
        user, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
        owner = user.id
    async with session_scope(owner) as s:
        wish, _, _, _ = await seed_wish(
            s, owner, source="text", text="想一个人去海边待两天", media_id=None, photo_media_ids=[]
        )
        wish.state = owner_state
        wish.understanding = {"kind": "future_wish", "feeling": "放松", "conditions": {}}
        wid = wish.id
    return owner, wid


@pytest.mark.asyncio
async def test_UT_S04_20_rejected_steps_are_excluded(app_env: None) -> None:
    from app.agent import set_llm_provider
    from app.db import dispose_engines, session_scope
    from app.services import request_next_step

    provider = _Provider()
    set_llm_provider(provider)
    try:
        owner, wid = await _prepare()
        async with session_scope(owner) as s:
            first, _ = await request_next_step(s, owner, wid)
            first_id, first_text = first.id, first.text_enc
        async with session_scope(owner) as s:
            second, _ = await request_next_step(s, owner, wid, first_id)
            assert second.text_enc != first_text
        # 第二次请求时，被拒文本已作为排除项传给模型
        assert provider.seen_rejected[-1] == [first_text]
    finally:
        set_llm_provider(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_21_third_rejection_stops_calling_llm(app_env: None) -> None:
    from app.agent import set_llm_provider
    from app.db import dispose_engines, session_scope
    from app.services import MAX_REJECTED_BEFORE_FALLBACK, request_next_step

    assert MAX_REJECTED_BEFORE_FALLBACK == 3
    provider = _Provider()
    set_llm_provider(provider)
    try:
        owner, wid = await _prepare()
        step_id = None
        for _ in range(3):
            async with session_scope(owner) as s:
                step, _ = await request_next_step(s, owner, wid, step_id)
                step_id = step.id
        calls_before = provider.calls
        async with session_scope(owner) as s:
            step, _ = await request_next_step(s, owner, wid, step_id)
            assert step.source == "fallback"
        assert provider.calls == calls_before  # 第 4 次没有再调模型
    finally:
        set_llm_provider(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_22_only_one_proposed_returned(app_env: None) -> None:
    from sqlalchemy import select

    from app.agent import set_llm_provider
    from app.db import dispose_engines, session_scope
    from app.models import WishStep
    from app.services import request_next_step

    set_llm_provider(_Provider())
    try:
        owner, wid = await _prepare()
        async with session_scope(owner) as s:
            await request_next_step(s, owner, wid)
        async with session_scope(owner) as s:
            again, _ = await request_next_step(s, owner, wid)  # 不带 rejected：返回同一条
            count = len(
                (
                    await s.scalars(
                        select(WishStep).where(
                            WishStep.wish_id == wid, WishStep.status == "proposed"
                        )
                    )
                ).all()
            )
        assert count == 1
        assert again is not None
    finally:
        set_llm_provider(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_23_done_refreshes_last_activity(app_env: None) -> None:
    from app.agent import set_llm_provider
    from app.clock import clock
    from app.db import dispose_engines, session_scope
    from app.services import mark_step_done, request_next_step

    set_llm_provider(_Provider())
    base = clock.now()
    try:
        owner, wid = await _prepare()
        async with session_scope(owner) as s:
            step, _ = await request_next_step(s, owner, wid)
            step_id, version = step.id, (await s.get(type(step).__mro__[0], step.id)) and None
        from app.models import Wish

        async with session_scope(owner) as s:
            wish = await s.get(Wish, wid)
            wish.last_activity_at = base - timedelta(days=30)
            version = wish.version
        clock.set_fixed(base + timedelta(days=1))
        async with session_scope(owner) as s:
            _, wish = await mark_step_done(s, owner, wid, step_id, version)
            assert wish.state == "going"
            assert wish.last_activity_at > base
            assert wish.stale_notified_at is None
    finally:
        clock.set_fixed(None)
        set_llm_provider(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_26_amend_preserves_seeded_at_and_original(app_env: None) -> None:
    from app.agent import set_llm_provider
    from app.db import dispose_engines, session_scope
    from app.models import Wish, WishAmendment
    from app.services import send_message

    set_llm_provider(_Provider("amend"))
    try:
        owner, wid = await _prepare("going")
        async with session_scope(owner) as s:
            wish = await s.get(Wish, wid)
            seeded_at, original = wish.seeded_at, wish.original_text_enc
        async with session_scope(owner) as s:
            reply, intent, wish, degraded = await send_message(s, owner, wid, "想改成和妹妹一起去")
            assert intent == "amend" and degraded is False and reply
            assert wish.title_enc == "和妹妹一起去海边"
            assert wish.original_text_enc == original
            assert wish.seeded_at == seeded_at
            assert wish.understanding["conditions"]["companion"] == "妹妹"
        from sqlalchemy import select

        async with session_scope(owner) as s:
            snaps = list((await s.scalars(
                select(WishAmendment).where(WishAmendment.wish_id == wid)
            )).all())
            assert len(snaps) == 1
            assert snaps[0].prev_original_enc == original
    finally:
        set_llm_provider(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_27_fatigue_triggers_signal_wishes(app_env: None) -> None:
    from app.agent import set_llm_provider
    from app.db import dispose_engines, session_scope
    from app.models import Wish
    from app.services import send_message, set_timing

    set_llm_provider(_Provider("fatigue"))
    try:
        owner, wid = await _prepare("going")
        async with session_scope(owner) as s:
            other, _, _, _ = await __import__("app.services", fromlist=["x"]).seed_wish(
                s, owner, source="text", text="想学一门乐器", media_id=None, photo_media_ids=[]
            )
            other_id = other.id
        async with session_scope(owner) as s:
            await set_timing(s, owner, other_id, {"type": "when_tired"})
        async with session_scope(owner) as s:
            _, intent, _, _ = await send_message(s, owner, wid, "最近好累")
            assert intent == "fatigue"
        async with session_scope(owner) as s:
            signal_wish = await s.get(Wish, other_id)
            assert signal_wish.next_trigger_at is not None
            assert signal_wish.trigger_kind == "time"
    finally:
        set_llm_provider(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_24_stale_care_boundary_is_sixty_days(app_env: None) -> None:
    from app.clock import clock
    from app.db import dispose_engines, session_scope
    from app.models import ReminderOutbox, Wish
    from app.scheduler import run_tick

    base = clock.now()
    try:
        owner, wid = await _prepare("going")
        async with session_scope(owner) as s:
            wish = await s.get(Wish, wid)
            wish.last_activity_at = base - timedelta(days=59)
        assert (await run_tick()).enqueued == 0
        async with session_scope(owner) as s:
            wish = await s.get(Wish, wid)
            wish.last_activity_at = base - timedelta(days=60)
        assert (await run_tick()).enqueued == 1
        from sqlalchemy import select

        async with session_scope(owner) as s:
            rows = list((await s.scalars(
                select(ReminderOutbox).where(ReminderOutbox.owner_id == owner)
            )).all())
            assert [r.kind for r in rows] == ["stale_care"]
    finally:
        clock.set_fixed(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S04_25_stale_care_sent_only_once(app_env: None) -> None:
    from app.clock import clock
    from app.db import dispose_engines, session_scope
    from app.models import Wish
    from app.scheduler import run_tick

    base = clock.now()
    try:
        owner, wid = await _prepare("going")
        async with session_scope(owner) as s:
            wish = await s.get(Wish, wid)
            wish.last_activity_at = base - timedelta(days=90)
        assert (await run_tick()).enqueued == 1
        async with session_scope(owner) as s:
            assert (await s.get(Wish, wid)).stale_notified_at is not None
        assert (await run_tick()).enqueued == 0
    finally:
        clock.set_fixed(None)
        await dispose_engines()
