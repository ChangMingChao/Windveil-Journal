"""调度进程：每 5 分钟扫一轮到期时机。

S03 Step 9 → Step 17 的完整实现。四条约束都在这里：

  1. 单活：SQLite 没有咨询锁，改用排他文件锁（架构 5.2）。抢不到即静默退出，
     不记 error 日志——这是预期状态而非故障（EX-9.1）。
  2. 排序键是 timing_set_at 升序：周预算不够时被顺延的是用户最近才随手设的
     那些，而不是他半年前就认真定下的那件事（Step 11 说明）。
  3. 周预算 3 条，超额标记 deferred_to_next_week 且不发任何通知（EX-14.1）；
     绝不产生合并式提醒。
  4. 投递失败不消耗周预算（EX-16.2）。
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import clock
from app.config import get_settings
from app.crypto import decrypt_text
from app.db import owner_guard_bypass, session_scope
from app.models import (
    PushSubscription,
    ReminderOutbox,
    ReminderWeeklyCounter,
    SchedulerHeartbeat,
    User,
    Wish,
)
from app.notify import (
    get_email_sender,
    get_push_sender,
    render_reminder,
    render_stale_care,
)
from app.services import timing_of
from app.timing import week_start

logger = logging.getLogger("app.scheduler")


@dataclass
class TickResult:
    scanned: int = 0
    enqueued: int = 0
    deferred: int = 0
    delivered: int = 0
    failed: int = 0
    expired_proposals: int = 0
    digest_updated: int = 0
class FileLock:
    """排他文件锁。SQLite 无咨询锁，用它保证同机单活（EX-9.1）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    def acquire(self) -> bool:
        try:
            self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        os.write(self._fd, str(os.getpid()).encode())
        return True

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._path.unlink(missing_ok=True)


async def _weekly_delivered(session: AsyncSession, owner_id: UUID, wk: str) -> int:
    row = await session.get(ReminderWeeklyCounter, (owner_id, wk))
    return row.delivered_count if row else 0


async def _bump_weekly(session: AsyncSession, owner_id: UUID, wk: str) -> None:
    stmt = (
        sqlite_insert(ReminderWeeklyCounter)
        .values(owner_id=owner_id, week_start=wk, delivered_count=1, updated_at=clock.now())
        .on_conflict_do_update(
            index_elements=["owner_id", "week_start"],
            set_={
                "delivered_count": ReminderWeeklyCounter.delivered_count + 1,
                "updated_at": clock.now(),
            },
        )
    )
    await session.execute(stmt)


async def _enqueue(
    session: AsyncSession, wish: Wish, kind: str, occurrence: str, body: str
) -> bool:
    """写入 outbox。唯一索引拦住重复扫描（EX-14.2），返回是否新增。"""
    stmt = (
        sqlite_insert(ReminderOutbox)
        .values(
            id=uuid.uuid4(),
            owner_id=wish.owner_id,
            wish_id=wish.id,
            kind=kind,
            timing_occurrence=occurrence,
            body_enc=body,
            status="pending",
            attempts=0,
            next_attempt_at=clock.now(),
            created_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=["wish_id", "kind", "timing_occurrence"])
    )
    result = await session.execute(stmt)
    return bool(result.rowcount)


async def _deliver_one(session: AsyncSession, row: ReminderOutbox, result: TickResult) -> None:
    """Step 15 → Step 17：push 优先、邮件兜底，一次时机只送 1 条。

    S10 D2 增补：投递前读取用户的最新通道开关——
      push 关 + email 开 → 直接走邮件（不对已关闭通道做无谓调用）；
      全关 → 跳过该记录：不投递、不计失败、不改退避、不累加统计，
      pending 保持，用户重开任一通道后下一轮自然恢复（EX-D2.1）。
    """
    s = get_settings()
    user_row = await session.get(User, row.owner_id)
    push_on = user_row is not None and user_row.push_enabled
    email_on = user_row is not None and user_row.email_enabled
    if not push_on and not email_on:
        result.skipped_channels = getattr(result, "skipped_channels", 0) + 1
        return
    body = row.body_enc
    sub = None
    if push_on:
        sub = await session.scalar(
            select(PushSubscription).where(PushSubscription.owner_id == row.owner_id).limit(1)
        )
    channel: str | None = None
    error: str | None = None

    if push_on and sub is not None:
        try:
            await get_push_sender().send(
                endpoint=sub.endpoint, p256dh=sub.p256dh, auth=sub.auth_secret, body=body
            )
            channel = "push"
        except Exception as exc:  # noqa: BLE001 —— 含 410 订阅失效（EX-16.1）
            error = type(exc).__name__
            await session.delete(sub)

    if channel is None:
        if user_row is not None and user_row.email and email_on:
            try:
                await get_email_sender().send(
                    to=user_row.email, subject="你说过的那件事", body=body
                )
                channel = "email"
            except Exception as exc:  # noqa: BLE001
                error = type(exc).__name__
        elif sub is None:
            # 既无 push 订阅也无邮箱：无从投递，直接标记失败并保留额度
            error = "NO_CHANNEL_AVAILABLE"

    if channel is not None:
        row.status = "delivered"
        row.channel = channel
        row.delivered_at = clock.now()
        await _bump_weekly(session, row.owner_id, week_start(clock.now(), _tz_of(session, row)))
        result.delivered += 1
        return

    # 两条通道都失败：不消耗周预算（EX-16.2）
    row.attempts += 1
    row.last_error_code = error
    if row.attempts >= s.REMINDER_MAX_ATTEMPTS:
        row.status = "failed"
        result.failed += 1
    else:
        backoff = s.REMINDER_BACKOFF_SECONDS[min(row.attempts - 1, len(s.REMINDER_BACKOFF_SECONDS) - 1)]
        row.next_attempt_at = clock.now() + timedelta(seconds=backoff)


