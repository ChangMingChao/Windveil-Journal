"""轻量事件的业务逻辑（S09）。

来源：core-S09-lite-events.md 与 lite-events.yaml。三条贯穿规则：
  1. 纯写入：不调用 Agent、不产生任何提醒——「结构上无提醒路径」由数据与
     代码共同保证（架构 5.6），本模块不存在任何提醒相关分支。
  2. 两态：open（在列表）/ done（划掉，行保留以备追溯）；收走（硬删除）不留行。
  3. done 幂等保护：对已关闭的事件重复 done 返回 409，而非静默重放（EX-14.1）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import clock
from app.models import LiteEvent
from app.services import DomainError

LITE_NOT_FOUND = (404, "LITE_EVENT_NOT_FOUND", "这条小事已经不在这里了")
LITE_ALREADY_CLOSED = (409, "LITE_EVENT_ALREADY_CLOSED", "这一条已经划掉了")
LITE_TEXT_INVALID = (422, "VALIDATION_FAILED", "想记的那句话先写完整")
TEXT_MAX_LEN = 200


def _item(row: LiteEvent) -> dict:
    return {
        "id": row.id,
        "text": row.text_enc,  # EncryptedText TypeDecorator 已解密
        "status": row.status,
        "created_at": row.created_at,
        "closed_at": row.closed_at,
    }


async def create(session: AsyncSession, owner_id: uuid.UUID, text: str) -> dict:
    """POST /lite-events。纯写入：无 Agent、无提醒、无任何副作用扩散。"""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > TEXT_MAX_LEN:
        raise DomainError(*LITE_TEXT_INVALID)
    now = clock.now()
    row = LiteEvent(
        owner_id=owner_id,
        text_enc=stripped,
        status="open",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return _item(row)


async def list_events(
    session: AsyncSession, owner_id: uuid.UUID, include_done: bool = False
) -> list[dict]:
    """GET /lite-events。默认只取 open 状态，最近在上；无分页、无计数。"""
    stmt = select(LiteEvent).where(LiteEvent.owner_id == owner_id)
    if not include_done:
        stmt = stmt.where(LiteEvent.status == "open")
    rows = (
        (await session.execute(stmt.order_by(LiteEvent.created_at.desc())))
        .scalars()
        .all()
    )
    return [_item(r) for r in rows]


async def mark_done(session: AsyncSession, owner_id: uuid.UUID, event_id: uuid.UUID) -> dict:
    """POST /{id}/done。对已关闭的事件返回 409 而非静默重放（EX-14.1）。"""
    row = await session.get(LiteEvent, event_id)
    if row is None or row.owner_id != owner_id:
        raise DomainError(*LITE_NOT_FOUND)
    if row.status != "open":
        raise DomainError(*LITE_ALREADY_CLOSED)
    now = clock.now()
    row.status = "done"
    row.closed_at = now
    row.updated_at = now
    return _item(row)


async def create_from_wish(session: AsyncSession, owner_id: uuid.UUID, wish_row) -> dict:
    """s02-lite-conversion：从 wish 转换——同事务删 wish 行、建同文本轻事件。

    照片/语音与 Agent 理解结果不迁移（规格边界：转换只保留文本）。
    """
    item = await create(session, owner_id, wish_row.original_text_enc or wish_row.title_enc)
    await session.delete(wish_row)
    return item


async def delete(session: AsyncSession, owner_id: uuid.UUID, event_id: uuid.UUID) -> None:
    """DELETE /{id}。硬删除，无软删除标记；重复或跨用户一律 404（EX-22.1）。"""
    row = await session.get(LiteEvent, event_id)
    if row is None or row.owner_id != owner_id:
        raise DomainError(*LITE_NOT_FOUND)
    await session.delete(row)
