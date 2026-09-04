"""偏好与可用时段的业务逻辑（S08）。

来源：core-S08-preferences-availability.md 与 auth.yaml（preferences tag）。
三条贯穿规则：
  1. 用户写入一律 declared / confidence=100 —— 请求中的任何 source/confidence 被忽略
     （S08 Step 8），同 key 的 inferred 行保持原样并列，不覆盖（S08 Step 9）。
  2. 撤回（软失效，保留审计痕迹）与删除（硬删除，无影子）是两个独立动作；
     两者都同事务失效引用该条目的 pending 时机建议（S08 Step 15 / Step 19）。
  3. 写接口的响应只含元数据，不回显 value 明文（敏感值不回显）；
     GET 回显明文（本人查看自己的数据）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import clock
from app.models import (
    DIGEST_KEY,
    PREFERENCE_KEYS,
    AvailabilityWindow,
    TimingProposal,
    UserPreference,
)
from app.services import DomainError

PREF_REVOKE_ALLOWED_SOURCES = ("inferred",)
PREF_NOT_REVOCABLE = (409, "PREFERENCE_NOT_REVOCABLE", "这一条不能这样收回")
PREF_NOT_FOUND = (404, "PREFERENCE_NOT_FOUND", "这条记忆不在这里")
PREF_KEY_INVALID = (422, "VALIDATION_FAILED", "不认识这个主题")
VALUE_INVALID = (422, "VALIDATION_FAILED", "想说的那句话先写完整")
AVAIL_INVALID = (422, "AVAILABILITY_INVALID", "结束要晚于开始")
AVAIL_NOT_FOUND = (404, "AVAILABILITY_NOT_FOUND", "这一段空闲已经不在这里")
VALUE_MAX_LEN = 200
NOTE_MAX_LEN = 50


class PreferenceError(DomainError):
    """业务校验失败。继承 DomainError 以复用统一的 {code,message} 响应转换。"""


def _fail(spec: tuple[int, str, str]) -> None:
    raise PreferenceError(*spec)


async def expire_proposals_referencing(
    session: AsyncSession, owner_id: uuid.UUID, kind: str, ref_id: uuid.UUID
) -> int:
    """撤回/删除偏好或时段后，把引用它的 pending 提议置 expired（S03 EX-P.5）。"""
    now = clock.now()
    rows = (
        (
            await session.execute(
                select(TimingProposal).where(
                    TimingProposal.owner_id == owner_id,
                    TimingProposal.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    hit = 0
    for row in rows:
        refs = row.evidence or []
        if any(r.get("kind") == kind and str(r.get("id")) == str(ref_id) for r in refs):
            row.status = "expired"
            row.updated_at = now
            hit += 1
    return hit


def _pref_meta(row: UserPreference) -> dict:
    """写操作响应：只含元数据，不含 value 明文（敏感值不回显）。"""
    return {
        "id": row.id,
        "kind": row.kind,
        "pref_key": row.pref_key,
        "source": row.source,
        "confidence": row.confidence,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _pref_item(row: UserPreference, *, include_value: bool = True) -> dict:
    data = _pref_meta(row)
    data["revoked_at"] = row.revoked_at
    if include_value:
        data["value"] = row.value_enc  # EncryptedText TypeDecorator 已解密为明文
    return data


async def list_preferences(owner_id: uuid.UUID, include_revoked: bool = False) -> dict:
    """GET /me/preferences。默认不含已撤回行；摘要（digest）随列表返回（S08 Step 2→6）。"""
    async with session_scope_for(owner_id) as session:
        stmt = select(UserPreference).where(UserPreference.owner_id == owner_id)
        if not include_revoked:
            stmt = stmt.where(UserPreference.revoked_at.is_(None))
        rows = (await session.execute(stmt)).scalars().all()
        items = [
            _pref_item(r) for r in rows if r.kind == "entry"
        ]
        items.sort(key=lambda r: r["created_at"])
        digest_row = next((r for r in rows if r.kind == "digest"), None)
        digest = _pref_item(digest_row) if digest_row else None
    return {"items": items, "digest": digest}


async def declare_preference(owner_id: uuid.UUID, pref_key: str, value: str) -> dict:
    """PUT /me/preferences。UPSERT 一条 declared 行；同 key 的 inferred 行不动（UT-S08-15）。"""
    if pref_key not in PREFERENCE_KEYS:
        _fail(PREF_KEY_INVALID)
    if not value or len(value) > VALUE_MAX_LEN:
        _fail(VALUE_INVALID)
    async with session_scope_for(owner_id) as session:
        now = clock.now()
        stmt = select(UserPreference).where(
            UserPreference.owner_id == owner_id,
            UserPreference.kind == "entry",
            UserPreference.pref_key == pref_key,
            UserPreference.source == "declared",
        )
        row = (await session.execute(stmt)).scalars().first()
        if row is None:
            row = UserPreference(
                owner_id=owner_id,
                kind="entry",
                pref_key=pref_key,
                source="declared",
                value_enc=value,
                confidence=100,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
        else:
            row.value_enc = value
            row.confidence = 100
            row.updated_at = now
        meta = _pref_meta(row)
    return meta


async def revoke_preference(owner_id: uuid.UUID, pref_id: uuid.UUID) -> dict:
    """POST /me/preferences/{id}/revoke。仅 inferred 且未撤回可撤回（EX-14.1）。"""
    async with session_scope_for(owner_id) as session:
        row = await session.get(UserPreference, pref_id)
        if row is None or row.owner_id != owner_id:
            _fail(PREF_NOT_FOUND)
        if row.source != "inferred" or row.revoked_at is not None:
            _fail(PREF_NOT_REVOCABLE)
        now = clock.now()
        row.revoked_at = now
        row.updated_at = now
        await expire_proposals_referencing(session, owner_id, "preference", pref_id)
        item = _pref_item(row)
    return item


async def delete_preference(owner_id: uuid.UUID, pref_id: uuid.UUID) -> None:
    """DELETE /me/preferences/{id}。硬删除，同事务失效引用它的 pending 建议（EX-19.1）。"""
    async with session_scope_for(owner_id) as session:
        row = await session.get(UserPreference, pref_id)
        if row is None or row.owner_id != owner_id:
            _fail(PREF_NOT_FOUND)
        await expire_proposals_referencing(session, owner_id, "preference", pref_id)
        await session.delete(row)


async def list_availability(owner_id: uuid.UUID) -> dict:
    """GET /me/availability。按 weekday 升序、start_minute 升序（auth.yaml）。"""
    async with session_scope_for(owner_id) as session:
        rows = (
            (
                await session.execute(
                    select(AvailabilityWindow)
                    .where(AvailabilityWindow.owner_id == owner_id)
                    .order_by(AvailabilityWindow.weekday, AvailabilityWindow.start_minute)
                )
            )
            .scalars()
            .all()
        )
        items = [_window_item(r) for r in rows]
    return {"items": items}


def _window_item(row: AvailabilityWindow) -> dict:
    return {
        "id": row.id,
        "weekday": row.weekday,
        "start_minute": row.start_minute,
        "end_minute": row.end_minute,
        "note": row.note_enc,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_window(weekday: int, start_minute: int, end_minute: int) -> None:
    """结构化字段的服务端校验。错误码统一 AVAILABILITY_INVALID（S08 EX-23.1）。"""
    if weekday not in range(0, 7):
        _fail(AVAIL_INVALID)
    if start_minute not in range(0, 1440) or end_minute not in range(1, 1441):
        _fail(AVAIL_INVALID)
    if end_minute <= start_minute:
        _fail(AVAIL_INVALID)


async def create_availability(
    owner_id: uuid.UUID, weekday: int, start_minute: int, end_minute: int, note: str | None
) -> dict:
    """POST /me/availability。跨午夜段由前端拆两行提交（S08 Step 23）。"""
    _validate_window(weekday, start_minute, end_minute)
    if note is not None and len(note) > NOTE_MAX_LEN:
        _fail(VALUE_INVALID)
    async with session_scope_for(owner_id) as session:
        row = AvailabilityWindow(
            owner_id=owner_id,
            weekday=weekday,
            start_minute=start_minute,
            end_minute=end_minute,
            note_enc=note,
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        session.add(row)
        await session.flush()
        item = _window_item(row)
    return item


async def update_availability(
    owner_id: uuid.UUID,
    window_id: uuid.UUID,
    changes: dict,
) -> dict:
    """PATCH /me/availability/{id}。校验规则与 POST 相同。"""
    async with session_scope_for(owner_id) as session:
        row = await session.get(AvailabilityWindow, window_id)
        if row is None or row.owner_id != owner_id:
            _fail(AVAIL_NOT_FOUND)
        weekday = changes.get("weekday", row.weekday)
        start_minute = changes.get("start_minute", row.start_minute)
        end_minute = changes.get("end_minute", row.end_minute)
        note = changes.get("note", row.note_enc)
        _validate_window(weekday, start_minute, end_minute)
        if note is not None and len(note) > NOTE_MAX_LEN:
            _fail(VALUE_INVALID)
        row.weekday = weekday
        row.start_minute = start_minute
        row.end_minute = end_minute
        row.note_enc = note
        row.updated_at = clock.now()
        await session.flush()
        item = _window_item(row)
    return item


async def delete_availability(owner_id: uuid.UUID, window_id: uuid.UUID) -> None:
    """DELETE /me/availability/{id}。硬删除；同事务失效引用它的 pending 建议。"""
    async with session_scope_for(owner_id) as session:
        row = await session.get(AvailabilityWindow, window_id)
        if row is None or row.owner_id != owner_id:
            _fail(AVAIL_NOT_FOUND)
        await expire_proposals_referencing(session, owner_id, "availability", window_id)
        await session.delete(row)


async def upsert_digest(owner_id: uuid.UUID, summary: str | None) -> bool:
    """Scheduler 摘要支线 D4：UPSERT kind='digest' 行，只保留最近一份。

    summary 为 None（LLM 降级）时保持既有 digest 不变（EX-D2.1），返回 False。
    """
    async with session_scope_for(owner_id) as session:
        stmt = select(UserPreference).where(
            UserPreference.owner_id == owner_id,
            UserPreference.kind == "digest",
            UserPreference.pref_key == DIGEST_KEY,
        )
        row = (await session.execute(stmt)).scalars().first()
        if summary is None:
            return row is not None
        now = clock.now()
        if row is None:
            session.add(
                UserPreference(
                    owner_id=owner_id,
                    kind="digest",
                    pref_key=DIGEST_KEY,
                    source="inferred",
                    value_enc=summary,
                    confidence=75,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.value_enc = summary
            row.updated_at = now
    return True


def session_scope_for(owner_id: uuid.UUID):
    """事务作用域。独立包装以便测试时 monkeypatch。"""
    from app.db import session_scope

    return session_scope(owner_id)
