"""S05 业务层：列表游标分页、整理半屏动作、彻底删除。

三条产品约束在这里落地：
  1. 列表响应只有 items 与 next_cursor —— 不返回任何计数字段（EX-6.1）
  2. 放下时同事务清空 pending 提醒（S05.2 Step 19）
  3. 彻底删除先删对象后删记录；对象部分失败不阻塞删除意图（EX-28.1）
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import clock
from app.models import (
    Media,
    OrphanObject,
    ReminderOutbox,
    Wish,
    WishAmendment,
    WishPhoto,
)
from app.storage import get_storage

ALLOWED_STATES = ("all", "seeded", "brewing", "wind", "going", "happened", "let_go")


@dataclass(frozen=True)
class Cursor:
    seeded_at: datetime
    wish_id: UUID

    def encode(self) -> str:
        raw = f"{self.seeded_at.isoformat()}|{self.wish_id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def decode(token: str) -> Cursor:
        padded = token + "=" * (-len(token) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode()).decode()
            iso, wid = raw.rsplit("|", 1)
            return Cursor(datetime.fromisoformat(iso), UUID(wid))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            from app.services import DomainError

            raise DomainError(400, "CURSOR_INVALID", "这一页已经翻不到了") from exc


async def list_wishes_page(
    session: AsyncSession, owner_id: UUID, *, state: str = "all", limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[Wish], str | None]:
    """S05.1 Step 2 → Step 5。按 seeded_at 倒序 + id 打破并列的稳定游标。"""
    from app.services import DomainError

    if state not in ALLOWED_STATES:
        raise DomainError(422, "VALIDATION_FAILED", "没有这种状态")
    stmt = select(Wish).where(Wish.owner_id == owner_id)
    if state != "all":
        stmt = stmt.where(Wish.state == state)
    if cursor:
        cur = Cursor.decode(cursor)
        # EX-2.1 的后半句：游标指向已被删除的记录也算失效。
        # 不静默返回下一页 —— 客户端拿到 400 才知道该丢弃游标重取第一页，
        # 否则锚点消失后翻页结果会静默偏移，用户看到的是「漏了几张卡」。
        anchor = await session.get(Wish, cur.wish_id)
        if anchor is None or anchor.owner_id != owner_id:
            raise DomainError(400, "CURSOR_INVALID", "这一页已经翻不到了")
        # (seeded_at, id) 的字典序小于游标位置即为「更旧」
        stmt = stmt.where(
            (Wish.seeded_at < cur.seeded_at)
            | ((Wish.seeded_at == cur.seeded_at) & (Wish.id < cur.wish_id))
        )
    order = (
        (Wish.let_go_at.desc().nulls_last(), Wish.seeded_at.desc(), Wish.id.desc())
        if state == "let_go"
        else (Wish.seeded_at.desc(), Wish.id.desc())
    )
    rows = list((await session.scalars(stmt.order_by(*order).limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = Cursor(page[-1].seeded_at, page[-1].id).encode() if has_more and page else None
    return page, next_cursor


async def amend_wish(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, *,
    title: str | None = None, original_text: str | None = None,
) -> Wish:
    """S05.2 Step 15「改一改它」。写入修订快照，seeded_at 与原话永不被覆盖丢失。"""
    from app.services import DomainError

    if title is None and original_text is None:
        raise DomainError(422, "VALIDATION_FAILED", "至少要改一个地方")
    if title is not None and not (1 <= len(title) <= 60):
        raise DomainError(422, "VALIDATION_FAILED", "标题太长了")
    if original_text is not None and not (1 <= len(original_text) <= 500):
        raise DomainError(422, "VALIDATION_FAILED", "写得有点长了")

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")

    session.add(
        WishAmendment(
            id=uuid.uuid4(),
            wish_id=wish_id,
            owner_id=owner_id,
            prev_title_enc=wish.title_enc,
            prev_original_enc=wish.original_text_enc,
            prev_understanding=wish.understanding,
        )
    )
    if title is not None:
        wish.title_enc = title
    if original_text is not None:
        wish.original_text_enc = original_text
    wish.last_activity_at = clock.now()
    wish.updated_at = clock.now()
    return wish


async def let_go_wish(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> Wish:
    """S05.2 Step 17 → Step 21。同事务清空待投递提醒，保留标题/原话/种下时间。"""
    from app.services import DomainError

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.state == "happened":
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "它已经发生过了")
    wish.state = "let_go"
    wish.let_go_at = clock.now()
    wish.timing_type = None
    wish.timing_value = None
    wish.timing_set_at = None
    wish.next_trigger_at = None
    wish.timing_occurrence = None
    wish.trigger_kind = "none"
    wish.soft_deferred = False
    wish.last_activity_at = clock.now()
    wish.version += 1
    await session.execute(
        delete(ReminderOutbox).where(
            ReminderOutbox.owner_id == owner_id,
            ReminderOutbox.wish_id == wish_id,
            ReminderOutbox.status == "pending",
        )
    )
    return wish


async def recall_wish(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> Wish:
    """S07：只把安静放下的愿望唤回刚种下，保留内容与准备过程。"""
    from app.services import DomainError

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.state != "let_go":
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "这件事现在还不能重新种下")
    wish.state = "seeded"
    wish.let_go_at = None
    wish.timing_type = None
    wish.timing_value = None
    wish.timing_set_at = None
    wish.next_trigger_at = None
    wish.timing_occurrence = None
    wish.trigger_kind = "none"
    wish.soft_deferred = False
    wish.last_activity_at = clock.now()
    wish.updated_at = clock.now()
    wish.version += 1
    await session.execute(
        delete(ReminderOutbox).where(
            ReminderOutbox.owner_id == owner_id,
            ReminderOutbox.wish_id == wish_id,
            ReminderOutbox.status == "pending",
        )
    )
    return wish


async def delete_wish_permanently(
    session: AsyncSession, owner_id: UUID, wish_id: UUID
) -> bool:
    """S05.2 Step 25 → Step 31。返回 True 表示确实删掉了一条（不存在时返回 False，仍幂等）。

    顺序是刻意的：**先删对象，后删记录**。反过来一旦对象删除失败，
    就再也查不到该删哪些 key，直接变成永久孤儿数据。
    """
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        return False

    keys: list[str] = []
    if wish.audio_media_id is not None:
        audio = await session.get(Media, wish.audio_media_id)
        if audio is not None:
            keys.append(audio.object_key)
    photo_ids = list(
        (
            await session.scalars(
                select(WishPhoto.media_id).where(WishPhoto.wish_id == wish_id)
            )
        ).all()
    )
    for media_id in photo_ids:
        media = await session.get(Media, media_id)
        if media is not None:
            keys.append(media.object_key)

    failed = get_storage().delete_many(keys) if keys else []
    for key in failed:
        # EX-28.1：删除意图立即生效，残留 key 交给每日清理任务重试
        await register_orphan_object(session, key, "delete_failed")

    # 先断开 wishes → media 的 RESTRICT 引用，再删愿望，最后清媒体记录
    audio_media_id = wish.audio_media_id
    wish.audio_media_id = None
    await session.flush()
    await session.delete(wish)
    await session.flush()
    for media_id in [*photo_ids, *([audio_media_id] if audio_media_id else [])]:
        media = await session.get(Media, media_id)
        if media is not None:
            await session.delete(media)
    return True


# ---------------------------------------------------------------- 孤儿对象清理队列


async def register_orphan_object(session: AsyncSession, key: str, reason: str) -> None:
    """登记一个待清理的对象键。

    `orphan_objects.object_key` 是 UNIQUE，重复登记**幂等不新增**（UT-S05-16）——
    用 ON CONFLICT DO NOTHING 而不是先查后插，避免并发下的竞态。
    此表不含 owner_id：记录已从业务表删除，无所属用户可言。
    """
    await session.execute(
        sqlite_insert(OrphanObject.__table__)
        .values(id=uuid.uuid4(), object_key=key, reason=reason, attempts=0)
        .on_conflict_do_nothing(index_elements=["object_key"])
    )


async def retry_orphan_objects(session: AsyncSession) -> tuple[int, int]:
    """每日清理任务：重试队列里残留的对象键。返回 (已清除, 仍失败)。

    这是 EX-28.1 的收敛端——彻底删除时对象存储失败不阻塞用户的删除意图，
    残留在这里被反复重试直到真的删掉。删成功即删行；仍失败则 `attempts + 1`
    留待下一日，计数只作可观测用途，不设放弃阈值：一个删不掉的对象
    就是一份还没兑现的删除承诺。
    """
    rows = list(
        (await session.scalars(select(OrphanObject).order_by(OrphanObject.created_at))).all()
    )
    if not rows:
        return 0, 0
    failed = set(get_storage().delete_many([r.object_key for r in rows]))
    cleared = 0
    for row in rows:
        if row.object_key in failed:
            row.attempts += 1
        else:
            await session.delete(row)
            cleared += 1
    return cleared, len(failed)
