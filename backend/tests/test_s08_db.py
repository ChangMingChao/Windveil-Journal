"""S08 数据库约束单测（UT-S08-09 ~ UT-S08-11）。

DB 约束来自 schema.sql（由 0008 迁移转写）；CHECK 的行为在真实 SQLite 上验证，不 mock。
UT-S08-13（加密落库）在 test_s08_scenarios.py 用 HTTP 写入 + 原始字节直查实现。
"""

from __future__ import annotations

import uuid

import pytest


def _user(raw_db) -> str:
    uid = str(uuid.uuid4())
    raw_db.execute(
        "INSERT INTO users (id, is_anonymous, timezone) VALUES (?, 1, 'Asia/Shanghai')", (uid,)
    )
    raw_db.commit()
    return uid


def _pref_sql(owner: str, **over) -> tuple[str, tuple]:
    row = {
        "id": str(uuid.uuid4()),
        "owner_id": owner,
        "kind": "entry",
        "pref_key": "companion",
        "source": "declared",
        "value_enc": b"\x00cipher",
        "confidence": 100,
        "revoked_at": None,
    }
    row.update(over)
    cols = ",".join(row)
    marks = ",".join("?" * len(row))
    return f"INSERT INTO user_preferences ({cols}) VALUES ({marks})", tuple(row.values())


def test_UT_S08_09_declared_must_be_certain(raw_db) -> None:
    """declared_is_certain CHECK：用户声明不承认任何「不确定」（UT-S08-09）。"""
    uid = _user(raw_db)
    sql, args = _pref_sql(uid, confidence=60)
    with pytest.raises(Exception, match="declared_is_certain"):
        raw_db.execute(sql, args)


def test_UT_S08_10_digest_never_revoked(raw_db) -> None:
    """digest_never_revoked CHECK：摘要行删除即可，没有撤回语义（UT-S08-10）。"""
    uid = _user(raw_db)
    sql, args = _pref_sql(
        uid,
        id=str(uuid.uuid4()),
        kind="digest",
        pref_key="overall",
        source="inferred",
        confidence=75,
        revoked_at="2026-09-03T00:00:00.000Z",
    )
    with pytest.raises(Exception, match="digest_never_revoked"):
        raw_db.execute(sql, args)


def test_UT_S08_11_unique_owner_kind_key_source(raw_db) -> None:
    """唯一性按 (owner, kind, key, source)：同 source 同 key 冲突（UPSERT 语义），
    不同 source 并存成功——「声明不覆盖推断」的数据基础（UT-S08-11 / S08 Step 9）。
    """
    uid = _user(raw_db)
    sql1, args1 = _pref_sql(uid, id=str(uuid.uuid4()))
    sql2, args2 = _pref_sql(uid, id=str(uuid.uuid4()), source="inferred", confidence=60)
    sql3, args3 = _pref_sql(uid, id=str(uuid.uuid4()))
    raw_db.execute(sql1, args1)
    # 不同 source 并存：需求 AC-01 的「不互相覆盖、不丢失」
    raw_db.execute(sql2, args2)
    raw_db.commit()
    rows = raw_db.execute(
        "SELECT count(*) FROM user_preferences WHERE owner_id=? AND pref_key='companion'",
        (uid,),
    ).fetchone()[0]
    assert rows == 2, "declared 与 inferred 必须可并存（S08 Step 9）"
    # 同 source 同 key：唯一索引拦截，应用层以 UPSERT 更新而非新增
    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        raw_db.execute(sql3, args3)
    raw_db.rollback()
