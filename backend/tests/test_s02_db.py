"""S02 的数据库约束与服务层单元测试（SQLite）。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import timedelta

import pytest


def _user(db: sqlite3.Connection) -> str:
    uid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, is_anonymous, onboarded_at)"
        " VALUES (?, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        (uid,),
    )
    return uid


def _media(db: sqlite3.Connection, owner: str, *, kind: str = "audio", status: str = "ready") -> str:
    mid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO media (id, owner_id, kind, object_key, content_type, size_bytes, status)"
        " VALUES (?, ?, ?, ?, ?, 1024, ?)",
        (mid, owner, kind, f"{owner}/{kind}/{mid}.bin", "audio/webm", status),
    )
    return mid


def test_UT_S02_12_object_key_unique(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    raw_db.execute(
        "INSERT INTO media (id, owner_id, kind, object_key, content_type)"
        " VALUES (?, ?, 'audio', 'dup/key.webm', 'audio/webm')",
        (str(uuid.uuid4()), uid),
    )
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO media (id, owner_id, kind, object_key, content_type)"
            " VALUES (?, ?, 'audio', 'dup/key.webm', 'audio/webm')",
            (str(uuid.uuid4()), uid),
        )


def test_UT_S02_13_media_status_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO media (id, owner_id, kind, object_key, content_type, status)"
            " VALUES (?, ?, 'audio', 'k1.webm', 'audio/webm', 'uploading')",
            (str(uuid.uuid4()), uid),
        )


def test_UT_S02_14_media_status_defaults_to_pending(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    mid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO media (id, owner_id, kind, object_key, content_type)"
        " VALUES (?, ?, 'audio', 'k2.webm', 'audio/webm')",
        (mid, uid),
    )
    got = raw_db.execute("SELECT status FROM media WHERE id = ?", (mid,)).fetchone()[0]
    assert got == "pending"


def test_UT_S02_15_voice_requires_audio(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, audio_media_id)"
            " VALUES (?, ?, ?, 'voice', NULL)",
            (str(uuid.uuid4()), uid, b"cipher"),
        )


def test_UT_S02_16_degraded_reason_enum(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, degraded_reason)"
            " VALUES (?, ?, ?, 'text', 'unknown')",
            (str(uuid.uuid4()), uid, b"cipher"),
        )
    for ok in ("llm_failed", "asr_failed", "asr_empty"):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source, degraded_reason)"
            " VALUES (?, ?, ?, 'text', ?)",
            (str(uuid.uuid4()), uid, b"cipher", ok),
        )


def test_UT_S02_17_wish_photos_primary_key_prevents_duplicates(
    raw_db: sqlite3.Connection,
) -> None:
    uid = _user(raw_db)
    mid = _media(raw_db, uid, kind="image")
    wid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, ?, 'text')",
        (wid, uid, b"cipher"),
    )
    raw_db.execute("INSERT INTO wish_photos (wish_id, media_id) VALUES (?, ?)", (wid, mid))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute("INSERT INTO wish_photos (wish_id, media_id) VALUES (?, ?)", (wid, mid))


def test_UT_S02_18_referenced_audio_cannot_be_deleted(raw_db: sqlite3.Connection) -> None:
    """ON DELETE RESTRICT：被愿望引用的音频不可单独删除。

    这条约束与 wishes_voice_requires_audio 是一对：若用 SET NULL，
    删除音频会把 source='voice' 的行改成 audio_media_id IS NULL，
    直接违反 CHECK。RESTRICT 才是「原始音频永久保留」的正确编码。
    """
    uid = _user(raw_db)
    mid = _media(raw_db, uid)
    wid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source, audio_media_id)"
        " VALUES (?, ?, ?, 'voice', ?)",
        (wid, uid, b"cipher", mid),
    )
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute("DELETE FROM media WHERE id = ?", (mid,))
    row = raw_db.execute(
        "SELECT count(*), audio_media_id FROM wishes WHERE id = ?", (wid,)
    ).fetchone()
    assert row[0] == 1
    assert row[1] == mid
    # 愿望被删除后，音频不再被引用，即可清理
    raw_db.execute("DELETE FROM wishes WHERE id = ?", (wid,))
    raw_db.execute("DELETE FROM media WHERE id = ?", (mid,))
    assert raw_db.execute("SELECT count(*) FROM media WHERE id = ?", (mid,)).fetchone()[0] == 0


def test_UT_S02_19_pending_agent_jobs_dedup(raw_db: sqlite3.Connection) -> None:
    uid = _user(raw_db)
    wid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, ?, 'text')",
        (wid, uid, b"cipher"),
    )
    sql = (
        "INSERT INTO pending_agent_jobs (id, owner_id, wish_id, job_kind)"
        " VALUES (?, ?, ?, 'transcription')"
    )
    raw_db.execute(sql, (str(uuid.uuid4()), uid, wid))
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(sql, (str(uuid.uuid4()), uid, wid))
    # 换一种 job_kind 则允许共存
    raw_db.execute(
        "INSERT INTO pending_agent_jobs (id, owner_id, wish_id, job_kind)"
        " VALUES (?, ?, ?, 'wish_understanding')",
        (str(uuid.uuid4()), uid, wid),
    )


@pytest.mark.asyncio
async def test_UT_S02_11_cross_user_media_reference_is_404(app_env: None) -> None:
    """跨用户引用媒体返回 404 而非 403（与 S05 EX-3.1 一致）。"""
    from app.db import dispose_engines, session_scope
    from app.services import DomainError, complete_upload, create_anonymous_space

    async with session_scope() as s:
        user_a, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
        user_b, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
        a_id, b_id = user_a.id, user_b.id

    async with session_scope(a_id) as s:
        media, _, _ = await __import__("app.services", fromlist=["x"]).create_upload_url(
            s, a_id, kind="audio", content_type="audio/webm", size_bytes=1024
        )
        media_id = media.id

    with pytest.raises(DomainError) as exc:
        async with session_scope(b_id) as s:
            await complete_upload(s, b_id, media_id)
    assert exc.value.status == 404
    assert exc.value.code == "MEDIA_NOT_FOUND"
    await dispose_engines()


@pytest.mark.asyncio
async def test_UT_S02_24_orphan_media_cutoff_is_24_hours(app_env: None) -> None:
    """23 小时不清理，25 小时清理（EX-13.1）。"""
    from app.clock import clock
    from app.db import dispose_engines, session_scope
    from app.services import cleanup_orphan_media, create_anonymous_space, create_upload_url

    async with session_scope() as s:
        user, _, _ = await create_anonymous_space(s, "Asia/Shanghai")
        owner = user.id

    async with session_scope(owner) as s:
        await create_upload_url(s, owner, kind="audio", content_type="audio/webm", size_bytes=1024)

    base = clock.now()
    try:
        clock.set_fixed(base + timedelta(hours=23))
        async with session_scope(owner) as s:
            assert await cleanup_orphan_media(s, owner) == 0
        clock.set_fixed(base + timedelta(hours=25))
        async with session_scope(owner) as s:
            assert await cleanup_orphan_media(s, owner) == 1
    finally:
        clock.set_fixed(None)
        await dispose_engines()
