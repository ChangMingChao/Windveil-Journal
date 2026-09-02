"""S07 唤回场景测试：真实 HTTP 闭环与编排契约。"""

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from test_s05_scenarios import (
    BASE,
    _add_pending_reminders,
    _at,
    _brewing,
    _pending_reminders,
    _seed,
    _signup,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def env(app_env: None, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import InMemoryEmailSender, set_senders
    from app.storage import set_storage
    from test_s05_scenarios import FakeLLM, T0

    get_settings.cache_clear()
    set_storage(None)
    set_llm_provider(FakeLLM())
    set_senders(None, InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post("/api/test/clock", json={"now": T0.isoformat()})
        yield client
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


def _flow():
    path = ROOT / "logos/resources/scenario/core-S07-recall.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_flow_contract_browse_let_go():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-01" for x in data["flows"])


def test_flow_contract_open_recall_sheet():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-02" for x in data["flows"])


def test_flow_contract_recall():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-03" for x in data["flows"])


def test_flow_contract_retime_after_recall():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-04" for x in data["flows"])


def test_flow_contract_empty_let_go():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-05" for x in data["flows"])


def test_flow_contract_foreign_wish():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-06" for x in data["flows"])


def test_flow_contract_conflict():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-07" for x in data["flows"])


def test_flow_contract_secondary_action():
    data = _flow()
    assert any(x["case_id"] == "ST-S07-08" for x in data["flows"])


async def test_ST_S07_01_browse_orders_by_let_go_time(env: AsyncClient) -> None:
    h, uid = await _signup(env)
    first = await _seed(env, h, "先放下的事")
    second = await _seed(env, h, "后放下的事")
    await _at(env, 10)
    assert (await env.post(f"{BASE}/wishes/{first}/let-go", headers=h)).status_code == 200
    await _at(env, 20)
    assert (await env.post(f"{BASE}/wishes/{second}/let-go", headers=h)).status_code == 200

    listed = await env.get(f"{BASE}/wishes", headers=h, params={"state": "let_go"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [second, first]
    assert "total" not in listed.json()
    assert await _pending_reminders(uid, first) == 0


async def test_ST_S07_02_open_recall_sheet_details(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    wid = await _seed(env, h, "想重新拿起画笔")
    assert (await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)).status_code == 200

    detail = await env.get(f"{BASE}/wishes/{wid}", headers=h)
    assert detail.status_code == 200
    body = detail.json()
    assert body["state"] == "let_go"
    assert body["original_text"]
    assert body["seeded_at"]
    assert body["let_go_at"]
    assert "timeline" in body

async def test_ST_S07_03_recall_preserves_content_and_clears_timing(env: AsyncClient) -> None:
    h, uid = await _signup(env)
    wid = await _brewing(env, h, "想重新拿起画笔")
    before = (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    await _add_pending_reminders(uid, wid, 2)
    assert (await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)).status_code == 200

    recalled = await env.post(f"{BASE}/wishes/{wid}/recall", headers=h)
    assert recalled.status_code == 200, recalled.text
    body = recalled.json()
    assert body["state"] == "seeded"
    assert body["let_go_at"] is None
    assert body["timing"]["type"] is None
    assert body["timing"]["next_trigger_at"] is None
    assert body["title"] == before["title"]
    assert body["original_text"] == before["original_text"]
    assert body["seeded_at"] == before["seeded_at"]
    assert await _pending_reminders(uid, wid) == 0


async def test_ST_S07_04_recalled_wish_can_be_timed_again(env: AsyncClient) -> None:
    h, uid = await _signup(env)
    wid = await _brewing(env, h, "等一个空闲周末")
    assert (await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)).status_code == 200
    assert (await env.post(f"{BASE}/wishes/{wid}/recall", headers=h)).status_code == 200

    retimed = await env.put(
        f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "free_weekend"}
    )
    assert retimed.status_code == 200, retimed.text
    assert retimed.json()["state"] == "brewing"
    assert retimed.json()["let_go_at"] is None
    assert await _pending_reminders(uid, wid) == 0


async def test_ST_S07_05_empty_let_go_returns_empty_without_count(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    listed = await env.get(f"{BASE}/wishes", headers=h, params={"state": "let_go"})
    assert listed.status_code == 200
    assert listed.json() == {"items": [], "next_cursor": None}


async def test_ST_S07_06_foreign_wish_is_hidden(env: AsyncClient) -> None:
    owner_headers, _ = await _signup(env)
    foreign_headers, _ = await _signup(env)
    wid = await _seed(env, owner_headers, "只属于第一个人")
    assert (await env.post(f"{BASE}/wishes/{wid}/let-go", headers=owner_headers)).status_code == 200
    recalled = await env.post(f"{BASE}/wishes/{wid}/recall", headers=foreign_headers)
    assert recalled.status_code == 404
    assert recalled.json()["code"] == "WISH_NOT_FOUND"


async def test_ST_S07_07_recall_is_conflict_after_first_success(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    wid = await _seed(env, h, "只回来一次")
    assert (await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)).status_code == 200
    assert (await env.post(f"{BASE}/wishes/{wid}/recall", headers=h)).status_code == 200
    conflict = await env.post(f"{BASE}/wishes/{wid}/recall", headers=h)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"


async def test_ST_S07_08_secondary_action_does_not_write(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    wid = await _seed(env, h, "再放一会儿")
    assert (await env.post(f"{BASE}/wishes/{wid}/let-go", headers=h)).status_code == 200
    before = (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    await _at(env, 60)
    after = (await env.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    assert after["state"] == "let_go"
    assert after["let_go_at"] == before["let_go_at"]
    assert after["version"] == before["version"]

