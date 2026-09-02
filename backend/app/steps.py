"""S04 业务层：最小下一步、乐观锁、对话意图、详情装配。

从 services.py 拆出是为了避免单文件过长；导入侧统一从 app.services 暴露
（services.py 末尾 re-export），因此 api.py 的 import 路径不变。
"""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import fallback_step, get_llm_provider
from app.clock import clock
from app.models import Wish, WishAmendment, WishMessage, WishStep
from app.schemas import WishDetail

MAX_REJECTED_BEFORE_FALLBACK = 3


async def _rejected_texts(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> list[str]:
    rows = await session.scalars(
        select(WishStep.text_enc).where(
            WishStep.owner_id == owner_id,
            WishStep.wish_id == wish_id,
            WishStep.status == "rejected",
        )
    )
    return list(rows.all())


async def request_next_step(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, rejected_step_id: UUID | None = None
) -> tuple[WishStep | None, bool]:
    """S04 Step 5 → Step 11。返回 (step, degraded)。

    三条约束都在这里：一次只给 1 个（部分唯一索引兜底）、服务端校验模型自报的
    合规字段（EX-8.2）、连续拒绝到上限后不再调用 LLM（EX-13.2）。
    """
    from app.services import DomainError, _enqueue_agent_job

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.state not in ("wind", "going"):
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "它还没到开始的时候")

    if rejected_step_id is not None:
        step = await session.get(WishStep, rejected_step_id)
        if step is None or step.wish_id != wish_id:
            raise DomainError(404, "STEP_NOT_FOUND", "找不到这个步骤")
        step.status = "rejected"
        await session.flush()
    else:
        current = await session.scalar(
            select(WishStep).where(
                WishStep.owner_id == owner_id,
                WishStep.wish_id == wish_id,
                WishStep.status == "proposed",
            )
        )
        if current is not None:
            return current, False

    rejected = await _rejected_texts(session, owner_id, wish_id)
    feeling = (wish.understanding or {}).get("feeling")
    original = wish.original_text_enc or wish.title_enc

    if len(rejected) >= MAX_REJECTED_BEFORE_FALLBACK:
        # EX-13.2：不再调用 LLM，直接给最轻一档，避免反复点击放大成本
        suggestion, source = fallback_step(feeling), "fallback"
    else:
        suggestion = await get_llm_provider().next_step(
            original_text=original, feeling=feeling, rejected=rejected
        )
        if suggestion is None:
            # EX-8.1：状态保持 wind 不回退，入队待补
            await _enqueue_agent_job(session, owner_id, wish_id, "next_step")
            return None, True
        if suggestion.compliant:
            source = "llm"
        else:
            # EX-8.2：模型自报违规 → 重试一次；仍违规则用兜底
            retry = await get_llm_provider().next_step(
                original_text=original, feeling=feeling, rejected=[*rejected, suggestion.text]
            )
            if retry is not None and retry.compliant:
                suggestion, source = retry, "llm"
            else:
                suggestion, source = fallback_step(feeling), "fallback"

    step = WishStep(
        id=uuid.uuid4(),
        wish_id=wish_id,
        owner_id=owner_id,
        text_enc=suggestion.text,
        status="proposed",
        est_minutes=suggestion.est_minutes,
        involves_cost=suggestion.involves_cost,
        involves_others=suggestion.involves_others,
        source=source,
    )
    session.add(step)
    wish.last_activity_at = clock.now()
    await session.flush()
    return step, False


async def mark_step_done(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, step_id: UUID, expected_version: int
) -> tuple[WishStep, Wish]:
    """S04 Step 14 → Step 17。乐观锁用 If-Match 承载（EX-15.1）。"""
    from app.services import DomainError

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.version != expected_version:
        raise DomainError(409, "STATE_CONFLICT", "这件事刚刚被另一处改过了")
    step = await session.get(WishStep, step_id)
    if step is None or step.wish_id != wish_id:
        raise DomainError(404, "STEP_NOT_FOUND", "找不到这个步骤")
    if step.status != "proposed":
        raise DomainError(409, "STATE_CONFLICT", "这一步已经处理过了")
    now = clock.now()
    step.status = "done"
    step.completed_at = now
    wish.state = "going"
    wish.last_activity_at = now
    wish.stale_notified_at = None  # 有新动作，停滞关心重新计时
    wish.version += 1
    return step, wish


