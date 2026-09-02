"""Agent 能力：LLM 供应商抽象 + 结构化输出 + 降级。

硬约束（tech_stack.llm）：只走 OpenAI 兼容端点，代码中不出现任何厂商名。
base_url / api_key / model 全部来自环境变量。

架构 5.1 的三条规则在这里落地：
  1. 超时 5 秒、重试 1 次，失败一律返回 None（不抛给调用方）。
  2. 结构化输出用 response_format=json_schema，再由 Pydantic 二次校验；
     校验失败等同不可用（S01 EX-16.2），绝不返回半结构化结果。
  3. 日志只记响应长度与错误类型，不记响应内容（隐私红线）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings

logger = logging.getLogger("app.agent")

SYSTEM_PROMPT = """你是「未发生事件管理局」的记录者，不是效率教练。
你的任务是理解用户随口说出的一件想在未来发生的事。

规则：
- 不评价这件事是否值得、是否现实，不建议放弃。
- 不使用「任务」「截止」「逾期」「未完成」「打卡」这些词。
- 追问最多一句，且必须是用户可以不回答的问题。
- 如果这明显是这几天要办的事而不是未来的愿望，把 kind 标为 near_term_todo。
"""


class WishUnderstanding(BaseModel):
    """与 wishes.yaml 的 WishUnderstanding schema 一致。"""

    kind: Literal["future_wish", "near_term_todo"]
    feeling: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    smallest_step: str | None = None


class UnderstandResult(BaseModel):
    understanding: WishUnderstanding
    question: str | None = None


_UNDERSTAND_JSON_SCHEMA: dict[str, Any] = {
    "name": "wish_understanding",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["understanding", "question"],
        "properties": {
            "understanding": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "feeling", "conditions", "smallest_step"],
                "properties": {
                    "kind": {"type": "string", "enum": ["future_wish", "near_term_todo"]},
                    "feeling": {"type": ["string", "null"]},
                    "conditions": {"type": "object", "additionalProperties": True},
                    "smallest_step": {"type": ["string", "null"]},
                },
            },
            "question": {"type": ["string", "null"]},
        },
    },
}


STEP_PROMPT = """你要给出**一个**很小的下一步，不是一套计划。

硬性约束（必须同时满足，并在返回的自检字段里如实标注）：
- 5 分钟内可以独立完成
- 不涉及花钱
- 不需要联系任何人
- 不使用「任务」「截止」「逾期」「打卡」这些词

已经被用户拒绝过的步骤不要再提。
"""

INTENT_PROMPT = """判断用户这句话的意图，只返回其中一个：
- amend：想修改这件事本身（内容、同行的人、时间范围变了）
- assist：想让你帮他往前推一步（定日期、算预算、排行程）
- fatigue：表达疲惫、累、撑不住
- chat：其余情况

再给一句不超过 40 字的回应。不要评价这件事是否值得做。
"""

MEMORY_PROMPT = """用户告诉你，他曾经写下的一件事已经发生了。为它草拟一页记忆的三段文字：

- title：不超过 80 字的一句标题，用陈述语气，写这件事本身，不要用「成功」「完成」「达成」这类词
- cause：起因。引用他当初写下它时的原始期待，一到两句，如「你原本想逃离一点压力。」
- process：经过。只依据他实际留下的准备过程记录来写；**如果没有任何记录，返回 null**，
  不要编造过程，也不要用「你一步步地」这类没有依据的叙述

