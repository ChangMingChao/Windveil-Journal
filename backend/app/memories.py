"""S06 业务层：记忆页草稿、编辑、幂等发布、书架。

四条产品约束在这里落地：

  1. 全部内容字段可为空仍可发布 —— 没有任何非空校验（ST-S06-02）。`title_enc` 在 DDL 里是
     NOT NULL，所以「清空标题」落库为空字符串而不是 NULL；对外仍然是一个字符串。
  2. 发生日期早于种下日期**不拦截**，只回一个 warning 让前端用询问式确认（EX-3.1）。
     未来日期则硬拦——「已经发生」与未来日期在语义上直接矛盾（EX-3.2）。
  3. 标记已发生就停提醒，但愿望状态要到「收进书里」才转 happened（Step 6 与 Step 17 解耦）。
  4. 补草拟永不覆盖用户手动改过的段落（EX-7.1 的 edited_fields）。
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import get_llm_provider
from app.clock import clock
from app.models import (
    MEMORY_DRAFTED_FIELDS,
    MOODS,
    Media,
    Memory,
    MemoryPhoto,
    PendingAgentJob,
    ReminderOutbox,
    User,
    Wish,
    WishStep,
)

MAX_MEMORY_PHOTOS = 9
FIELD_LIMITS = {"title": 80, "cause": 2000, "process": 4000, "last_line": 300}
PATCHABLE_FIELDS = frozenset(
    {"title", "cause", "process", "mood", "last_line", "photo_media_ids", "voice_media_id"}
)
BEFORE_SEEDED_WARNING = {
    "code": "HAPPENED_BEFORE_SEEDED",
    "message": "它比你写下它的时候更早发生了吗？",
}


@dataclass(frozen=True)
class MemoryCursor:
    """书架游标。排序键是 (happened_from DESC, id DESC)，与部分索引的列序一致。"""

    happened_from: str
    memory_id: UUID

    def encode(self) -> str:
        raw = f"{self.happened_from}|{self.memory_id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def decode(token: str) -> MemoryCursor:
        from app.services import DomainError

        padded = token + "=" * (-len(token) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode()).decode()
            day, mid = raw.rsplit("|", 1)
            date.fromisoformat(day)
            return MemoryCursor(day, UUID(mid))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise DomainError(400, "CURSOR_INVALID", "这一页已经翻不到了") from exc


def _tz_of(user: User | None) -> str:
    return user.timezone if user else "Asia/Shanghai"


def _as_uuid(raw: object) -> UUID:
    from app.services import DomainError

    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise DomainError(422, "VALIDATION_FAILED", "这个标识格式不对") from exc


async def _timeline_texts(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> list[str]:
    """准备过程时间线：只有已完成的步骤才是「实际发生过的事」，草拟经过时的唯一素材。"""
    rows = await session.scalars(
        select(WishStep)
        .where(
            WishStep.owner_id == owner_id,
            WishStep.wish_id == wish_id,
            WishStep.status == "done",
        )
        .order_by(WishStep.completed_at)
    )
    return [r.text_enc for r in rows.all()]


async def _enqueue_memory_draft(session: AsyncSession, owner_id: UUID, memory_id: UUID) -> None:
    """EX-7.1：草拟失败不回滚已写入的草稿，只入队等 Scheduler 低频补做。"""
    await session.execute(
        sqlite_insert(PendingAgentJob)
        .values(
            id=uuid.uuid4(),
            owner_id=owner_id,
            memory_id=memory_id,
            job_kind="memory_draft",
            next_attempt_at=clock.now(),
        )
        .on_conflict_do_nothing()
    )


# ---------------------------------------------------------------- Step 3 → Step 10


async def mark_wish_happened(
    session: AsyncSession,
    owner_id: UUID,
    wish_id: UUID,
    *,
    happened_from: date,
    happened_to: date | None = None,
    acknowledged_before_seeded: bool = False,
) -> tuple[Memory, bool, dict[str, str] | None]:
    """「它已经发生了」。返回 (记忆页, 是否降级, warning)。"""
    from app.services import DomainError

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")

    tz = _tz_of(await session.get(User, owner_id))
    if happened_from > clock.now().astimezone(ZoneInfo(tz)).date():
        # EX-3.2：这是少数应当硬拦的校验，与 EX-3.1 的宽容处理不是同一类问题
        raise DomainError(422, "HAPPENED_DATE_IN_FUTURE", "这一天还没有到")
    if happened_to is not None and happened_to < happened_from:
        raise DomainError(422, "HAPPENED_RANGE_INVALID", "这两个日期的先后反了")

    before_seeded = happened_from < wish.seeded_at.astimezone(ZoneInfo(tz)).date()
    warning = (
        dict(BEFORE_SEEDED_WARNING)
        if before_seeded and not acknowledged_before_seeded
        else None
    )

    # Step 6：提醒在这一步就停。让用户在写记忆的过程中还收到「冬天到了，你说过想学滑雪」
    # 会很荒谬。但状态要到 Step 17 才转 happened——那是 Phase 2 定义的 UI 行为，两件事解耦。
    wish.next_trigger_at = None
    wish.soft_deferred = False
    wish.last_activity_at = clock.now()
    await session.execute(
        delete(ReminderOutbox).where(
            ReminderOutbox.owner_id == owner_id,
            ReminderOutbox.wish_id == wish_id,
            ReminderOutbox.status == "pending",
        )
    )

    existing = await session.scalar(
        select(Memory).where(Memory.owner_id == owner_id, Memory.wish_id == wish_id)
    )
    if existing is not None:
        # UT-S06-15：一事一页。重复提交视为「改一下日期」，不新建、也不重新花一次 LLM
        if existing.status == "draft":
            existing.happened_from = happened_from.isoformat()
            existing.happened_to = happened_to.isoformat() if happened_to else None
            existing.note_before_seeded = before_seeded and acknowledged_before_seeded
            existing.updated_at = clock.now()
        return existing, False, warning

    original = wish.original_text_enc or wish.title_enc
    draft = await get_llm_provider().draft_memory(
        original_text=original,
        feeling=(wish.understanding or {}).get("feeling"),
        timeline=await _timeline_texts(session, owner_id, wish_id),
    )
    if draft is None:
        # EX-7.1：标题回退为愿望原标题、起因回退为直接引用原话、经过留空
        title, cause, process = wish.title_enc, original, None
    else:
        title, cause, process = draft.title, draft.cause, draft.process

    now = clock.now()
    memory = Memory(
        id=uuid.uuid4(),
        wish_id=wish_id,
        owner_id=owner_id,
        title_enc=title,
        cause_enc=cause,
        process_enc=process,
        happened_from=happened_from.isoformat(),
        happened_to=happened_to.isoformat() if happened_to else None,
        note_before_seeded=before_seeded and acknowledged_before_seeded,
        edited_fields=[],
        status="draft",
        created_at=now,
        updated_at=now,
    )
    session.add(memory)
    await session.flush()
    if draft is None:
        await _enqueue_memory_draft(session, owner_id, memory.id)
    return memory, draft is None, warning


# ---------------------------------------------------------------- Step 12 → Step 14


def _check_lengths(patch: dict) -> None:
    from app.services import DomainError

    for field, limit in FIELD_LIMITS.items():
        if field not in patch:
            continue
        value = patch[field]
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > limit:
            raise DomainError(422, "VALIDATION_FAILED", "写得有点长了")


async def _replace_photos(
    session: AsyncSession, owner_id: UUID, memory_id: UUID, raw_ids: object
) -> None:
    from app.services import DomainError

    if not isinstance(raw_ids, list):
        raise DomainError(422, "VALIDATION_FAILED", "照片列表格式不对")
    if len(raw_ids) > MAX_MEMORY_PHOTOS:
        # EX-12.1：长度先判。反过来先查存在性，会让「传了 10 个不存在的 id」
        # 回一个 404，把真正的原因（超限）藏起来。
        raise DomainError(422, "MEDIA_LIMIT_EXCEEDED", "一页最多放 9 张照片")
    ids = [_as_uuid(x) for x in raw_ids]
    if ids:
        rows = (
            await session.scalars(
                select(Media).where(
                    Media.id.in_(ids), Media.owner_id == owner_id, Media.kind == "image"
                )
            )
        ).all()
        if {m.id for m in rows} != set(ids):
            raise DomainError(404, "MEDIA_NOT_FOUND", "找不到这些照片")
    await session.execute(delete(MemoryPhoto).where(MemoryPhoto.memory_id == memory_id))
    for order, media_id in enumerate(ids):
        session.add(MemoryPhoto(memory_id=memory_id, media_id=media_id, sort_order=order))


async def update_memory(
    session: AsyncSession, owner_id: UUID, memory_id: UUID, patch: dict
) -> Memory:
    """保存记忆页编辑。所有字段均可置 null，不做任何非空校验。"""
    from app.services import DomainError

    if not patch:
        raise DomainError(422, "VALIDATION_FAILED", "至少要改一个地方")
    if set(patch) - PATCHABLE_FIELDS:
        raise DomainError(422, "VALIDATION_FAILED", "有些内容还不太对")

    memory = await session.get(Memory, memory_id)
    if memory is None or memory.owner_id != owner_id:
        raise DomainError(404, "MEMORY_NOT_FOUND", "找不到这一页")

    _check_lengths(patch)
    if "mood" in patch and patch["mood"] is not None and patch["mood"] not in MOODS:
        raise DomainError(422, "VALIDATION_FAILED", "没有这种心情")

    if "photo_media_ids" in patch:
        await _replace_photos(session, owner_id, memory_id, patch["photo_media_ids"])
    if "voice_media_id" in patch:
        raw = patch["voice_media_id"]
        if raw is None:
            memory.voice_media_id = None
        else:
            voice_id = _as_uuid(raw)
            media = await session.get(Media, voice_id)
            if media is None or media.owner_id != owner_id or media.kind != "audio":
                raise DomainError(404, "MEDIA_NOT_FOUND", "找不到这段声音")
            memory.voice_media_id = voice_id

    edited = set(memory.edited_fields or [])
    if "title" in patch:
        # title_enc 是 NOT NULL：清空落库为空字符串，对外仍然是一个字符串
        memory.title_enc = patch["title"] or ""
        edited.add("title")
    if "cause" in patch:
        memory.cause_enc = patch["cause"]
        edited.add("cause")
    if "process" in patch:
        memory.process_enc = patch["process"]
        edited.add("process")
    if "mood" in patch:
        memory.mood = patch["mood"]
    if "last_line" in patch:
        memory.last_line_enc = patch["last_line"]

    memory.edited_fields = [f for f in MEMORY_DRAFTED_FIELDS if f in edited]
    memory.updated_at = clock.now()
    return memory


# ---------------------------------------------------------------- Step 16 → Step 19


async def publish_memory(session: AsyncSession, owner_id: UUID, memory_id: UUID) -> Memory:
    """「收进书里」。一个事务内置 published 并把愿望转 happened 终态。"""
    from app.services import DomainError

    # EX-18.1：愿望被彻底删除时草稿随之级联消失。publishMemory 在 memories.yaml 里
    # 唯一记载的 404 就是 WISH_NOT_FOUND，所以草稿查不到时也用这个码——
    # 从客户端看这两种情况本来就是同一件事：这一页已经不在了。
    memory = await session.get(Memory, memory_id)
    if memory is None or memory.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "这件事已经被删掉了")
    wish = await session.get(Wish, memory.wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "这件事已经被删掉了")

    if memory.status == "published":
        # EX-17.1：幂等。published_at 保持不变，/book 的页数不会因重复提交而虚增
        return memory

    now = clock.now()
    memory.status = "published"
    memory.published_at = now
    memory.updated_at = now
    wish.state = "happened"
    wish.next_trigger_at = None
    wish.last_activity_at = now
    wish.version += 1
    return memory


# ---------------------------------------------------------------- Step 20（书架）


async def list_memories(
    session: AsyncSession, owner_id: UUID, *, limit: int = 20, cursor: str | None = None
) -> tuple[list[Memory], str | None, int]:
    """书架。只返回 published，按发生时间倒序。返回 (页, next_cursor, lived_pages)。"""
    from app.services import DomainError

    if not 1 <= limit <= 50:
        raise DomainError(422, "VALIDATION_FAILED", "每页数量超出范围")
    stmt = select(Memory).where(Memory.owner_id == owner_id, Memory.status == "published")
    if cursor:
        cur = MemoryCursor.decode(cursor)
        stmt = stmt.where(
            (Memory.happened_from < cur.happened_from)
            | ((Memory.happened_from == cur.happened_from) & (Memory.id < cur.memory_id))
        )
    rows = list(
        (
            await session.scalars(
                stmt.order_by(Memory.happened_from.desc(), Memory.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        MemoryCursor(page[-1].happened_from, page[-1].id).encode() if has_more and page else None
    )
    # 「你已经活过的 N 页」是这个产品里唯一允许出现的计数——它数的是已经发生的事
    lived = await session.scalar(
        select(func.count())
        .select_from(Memory)
        .where(Memory.owner_id == owner_id, Memory.status == "published")
    )
    return page, next_cursor, int(lived or 0)


async def get_memory(session: AsyncSession, owner_id: UUID, memory_id: UUID) -> Memory:
    from app.services import DomainError

    memory = await session.get(Memory, memory_id)
    if memory is None or memory.owner_id != owner_id:
        raise DomainError(404, "MEMORY_NOT_FOUND", "找不到这一页")
    return memory


async def memory_photo_ids(session: AsyncSession, memory_id: UUID) -> list[UUID]:
    await session.flush()  # autoflush 关掉了：刚 add 的关联行否则查不到
    rows = await session.scalars(
        select(MemoryPhoto)
        .where(MemoryPhoto.memory_id == memory_id)
        .order_by(MemoryPhoto.sort_order)
    )
    return [r.media_id for r in rows.all()]


# ---------------------------------------------------------------- EX-7.1 补草拟


async def redraft_memory(session: AsyncSession, owner_id: UUID, memory_id: UUID) -> bool:
    """补草拟一页降级过的记忆。返回 True 表示这次真的补上了内容。

    用户手动改过的段落一律跳过——这是 `edited_fields` 存在的唯一理由。
    补草拟晚于用户编辑发生，如果它有权覆盖，用户的修改就会在某个夜里悄悄消失。
    """
    memory = await get_memory(session, owner_id, memory_id)
    wish = await session.get(Wish, memory.wish_id)
    if wish is None:
        return False
    draft = await get_llm_provider().draft_memory(
        original_text=wish.original_text_enc or wish.title_enc,
        feeling=(wish.understanding or {}).get("feeling"),
        timeline=await _timeline_texts(session, owner_id, memory.wish_id),
    )
    if draft is None:
        return False
    edited = set(memory.edited_fields or [])
    if "title" not in edited:
        memory.title_enc = draft.title
    if "cause" not in edited:
        memory.cause_enc = draft.cause
    if "process" not in edited:
        memory.process_enc = draft.process
    memory.updated_at = clock.now()
    return True


async def run_memory_draft_jobs(session: AsyncSession, owner_id: UUID) -> int:
    """低频后台任务：消费 memory_draft 队列。返回补齐的页数。

    与 `cleanup_orphan_media` / `retry_orphan_objects` 同一形态——独立的异步函数，
    由调度进程按自己的节奏调用，不挂在提醒 tick 上（提醒是用户可见的，补草拟不是）。
    """
    jobs = list(
        (
            await session.scalars(
                select(PendingAgentJob).where(
                    PendingAgentJob.owner_id == owner_id,
                    PendingAgentJob.job_kind == "memory_draft",
                    PendingAgentJob.next_attempt_at <= clock.now(),
                )
            )
        ).all()
    )
    filled = 0
    for job in jobs:
        memory = await session.get(Memory, job.memory_id) if job.memory_id else None
        if memory is None:
            # 记忆页已随愿望被彻底删除：任务没有目标了，直接出队
            await session.delete(job)
            continue
        if await redraft_memory(session, owner_id, job.memory_id):
            await session.delete(job)
            filled += 1
        else:
            job.attempts += 1
            job.last_error_code = "llm_failed"
    return filled





