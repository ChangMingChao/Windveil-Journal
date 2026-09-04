"""S08 与提议链路的交叉用例（Batch 9）。

覆盖用例（批前声明，接续 test_s08_*.py 的 UT-S08-01~16/18）：
  - UT-S08-17：撤回/删除偏好 → 引用它的 pending 建议立即失效（S08 Step 15 / 19）
  - UT-S08-19 / UT-S08-20：digest UPSERT 单行 / LLM 降级保持旧值不重试（EX-D2.1）
  - ST-S08-02：声明与推断并列（inferred 行由 fixture 注入，与编排 not_orchestrated 说明一致）
  - ST-S08-03：撤回推断 → 痕迹 → 联动失效 → confirm 409（EX-P.5）
  - ST-S08-06：摘要支线 D1–D4 走调度轮（生成、单份覆盖、降级保持）
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from test_s03_proposals import ProposalLLM, T0
from test_s05_scenarios import BASE
from test_s08_units import _inject_inferred

VALID = {"pref_key": "companion", "value": "更想和朋友一起做这些事"}


@pytest.fixture
async def env(app_env: None, tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, ProposalLLM]]:
    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.clock import clock
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.notify import DisabledPushSender, InMemoryEmailSender, set_senders
    from app.storage import set_storage

    llm = ProposalLLM()
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
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _fresh(uid: str) -> dict:
    import uuid as _uuid

    from app.security import issue_access_token

    return {"Authorization": f"Bearer {issue_access_token(_uuid.UUID(uid))}"}


# ---------------------------------------------------------------- ST-S08-02


async def test_ST_S08_02_declared_and_inferred_coexist(env) -> None:
    """声明与推断并列：同 key 两条并存，来源徽标字段齐全（S08 Step 9 / AC-01）。"""
    client, llm = env
    h, uid = await _signup(client)
    await _inject_inferred(client, uid, key="companion")
    r = await client.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    assert r.status_code == 200, r.text
    r = await client.get(f"{BASE}/me/preferences", headers=h)
    rows = [i for i in r.json()["items"] if i["pref_key"] == "companion"]
    assert len(rows) == 2
    assert {i["source"] for i in rows} == {"declared", "inferred"}
    inferred = next(i for i in rows if i["source"] == "inferred")
    assert inferred["confidence"] == 60 and inferred["revoked_at"] is None
    declared = next(i for i in rows if i["source"] == "declared")
    assert declared["value"] == VALID["value"]


# ---------------------------------------------------------------- ST-S08-03 / UT-S08-17


async def test_ST_S08_03_revoke_inferred_expires_pending_proposal(env) -> None:
    """撤回推断 → 默认列表消失 → 引用它的 pending 建议立即失效 → confirm 409（EX-P.5）。"""
    client, llm = env
    h, uid = await _signup(client)
    rid = await _inject_inferred(client, uid, key="companion")
    # 生成建议：bounded_context 会把 inferred 行放进 evidence
    wid = (
        await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想去学陶艺"})
    ).json()["wish"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["status"] == "pending"
    assert any(
        e["kind"] == "preference" and e["id"] == rid for e in p["evidence"]
    ), "生成的建议应引用注入的推断条目"
    # 撤回（S08 Step 12→16）
    r = await client.post(f"{BASE}/me/preferences/{rid}/revoke", headers=h)
    assert r.status_code == 200, r.text
    r = await client.get(f"{BASE}/me/preferences", headers=h)
    assert all(i["id"] != rid for i in r.json()["items"])
    # 联动失效：提议 expired，confirm 409（同事务，S08 Step 15）
    r = await client.get(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert next(i for i in r.json()["items"] if i["id"] == p["id"])["status"] == "expired"
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals/{p['id']}/confirm", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PROPOSAL_EXPIRED"


async def test_UT_S08_17_delete_preference_expires_pending_proposal(env) -> None:
    """删除偏好同样同事务失效 pending 建议（S08 Step 19）。"""
    client, llm = env
    h, uid = await _signup(client)
    r = await client.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    pid = r.json()["id"]
    wid = (
        await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想去看一次日出"})
    ).json()["wish"]["id"]
    r = await client.post(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    proposal_id = r.json()["proposal"]["id"]
    r = await client.delete(f"{BASE}/me/preferences/{pid}", headers=h)
    assert r.status_code == 204
    r = await client.get(f"{BASE}/wishes/{wid}/timing-proposals", headers=h)
    assert next(i for i in r.json()["items"] if i["id"] == proposal_id)["status"] == "expired"


# ---------------------------------------------------------------- UT-S08-19 / 20


async def _ensure_user(owner: str) -> None:
    from sqlalchemy import text

    from app.db import get_sessionmaker

    session = get_sessionmaker()()
    try:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO users (id, is_anonymous, timezone) "
                    "VALUES (:id, 1, 'Asia/Shanghai') ON CONFLICT DO NOTHING"
                ),
                {"id": owner},
            )
    finally:
        await session.close()


async def test_UT_S08_19_digest_upsert_keeps_single_row(app_env: None) -> None:
    """digest UPSERT 只保留最近一份（S08 D4）。"""
    from app.preferences import upsert_digest

    owner = "00000000-0000-0000-0000-00000000d001"
    await _ensure_user(owner)
    assert await upsert_digest(owner, "第一版摘要") is True
    assert await upsert_digest(owner, "第二版摘要") is True
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import UserPreference

    session = get_sessionmaker()()
    try:
        rows = (
            (
                await session.execute(
                    select(UserPreference).where(
                        UserPreference.owner_id == owner, UserPreference.kind == "digest"
                    )
                )
            )
            .scalars()
            .all()
        )
    finally:
        await session.close()
    assert len(rows) == 1 and rows[0].value_enc == "第二版摘要"
    assert rows[0].source == "inferred"


async def test_UT_S08_20_digest_degradation_keeps_old_value(app_env: None) -> None:
    """LLM 降级（summary=None）：旧 digest 保持不变、无重试队列（EX-D2.1）。"""
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import UserPreference
    from app.preferences import upsert_digest

    owner = "00000000-0000-0000-0000-00000000d002"
    await _ensure_user(owner)
    await upsert_digest(owner, "旧的理解")
    changed = await upsert_digest(owner, None)
    assert changed is True, "已有旧值时返回 True（保持）"
    session = get_sessionmaker()()
    try:
        row = (
            await session.execute(
                select(UserPreference).where(UserPreference.owner_id == owner)
            )
        ).scalar_one()
    finally:
        await session.close()
    assert row.value_enc == "旧的理解"
    assert await upsert_digest("00000000-0000-0000-0000-00000000d003", None) is False, (
        "无旧值且降级：digest 保持缺失，返回 False"
    )


# ---------------------------------------------------------------- ST-S08-06


async def test_ST_S08_06_digest_via_scheduler_tick(env) -> None:
    """摘要支线走调度轮：生成 → 单份覆盖 → LLM 降级保持（D1–D4 / EX-D2.1）。"""
    client, llm = env
    h, uid = await _signup(client)
    r = await client.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    assert r.status_code == 200
    assert (await client.post("/api/test/scheduler/tick")).status_code == 200
    r = await client.get(f"{BASE}/me/preferences", headers=h)
    assert r.json()["digest"] is not None
    assert r.json()["digest"]["kind"] == "digest"
    assert r.json()["digest"]["source"] == "inferred"
    first = r.json()["digest"]["value"]
    # 时钟推进 1 天（超过 DIGEST_INTERVAL）+ LLM 降级：旧 digest 保持
    await client.post("/api/test/clock", json={"now": (T0 + timedelta(days=2)).isoformat()})
    llm.mode = "unavailable"
    r = await client.post("/api/test/scheduler/tick")
    assert r.status_code == 200
    r = await client.get(f"{BASE}/me/preferences", headers=_fresh(uid))
    assert r.json()["digest"]["value"] == first, "降级时保持旧摘要"
    assert r.json()["digest"]["value"] == "他更想和朋友一起做这些事，节奏上想慢一点。"
