"""S01 单元测试（不依赖数据库的部分）。

用例 ID 与 logos/resources/test/core-S01-test-cases.md 完全一致。
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.agent import UnderstandResult, parse_understand_payload
from app.config import get_settings
from app.schemas import AnonymousRequest, OnboardingAnswerItem, OnboardingAnswersRequest, SeedWishRequest
from app.services import DomainError, _derive_title, _fallback_title, normalize_wish_text

VALID_JSON = (
    '{"understanding":{"kind":"future_wish","feeling":"放松",'
    '"conditions":{"season":"winter"},"smallest_step":"先收藏一张海的照片"},'
    '"question":"这更像是一次独处吗？"}'
)


# ---------------------------------------------------------------- 1.1 API 字段约束


def test_UT_S01_01_timezone_default() -> None:
    assert AnonymousRequest().timezone == "Asia/Shanghai"


def test_UT_S01_02_timezone_invalid_rejected() -> None:
    with pytest.raises(ValidationError):
        AnonymousRequest(timezone="Mars/Olympus")


def test_UT_S01_03_answers_required() -> None:
    with pytest.raises(ValidationError):
        OnboardingAnswersRequest()


def test_UT_S01_04_answers_empty_array_allowed() -> None:
    assert OnboardingAnswersRequest(answers=[]).answers == []


def test_UT_S01_05_answers_over_limit_rejected() -> None:
    limit = get_settings().ONBOARDING_MAX_ANSWERS
    items = [{"question_key": f"q{i}"} for i in range(limit + 1)]
    with pytest.raises(ValidationError):
        OnboardingAnswersRequest(answers=items)
    OnboardingAnswersRequest(answers=items[:limit])


def test_UT_S01_06_answer_text_length_boundary() -> None:
    OnboardingAnswerItem(question_key="q1", answer_text="海" * 500)
    with pytest.raises(ValidationError):
        OnboardingAnswerItem(question_key="q1", answer_text="海" * 501)


def test_UT_S01_07_answer_text_nullable() -> None:
    assert OnboardingAnswerItem(question_key="q1", answer_text=None).answer_text is None


def test_UT_S01_08_question_key_required() -> None:
    with pytest.raises(ValidationError):
        OnboardingAnswerItem(answer_text="x")


def test_UT_S01_09_text_missing_for_text_source() -> None:
    with pytest.raises(DomainError) as exc:
        normalize_wish_text(None)
    assert exc.value.code == "WISH_TEXT_INVALID"
    assert exc.value.status == 422


def test_UT_S01_10_text_blank_rejected_single_char_ok() -> None:
    assert normalize_wish_text("海") == "海"
    with pytest.raises(DomainError) as exc:
        normalize_wish_text("   ")
    assert exc.value.code == "WISH_TEXT_INVALID"


def test_UT_S01_11_text_length_boundary() -> None:
    limit = get_settings().WISH_TEXT_MAX_LEN
    assert len(normalize_wish_text("海" * limit)) == limit
    with pytest.raises(DomainError):
        normalize_wish_text("海" * (limit + 1))
    # API 层同样拦住超长（schemas.SeedWishRequest.text.maxLength）
    with pytest.raises(ValidationError):
        SeedWishRequest(source="text", text="海" * (limit + 1))


def test_UT_S01_12_source_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        SeedWishRequest(source="image", text="x")
    assert SeedWishRequest(source="text", text="x").source == "text"


# ---------------------------------------------------------------- 1.3 业务规则


@pytest.mark.asyncio
async def test_UT_S01_21_unauthenticated_returns_401() -> None:
    """未带 access token 访问业务端点返回 401；该判定发生在任何数据库访问之前。"""
    import os

    from httpx import ASGITransport, AsyncClient

    os.environ["APP_ENV"] = "test"
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.post("/api/v1/wishes", json={"source": "text", "text": "x"})
        assert r.status_code == 401
        assert r.json()["code"] == "UNAUTHENTICATED"
        r = await client.get("/api/v1/me")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_UT_S01_22_llm_timeout_returns_none() -> None:
    """超时上限由 LLM_TIMEOUT_SECONDS 控制；任何异常一律降级为 None，不抛出。"""
    from app.agent import OpenAICompatibleProvider

    assert get_settings().LLM_TIMEOUT_SECONDS == 5.0

    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider._model = "mock-model"  # noqa: SLF001

    class _Raising:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_kwargs: object) -> object:
                    raise TimeoutError("simulated timeout")

    provider._client = _Raising()  # noqa: SLF001
    assert await provider.understand_wish("想去看海") is None


def test_UT_S01_23_schema_validation_failure_equals_unavailable() -> None:
    # 合法载荷可解析
    assert isinstance(parse_understand_payload(VALID_JSON), UnderstandResult)
    # 缺 kind 字段 → 视为不可用
    assert parse_understand_payload('{"understanding":{"feeling":"放松"},"question":null}') is None
    # 完全不是 JSON → 视为不可用
    assert parse_understand_payload("not-json") is None


def test_UT_S01_24_degraded_title_falls_back_to_first_20_chars() -> None:
    text = "等压力没这么大的时候，想去海边待两天，最好是有日出的那种"
    assert len(text) > 20
    assert _fallback_title(text) == text[:20]
    assert _derive_title(text, None) == text[:20]


def test_UT_S01_25_degraded_log_excludes_response_body(caplog: pytest.LogCaptureFixture) -> None:
    secret = "这是模型返回的原始内容，绝不能出现在日志里"
    with caplog.at_level(logging.WARNING, logger="app.agent"):
        assert parse_understand_payload(secret) is None
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "llm_invalid_json" in joined
    assert secret not in joined
    record = next(r for r in caplog.records if r.getMessage() == "llm_invalid_json")
    assert getattr(record, "response_len") == len(secret)
