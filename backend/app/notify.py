"""提醒投递：Web Push 与邮件双通道。

架构第七节的测试策略：
  Web Push → env-disable（APP_ENV=test 时不真实投递，仅按成功记账）
  邮件     → test-api（GET /api/test/latest-email?to= 读最近一封）

S03 的三条规则在这里落地：
  1. 通知文案是纯模板拼接，不调用 LLM（Step 15 说明）——要求逐字引用用户原话
  2. push 订阅缺失或返回 404/410 时改走邮件；一次时机只送达 1 条（EX-16.1）
  3. 两条通道都失败时不消耗周预算（EX-16.2）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger("app.notify")


class DeliveryGone(Exception):
    """订阅已失效（404/410），应删除订阅并改走邮件。"""


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str
    sent_at: datetime


class PushSender(Protocol):
    async def send(self, *, endpoint: str, p256dh: str, auth: str, body: str) -> None: ...


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class DisabledPushSender:
    """env-disable：不调用真实推送服务，但按成功记账。

    这样周预算与去重语义仍可被断言（编排 core-S03-timing.json 的说明）。
    """

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, endpoint: str, p256dh: str, auth: str, body: str) -> None:
        del p256dh, auth
        self.sent.append(endpoint)
        logger.info("push_delivery_disabled", extra={"endpoint_len": len(endpoint)})


class InMemoryEmailSender:
    """test-api 策略的落地：邮件存在内存里，由后门端点读取。"""

    def __init__(self) -> None:
        self.mailbox: list[SentEmail] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        from app.clock import clock

        self.mailbox.append(SentEmail(to=to, subject=subject, body=body, sent_at=clock.now()))

    def latest(self, to: str) -> SentEmail | None:
        for item in reversed(self.mailbox):
            if item.to == to:
                return item
        return None


class SmtpEmailSender:  # pragma: no cover —— staging/production 才走这条
    async def send(self, *, to: str, subject: str, body: str) -> None:
        import smtplib
        from email.message import EmailMessage

        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.SMTP_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT) as smtp:
            smtp.send_message(msg)


MONTHS = ["", "一月", "二月", "三月", "四月", "五月", "六月",
          "七月", "八月", "九月", "十月", "十一月", "十二月"]


def render_reminder(*, seeded_at: datetime, original_text: str, timing_label: str) -> str:
    """S03 Step 15 的文案模板。纯拼接，逐字引用用户原话，不调用 LLM。"""
    excerpt = original_text.strip()
    if len(excerpt) > 40:
        excerpt = excerpt[:40]
    return f"你在{MONTHS[seeded_at.month]}说过{excerpt}，{timing_label}了。"


def render_stale_care(original_text: str) -> str:
    """S04 EX-15.2 的关心文案，同样是模板。"""
    excerpt = original_text.strip()[:40] if original_text else "那件事"
    return f"{excerpt}——最近怎么样了？还想继续吗？"


_push: PushSender | None = None
_email: EmailSender | None = None


def get_push_sender() -> PushSender:
    global _push
    if _push is None:
        _push = DisabledPushSender()
    return _push


def get_email_sender() -> EmailSender:
    global _email
    if _email is None:
        s = get_settings()
        _email = InMemoryEmailSender() if s.APP_ENV in ("local", "test") else SmtpEmailSender()
    return _email


def set_senders(push: PushSender | None, email: EmailSender | None) -> None:
    global _push, _email
    _push, _email = push, email
