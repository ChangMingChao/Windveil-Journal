"""语音转写。

硬约束（tech_stack.asr）：只走 OpenAI 兼容 /v1/audio/transcriptions，
base_url / api_key / model 全部来自环境变量，代码中不出现任何厂商名。

S02 的三条规则在这里落地：
  1. 超时 15 秒（与「转写 P95 ≤ 15 秒」对齐），失败返回 TranscribeResult(text=None, reason="asr_failed")
  2. 返回 200 但文本去空白后为空 → reason="asr_empty"（EX-15.2）
     区分这两种原因是为了让文案准确——「没听清」和「服务坏了」对用户是两件事
  3. 原始音频永久保留，转写永远可重试（EX-15.1）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger("app.asr")


@dataclass(frozen=True)
class TranscribeResult:
    text: str | None
    reason: str | None  # None / "asr_failed" / "asr_empty"

    @property
    def ok(self) -> bool:
        return self.text is not None


def classify_transcript(raw: str | None) -> TranscribeResult:
    """把原始转写文本归一为结果对象。纯函数，便于 UT 不依赖网络地覆盖边界。"""
    if raw is None:
        return TranscribeResult(text=None, reason="asr_failed")
    cleaned = raw.strip()
    if not cleaned:
        return TranscribeResult(text=None, reason="asr_empty")
    return TranscribeResult(text=cleaned, reason=None)


class ASRProvider(Protocol):
    async def transcribe(self, audio: bytes, filename: str) -> TranscribeResult: ...


class OpenAICompatibleASR:
    def __init__(self) -> None:
        from openai import AsyncOpenAI

        s = get_settings()
        self._client = AsyncOpenAI(
            base_url=s.ASR_BASE_URL,
            api_key=s.ASR_API_KEY,
            timeout=s.ASR_TIMEOUT_SECONDS,
            max_retries=1,
        )
        self._model = s.ASR_MODEL

    async def transcribe(self, audio: bytes, filename: str) -> TranscribeResult:
        try:
            resp = await self._client.audio.transcriptions.create(
                model=self._model, file=(filename, audio)
            )
        except Exception as exc:  # 超时 / 5xx / 连接错误
            logger.warning("asr_unavailable", extra={"error_type": type(exc).__name__})
            return TranscribeResult(text=None, reason="asr_failed")
        return classify_transcript(getattr(resp, "text", None))


_provider: ASRProvider | None = None


def get_asr_provider() -> ASRProvider:
    global _provider
    if _provider is None:
        _provider = OpenAICompatibleASR()
    return _provider


def set_asr_provider(provider: ASRProvider | None) -> None:
    """测试注入点。"""
    global _provider
    _provider = provider
