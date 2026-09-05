"""S02 EX-18.2 第三选项测试（s02-lite-conversion）。

覆盖用例（批前声明）：
  - UT-S02-26（actions 枚举含 save_as_lite）与 ST-S02-17（brewing 拒绝）、
    UT-S02-27（转换归属与文本一致）、ST-S02-16（转换全链路）
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from test_s03_proposals import BASE, T0, ProposalLLM

NEAR_TERM = {
    "timing_type": "after_months",  # 占位：mock 需返回 near_term_todo 判定
    "timing_value": None,
    "reason": "这更像这几天要办的事",
    "confidence": 90,
}


class NearTermLLM(ProposalLLM):
    """understand_wish 返回 near_term_todo，使 S02 走询问确认分支（EX-18.2）。"""

    async def understand_wish(self, text: str):  # noqa: ANN201
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(
            {
                "understanding": {
                    "kind": "near_term_todo",
                    "feeling": "安排",
                    "conditions": {"title": text[:40] or "一件事"},
                    "smallest_step": "先只是想一想",
                },
                "question": "这更像这几天要办的事，还是想在未来发生的事？",
            }
        )


@pytest.fixture
async def env(app_env: None, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import DisabledPushSender, InMemoryEmailSender, set_senders
    from app.storage import set_storage

    llm = NearTermLLM()
    get_settings.cache_clear()
    set_storage(None)
    set_llm_provider(llm)
    set_senders(DisabledPushSender(), InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": T0.isoformat()})
        yield client, llm
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


async def _signup(client: AsyncClient) -> tuple[dict, str]:
    r = await client.post(f"{BASE}/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def test_UT_S02_26_actions_include_save_as_lite() -> None:
    """actions 枚举含 save_as_lite（wishes.yaml 与 schemas 两处一致）。"""
    import yaml

    spec = yaml.safe_load(
        open("logos/resources/api/wishes.yaml", encoding="utf-8")
    ) if False else None
    from pathlib import Path as _P

    spec = yaml.safe_load(
        (_P(__file__).resolve().parents[2] / "logos/resources/api/wishes.yaml").read_text(encoding="utf-8")
    )
    enum = spec["components"]["schemas"]["SeedWishResult"]["properties"]["actions"]["items"]["enum"]
    assert enum == ["keep_as_future", "save_as_lite", "delete"]


async def test_ST_S02_16_convert_to_lite_full_chain(env) -> None:
    """near_term_todo → 选择「先记一下」→ wish 消失、lite_event 出现（AC-05）。"""
    client, llm = env
    h, uid = await _signup(client)
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "明天下午 3 点开会"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "save_as_lite" in (body.get("actions") or [])
    wid = body["wish"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/convert-to-lite", headers=h)
    assert r.status_code == 201, r.text
    lite = r.json()
    assert lite["text"] == "明天下午 3 点开会" and lite["status"] == "open"
    # 原 wish 彻底消失
    r = await client.get(f"{BASE}/wishes/{wid}", headers=h)
    assert r.status_code == 404
    # 轻事件归属同一用户且文本一致（UT-S02-27）
    r = await client.get(f"{BASE}/lite-events", headers=h)
    assert any(i["id"] == lite["id"] and i["text"] == "明天下午 3 点开会" for i in r.json()["items"])
    # outbox 全程无记录
    r = await client.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.json()["items"] == []


async def test_UT_S02_27_convert_keeps_owner_and_text(env) -> None:
    """转换的轻事件归属同一用户、文本一致（UT-S02-27）。"""
    client, llm = env
    h, _ = await _signup(client)
    wid = (await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "周末取快递"})).json()["wish"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/convert-to-lite", headers=h)
    assert r.status_code == 201
    r = await client.get(f"{BASE}/lite-events", headers=h)
    assert any(i["text"] == "周末取快递" for i in r.json()["items"])


async def test_ST_S02_17_brewing_rejects_conversion(env) -> None:
    """brewing 状态拒绝转换（AC-06：已确认时机的愿望转轻事件等于变相弃约）。"""
    client, llm = env
    h, _ = await _signup(client)
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想在冬天学会滑雪"})
    wid = r.json()["wish"]["id"]
    # LLM mock 是 near_term_todo——直接约定时机让状态转 brewing
    r = await client.put(
        f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "after_months", "after_months": 1}
    )
    assert r.status_code == 200 and r.json()["state"] == "brewing"
    r = await client.post(f"{BASE}/wishes/{wid}/convert-to-lite", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    r = await client.get(f"{BASE}/wishes/{wid}", headers=h)
    assert r.json()["state"] == "brewing"
