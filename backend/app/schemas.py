"""API 请求 / 响应模型。字段名与 logos/resources/api/*.yaml 严格一致。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import get_settings


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


# ---------- auth.yaml ----------


class AnonymousRequest(BaseModel):
    timezone: str = "Asia/Shanghai"

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown IANA timezone") from exc
        return v


class UserProfile(BaseModel):
    id: UUID
    email: str | None = None
    is_anonymous: bool
    onboarded_at: datetime | None = None
    timezone: str
    created_at: datetime | None = None


class AuthResult(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = Field(default_factory=lambda: get_settings().ACCESS_TOKEN_TTL_SECONDS)
    user: UserProfile


class LinkEmailRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- onboarding ----------


class OnboardingAnswerItem(BaseModel):
    question_key: str
    answer_text: str | None = Field(default=None, max_length=500)


class OnboardingAnswersRequest(BaseModel):
    answers: list[OnboardingAnswerItem] = Field(
        max_length=get_settings().ONBOARDING_MAX_ANSWERS
    )


# ---------- media.yaml ----------


class UploadUrlRequest(BaseModel):
    kind: Literal["audio", "image"]
    content_type: str
    size_bytes: int = Field(ge=1)


class UploadUrlResult(BaseModel):
    media_id: UUID
    upload_url: str
    expires_at: datetime


# ---------- wishes.yaml ----------


class SeedWishRequest(BaseModel):
    source: Literal["text", "voice"]
    text: str | None = Field(default=None, max_length=get_settings().WISH_TEXT_MAX_LEN)
    media_id: UUID | None = None
    photo_media_ids: list[UUID] = Field(default_factory=list, max_length=9)


class TimingOut(BaseModel):
    type: str | None = None
    label: str
    trigger_kind: Literal["time", "signal", "none"]
    next_trigger_at: datetime | None = None


class WishCard(BaseModel):
    id: UUID
    title: str
    original_text_excerpt: str | None = None
    seeded_at: datetime
    state: Literal["seeded", "brewing", "wind", "going", "happened", "let_go"]
    let_go_at: datetime | None = None
    timing: TimingOut
    soft_deferred: bool = False
    degraded_reason: str | None = None
    version: int


class WishDetail(WishCard):
    original_text: str | None = None
    audio_media_id: UUID | None = None
    photo_media_ids: list[UUID] = Field(default_factory=list)
    understanding: dict[str, Any] | None = None
    pending_question: bool = False
    amended_from: str | None = None
    current_step: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class SeedWishResult(BaseModel):
    wish: WishDetail
    question: str | None = None
    actions: list[Literal["keep_as_future", "delete"]] | None = None
    degraded: bool


class WishListResponse(BaseModel):
    items: list[WishCard]
    next_cursor: str | None = None


class AnswerRequest(BaseModel):
    answer: str | None = Field(default=None, min_length=1, max_length=500)
    skipped: bool | None = None
    action: Literal["keep_as_future"] | None = None


# ---------- memories.yaml ----------

Mood = Literal["relieved", "healed", "tearful", "calm", "proud", "unspeakable"]


class HappenedRequest(BaseModel):
    """`format: date` 由 pydantic 承担：`2026/10/17` 在这里就被拒（UT-S06-02）。"""

    happened_from: date
    happened_to: date | None = None
    acknowledged_before_seeded: bool = False


class MemoryCard(BaseModel):
    id: UUID
    wish_id: UUID
    title: str
    happened_from: str
    happened_to: str | None = None
    cover_media_id: UUID | None = None
    status: Literal["draft", "published"]


class MemoryOut(MemoryCard):
    cause: str | None = None
    process: str | None = None
    mood: Mood | None = None
    last_line: str | None = None
    photo_media_ids: list[UUID] = Field(default_factory=list)
    voice_media_id: UUID | None = None
    note_before_seeded: bool = False
    edited_fields: list[Literal["title", "cause", "process"]] = Field(default_factory=list)
    published_at: datetime | None = None
    created_at: datetime


class MemoryResult(BaseModel):
    memory: MemoryOut
    degraded: bool
    warning: dict[str, str] | None = None


class PublishResult(BaseModel):
    memory: MemoryOut


class MemoryListResponse(BaseModel):
    items: list[MemoryCard]
    next_cursor: str | None = None
    lived_pages: int
