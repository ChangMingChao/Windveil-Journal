"""SQLAlchemy 模型。表名、列名、约束与 logos/resources/database/schema.sql 严格一致。

本批（Batch 1）覆盖 S01 所需的表：users、sessions、onboarding_answers、
media、wishes、wish_photos、pending_agent_jobs。其余表在后续批次加入。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.crypto import EncryptedText
from app.types import GUID, TZDateTime

WISH_STATES = ("seeded", "brewing", "wind", "going", "happened", "let_go")
TIMING_TYPES = ("season", "month_day", "after_months", "free_weekend", "when_tired", "none")
TRIGGER_KINDS = ("time", "signal", "none")
DEGRADED_REASONS = ("llm_failed", "asr_failed", "asr_empty")
MEDIA_KINDS = ("audio", "image")
MEDIA_STATUSES = ("pending", "ready", "rejected")
AGENT_JOB_KINDS = ("wish_understanding", "transcription", "next_step", "memory_draft")
# 6 个低饱和心情词，不使用 emoji（S06 memories.mood CHECK）
MOODS = ("relieved", "healed", "tearful", "calm", "proud", "unspeakable")
MEMORY_STATUSES = ("draft", "published")
# 可被 Scheduler 补草拟、也可被用户手动编辑的三段正文（S06 EX-7.1 的 edited_fields 取值）
MEMORY_DRAFTED_FIELDS = ("title", "cause", "process")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(GUID, primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    onboarded_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Shanghai")
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(email IS NULL AND password_hash IS NULL) "
            "OR (email IS NOT NULL AND password_hash IS NOT NULL)",
            name="users_email_password_together",
        ),
        CheckConstraint("is_anonymous = (email IS NULL)", name="users_anonymous_has_no_email"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )


class OnboardingAnswer(Base):
    __tablename__ = "onboarding_answers"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_key: Mapped[str] = mapped_column(Text, nullable=False)
    answer_enc: Mapped[str | None] = mapped_column(EncryptedText)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "question_key", name="onboarding_answers_unique_per_question"),
    )
class Media(Base):
    __tablename__ = "media"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    alt_text_enc: Mapped[str | None] = mapped_column(EncryptedText)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("kind IN ('audio', 'image')", name="media_kind_check"),
        CheckConstraint(
            "status IN ('pending', 'ready', 'rejected')", name="media_status_check"
        ),
        CheckConstraint(
            "size_bytes IS NULL "
            "OR (kind = 'audio' AND size_bytes <= 10485760) "
            "OR (kind = 'image' AND size_bytes <= 8388608)",
            name="media_size_within_limit",
        ),
    )


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title_enc: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    original_text_enc: Mapped[str | None] = mapped_column(EncryptedText)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    audio_media_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("media.id", ondelete="RESTRICT")
    )
    state: Mapped[str] = mapped_column(Text, nullable=False, default="seeded")
    understanding: Mapped[dict | None] = mapped_column(JSON)
    pending_question: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question_enc: Mapped[str | None] = mapped_column(EncryptedText)
    answer_enc: Mapped[str | None] = mapped_column(EncryptedText)
    timing_type: Mapped[str | None] = mapped_column(Text)
    timing_value: Mapped[str | None] = mapped_column(Text)
    trigger_kind: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    timing_set_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    next_trigger_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    timing_occurrence: Mapped[str | None] = mapped_column(Text)
    soft_deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    let_go_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    degraded_reason: Mapped[str | None] = mapped_column(Text)
    seeded_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    stale_notified_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("source IN ('text', 'voice')", name="wishes_source_check"),
        CheckConstraint(
            "state IN ('seeded','brewing','wind','going','happened','let_go')",
            name="wishes_state_check",
        ),
        CheckConstraint(
            "timing_type IS NULL OR timing_type IN "
            "('season','month_day','after_months','free_weekend','when_tired','none')",
            name="wishes_timing_type_check",
        ),
        CheckConstraint(
            "state = 'let_go' OR let_go_at IS NULL",
            name="wishes_let_go_timestamp_matches_state",
        ),
        CheckConstraint(
            "trigger_kind IN ('time','signal','none')", name="wishes_trigger_kind_check"
        ),
        CheckConstraint(
            "degraded_reason IS NULL OR degraded_reason IN "
            "('llm_failed','asr_failed','asr_empty')",
            name="wishes_degraded_reason_check",
        ),
        CheckConstraint(
            "source <> 'voice' OR audio_media_id IS NOT NULL",
            name="wishes_voice_requires_audio",
        ),
        CheckConstraint(
            "trigger_kind = 'time' OR next_trigger_at IS NULL",
            name="wishes_signal_and_none_have_no_trigger_time",
        ),
    )


class WishPhoto(Base):
    __tablename__ = "wish_photos"

    wish_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PendingAgentJob(Base):
    __tablename__ = "pending_agent_jobs"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    wish_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE")
    )
    memory_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    job_kind: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    last_error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "job_kind IN ('wish_understanding','transcription','next_step','memory_draft')",
            name="pending_agent_jobs_kind_check",
        ),
        CheckConstraint(
            "wish_id IS NOT NULL OR memory_id IS NOT NULL",
            name="pending_agent_jobs_has_target",
        ),
    )


class WishAmendment(Base):
    __tablename__ = "wish_amendments"

    id: Mapped[uuid.UUID] = _pk()
    wish_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    prev_title_enc: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    prev_original_enc: Mapped[str | None] = mapped_column(EncryptedText)
    prev_understanding: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )


class WishStep(Base):
    __tablename__ = "wish_steps"

    id: Mapped[uuid.UUID] = _pk()
    wish_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    text_enc: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    est_minutes: Mapped[int | None] = mapped_column(Integer)
    involves_cost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    involves_others: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'done', 'rejected')", name="wish_steps_status_check"
        ),
        CheckConstraint(
            "est_minutes IS NULL OR est_minutes <= 5", name="wish_steps_est_minutes_check"
        ),
        CheckConstraint("source IN ('llm', 'fallback')", name="wish_steps_source_check"),
        CheckConstraint(
            "(status = 'done' AND completed_at IS NOT NULL)"
            " OR (status <> 'done' AND completed_at IS NULL)",
            name="wish_steps_done_has_completed_at",
        ),
    )


class WishMessage(Base):
    __tablename__ = "wish_messages"

    id: Mapped[uuid.UUID] = _pk()
    wish_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    text_enc: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    intent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('user', 'agent')", name="wish_messages_role_check"),
        CheckConstraint(
            "intent IS NULL OR intent IN ('chat', 'amend', 'assist', 'fatigue')",
            name="wish_messages_intent_check",
        ),
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth_secret: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )


class ReminderOutbox(Base):
    __tablename__ = "reminder_outbox"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    wish_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    timing_occurrence: Mapped[str] = mapped_column(Text, nullable=False)
    body_enc: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    channel: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("kind IN ('timing', 'stale_care')", name="reminder_outbox_kind_check"),
        CheckConstraint(
            "status IN ('pending','delivered','failed','deferred_to_next_week')",
            name="reminder_outbox_status_check",
        ),
        CheckConstraint(
            "status <> 'delivered' OR (delivered_at IS NOT NULL AND channel IS NOT NULL)",
            name="reminder_outbox_delivered_has_channel",
        ),
        UniqueConstraint(
            "wish_id", "kind", "timing_occurrence", name="idx_reminder_outbox_once"
        ),
    )


class ReminderWeeklyCounter(Base):
    __tablename__ = "reminder_weekly_counters"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    week_start: Mapped[str] = mapped_column(Text, primary_key=True)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "delivered_count BETWEEN 0 AND 3", name="reminder_weekly_counters_budget_check"
        ),
    )


class Memory(Base):
    """记忆页。一个愿望最多一页（wish_id 唯一）。

    全部内容字段均可为空——「跳过全部补充内容直接发布」是明确的验收条件（S06 ST-S06-02），
    所以这里没有任何 NOT NULL 内容列，只有 title_enc 与 happened_from 是必需的。
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = _pk()
    wish_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title_enc: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    cause_enc: Mapped[str | None] = mapped_column(EncryptedText)
    process_enc: Mapped[str | None] = mapped_column(EncryptedText)
    mood: Mapped[str | None] = mapped_column(Text)
    last_line_enc: Mapped[str | None] = mapped_column(EncryptedText)
    voice_media_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("media.id", ondelete="SET NULL")
    )
    happened_from: Mapped[str] = mapped_column(Text, nullable=False)
    happened_to: Mapped[str | None] = mapped_column(Text)
    note_before_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edited_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "mood IS NULL OR mood IN "
            "('relieved','healed','tearful','calm','proud','unspeakable')",
            name="memories_mood_check",
        ),
        CheckConstraint("status IN ('draft', 'published')", name="memories_status_check"),
        CheckConstraint(
            "happened_to IS NULL OR happened_to >= happened_from",
            name="memories_range_ordered",
        ),
        CheckConstraint(
            "(status = 'published' AND published_at IS NOT NULL) "
            "OR (status <> 'published' AND published_at IS NULL)",
            name="memories_published_has_timestamp",
        ),
    )


