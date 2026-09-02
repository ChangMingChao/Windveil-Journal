"""S03 的数据库约束与调度器单元测试。"""

from __future__ import annotations

import sqlite3
import uuid

import pytest


def _user(db: sqlite3.Connection, *, email: str | None = None) -> str:
    uid = str(uuid.uuid4())
    if email:
        db.execute(
            "INSERT INTO users (id, is_anonymous, email, password_hash) VALUES (?, 0, ?, 'h')",
            (uid, email),
        )
    else:
        db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    return uid


def _wish(db: sqlite3.Connection, owner: str) -> str:
    wid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, ?, 'text')",
        (wid, owner, b"cipher"),
    )
    return wid


def test_UT_S03_11_signal_and_none_have_no_trigger_time(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, trigger_kind, next_trigger_at)"
            " VALUES (?, ?, ?, 'text', 'signal', '2026-12-01T01:00:00.000Z')",
            (str(uuid.uuid4()), uid, b"cipher"),
        )


def test_UT_S03_12_timing_type_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, timing_type)"
            " VALUES (?, ?, ?, 'text', 'weather')",
            (str(uuid.uuid4()), uid, b"cipher"),
        )


def test_UT_S03_13_same_occurrence_enqueued_once(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    sql = (
        "INSERT INTO reminder_outbox (id, owner_id, wish_id, kind, timing_occurrence, body_enc)"
        " VALUES (?, ?, ?, 'timing', 'season:winter:2026', ?)"
    )
    raw_db.execute(sql, (str(uuid.uuid4()), uid, wid, b"body"))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(sql, (str(uuid.uuid4()), uid, wid, b"body"))
    # ON CONFLICT DO NOTHING 时行数不变
    raw_db.execute(sql.replace("INSERT INTO", "INSERT OR IGNORE INTO"),
                   (str(uuid.uuid4()), uid, wid, b"body"))
    assert raw_db.execute("SELECT count(*) FROM reminder_outbox").fetchone()[0] == 1


def test_UT_S03_14_weekly_budget_is_enforced_by_database(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    raw_db.execute(
        "INSERT INTO reminder_weekly_counters (owner_id, week_start, delivered_count)"
        " VALUES (?, '2026-08-31', 3)",
        (uid,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "UPDATE reminder_weekly_counters SET delivered_count = 4 WHERE owner_id = ?", (uid,)
        )


def test_UT_S03_15_outbox_status_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO reminder_outbox"
            " (id, owner_id, wish_id, kind, timing_occurrence, body_enc, status)"
            " VALUES (?, ?, ?, 'timing', 'o1', ?, 'sent')",
            (str(uuid.uuid4()), uid, wid, b"body"),
        )


def test_UT_S03_16_delivered_requires_channel_and_timestamp(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = _wish(raw_db, uid)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO reminder_outbox"
            " (id, owner_id, wish_id, kind, timing_occurrence, body_enc, status)"
            " VALUES (?, ?, ?, 'timing', 'o2', ?, 'delivered')",
            (str(uuid.uuid4()), uid, wid, b"body"),
        )
    raw_db.execute(
        "INSERT INTO reminder_outbox"
        " (id, owner_id, wish_id, kind, timing_occurrence, body_enc, status, channel, delivered_at)"
        " VALUES (?, ?, ?, 'timing', 'o3', ?, 'delivered', 'push',"
        " strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        (str(uuid.uuid4()), uid, wid, b"body"),
    )


def test_UT_S03_17_weekly_counter_primary_key(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    sql = (
        "INSERT INTO reminder_weekly_counters (owner_id, week_start, delivered_count)"
        " VALUES (?, '2026-08-31', 1)"
    )
    raw_db.execute(sql, (uid,))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(sql, (uid,))
    raw_db.execute(
        sql + " ON CONFLICT (owner_id, week_start)"
        " DO UPDATE SET delivered_count = delivered_count + 1",
        (uid,),
    )
    got = raw_db.execute(
        "SELECT delivered_count FROM reminder_weekly_counters WHERE owner_id = ?", (uid,)
    ).fetchone()[0]
    assert got == 2


def test_UT_S03_18_push_endpoint_unique(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    sql = (
        "INSERT INTO push_subscriptions (id, owner_id, endpoint, p256dh, auth_secret)"
        " VALUES (?, ?, 'https://push.test/x', 'k', 'a')"
    )
    raw_db.execute(sql, (str(uuid.uuid4()), uid))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(sql, (str(uuid.uuid4()), uid))


@pytest.mark.asyncio
async def test_UT_S03_24_failed_delivery_does_not_consume_budget(app_env: None) -> None:
    """两条通道都不可用时，outbox 进入重试而周计数保持 0（EX-16.2）。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.clock import clock
    from app.db import dispose_engines, session_scope
    from app.scheduler import run_tick
    from app.services import create_anonymous_space, seed_wish, set_timing

    clock.set_fixed(datetime(2026, 9, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    try:
        async with session_scope() as s:
            user, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
            owner = user.id
        async with session_scope(owner) as s:
            wish, _, _, _ = await seed_wish(
                s, owner, source="text", text="想去看海", media_id=None, photo_media_ids=[]
            )
            wid = wish.id
        async with session_scope(owner) as s:
            await set_timing(s, owner, wid, {"type": "after_months", "after_months": 1})

        clock.set_fixed(datetime(2026, 10, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        result = await run_tick()
        assert result.enqueued == 1
        # 匿名用户没有邮箱、也没有 push 订阅 → 无从投递
        assert result.delivered == 0

        from app.models import ReminderOutbox, ReminderWeeklyCounter
        from app.timing import week_start

        async with session_scope(owner) as s:
            from sqlalchemy import select

            row = await s.scalar(select(ReminderOutbox).where(ReminderOutbox.owner_id == owner))
            assert row is not None
            assert row.status in ("pending", "failed")
            assert row.attempts >= 1
            wk = week_start(clock.now(), "Asia/Shanghai").isoformat()
            counter = await s.get(ReminderWeeklyCounter, (owner, wk))
            assert counter is None or counter.delivered_count == 0
    finally:
        clock.set_fixed(None)
        await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S03_27_lock_contention_exits_silently(app_env: None, caplog) -> None:  # noqa: ANN001
    """锁被占用时静默退出，且不记 error 级日志（EX-9.1）。"""
    import logging
    from pathlib import Path

    from app.config import get_settings
    from app.db import dispose_engines
    from app.scheduler import FileLock, run_tick

    lock_path = Path(get_settings().scheduler_lock_path)
    holder = FileLock(lock_path)
    assert holder.acquire() is True
    try:
        with caplog.at_level(logging.INFO, logger="app.scheduler"):
            result = await run_tick()
        assert result.scanned == 0 and result.enqueued == 0
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any(r.getMessage() == "scheduler_lock_busy" for r in caplog.records)
    finally:
        holder.release()
        await dispose_engines()