async def back_to_brewing(session: AsyncSession, owner_id: UUID, wish_id: UUID) -> Wish:
    """S05.2 整理半屏第 3 项 / S04 EX-15.2 三选项之一。时间线保留。"""
    from app.services import DomainError

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")
    if wish.state != "going":
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "它现在不在进行中")
    wish.state = "brewing"
    wish.last_activity_at = clock.now()
    wish.version += 1
    return wish


async def send_message(
    session: AsyncSession, owner_id: UUID, wish_id: UUID, text: str
) -> tuple[str | None, str, Wish, bool]:
    """S04 EX-23.1。返回 (reply, intent, wish, degraded)。"""
    from app.services import DomainError, trigger_fatigue_signals

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(404, "WISH_NOT_FOUND", "找不到这件事")

    session.add(
        WishMessage(
            id=uuid.uuid4(), wish_id=wish_id, owner_id=owner_id, role="user", text_enc=text
        )
    )
    result = await get_llm_provider().classify_message(
        text=text, original_text=wish.original_text_enc or wish.title_enc
    )
    if result is None:
        wish.last_activity_at = clock.now()
        return None, "chat", wish, True

    if result.intent == "amend":
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
        if result.amended_title:
            wish.title_enc = result.amended_title
        if result.amended_conditions:
            data = dict(wish.understanding or {})
            conditions = dict(data.get("conditions") or {})
            conditions.update(result.amended_conditions)
            data["conditions"] = conditions
            wish.understanding = data
        # seeded_at 与 original_text_enc 永不改动（EX-23.1）
    elif result.intent == "fatigue":
        await trigger_fatigue_signals(session, owner_id)

    session.add(
        WishMessage(
            id=uuid.uuid4(),
            wish_id=wish_id,
            owner_id=owner_id,
            role="agent",
            text_enc=result.reply,
            intent=result.intent,
        )
    )
    wish.last_activity_at = clock.now()
    wish.version += 1
    return result.reply, result.intent, wish, False


async def detail_of(session: AsyncSession, wish: Wish) -> WishDetail:
    """装配 current_step / timeline / messages / amended_from（wishes.yaml）。"""
    from app.services import photo_ids_of, to_detail

    # sessionmaker 关掉了 autoflush，所以同一事务内刚写入的步骤 / 修订快照
    # 不会自动出现在后面的 SELECT 里——装配前显式 flush 一次。
    await session.flush()
    detail = to_detail(wish, await photo_ids_of(session, wish.id))
    current = await session.scalar(
        select(WishStep).where(
            WishStep.owner_id == wish.owner_id,
            WishStep.wish_id == wish.id,
            WishStep.status == "proposed",
        )
    )
    if current is not None:
        detail.current_step = {
            "id": str(current.id),
            "text": current.text_enc,
            "status": current.status,
            "est_minutes": current.est_minutes,
            "involves_cost": current.involves_cost,
            "involves_others": current.involves_others,
            "source": current.source,
            "completed_at": None,
        }
    done = list(
        (
            await session.scalars(
                select(WishStep)
                .where(
                    WishStep.owner_id == wish.owner_id,
                    WishStep.wish_id == wish.id,
                    WishStep.status == "done",
                )
                .order_by(WishStep.completed_at)
            )
        ).all()
    )
    detail.timeline = [
        {"id": str(s.id), "text": s.text_enc, "completed_at": s.completed_at.isoformat()}
        for s in done
        if s.completed_at
    ]
    msgs = list(
        (
            await session.scalars(
                select(WishMessage)
                .where(WishMessage.owner_id == wish.owner_id, WishMessage.wish_id == wish.id)
                .order_by(WishMessage.created_at)
            )
        ).all()
    )
    detail.messages = [
        {
            "id": str(m.id),
            "role": m.role,
            "text": m.text_enc,
            "intent": m.intent,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]
    first_amend = await session.scalar(
        select(WishAmendment)
        .where(WishAmendment.owner_id == wish.owner_id, WishAmendment.wish_id == wish.id)
        .order_by(WishAmendment.created_at)
        .limit(1)
    )
    if first_amend is not None:
        detail.amended_from = first_amend.prev_original_enc or first_amend.prev_title_enc
    return detail