_TZ_CACHE: dict[UUID, str] = {}


def _tz_of(session: AsyncSession, row: ReminderOutbox) -> str:
    del session
    return _TZ_CACHE.get(row.owner_id, "Asia/Shanghai")


async def run_tick() -> TickResult:
    """执行一轮扫描。测试与 smoke 通过 POST /api/test/scheduler/tick 调用。"""
    s = get_settings()
    result = TickResult()
    lock = FileLock(Path(s.scheduler_lock_path))
    if not lock.acquire():
        logger.info("scheduler_lock_busy")  # 预期状态，不是 error
        return result
    try:
        now = clock.now()
        async with session_scope() as session:
            with owner_guard_bypass():  # Scheduler 天然跨 owner 扫描
                due = list(
                    (
                        await session.scalars(
                            select(Wish)
                            .where(
                                Wish.trigger_kind == "time",
                                Wish.next_trigger_at.is_not(None),
                                Wish.next_trigger_at <= now,
                                Wish.state.in_(("seeded", "brewing")),
                            )
                            .order_by(Wish.timing_set_at)
                        )
                    ).all()
                )
                result.scanned = len(due)
                for wish in due:
                    user = await session.get(User, wish.owner_id)
                    tz = user.timezone if user else "Asia/Shanghai"
                    _TZ_CACHE[wish.owner_id] = tz
                    wk = week_start(now, tz).isoformat()
                    used = await _weekly_delivered(session, wish.owner_id, wk)
                    pending_same_week = await session.scalar(
                        select(ReminderOutbox)
                        .where(
                            ReminderOutbox.owner_id == wish.owner_id,
                            ReminderOutbox.status == "pending",
                        )
                        .limit(1)
                    )
                    del pending_same_week
                    if used >= s.REMINDER_WEEKLY_BUDGET:
                        wish.soft_deferred = True
                        await _enqueue(
                            session,
                            wish,
                            "timing",
                            wish.timing_occurrence or "unknown",
                            render_reminder(
                                seeded_at=wish.seeded_at,
                                original_text=wish.original_text_enc or wish.title_enc,
                                timing_label=timing_of(wish).label,
                            ),
                        )
                        await session.execute(
                            update(ReminderOutbox)
                            .where(
                                ReminderOutbox.wish_id == wish.id,
                                ReminderOutbox.kind == "timing",
                                ReminderOutbox.timing_occurrence
                                == (wish.timing_occurrence or "unknown"),
                                ReminderOutbox.status == "pending",
                            )
                            .values(status="deferred_to_next_week", next_attempt_at=None)
                        )
                        result.deferred += 1
                        continue

                    body = render_reminder(
                        seeded_at=wish.seeded_at,
                        original_text=wish.original_text_enc or wish.title_enc,
                        timing_label=timing_of(wish).label,
                    )
                    if await _enqueue(
                        session, wish, "timing", wish.timing_occurrence or "unknown", body
                    ):
                        result.enqueued += 1

                # S04 EX-15.2：going 且 60 天无动作 → 一条关心，只发一次
                stale_cut = now - timedelta(days=s.STALE_CARE_DAYS)
                stale = list(
                    (
                        await session.scalars(
                            select(Wish).where(
                                Wish.state == "going",
                                Wish.stale_notified_at.is_(None),
                                Wish.last_activity_at <= stale_cut,
                            )
                        )
                    ).all()
                )
                for wish in stale:
                    result.scanned += 1
                    body = render_stale_care(wish.original_text_enc or wish.title_enc)
                    if await _enqueue(
                        session, wish, "stale_care", f"stale:{now.date().isoformat()}", body
                    ):
                        wish.stale_notified_at = now
                        result.enqueued += 1

                pending = list(
                    (
                        await session.scalars(
                            select(ReminderOutbox).where(ReminderOutbox.status == "pending")
                        )
                    ).all()
                )
                for row in pending:
                    if row.next_attempt_at and row.next_attempt_at > now:
                        continue
                    wk = week_start(now, _tz_of(session, row)).isoformat()
                    if await _weekly_delivered(session, row.owner_id, wk) >= s.REMINDER_WEEKLY_BUDGET:
                        # 周预算在投递时刻才真正见分晓：扫描阶段计数还没被本轮的
                        # 成功投递抬高，所以顺延判定必须放在这里（EX-14.1）。
                        row.status = "deferred_to_next_week"
                        row.next_attempt_at = None
                        wish = await session.get(Wish, row.wish_id)
                        if wish is not None:
                            wish.soft_deferred = True
                        result.deferred += 1
                        continue
                    await _deliver_one(session, row, result)

                # 低频任务 1：提议过期扫描（S03 分支第 3 层，S08 增补）
                from app.proposals import expire_stale_proposals
                result.expired_proposals = await expire_stale_proposals(session)

                # 低频任务 2：偏好摘要生成（S08 摘要支线 D1–D4，每日一次）
                result.digest_updated = await refresh_preference_digests(session)

                await _beat(session)
        return result
    finally:
        lock.release()


