"""LLM 时机建议的四层链路（S03 时机提议分支，preferences-availability-timing）。

第 1 层 模型提议：LLM 只产出 TimingProposalDraft（4 种时间类），Pydantic 校验失败等同 None。
第 2 层 规则校验：复用 set_timing 的 plan_timing 全部校验；free_weekend 额外要求可用时段。
        校验结果写入 validation_result；invalid 的提议照常入库但立即 expired（保留审计）。
第 3 层 用户确认：confirm 空 body，事务内复用 set_timing 写 wishes；reject 不写任何 wishes 字段。
第 4 层 调度执行：Scheduler 只扫描 wishes 的合法时机，永不读取本模块的表（架构 5.4）。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import TimingProposalDraft, get_llm_provider
from app.clock import clock
from app.models import (
    PROPOSAL_TIMING_TYPES,
    AvailabilityWindow,
    TimingProposal,
    UserPreference,
    User,
    Wish,
)
from app.services import DomainError

# 提议有效期。需求 5.4 第 6 条待确认项的当前假设：7 天未确认自动失效
PROPOSAL_TTL = timedelta(days=7)
PROPOSAL_NOT_FOUND = (404, "WISH_NOT_FOUND", "找不到这件事")
PROPOSAL_EXPIRED = (409, "PROPOSAL_EXPIRED", "这条建议已经不在等待里了")
PROPOSAL_NOT_CONFIRMABLE = (409, "PROPOSAL_NOT_CONFIRMABLE", "这条建议先不成立")
CONFIRM_BODY_FORBIDDEN = (422, "PROPOSAL_CONFIRM_BODY_FORBIDDEN", "确认就好，不用再填时间")


def _payload_of(draft: TimingProposalDraft) -> dict[str, Any]:
    """把模型草稿映射为 set_timing 的 payload（TimingInput 形态）。"""
    t = draft.timing_type
    if t == "season":
        return {"type": "season", "season": draft.timing_value}
    if t == "month_day":
        return {"type": "month_day", "month_day": draft.timing_value}
    if t == "after_months":
        try:
            months = int(draft.timing_value) if draft.timing_value else 0
        except ValueError:
            months = 0
        return {"type": "after_months", "after_months": months}
    return {"type": "free_weekend"}


def _validate_draft_payload(
    payload: dict[str, Any], has_availability: bool, timezone: str
) -> dict[str, Any]:
    """第 2 层：与 set_timing 完全相同的确定性校验，但不写库。

    返回 {"valid": bool, "reason_code": str | None}。校验失败的提议照常入库
    但立即 expired——保留「为什么这条建议没成立」的审计（S03 分支 P8）。
    """
    from app.timing import TimingError, plan_timing

    if payload["type"] == "free_weekend" and not has_availability:
        return {"valid": False, "reason_code": "PROPOSAL_NO_AVAILABILITY"}
    try:
        plan_timing(
            timing_type=payload.get("type", ""),
            timezone=timezone,
            season=payload.get("season"),
            month_day=payload.get("month_day"),
            after_months=payload.get("after_months"),
        )
    except (TimingError, ValueError) as exc:
        # 类型不对或日期不存在：全部归为 TIMING_INVALID（与 EX-4.2 同码）
        _ = exc
        return {"valid": False, "reason_code": "TIMING_INVALID"}
    return {"valid": True, "reason_code": None}


def _to_out(row: TimingProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "wish_id": row.wish_id,
        "status": row.status,
        "timing_type": row.timing_type,
        "timing_value": row.timing_value,
        "proposed_trigger_at": row.proposed_trigger_at,
        "reason": row.reason_enc,
        "confidence": row.confidence,
        "evidence": row.evidence or [],
        "validation": row.validation_result or {"valid": True, "reason_code": None},
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "decided_at": row.decided_at,
    }


async def _bounded_context(session: AsyncSession, owner_id: uuid.UUID, wish: Wish) -> tuple[str, list[dict[str, Any]]]:
    """组装有界上下文：偏好摘要 1 份 + 命中的偏好/时段明细 + 愿望时间线摘要。

    不注入完整对话历史（隐私边界，架构 5.3 增补）。evidence 由服务端组装——
    依据条目 ID 来自这里检索到的内容，模型不参与引用。
    """
    evidence: list[dict[str, Any]] = []
    lines: list[str] = []

    digest = (
        await session.execute(
            select(UserPreference).where(
                UserPreference.owner_id == owner_id,
                UserPreference.kind == "digest",
            )
        )
    ).scalars().first()
    if digest is not None and digest.revoked_at is None:
        lines.append(f"它的理解：{digest.value_enc}")
        evidence.append({"kind": "preference", "id": str(digest.id)})

    prefs = (
        (
            await session.execute(
                select(UserPreference).where(
                    UserPreference.owner_id == owner_id,
                    UserPreference.kind == "entry",
                    UserPreference.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for p in prefs[:5]:  # 有界：至多 5 条明细
        lines.append(f"偏好（{'你说过的' if p.source == 'declared' else '我猜的'}）：{p.value_enc}")
        evidence.append({"kind": "preference", "id": str(p.id)})

    windows = (
        (
            await session.execute(
                select(AvailabilityWindow).where(
                    AvailabilityWindow.owner_id == owner_id
                )
            )
        )
        .scalars()
        .all()
    )
    names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    for w in windows[:7]:
        lines.append(f"可用时段：{names[w.weekday]} {w.start_minute // 60:02d}:{w.start_minute % 60:02d} 起")
        evidence.append({"kind": "availability", "id": str(w.id)})

    # 节假日事实（holiday-aware-timing）：临近节假日的日期区间与调休提示。
    # 数据来自内置文件，无网络请求；缺年份时 upcoming_facts 为空、不加 calendar 条目
    # ——与「Agent 不可用也不阻塞」同一降级哲学（EX-P.6）。
    from app.holidays import upcoming_facts

    facts = upcoming_facts(clock.now().date())
    for fact in facts[:3]:
        lines.append(f"节假日：{fact}")
    if facts:
        evidence.append({"kind": "calendar", "id": f"holidays-{clock.now().year}"})

    lines.append(f"这件事本身：{wish.original_text_enc or wish.title_enc}")
    return "\n".join(lines), evidence


async def create_proposal(session: AsyncSession, owner_id: uuid.UUID, wish_id: uuid.UUID) -> dict[str, Any] | None:
    """POST /wishes/{id}/timing-proposals。返回提议 dict；LLM 不可用时返回 None（EX-P.1）。"""
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(*PROPOSAL_NOT_FOUND)
    if wish.state == "happened":
        raise DomainError(409, "STATE_TRANSITION_NOT_ALLOWED", "它已经发生过了")

    context, evidence = await _bounded_context(session, owner_id, wish)
    provider = get_llm_provider()
    if provider is None:
        return None
    draft = await provider.propose_timing(
        wish_text=wish.original_text_enc or wish.title_enc, context=context
    )
    if draft is None:
        return None

    now = clock.now()
    # 第 1 层收尾：同事务终结旧 pending（部分唯一索引兜底），再插入新提议
    for old in (
        (
            await session.execute(
                select(TimingProposal).where(
                    TimingProposal.wish_id == wish_id,
                    TimingProposal.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    ):
        old.status = "expired"
        old.updated_at = now

    has_availability = any(e["kind"] == "availability" for e in evidence)
    user = await session.get(User, owner_id)
    tz = user.timezone if user else "Asia/Shanghai"
    validation = _validate_draft_payload(_payload_of(draft), has_availability, tz)
    row = TimingProposal(
        owner_id=owner_id,
        wish_id=wish_id,
        status="pending",
        timing_type=draft.timing_type,
        timing_value=draft.timing_value,
        proposed_trigger_at=None,
        reason_enc=draft.reason,
        confidence=draft.confidence,
        evidence=evidence,
        validation_result=validation,
        expires_at=now + PROPOSAL_TTL,
        created_at=now,
        updated_at=now,
    )
    if not validation["valid"]:
        row.status = "expired"
    session.add(row)
    await session.flush()
    return _to_out(row)


async def list_proposals(session: AsyncSession, owner_id: uuid.UUID, wish_id: uuid.UUID) -> list[dict[str, Any]]:
    """GET /wishes/{id}/timing-proposals。含全部决策与过期记录，按创建倒序。"""
    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != owner_id:
        raise DomainError(*PROPOSAL_NOT_FOUND)
    rows = (
        (
            await session.execute(
                select(TimingProposal)
                .where(TimingProposal.owner_id == owner_id, TimingProposal.wish_id == wish_id)
                .order_by(TimingProposal.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_out(r) for r in rows]


async def confirm_proposal(
    session: AsyncSession, owner_id: uuid.UUID, wish_id: uuid.UUID, proposal_id: uuid.UUID
) -> tuple[Wish, TimingProposal]:
    """POST …/confirm。第 3 层：唯一生效通道。body 非空在端点层拦截（EX-P.4）。"""
    from app.services import set_timing

    proposal = await session.get(TimingProposal, proposal_id)
    if proposal is None or proposal.owner_id != owner_id or proposal.wish_id != wish_id:
        raise DomainError(*PROPOSAL_NOT_FOUND)
    if proposal.status != "pending":
        raise DomainError(*PROPOSAL_EXPIRED)
    validation = proposal.validation_result or {}
    if not validation.get("valid", False):
        raise DomainError(*PROPOSAL_NOT_CONFIRMABLE)
    wish = await set_timing(session, owner_id, wish_id, _payload_of(
        TimingProposalDraft(
            timing_type=proposal.timing_type,
            timing_value=proposal.timing_value,
            reason=None,
            confidence=proposal.confidence,
        )
    ))
    proposal.status = "confirmed"
    proposal.decided_at = clock.now()
    proposal.updated_at = clock.now()
    return wish, proposal


async def reject_proposal(
    session: AsyncSession, owner_id: uuid.UUID, wish_id: uuid.UUID, proposal_id: uuid.UUID
) -> TimingProposal:
    """POST …/reject（EX-P.3）。不写 wishes 任何字段；不自动生成新建议。"""
    proposal = await session.get(TimingProposal, proposal_id)
    if proposal is None or proposal.owner_id != owner_id or proposal.wish_id != wish_id:
        raise DomainError(*PROPOSAL_NOT_FOUND)
    if proposal.status != "pending":
        raise DomainError(*PROPOSAL_EXPIRED)
    proposal.status = "rejected"
    proposal.decided_at = clock.now()
    proposal.updated_at = clock.now()
    return proposal


async def pending_proposal_of(session: AsyncSession, wish_id: uuid.UUID) -> TimingProposal | None:
    """详情页的「待确认」建议卡。已决策/过期的建议不再出现在 WishDetail。"""
    return await session.scalar(
        select(TimingProposal).where(
            TimingProposal.wish_id == wish_id, TimingProposal.status == "pending"
        )
    )


async def expire_stale_proposals(session: AsyncSession) -> int:
    """Scheduler 低频任务：把超时未确认的提议置 expired（第 3 层的过期路径）。"""
    now = clock.now()
    rows = (
        (
            await session.execute(
                select(TimingProposal).where(
                    TimingProposal.status == "pending",
                    TimingProposal.expires_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = "expired"
        row.updated_at = now
    return len(rows)

