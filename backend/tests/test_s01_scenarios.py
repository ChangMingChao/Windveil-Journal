"""S01 场景测试（端到端 HTTP）。

覆盖 ST-S01-01 ~ ST-S01-08、ST-S01-11。数据库为临时 SQLite 文件，不依赖任何外部服务。
ST-S01-03（DB 不可用）与 ST-S01-04（初始记忆写入失败）由 Batch 7 的故障注入夹具
（`app/faults.py` + `POST /api/test/faults`）驱动；ST-S01-09/10 为 [manual]，不产出 JSONL。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
VALID = {
    "understanding": {
        "kind": "future_wish",
        "feeling": "喘口气",
        "conditions": {"season": "winter", "title": "去海边待两天"},
        "smallest_step": "今晚收藏一张想看的海的照片",
    },
    "question": "这更像是一次独处，还是想和某个人一起去？",
}


class FakeProvider:
    """可控的 LLMProvider 替身：mode=ok / none。"""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.calls = 0

    async def understand_wish(self, text: str):  # noqa: ANN201, ARG002
        self.calls += 1
        if self.mode != "ok":
            return None
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(VALID)


@pytest.fixture
async def env(app_env: None) -> AsyncIterator[tuple[AsyncClient, FakeProvider]]:
    """应用 + 临时 SQLite 库 + 可控 LLM 替身。无需任何外部服务。"""
    from app.agent import set_llm_provider
    from app.db import dispose_engines
    from app.main import create_app

    provider = FakeProvider()
    set_llm_provider(provider)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, provider
    set_llm_provider(None)
    await dispose_engines()


async def _signup(client: AsyncClient) -> str:
    r = await client.post("/api/v1/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_ST_S01_01_full_onboarding_and_first_wish(env) -> None:  # noqa: ANN001
    client, provider = env
    r = await client.post("/api/v1/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["is_anonymous"] is True
    assert body["user"]["onboarded_at"] is not None
    assert body["expires_in"] == 900
    token = body["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/onboarding/answers",
        headers=h,
        json={
            "answers": [
                {"question_key": "wanted_but_not_done", "answer_text": "想一个人去看海"},
                {"question_key": "what_stops_you", "answer_text": "工作太忙"},
                {"question_key": "when_would_feel_right", "answer_text": "压力小一点的时候"},
            ]
        },
    )
    assert r.status_code == 204

    original = "等压力没这么大的时候，想去海边待两天。"
    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": original})
    assert r.status_code == 201, r.text
    seeded = r.json()
    assert seeded["degraded"] is False
    assert seeded["question"] == VALID["question"]
    assert seeded["wish"]["state"] == "seeded"
    assert seeded["wish"]["understanding"] is not None
    assert seeded["wish"]["original_text"] == original
    assert seeded["wish"]["title"] == "去海边待两天"
    wish_id = seeded["wish"]["id"]

    r = await client.post(
        f"/api/v1/wishes/{wish_id}/answer", headers=h, json={"answer": "更像一次独处"}
    )
    assert r.status_code == 200
    assert r.json()["pending_question"] is False

    r = await client.get("/api/v1/wishes", headers=h)
    assert r.status_code == 200
    listed = r.json()
    assert set(listed.keys()) == {"items", "next_cursor"}
    assert len(listed["items"]) == 1
    assert listed["items"][0]["id"] == wish_id
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_ST_S01_02_skip_gentle_questions(env) -> None:  # noqa: ANN001
    client, _ = env
    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/onboarding/answers", headers=h, json={"answers": []})
    assert r.status_code == 204

    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想在冬天学会滑雪"}
    )
    assert r.status_code == 201
    wish_id = r.json()["wish"]["id"]

    r = await client.post(f"/api/v1/wishes/{wish_id}/answer", headers=h, json={"skipped": True})
    assert r.status_code == 200
    assert r.json()["pending_question"] is True


@pytest.mark.asyncio
async def test_ST_S01_05_leave_without_writing_anything(env) -> None:  # noqa: ANN001
    client, _ = env
    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/me", headers=h)
    assert r.status_code == 200
    assert r.json()["onboarded_at"] is not None

    r = await client.get("/api/v1/wishes", headers=h)
    assert r.status_code == 200
    assert r.json() == {"items": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_ST_S01_06_empty_or_too_long_text_rejected(env) -> None:  # noqa: ANN001
    client, _ = env
    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": "   "})
    assert r.status_code == 422
    assert r.json()["code"] == "WISH_TEXT_INVALID"

    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": "海" * 500})
    assert r.status_code == 201

    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": "海" * 501})
    assert r.status_code == 422

    r = await client.get("/api/v1/wishes", headers=h)
    assert len(r.json()["items"]) == 1


@pytest.mark.asyncio
async def test_ST_S01_07_llm_timeout_degrades(env) -> None:  # noqa: ANN001
    client, provider = env
    provider.mode = "none"
    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    original = "等压力没这么大的时候，想去海边待两天，最好是有日出的那种"
    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": original})
    assert r.status_code == 201
    body = r.json()
    assert body["degraded"] is True
    assert body["question"] is None
    assert body["wish"]["understanding"] is None
    assert body["wish"]["degraded_reason"] == "llm_failed"
    assert body["wish"]["original_text"] == original
    assert body["wish"]["title"] == original[:20]
    wish_id = body["wish"]["id"]

    provider.mode = "ok"
    r = await client.post(f"/api/v1/wishes/{wish_id}/understanding", headers=h)
    assert r.status_code == 200
    retried = r.json()
    assert retried["degraded"] is False
    assert retried["wish"]["understanding"] is not None
    assert retried["wish"]["original_text"] == original


@pytest.mark.asyncio
async def test_ST_S01_08_llm_invalid_json_degrades_identically(env) -> None:  # noqa: ANN001
    client, _ = env

    class InvalidJsonProvider:
        async def understand_wish(self, text: str):  # noqa: ANN201, ARG002
            from app.agent import parse_understand_payload

            return parse_understand_payload("not-json")

    from app.agent import set_llm_provider

    set_llm_provider(InvalidJsonProvider())
    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/wishes", headers=h, json={"source": "text", "text": "想重新开始画画"})
    assert r.status_code == 201
    body = r.json()
    assert body["degraded"] is True
    assert body["question"] is None
    assert body["wish"]["understanding"] is None
    assert body["wish"]["original_text"] == "想重新开始画画"


@pytest.mark.asyncio
async def test_ST_S01_11_auth_and_field_boundaries(env) -> None:  # noqa: ANN001
    client, _ = env

    r = await client.post("/api/v1/wishes", json={"source": "text", "text": "x"})
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHENTICATED"

    r = await client.post(
        "/api/v1/wishes", headers={"Authorization": "Bearer not-a-token"},
        json={"source": "text", "text": "x"},
    )
    assert r.status_code == 401

    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/onboarding/answers",
        headers=h,
        json={"answers": [{"question_key": f"q{i}", "answer_text": "a"} for i in range(11)]},
    )
    assert r.status_code == 422

    r = await client.post(
        "/api/v1/onboarding/answers",
        headers=h,
        json={"answers": [{"question_key": "q1", "answer_text": None}]},
    )
    assert r.status_code == 204

    r = await client.get(f"/api/v1/wishes/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404
    assert r.json()["code"] == "WISH_NOT_FOUND"


# ---------------------------------------------------------------- 故障注入（Batch 7）


async def _arm(client: AsyncClient, *points: str) -> None:
    r = await client.post("/api/test/faults", json={"armed": list(points)})
    assert r.status_code == 204, r.text


async def _table_count(table: str) -> int:
    from sqlalchemy import text as sql_text

    from app.db import owner_guard_bypass, session_scope

    with owner_guard_bypass():
        async with session_scope() as s:
            return (await s.execute(sql_text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608


@pytest.mark.asyncio
async def test_ST_S01_03_anonymous_signup_fails_when_db_is_down(env) -> None:  # noqa: ANN001
    """EX-3.1：建号失败返回 503，不建用户，响应里不带堆栈或 SQL。"""
    client, _ = env
    before = await _table_count("users")
    await _arm(client, "db")
    try:
        r = await client.post("/api/v1/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    finally:
        await _arm(client)  # 先解除，否则后面的断言自己也连不上库

    assert r.status_code == 503
    body = r.json()
    assert body["code"] == "SPACE_CREATE_FAILED"
    assert set(body) <= {"code", "message", "details"}
    raw = r.text
    for leaked in ("Traceback", "sqlalchemy", "SELECT", "INSERT", "sqlite"):
        assert leaked not in raw, leaked
    assert await _table_count("users") == before


@pytest.mark.asyncio
async def test_ST_S01_04_onboarding_write_failure_still_returns_204(env, caplog) -> None:  # noqa: ANN001
    """EX-10.1：初始记忆是增强项，写不进去也不为它中断首次体验。"""
    import logging

    client, _ = env
    token = await _signup(client)
    h = {"Authorization": f"Bearer {token}"}

    await _arm(client, "onboarding_answers_write")
    try:
        with caplog.at_level(logging.ERROR, logger="app.onboarding"):
            r = await client.post(
                "/api/v1/onboarding/answers",
                headers=h,
                json={
                    "answers": [
                        {"question_key": f"q{i}", "answer_text": f"答案 {i}"} for i in range(3)
                    ]
                },
            )
    finally:
        await _arm(client)

    assert r.status_code == 204
    assert await _table_count("onboarding_answers") == 0
    errors = [rec for rec in caplog.records if rec.name == "app.onboarding"]
    assert len(errors) == 1
    assert errors[0].levelno >= logging.ERROR

    # 后续种下流程不受影响
    seeded = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想一个人去海边待两天"}
    )
    assert seeded.status_code == 201, seeded.text
    assert (await client.get("/api/v1/wishes", headers=h)).json()["items"]