全程用第二人称「你」。不做评价，不总结教训，不鼓励。
"""


class StepSuggestion(BaseModel):
    """与 wishes.yaml 的 WishStep 自检字段一致。

    让模型自报三个字段再由服务端校验，比只在 prompt 里写「不要涉及花钱」可靠得多：
    前者可以被代码拦下，后者只能指望模型听话（S04 EX-8.2）。
    """

    text: str = Field(min_length=1, max_length=200)
    est_minutes: int = Field(ge=1, le=60)
    involves_cost: bool
    involves_others: bool

    @property
    def compliant(self) -> bool:
        return self.est_minutes <= 5 and not self.involves_cost and not self.involves_others


class MessageReply(BaseModel):
    intent: Literal["chat", "amend", "assist", "fatigue"]
    reply: str = Field(max_length=200)
    amended_title: str | None = None
    amended_conditions: dict[str, Any] = Field(default_factory=dict)


class MemoryDraft(BaseModel):
    """S06 Step 7 → Step 8 的 MemoryDraft JSON。

    三段都由模型草拟，但只有 title 是必需的——「经过」依据准备过程时间线，
    没有时间线时它本就该为空（EX-4.1），不该逼模型编一段出来。
    """

    title: str = Field(min_length=1, max_length=80)
    cause: str | None = Field(default=None, max_length=2000)
    process: str | None = Field(default=None, max_length=4000)


# 兜底步骤库：按 understanding.feeling 选一条纯想象类动作（EX-8.2 / EX-13.2）
FALLBACK_STEPS: dict[str, str] = {
    "放松": "只是想一想：你更想听海的声音，还是想看日出？",
    "喘口气": "只是想一想：那两天你最想避开的是什么？",
    "陪伴": "只是想一想：你最想和谁一起做这件事？",
    "勇气": "只是想一想：如果它已经开始了，第一个画面是什么？",
    "连接": "只是想一想：这件事会让你想起谁？",
    "成长": "只是想一想：做完它之后，你希望自己有什么不一样？",
}
FALLBACK_DEFAULT = "不用现在做任何事也可以。只是想一想：它发生的那天，你希望是什么天气？"


def fallback_step(feeling: str | None) -> StepSuggestion:
    text = FALLBACK_STEPS.get(feeling or "", FALLBACK_DEFAULT)
    return StepSuggestion(text=text, est_minutes=1, involves_cost=False, involves_others=False)


class LLMProvider(Protocol):
    async def understand_wish(self, text: str) -> UnderstandResult | None: ...

    async def next_step(
        self, *, original_text: str, feeling: str | None, rejected: list[str]
    ) -> StepSuggestion | None: ...

    async def classify_message(self, *, text: str, original_text: str) -> MessageReply | None: ...

    async def draft_memory(
        self, *, original_text: str, feeling: str | None, timeline: list[str]
    ) -> MemoryDraft | None: ...


class OpenAICompatibleProvider:
    """唯一实现。任何兼容 /v1/chat/completions 的端点都可零改码替换。"""

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        s = get_settings()
        self._client = AsyncOpenAI(
            base_url=s.LLM_BASE_URL,
            api_key=s.LLM_API_KEY,
            timeout=s.LLM_TIMEOUT_SECONDS,
            max_retries=1,
        )
        self._model = s.LLM_MODEL

    async def next_step(
        self, *, original_text: str, feeling: str | None, rejected: list[str]
    ) -> StepSuggestion | None:
        excluded = chr(10).join(f"- {r}" for r in rejected) or "（暂无）"
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": STEP_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"这件事：{original_text} / "
                            f"他想要的感受：{feeling or '未知'} / "
                            f"已被拒绝的步骤：{excluded}"
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("llm_unavailable", extra={"error_type": type(exc).__name__})
            return None
        return _parse_model(StepSuggestion, resp)

    async def classify_message(self, *, text: str, original_text: str) -> MessageReply | None:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": INTENT_PROMPT},
                    {"role": "user", "content": f"这件事：{original_text} / 他说：{text}"},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("llm_unavailable", extra={"error_type": type(exc).__name__})
            return None
        return _parse_model(MessageReply, resp)

    async def draft_memory(
        self, *, original_text: str, feeling: str | None, timeline: list[str]
    ) -> MemoryDraft | None:
        """S06 Step 7。超时 / 5xx / schema 不合法一律返回 None，由调用方降级（EX-7.1）。"""
        records = chr(10).join(f"- {t}" for t in timeline) or "（没有任何准备过程记录）"
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": MEMORY_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"他当初写下的话：{original_text} / "
                            f"他想要的感受：{feeling or '未知'} / "
                            f"他留下的准备过程：{chr(10)}{records}"
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("llm_unavailable", extra={"error_type": type(exc).__name__})
            return None
        return _parse_model(MemoryDraft, resp)

    async def understand_wish(self, text: str) -> UnderstandResult | None:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_schema", "json_schema": _UNDERSTAND_JSON_SCHEMA},
            )
        except Exception as exc:  # 超时 / 5xx / 连接错误
            logger.warning("llm_unavailable", extra={"error_type": type(exc).__name__})
            return None

        raw = (resp.choices[0].message.content or "") if resp.choices else ""
        return parse_understand_payload(raw)


def _parse_model(model: type[BaseModel], resp: Any) -> Any:
    raw = (resp.choices[0].message.content or "") if resp.choices else ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("llm_invalid_json", extra={"response_len": len(raw or "")})
        return None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "llm_schema_invalid",
            extra={"response_len": len(raw), "error_count": len(exc.errors())},
        )
        return None


def parse_understand_payload(raw: str) -> UnderstandResult | None:
    """把模型返回的原始字符串解析为 UnderstandResult；失败返回 None。

    这一步与 HTTP 调用分离，使 UT 可以不依赖网络地验证「非法 JSON 等同不可用」。
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("llm_invalid_json", extra={"response_len": len(raw or "")})
        return None
    try:
        return UnderstandResult.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "llm_schema_invalid",
            extra={"response_len": len(raw), "error_count": len(exc.errors())},
        )
        return None


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = OpenAICompatibleProvider()
    return _provider


def set_llm_provider(provider: LLMProvider | None) -> None:
    """测试注入点。"""
    global _provider
    _provider = provider
