"""业务层。S01 的时序图 Step 序列在这里逐步落地。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import UnderstandResult, get_llm_provider
from app.asr import get_asr_provider
from app.clock import clock
from app.config import get_settings
from app.db import owner_guard_bypass
from app.models import (
    Media,
    Memory,
    OnboardingAnswer,
    PendingAgentJob,
    Session,
    User,
    Wish,
    WishAmendment,
    WishMessage,
    WishPhoto,
    WishStep,
)
from app.schemas import (
    MemoryCard,
    MemoryOut,
    OnboardingAnswerItem,
    TimingOut,
    WishCard,
    WishDetail,
)
from app.security import hash_password, hash_refresh_token, issue_access_token, new_refresh_token
from app.storage import get_storage

TIMING_LABELS = {
    "season": {"spring": "入春", "summer": "入夏", "autumn": "入秋", "winter": "入冬"},
}


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message


# ---------------------------------------------------------------- auth / onboarding


async def create_anonymous_space(session: AsyncSession, timezone: str) -> tuple[User, str, str]:
    """S01 Step 3 → Step 6。

    onboarded_at 在建号时即写入，使「跳过问题后未输入即离开」不会重复
    首次体验（S01 EX-12.1）。
    """
    now = clock.now()
    user = User(
        id=uuid.uuid4(),
        is_anonymous=True,
        onboarded_at=now,
        timezone=timezone,
    )
    session.add(user)
    await session.flush()

    raw_refresh, refresh_hash = new_refresh_token()
    session.add(
        Session(
            owner_id=user.id,
            refresh_hash=refresh_hash,
            expires_at=now + timedelta(days=get_settings().REFRESH_TOKEN_TTL_DAYS),
        )
    )
    return user, issue_access_token(user.id), raw_refresh


async def link_email(session: AsyncSession, user_id: UUID, email: str, password: str) -> User:
    # 按邮箱查重无法带 owner_id，显式声明一次跨 owner 查询（db.owner_guard_bypass）
    with owner_guard_bypass():
        existing = await session.scalar(select(User).where(User.email == email.lower()))
    if existing is not None and existing.id != user_id:
        raise DomainError(409, "EMAIL_ALREADY_LINKED", "该邮箱已被其他账号使用")
    user = await session.get(User, user_id)
    if user is None:
        raise DomainError(404, "USER_NOT_FOUND", "找不到这个人")
    user.email = email.lower()
    user.password_hash = hash_password(password)
    user.is_anonymous = False
    user.updated_at = clock.now()
    return user


async def save_onboarding_answers(
    session: AsyncSession, owner_id: UUID, answers: list[OnboardingAnswerItem]
) -> None:
    """S01 Step 9 → Step 11。

    重复提交同一 question_key 走 upsert 覆盖而非报错（UT-S01-17）；
    写入失败由调用方吞掉并仍返回 204（EX-10.1）。
    """
    from app.faults import check_fault

    check_fault("onboarding_answers_write")  # 故障注入点（ST-S01-04）
    for item in answers:
        stmt = (
            sqlite_insert(OnboardingAnswer)
            .values(
                id=uuid.uuid4(),
                owner_id=owner_id,
                question_key=item.question_key,
                answer_enc=item.answer_text,
            )
            .on_conflict_do_update(
                index_elements=["owner_id", "question_key"],
                set_={"answer_enc": item.answer_text},
            )
        )
        await session.execute(stmt)


async def revoke_session(session: AsyncSession, refresh_raw: str) -> None:
    # refresh token 哈希是全局唯一键，同样无法带 owner_id
    with owner_guard_bypass():
        row = await session.scalar(
            select(Session).where(Session.refresh_hash == hash_refresh_token(refresh_raw))
        )
    if row is not None and row.revoked_at is None:
        row.revoked_at = clock.now()


# ---------------------------------------------------------------- wishes


def _fallback_title(text: str) -> str:
    """降级时标题回退为原话前 20 字（S01 EX-16.1）。"""
    return text[: get_settings().WISH_TITLE_FALLBACK_LEN]


def _derive_title(text: str, result: UnderstandResult | None) -> str:
    if result is None:
        return _fallback_title(text)
    step = result.understanding.smallest_step
    feeling = result.understanding.feeling
    # 标题由服务端从结构化结果里取一个短句；模型不直接决定标题字段，
    # 避免它返回长句造成卡面溢出。
    for candidate in (result.understanding.conditions.get("title"), feeling, step):
        if isinstance(candidate, str) and 0 < len(candidate) <= 60:
            return candidate
    return _fallback_title(text)


def timing_of(wish: Wish) -> TimingOut:
    if wish.timing_type is None:
        return TimingOut(type=None, label="刚种下", trigger_kind="none")
    if wish.timing_type == "none":
        return TimingOut(type="none", label="你说你会自己想起它", trigger_kind="none")
    if wish.timing_type == "season":
        season = TIMING_LABELS["season"].get(wish.timing_value or "", wish.timing_value or "")
        return TimingOut(
            type="season",
            label=f"正在等待合适的风：{season}",
            trigger_kind=wish.trigger_kind,
            next_trigger_at=wish.next_trigger_at,
        )
    if wish.timing_type == "when_tired":
        return TimingOut(
            type="when_tired", label="正在等待合适的风：你说累的时候", trigger_kind="signal"
        )
    if wish.timing_type == "free_weekend":
        return TimingOut(
            type="free_weekend",
            label="正在等待合适的风：一个空闲的周末",
            trigger_kind=wish.trigger_kind,
            next_trigger_at=wish.next_trigger_at,
        )
    return TimingOut(
        type=wish.timing_type,
        label=f"正在等待合适的风：{wish.timing_value}",
        trigger_kind=wish.trigger_kind,
        next_trigger_at=wish.next_trigger_at,
    )
def to_card(wish: Wish) -> WishCard:
    excerpt = wish.original_text_enc
    if excerpt and len(excerpt) > 40:
        excerpt = excerpt[:40]
    return WishCard(
        id=wish.id,
        title=wish.title_enc,
        original_text_excerpt=excerpt,
        seeded_at=wish.seeded_at,
        state=wish.state,
        let_go_at=wish.let_go_at,
        timing=timing_of(wish),
        soft_deferred=wish.soft_deferred,
        degraded_reason=wish.degraded_reason,
        version=wish.version,
    )


def to_detail(wish: Wish, photo_ids: list[UUID] | None = None) -> WishDetail:
    card = to_card(wish)
    return WishDetail(
        **card.model_dump(),
        original_text=wish.original_text_enc,
        audio_media_id=wish.audio_media_id,
        photo_media_ids=photo_ids or [],
        understanding=wish.understanding,
        pending_question=wish.pending_question,
    )


async def _attach_photos(
    session: AsyncSession, wish_id: UUID, owner_id: UUID, media_ids: list[UUID]
) -> list[UUID]:
    if not media_ids:
        return []
    rows = (
        await session.scalars(
            select(Media).where(
                Media.id.in_(media_ids), Media.owner_id == owner_id, Media.kind == "image"
            )
        )
    ).all()
    found = {m.id for m in rows}
    missing = [m for m in media_ids if m not in found]
    if missing:
        raise DomainError(404, "MEDIA_NOT_FOUND", "找不到这些照片")
    not_ready = [m.id for m in rows if m.status != "ready"]
    if not_ready:
        raise DomainError(422, "MEDIA_INVALID", "这些照片还没上传完")
    for order, media_id in enumerate(media_ids):
        session.add(WishPhoto(wish_id=wish_id, media_id=media_id, sort_order=order))
    return list(media_ids)


def normalize_wish_text(text: str | None) -> str:
    """校验并归一化用户写下的原话。纯函数，便于 UT 不依赖数据库地覆盖边界。"""
    cleaned = (text or "").strip()
    if not cleaned:
        raise DomainError(422, "WISH_TEXT_INVALID", "还没有写下任何内容")
    if len(cleaned) > get_settings().WISH_TEXT_MAX_LEN:
        raise DomainError(422, "WISH_TEXT_INVALID", "写得有点长了")
    return cleaned


async def seed_wish(
    session: AsyncSession,
    owner_id: UUID,
    *,
    source: str,
    text: str | None,
    media_id: UUID | None,
    photo_media_ids: list[UUID],
) -> tuple[Wish, list[UUID], UnderstandResult | None, bool]:
    """S01 Step 13 → Step 18 的第一段：落库原话。

    调用方负责在本函数返回（事务提交）之后再调用 enrich_wish()，
    确保 LLM 调用发生在提交之后 —— 这是「Agent 不可用也不丢用户的话」
    唯一能结构性成立的实现方式（S01 Step 14 说明）。
    """
    if source == "text":
        original = normalize_wish_text(text)
        audio_id = None
    else:
        if media_id is None:
            raise DomainError(422, "VALIDATION_FAILED", "缺少语音")
        media = await session.get(Media, media_id)
        if media is None or media.owner_id != owner_id or media.kind != "audio":
            raise DomainError(404, "MEDIA_NOT_FOUND", "找不到这段语音")
        if media.status != "ready":
            raise DomainError(422, "MEDIA_INVALID", "这段语音还没上传完")
        original = None
        audio_id = media.id

    now = clock.now()
    wish = Wish(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title_enc=_fallback_title(original) if original else "一段还没被读懂的话",
        original_text_enc=original,
        source=source,
        audio_media_id=audio_id,
        state="seeded",
        seeded_at=now,
        last_activity_at=now,
        version=1,
    )
    session.add(wish)
    await session.flush()
    photos = await _attach_photos(session, wish.id, owner_id, photo_media_ids)
    return wish, photos, None, False


async def enrich_wish(session: AsyncSession, wish_id: UUID, owner_id: UUID) -> tuple[Wish, bool]:
    """S01 Step 16 → Step 18：调用 LLM 并回填。

    返回 (wish, degraded)。任何失败都不回滚已提交的原话，而是入队待补
    （EX-16.1 / EX-16.2）。
    """
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if not wish.original_text_enc:
        # 语音尚未转写，理解无从进行
        return wish, True

    result = await get_llm_provider().understand_wish(wish.original_text_enc)
    if result is None:
        wish.degraded_reason = "llm_failed"
        wish.title_enc = _fallback_title(wish.original_text_enc)
        await _enqueue_agent_job(session, owner_id, wish.id, "wish_understanding")
        return wish, True

    wish.understanding = result.understanding.model_dump()
    wish.title_enc = _derive_title(wish.original_text_enc, result)
    wish.question_enc = result.question
    wish.pending_question = result.question is not None
    wish.degraded_reason = None
    wish.updated_at = clock.now()
    return wish, False


async def _enqueue_agent_job(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, kind: str
) -> None:
    stmt = (
        sqlite_insert(PendingAgentJob)
        .values(
            id=uuid.uuid4(),
            owner_id=owner_id,
            wish_id=wish_id,
            job_kind=kind,
            next_attempt_at=clock.now(),
        )
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)


async def answer_question(
    session: AsyncSession,
    owner_id: UUID,
    wish_id: UUID,
    *,
    answer: str | None,
    skipped: bool | None,
    action: str | None,
) -> Wish:
    """S01 Step 22 → Step 24。skipped 时保留 pending_question 供未来再问。"""
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if answer is not None:
        wish.answer_enc = answer
        wish.pending_question = False
    elif skipped:
        wish.pending_question = True
    elif action == "keep_as_future":
        if wish.understanding is not None:
            data: dict[str, Any] = dict(wish.understanding)
            data["kind"] = "future_wish"
            wish.understanding = data
    wish.last_activity_at = clock.now()
    return wish


async def list_wishes(
    session: AsyncSession, owner_id: UUID, *, state: str = "all", limit: int = 20
) -> list[Wish]:
    stmt = select(Wish).where(Wish.owner_id == owner_id)
    if state != "all":
        stmt = stmt.where(Wish.state == state)
    stmt = stmt.order_by(Wish.seeded_at.desc(), Wish.id).limit(limit)
    return list((await session.scalars(stmt)).all())


async def photo_ids_of(session: AsyncSession, wish_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        select(WishPhoto.media_id).where(WishPhoto.wish_id == wish_id).order_by(WishPhoto.sort_order)
    )
    return list(rows.all())


# ---------------------------------------------------------------- timing（S03）


async def set_timing(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, payload: dict[str, Any]
) -> Wish:
    """S03 Step 4 → Step 7。next_trigger_at 一律服务端计算（Step 5 说明）。"""
    from app.timing import TimingError, plan_timing

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.state == "happened":
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "它已经发生过了")
    user = await session.get(User, owner_id)
    tz = user.timezone if user else "Asia/Shanghai"
    try:
        plan = plan_timing(
            timing_type=payload.get("type", ""),
            timezone=tz,
            season=payload.get("season"),
            month_day=payload.get("month_day"),
            after_months=payload.get("after_months"),
            holidays=payload.get("holidays"),
        )
    except (TimingError, ValueError) as exc:
        raise DomainError(422, "TIMING_INVALID", "这个时机我还没法记下来") from exc

    wish.timing_type = plan.timing_type
    wish.timing_value = plan.timing_value
    wish.trigger_kind = plan.trigger_kind
    wish.next_trigger_at = plan.next_trigger_at
    wish.timing_occurrence = plan.occurrence
    wish.timing_set_at = clock.now()
    wish.soft_deferred = False
    # 「不必提醒」不转 brewing，状态保持 seeded（EX-4.1）
    wish.state = "seeded" if plan.timing_type == "none" else "brewing"
    wish.last_activity_at = clock.now()
    wish.updated_at = clock.now()
    return wish


async def mark_ready(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> Wish:
    """S03 Step 20 → Step 22 / S04 Step 2。任意状态下用户主动点击均可。"""
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.state == "happened":
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "它已经发生过了")
    wish.state = "wind"
    wish.soft_deferred = False
    wish.last_activity_at = clock.now()
    wish.version += 1
    return wish


async def defer_wish(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, after_months: int = 3
) -> Wish:
    """S03 EX-20.1「还不是现在」。只重算时机，不写任何顺延计数。"""
    from app.timing import plan_timing

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    user = await session.get(User, owner_id)
    plan = plan_timing(
        timing_type="after_months",
        timezone=user.timezone if user else "Asia/Shanghai",
        after_months=after_months,
    )
    wish.timing_type = "after_months"
    wish.timing_value = str(after_months)
    wish.trigger_kind = "time"
    wish.next_trigger_at = plan.next_trigger_at
    wish.timing_occurrence = plan.occurrence
    wish.timing_set_at = clock.now()
    wish.state = "brewing"
    wish.soft_deferred = False
    wish.last_activity_at = clock.now()
    return wish


async def pause_reminders(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> Wish:
    """S05.2 整理半屏第 2 项「暂时不提醒」：清时机、回 seeded、清 pending 提醒。"""
    from app.models import ReminderOutbox

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    wish.timing_type = None
    wish.timing_value = None
    wish.trigger_kind = "none"
    wish.next_trigger_at = None
    wish.timing_occurrence = None
    wish.soft_deferred = False
    wish.state = "seeded"
    wish.last_activity_at = clock.now()
    await session.execute(
        delete(ReminderOutbox).where(
            ReminderOutbox.owner_id == owner_id,
            ReminderOutbox.wish_id == wish_id,
            ReminderOutbox.status == "pending",
        )
    )
    return wish


async def trigger_fatigue_signals(session: AsyncSession, owner_id: UUID) -> int:
    """S03 EX-11.1：对话检出疲惫后，把该用户所有 signal 类时机置为立即触发。"""
    from app.timing import signal_occurrence

    now = clock.now()
    rows = list(
        (
            await session.scalars(
                select(Wish).where(Wish.owner_id == owner_id, Wish.trigger_kind == "signal")
            )
        ).all()
    )
    for wish in rows:
        wish.trigger_kind = "time"
        wish.next_trigger_at = now
        wish.timing_occurrence = signal_occurrence(now)
        wish.state = "brewing"
    return len(rows)


# ---------------------------------------------------------------- media（S02）


def validate_upload_request(kind: str, content_type: str, size_bytes: int) -> None:
    """media.yaml → createMediaUploadUrl 的字段组合校验。纯函数，便于 UT 覆盖边界。"""
    s = get_settings()
    whitelist = s.AUDIO_MIME_WHITELIST if kind == "audio" else s.IMAGE_MIME_WHITELIST
    if content_type not in whitelist:
        raise DomainError(422, "MEDIA_INVALID", "这种格式暂时收不下")
    limit = s.AUDIO_MAX_BYTES if kind == "audio" else s.IMAGE_MAX_BYTES
    if size_bytes > limit:
        raise DomainError(422, "MEDIA_INVALID", "这个文件有点大")


def object_key_for(owner_id: UUID, media_id: UUID, kind: str, content_type: str) -> str:
    ext = {
        "audio/webm": "webm",
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(content_type, "bin")
    return f"{owner_id}/{kind}/{media_id}.{ext}"


async def create_upload_url(
    session: AsyncSession, owner_id: UUID, *, kind: str, content_type: str, size_bytes: int
) -> tuple[Media, str, int]:
    """S02 Step 3 → Step 4。有效期 10 分钟，过期由 EX-5.1 处理。"""
    validate_upload_request(kind, content_type, size_bytes)
    media_id = uuid.uuid4()
    key = object_key_for(owner_id, media_id, kind, content_type)
    media = Media(
        id=media_id,
        owner_id=owner_id,
        kind=kind,
        object_key=key,
        content_type=content_type,
        size_bytes=size_bytes,
        status="pending",
    )
    session.add(media)
    await session.flush()
    url, ttl = get_storage().presign_put(key, content_type, size_bytes)
    return media, url, ttl


async def complete_upload(session: AsyncSession, owner_id: UUID, media_id: UUID) -> Media:
    """S02 Step 7 → Step 11。校验不通过时删对象并置 rejected（EX-8.1）。"""
    media = await session.get(Media, media_id)
    if media is None or media.owner_id != owner_id:
        raise DomainError(404, "MEDIA_NOT_FOUND", "找不到这个文件")
    storage = get_storage()
    meta = storage.head(media.object_key)
    s = get_settings()
    limit = s.AUDIO_MAX_BYTES if media.kind == "audio" else s.IMAGE_MAX_BYTES
    whitelist = s.AUDIO_MIME_WHITELIST if media.kind == "audio" else s.IMAGE_MIME_WHITELIST
    if meta is None or meta.size_bytes > limit or meta.content_type not in whitelist:
        storage.delete_many([media.object_key])
        media.status = "rejected"
        media.updated_at = clock.now()
        raise DomainError(422, "MEDIA_INVALID", "这个文件没能收下")
    media.status = "ready"
    media.size_bytes = meta.size_bytes
    media.updated_at = clock.now()
    return media


async def transcribe_wish_audio(
    session: AsyncSession, wish_id: UUID, owner_id: UUID
) -> tuple[Wish, str | None]:
    """S02 Step 15 → Step 17。返回 (wish, degraded_reason)。

    原始音频永远保留，因此本函数可被重复调用（EX-15.1 的「再读一次这段话」）。
    """
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.audio_media_id is None:
        raise DomainError(409, "NO_AUDIO_ATTACHED", "这件事没有关联语音")
    media = await session.get(Media, wish.audio_media_id)
    if media is None:
        raise DomainError(409, "NO_AUDIO_ATTACHED", "这段语音已经不在了")

    audio = b""
    storage = get_storage()
    reader = getattr(storage, "read", None)
    if callable(reader):
        audio = reader(media.object_key) or b""
    result = await get_asr_provider().transcribe(audio, media.object_key.rsplit("/", 1)[-1])
    if not result.ok:
        wish.degraded_reason = result.reason
        wish.title_enc = "一段还没被读懂的话"
        await _enqueue_agent_job(session, owner_id, wish.id, "transcription")
        return wish, result.reason
    wish.original_text_enc = result.text
    wish.title_enc = _fallback_title(result.text or "")
    wish.degraded_reason = None
    wish.updated_at = clock.now()
    return wish, None


async def cleanup_orphan_media(session: AsyncSession, owner_id: UUID) -> int:
    """S02 EX-13.1：超过 24 小时未被任何愿望或记忆页引用的媒体。

    返回清理条数。不产生任何用户可见通知，因此不占用提醒周预算。
    """
    cutoff = clock.now() - timedelta(hours=get_settings().ORPHAN_MEDIA_TTL_HOURS)
    referenced = select(Wish.audio_media_id).where(
        Wish.owner_id == owner_id, Wish.audio_media_id.is_not(None)
    )
    photo_refs = select(WishPhoto.media_id).join(Wish, Wish.id == WishPhoto.wish_id).where(
        Wish.owner_id == owner_id
    )
    rows = (
        await session.scalars(
            select(Media).where(
                Media.owner_id == owner_id,
                Media.created_at < cutoff,
                Media.status != "rejected",
                Media.id.not_in(referenced),
                Media.id.not_in(photo_refs),
            )
        )
    ).all()
    if not rows:
        return 0
    failed = set(get_storage().delete_many([m.object_key for m in rows]))
    for key in failed:
        # 与 EX-28.1 同一原则：删不掉的 key 转入清理队列（下方 re-export 的 app.tidy 实现），
        # 而不是就地丢弃后再也找不回来
        await register_orphan_object(session, key, "unreferenced")
    for m in rows:
        await session.delete(m)
    return len(rows)



# ------------------------------------------------------------ S04 / S05 re-export
# 浏览与整理实现在 app.tidy、步骤 / 对话 / 详情装配实现在 app.steps，
# 这里统一暴露，保持 api.py 与测试的导入路径不变。
from app.tidy import (  # noqa: E402
    ALLOWED_STATES,
    Cursor,
    amend_wish,
    delete_wish_permanently,
    let_go_wish,
    recall_wish,
    list_wishes_page,
    register_orphan_object,
    retry_orphan_objects,
)
from app.steps import (  # noqa: E402
    MAX_REJECTED_BEFORE_FALLBACK,
    back_to_brewing,
    detail_of,
    mark_step_done,
    request_next_step,
    send_message,
)
from app.memories import (  # noqa: E402
    MAX_MEMORY_PHOTOS,
    MemoryCursor,
    get_memory,
    list_memories,
    mark_wish_happened,
    memory_photo_ids,
    publish_memory,
    redraft_memory,
    run_memory_draft_jobs,
    update_memory,
)


async def to_memory_out(session: AsyncSession, memory: Memory) -> MemoryOut:
    """记忆页 → memories.yaml 的 Memory schema。cover 取第一张照片，没有则为 null。"""
    photos = await memory_photo_ids(session, memory.id)
    return MemoryOut(
        id=memory.id,
        wish_id=memory.wish_id,
        title=memory.title_enc,
        happened_from=memory.happened_from,
        happened_to=memory.happened_to,
        cover_media_id=photos[0] if photos else None,
        status=memory.status,
        cause=memory.cause_enc,
        process=memory.process_enc,
        mood=memory.mood,
        last_line=memory.last_line_enc,
        photo_media_ids=photos,
        voice_media_id=memory.voice_media_id,
        note_before_seeded=memory.note_before_seeded,
        edited_fields=list(memory.edited_fields or []),
        published_at=memory.published_at,
        created_at=memory.created_at,
    )


async def to_memory_card(session: AsyncSession, memory: Memory) -> MemoryCard:
    photos = await memory_photo_ids(session, memory.id)
    return MemoryCard(
        id=memory.id,
        wish_id=memory.wish_id,
        title=memory.title_enc,
        happened_from=memory.happened_from,
        happened_to=memory.happened_to,
        cover_media_id=photos[0] if photos else None,
        status=memory.status,
    )

