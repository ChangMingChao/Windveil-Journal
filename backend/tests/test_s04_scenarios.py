"""S04 场景测试（端到端 HTTP）。

覆盖 UT-S04-01~08（HTTP 层字段与状态断言）与 ST-S04-01~10。
ST-S04-11 为 [manual]（对话区只呈现 1 个下一步卡），不产出 JSONL。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient


class FakeLLM:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.step_calls = 0

    async def understand_wish(self, text: str):  # noqa: ANN201, ARG002
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(
            {
                "understanding": {
                    "kind": "future_wish",
                    "feeling": "放松",
                    "conditions": {"title": "去海边待两天"},
                    "smallest_step": "先收藏一张海的照片",
                },
                "question": "更像一次独处吗？",
            }
        )

    async def next_step(self, *, original_text, feeling, rejected):  # noqa: ANN001, ANN201, ARG002
        from app.agent import StepSuggestion

        self.step_calls += 1
        if self.mode == "none":
            return None
        if self.mode == "violating":
            return StepSuggestion(
                text="先去订一张机票", est_minutes=45, involves_cost=True, involves_others=True
            )
        return StepSuggestion(
            text=f"第 {self.step_calls} 步：只是想一想那片海",
            est_minutes=2,
            involves_cost=False,
            involves_others=False,
        )

    async def classify_message(self, *, text, original_text):  # noqa: ANN001, ANN201, ARG002
        from app.agent import MessageReply

        if self.mode == "amend":
            return MessageReply(
                intent="amend",
                reply="好，我把它改成和妹妹一起",
                amended_title="和妹妹一起去海边待两天",
                amended_conditions={"companion": "妹妹"},
            )
        return MessageReply(intent="chat", reply="嗯，我记着")


@pytest.fixture
async def env(app_env: None, tmp_path) -> AsyncIterator[tuple]:  # noqa: ANN001
    import os

    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import InMemoryEmailSender, set_senders
    from app.storage import set_storage

    get_settings.cache_clear()
    set_storage(None)
    llm = FakeLLM()
    set_llm_provider(llm)
    set_senders(None, InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": "2026-09-01T12:00:00+08:00"})
        yield client, llm
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


async def _signup(client: AsyncClient) -> tuple[dict, str]:
    r = await client.post("/api/v1/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _fresh(uid: str) -> dict:
    from app.security import issue_access_token

    return {"Authorization": f"Bearer {issue_access_token(uuid.UUID(uid))}"}


async def _wind_wish(client: AsyncClient, h: dict) -> tuple[str, int]:
    """种下 → 设时机 → ready，返回 (wish_id, version)。"""
    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想一个人去海边待两天"}
    )
    wid = r.json()["wish"]["id"]
    assert (
        await client.put(f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "free_weekend"})
    ).status_code == 200
    ready = await client.post(f"/api/v1/wishes/{wid}/ready", headers=h)
    assert ready.status_code == 200
    return wid, ready.json()["version"]


# ---------------------------------------------------------------- UT（HTTP 层）


@pytest.mark.asyncio
async def test_UT_S04_01_rejected_step_id_must_be_uuid(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    r = await client.post(
        f"/api/v1/wishes/{wid}/steps/next", headers=h, json={"rejected_step_id": "abc"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_UT_S04_02_foreign_step_returns_404(env) -> None:  # noqa: ANN001
    client, _ = env
    h_a, _ = await _signup(client)
    wid_a, _ = await _wind_wish(client, h_a)
    step = (await client.post(f"/api/v1/wishes/{wid_a}/steps/next", headers=h_a)).json()["step"]

    h_b, _ = await _signup(client)
    wid_b, _ = await _wind_wish(client, h_b)
    r = await client.post(
        f"/api/v1/wishes/{wid_b}/steps/next", headers=h_b,
        json={"rejected_step_id": step["id"]},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "STEP_NOT_FOUND"


@pytest.mark.asyncio
async def test_UT_S04_03_missing_if_match_returns_412(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]
    r = await client.post(f"/api/v1/wishes/{wid}/steps/{step['id']}/done", headers=h)
    assert r.status_code == 412
    assert r.json()["code"] == "PRECONDITION_REQUIRED"


@pytest.mark.asyncio
async def test_UT_S04_04_version_mismatch_returns_409(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, version = await _wind_wish(client, h)
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]
    r = await client.post(
        f"/api/v1/wishes/{wid}/steps/{step['id']}/done",
        headers={**h, "If-Match": str(version + 99)},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "STATE_CONFLICT"


@pytest.mark.asyncio
async def test_UT_S04_05_message_text_required(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    for bad in ({}, {"text": ""}, {"text": "   "}):
        r = await client.post(f"/api/v1/wishes/{wid}/messages", headers=h, json=bad)
        assert r.status_code == 422, bad


@pytest.mark.asyncio
async def test_UT_S04_06_message_text_length_boundary(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    ok = await client.post(f"/api/v1/wishes/{wid}/messages", headers=h, json={"text": "海" * 1000})
    assert ok.status_code == 200
    too_long = await client.post(
        f"/api/v1/wishes/{wid}/messages", headers=h, json={"text": "海" * 1001}
    )
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_UT_S04_07_next_step_requires_wind_or_going(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想学一门乐器"}
    )
    wid = r.json()["wish"]["id"]  # 状态 seeded
    got = await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)
    assert got.status_code == 409
    assert got.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_UT_S04_08_ready_rejected_in_terminal_state(env) -> None:  # noqa: ANN001
    from app.db import session_scope
    from app.models import Wish

    client, _ = env
    h, uid = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    async with session_scope(uuid.UUID(uid)) as s:
        wish = await s.get(Wish, uuid.UUID(wid))
        wish.state = "happened"
    r = await client.post(f"/api/v1/wishes/{wid}/ready", headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"


# ---------------------------------------------------------------- ST


@pytest.mark.asyncio
async def test_ST_S04_01_first_step_moves_to_going(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, version = await _wind_wish(client, h)

    got = await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)
    assert got.status_code == 200
    step = got.json()["step"]
    assert got.json()["degraded"] is False
    assert step["status"] == "proposed"
    assert step["est_minutes"] <= 5
    assert step["involves_cost"] is False and step["involves_others"] is False
    assert step["source"] == "llm"

    done = await client.post(
        f"/api/v1/wishes/{wid}/steps/{step['id']}/done", headers={**h, "If-Match": str(version)}
    )
    assert done.status_code == 200
    wish = done.json()["wish"]
    assert wish["state"] == "going"
    assert len(wish["timeline"]) == 1
    assert done.json()["timeline_entry"]["completed_at"] is not None

    again = await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)
    assert again.json()["step"]["id"] != step["id"]

    detail = (await client.get(f"/api/v1/wishes/{wid}", headers=h)).json()
    assert detail["current_step"] is not None
    assert len(detail["timeline"]) == 1
    for forbidden in ("due_date", "plan", "progress", "remaining_steps"):
        assert forbidden not in detail


@pytest.mark.asyncio
async def test_ST_S04_02_entry_from_notification_action(env) -> None:  # noqa: ANN001
    """从通知动作进入与从详情页进入走同一组端点，状态迁移一致。"""
    client, _ = env
    h, uid = await _signup(client)
    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想重新开始画画"}
    )
    wid = r.json()["wish"]["id"]
    await client.put(
        f"/api/v1/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    await client.post("/api/test/clock", json={"now": "2026-10-02T09:00:00+08:00"})
    await client.post("/api/test/scheduler/tick")

    h2 = _fresh(uid)
    ready = await client.post(f"/api/v1/wishes/{wid}/ready", headers=h2)
    assert ready.status_code == 200
    assert ready.json()["state"] == "wind"
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h2)).json()["step"]
    done = await client.post(
        f"/api/v1/wishes/{wid}/steps/{step['id']}/done",
        headers={**h2, "If-Match": str(ready.json()["version"])},
    )
    assert done.status_code == 200
    assert done.json()["wish"]["state"] == "going"


@pytest.mark.asyncio
async def test_ST_S04_03_llm_unavailable_keeps_wind(env) -> None:  # noqa: ANN001
    client, llm = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    llm.mode = "none"

    got = await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)
    assert got.status_code == 200
    assert got.json() == {"step": None, "degraded": True}

    detail = (await client.get(f"/api/v1/wishes/{wid}", headers=h)).json()
    assert detail["state"] == "wind"
    assert detail["current_step"] is None


@pytest.mark.asyncio
async def test_ST_S04_04_violating_step_falls_back(env) -> None:  # noqa: ANN001
    client, llm = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    llm.mode = "violating"

    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]
    assert step["source"] == "fallback"
    assert step["est_minutes"] <= 5
    assert step["involves_cost"] is False and step["involves_others"] is False
    assert llm.step_calls == 2  # 首次 + 指出违反项后重试


@pytest.mark.asyncio
async def test_ST_S04_05_smaller_step_replaces_rejected(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    first = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]

    second = await client.post(
        f"/api/v1/wishes/{wid}/steps/next", headers=h, json={"rejected_step_id": first["id"]}
    )
    assert second.status_code == 200
    step = second.json()["step"]
    assert step["id"] != first["id"]
    assert step["text"] != first["text"]
    assert step["est_minutes"] <= 5
    assert "rejected_count" not in second.json()


@pytest.mark.asyncio
async def test_ST_S04_06_third_rejection_uses_fallback(env) -> None:  # noqa: ANN001
    client, llm = env
    h, _ = await _signup(client)
    wid, _ = await _wind_wish(client, h)
    step_id = None
    for _ in range(3):
        body = {"rejected_step_id": step_id} if step_id else {}
        step_id = (
            await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h, json=body)
        ).json()["step"]["id"]
    calls_before = llm.step_calls
    last = await client.post(
        f"/api/v1/wishes/{wid}/steps/next", headers=h, json={"rejected_step_id": step_id}
    )
    assert last.json()["step"]["source"] == "fallback"
    assert llm.step_calls == calls_before


@pytest.mark.asyncio
async def test_ST_S04_07_concurrent_done_yields_one_conflict(env) -> None:  # noqa: ANN001
    import asyncio

    client, _ = env
    h, _ = await _signup(client)
    wid, version = await _wind_wish(client, h)
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]

    url = f"/api/v1/wishes/{wid}/steps/{step['id']}/done"
    headers = {**h, "If-Match": str(version)}
    r1, r2 = await asyncio.gather(
        client.post(url, headers=headers), client.post(url, headers=headers)
    )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409]
    conflict = r1 if r1.status_code == 409 else r2
    assert conflict.json()["code"] == "STATE_CONFLICT"

    detail = (await client.get(f"/api/v1/wishes/{wid}", headers=h)).json()
    assert len(detail["timeline"]) == 1


@pytest.mark.asyncio
async def test_ST_S04_08_stale_care_after_sixty_days(env) -> None:  # noqa: ANN001
    from app.db import session_scope
    from app.models import Wish

    client, _ = env
    h, uid = await _signup(client)
    wid, version = await _wind_wish(client, h)
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]
    await client.post(
        f"/api/v1/wishes/{wid}/steps/{step['id']}/done", headers={**h, "If-Match": str(version)}
    )

    from app.clock import clock

    base = clock.now()
    async with session_scope(uuid.UUID(uid)) as s:
        wish = await s.get(Wish, uuid.UUID(wid))
        wish.last_activity_at = base - timedelta(days=60)

    await client.post("/api/test/scheduler/tick")
    box = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    care = [i for i in box["items"] if i["kind"] == "stale_care"]
    assert len(care) == 1
    assert "最近怎么样了" in care[0]["body"]

    await client.post("/api/test/scheduler/tick")
    box2 = (await client.get(f"/api/test/outbox?user_id={uid}")).json()
    assert len([i for i in box2["items"] if i["kind"] == "stale_care"]) == 1

    detail = (await client.get(f"/api/v1/wishes/{wid}", headers=_fresh(uid))).json()
    assert "stale_days" not in detail and "progress" not in detail


@pytest.mark.asyncio
async def test_ST_S04_09_amend_keeps_original_and_timeline(env) -> None:  # noqa: ANN001
    client, llm = env
    h, _ = await _signup(client)
    wid, version = await _wind_wish(client, h)
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]
    await client.post(
        f"/api/v1/wishes/{wid}/steps/{step['id']}/done", headers={**h, "If-Match": str(version)}
    )
    before = (await client.get(f"/api/v1/wishes/{wid}", headers=h)).json()

    llm.mode = "amend"
    r = await client.post(
        f"/api/v1/wishes/{wid}/messages", headers=h, json={"text": "想改成和妹妹一起去"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "amend"
    wish = body["wish"]
    assert wish["title"] == "和妹妹一起去海边待两天"
    assert wish["original_text"] == "想一个人去海边待两天"
    assert wish["amended_from"] == "想一个人去海边待两天"
    assert wish["seeded_at"] == before["seeded_at"]
    assert len(wish["timeline"]) == 1
    assert wish["state"] == "going"


@pytest.mark.asyncio
async def test_ST_S04_10_back_to_brewing_keeps_timeline(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid, version = await _wind_wish(client, h)
    step = (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).json()["step"]
    await client.post(
        f"/api/v1/wishes/{wid}/steps/{step['id']}/done", headers={**h, "If-Match": str(version)}
    )

    back = await client.post(f"/api/v1/wishes/{wid}/back-to-brewing", headers=h)
    assert back.status_code == 200
    assert back.json()["state"] == "brewing"
    assert len(back.json()["timeline"]) == 1

    # brewing 状态下不能再取步骤（需要先 ready）
    assert (await client.post(f"/api/v1/wishes/{wid}/steps/next", headers=h)).status_code == 409