INSTANCE_ID = f"{os.uname().nodename if hasattr(os, 'uname') else 'host'}-{os.getpid()}"


DIGEST_INTERVAL = timedelta(hours=24)  # 需求 5.4 第 5 条的当前假设：每日低频生成


async def refresh_preference_digests(session: AsyncSession) -> int:
    """S08 摘要支线 D1–D4：为偏好有更新（超过间隔）的用户重新生成「它的理解」。

    LLM 降级时保持既有 digest 不变、不重试队列（EX-D2.1）；没有 entry 行的用户跳过。
    """
    from app.agent import get_llm_provider
    from app.models import UserPreference
    from app.preferences import upsert_digest

    provider = get_llm_provider()
    if provider is None:
        return 0
    now = clock.now()
    updated = 0
    owners = (
        (
            await session.execute(
                select(UserPreference.owner_id)
                .where(
                    UserPreference.kind == "entry",
                    UserPreference.revoked_at.is_(None),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    for owner_id in owners:
        rows = (
            (
                await session.execute(
                    select(UserPreference).where(
                        UserPreference.owner_id == owner_id,
                        UserPreference.kind == "digest",
                    )
                )
            )
            .scalars()
            .all()
        )
        digest = rows[0] if rows else None
        if digest is not None and digest.updated_at and now - digest.updated_at < DIGEST_INTERVAL:
            continue
        entries = (
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
        # owner_guard：digest / entry 行的读写都带 owner_id；此处在 bypass 上下文内，
        # 显式按 owner_id 过滤以保持隔离语义
        texts = [f"{r.pref_key}: {r.value_enc}" for r in entries]
        result = await provider.summarize_preferences(entries=texts)
        if result is None:
            continue  # EX-D2.1：保持旧值，下一周期自然重试
        await upsert_digest(owner_id, result.summary)
        updated += 1
    return updated


async def _beat(session: AsyncSession) -> None:
    """每轮扫描结束刷新心跳（部署方案 §7-2、SMOKE-core-02）。

    心跳写在**扫描结束**而不是开始：一个卡在投递里出不来的 tick 不该被算作活着。
    """
    await session.execute(
        update(SchedulerHeartbeat)
        .where(SchedulerHeartbeat.id == 1)
        .values(instance_id=INSTANCE_ID, last_beat_at=clock.now())
    )


async def heartbeat_age_seconds() -> float | None:
    """健康检查用。返回 None 表示心跳行不存在（迁移未跑）。"""
    async with session_scope() as session:
        row = await session.get(SchedulerHeartbeat, 1)
        if row is None:
            return None
        return max(0.0, (clock.now() - row.last_beat_at).total_seconds())


def decrypt_body(blob: bytes) -> str:  # pragma: no cover —— 后门读取用
    return decrypt_text(blob)


async def _run_forever() -> None:  # pragma: no cover —— 长驻进程入口
    import asyncio

    interval = get_settings().SCHEDULER_INTERVAL_SECONDS
    logger.info("scheduler_started", extra={"interval_seconds": interval, "instance": INSTANCE_ID})
    while True:
        try:
            result = await run_tick()
            logger.info("scheduler_tick", extra=vars(result))
        except Exception:  # noqa: BLE001 —— 一轮失败不该让长驻进程退出
            logger.exception("scheduler_tick_failed")
        await asyncio.sleep(interval)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover —— CLI 入口
    """`python -m app.scheduler [--once]`。

    `--once` 跑一轮就退出，是部署方案里 production 触发一轮扫描的方式
    （`docker compose run --rm scheduler --once`，SMOKE-core-12）——
    生产环境没有 `/api/test/*` 后门可用，这是唯一的外部触发口。
    """
    import asyncio
    import json as _json
    import sys

    # 长驻进程必须自己配日志。api 那侧在 app.main 里装配，
    # 而 `python -m app.scheduler` 根本不会导入它——不配的话 info 级全部丢掉，
    # 一个每轮都失败的调度进程在日志里会安静得像什么都没发生。
    from app.obs import configure_logging

    configure_logging()

    args = sys.argv[1:] if argv is None else argv
    once = "--once" in args
    if once:
        result = asyncio.run(run_tick())
        print(_json.dumps(vars(result), ensure_ascii=False))
        return 0
    asyncio.run(_run_forever())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
