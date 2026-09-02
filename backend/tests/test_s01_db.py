"""S01 的数据库约束单元测试（SQLite）。

不再需要任何外部服务：每个用例用 tmp_path 下的临时库，
装载 0001_batch1_core 的 DDL（与 schema.sql 的对应部分一致）。
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest


def _new_user(db: sqlite3.Connection, *, anonymous: bool = True) -> str:
    uid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, is_anonymous, onboarded_at)"
        " VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        (uid, 1 if anonymous else 0),
    )
    return uid


def test_UT_S01_13_anonymous_user_cannot_have_email(raw_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO users (id, is_anonymous, email, password_hash)"
            " VALUES (?, 1, 'a@b.c', 'h')",
            (str(uuid.uuid4()),),
        )


def test_UT_S01_14_email_and_hash_must_come_together(raw_db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO users (id, is_anonymous, email) VALUES (?, 0, 'only@mail.c')",
            (str(uuid.uuid4()),),
        )


def test_UT_S01_15_email_unique(raw_db: sqlite3.Connection) -> None:
    raw_db.execute(
        "INSERT INTO users (id, is_anonymous, email, password_hash)"
        " VALUES (?, 0, 'dup@mail.c', 'h')",
        (str(uuid.uuid4()),),
    )
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO users (id, is_anonymous, email, password_hash)"
            " VALUES (?, 0, 'dup@mail.c', 'h2')",
            (str(uuid.uuid4()),),
        )


def test_UT_S01_16_onboarded_at_written_at_signup(raw_db: sqlite3.Connection) -> None:
    uid = _new_user(raw_db)
    got = raw_db.execute("SELECT onboarded_at FROM users WHERE id = ?", (uid,)).fetchone()[0]
    assert got is not None
    assert got.endswith("Z")


def test_UT_S01_17_onboarding_answer_upsert_not_error(raw_db: sqlite3.Connection) -> None:
    uid = _new_user(raw_db)
    sql = (
        "INSERT INTO onboarding_answers (id, owner_id, question_key, answer_enc)"
        " VALUES (?, ?, 'q1', ?)"
        " ON CONFLICT (owner_id, question_key) DO UPDATE SET answer_enc = excluded.answer_enc"
    )
    raw_db.execute(sql, (str(uuid.uuid4()), uid, b"first"))
    raw_db.execute(sql, (str(uuid.uuid4()), uid, b"second"))
    count = raw_db.execute(
        "SELECT count(*) FROM onboarding_answers WHERE owner_id = ?", (uid,)
    ).fetchone()[0]
    assert count == 1
    value = raw_db.execute(
        "SELECT answer_enc FROM onboarding_answers WHERE owner_id = ?", (uid,)
    ).fetchone()[0]
    assert bytes(value) == b"second"


def test_UT_S01_18_wish_title_not_null(raw_db: sqlite3.Connection) -> None:
    uid = _new_user(raw_db)
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute(
            "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, NULL, 'text')",
            (str(uuid.uuid4()), uid),
        )


def test_UT_S01_19_wish_state_defaults_to_seeded(raw_db: sqlite3.Connection) -> None:
    uid = _new_user(raw_db)
    wid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, source) VALUES (?, ?, ?, 'text')",
        (wid, uid, b"blob"),
    )
    state = raw_db.execute("SELECT state FROM wishes WHERE id = ?", (wid,)).fetchone()[0]
    assert state == "seeded"


def test_UT_S01_20_encrypted_columns_are_not_readable_plaintext(
    raw_db: sqlite3.Connection, app_env: None
) -> None:
    """加密在应用层完成：库里存的密文不含明文子串，解密后可还原。"""
    from app.crypto import decrypt_text, encrypt_text

    uid = _new_user(raw_db)
    wid = str(uuid.uuid4())
    secret = "想去看海"
    blob = encrypt_text(secret)
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, original_text_enc, source)"
        " VALUES (?, ?, ?, ?, 'text')",
        (wid, uid, blob, blob),
    )
    stored = raw_db.execute(
        "SELECT original_text_enc FROM wishes WHERE id = ?", (wid,)
    ).fetchone()[0]
    assert isinstance(stored, bytes)
    assert secret.encode("utf-8") not in stored
    assert decrypt_text(stored) == secret


def test_UT_S01_26_wish_row_survives_llm_failure(raw_db: sqlite3.Connection) -> None:
    """落库与调用 LLM 分属不同事务：第二步失败时第一步已提交。"""
    uid = _new_user(raw_db)
    wid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO wishes (id, owner_id, title_enc, original_text_enc, source)"
        " VALUES (?, ?, ?, ?, 'text')",
        (wid, uid, b"title-cipher", b"original-cipher"),
    )
    raw_db.commit()  # 第一段事务提交

    # 第二段事务失败（非法状态被 CHECK 拦住），不影响已提交的行
    with pytest.raises(sqlite3.IntegrityError):
        raw_db.execute("UPDATE wishes SET state = 'archived' WHERE id = ?", (wid,))
    raw_db.rollback()

    row = raw_db.execute(
        "SELECT count(*), understanding FROM wishes WHERE id = ?", (wid,)
    ).fetchone()
    assert row[0] == 1
    assert row[1] is None