class MemoryPhoto(Base):
    __tablename__ = "memory_photos"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SchedulerHeartbeat(Base):
    """单行表（id = 1）。健康检查读 last_beat_at 判断调度进程是否还活着。"""

    __tablename__ = "scheduler_heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    instance_id: Mapped[str] = mapped_column(Text, nullable=False)
    last_beat_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (CheckConstraint("id = 1", name="scheduler_heartbeat_single_row"),)


class OrphanObject(Base):
    __tablename__ = "orphan_objects"

    id: Mapped[uuid.UUID] = _pk()
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "reason IN ('delete_failed', 'unreferenced')", name="orphan_objects_reason_check"
        ),
    )


__all__ = [
    "AGENT_JOB_KINDS",
    "DEGRADED_REASONS",
    "MEDIA_KINDS",
    "MEDIA_STATUSES",
    "MEMORY_DRAFTED_FIELDS",
    "MEMORY_STATUSES",
    "MOODS",
    "TIMING_TYPES",
    "TRIGGER_KINDS",
    "WISH_STATES",
    "Base",
    "Media",
    "Memory",
    "MemoryPhoto",
    "OnboardingAnswer",
    "OrphanObject",
    "PendingAgentJob",
    "PushSubscription",
    "ReminderOutbox",
    "ReminderWeeklyCounter",
    "SchedulerHeartbeat",
    "Session",
    "User",
    "Wish",
    "WishAmendment",
    "WishMessage",
    "WishPhoto",
    "WishStep",
]

