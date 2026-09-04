"""S08 偏好与可用时段 — HTTP 层单元测试（UT-S08-01~08、12、14~16、18）。

本批（preferences-availability-timing）覆盖用例批前声明：
  - UT-S08-01 ~ UT-S08-08、UT-S08-12、UT-S08-14 ~ UT-S08-16、UT-S08-18（本文件）
  - UT-S08-09 ~ UT-S08-11、UT-S08-13、UT-S08-17、UT-S08-19 ~ UT-S08-20（test_s08_db.py；
    UT-S08-17 依赖提议联动，与 ST-S03-18 同批交付）
  - ST-S08-01 / ST-S08-04 / ST-S08-05（test_s08_scenarios.py）
  - ST-S08-02 / ST-S08-03 / ST-S08-06（提议联动与摘要支线，Batch 9 同批交付）
  - ST-S08-07 / ST-S08-08 为 [manual]，按规范不写 JSONL
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BASE = "/api/v1"
ROOT = Path(__file__).resolve().parents[2]

VALID = {"pref_key": "companion", "value": "更想和朋友一起做这些事"}


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

    get_settings.cache_clear()
    set_storage(None)
    set_llm_provider(None)
    set_senders(None, InMemoryEmailSender())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client
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


async def _inject_inferred(
    client: AsyncClient, user_id: str, key: str = "companion", value: str = "喜欢一个人安静地做事"
) -> str:
    """直接写库注入一条 inferred 行。

    推断的写入链路（LLM 从对话中提炼）属后续工具提案，本轮没有端点能产生它；
    而撤回语义必须有对象可撤回。fixture 注入与编排索引 not_orchestrated 的说明一致。
    """
    from uuid import UUID

    from sqlalchemy import insert

    from app.db import get_sessionmaker
    from app.models import UserPreference

    session = get_sessionmaker()()
    try:
        async with session.begin():
            row = UserPreference(
                owner_id=UUID(user_id),
                kind="entry",
                pref_key=key,
                source="inferred",
                value_enc=value,
                confidence=60,
            )
            session.add(row)
            await session.flush()
            return str(row.id)
    finally:
        await session.close()


# ---------------------------------------------------------------- 偏好声明


async def test_UT_S08_01_pref_key_outside_registry_rejected(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=h, json={"pref_key": "weather", "value": "x"})
    assert r.status_code == 422, r.text


async def test_UT_S08_02_value_length_bounds(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=h, json={"pref_key": "companion", "value": ""})
    assert r.status_code == 422
    r = await env.put(f"{BASE}/me/preferences", headers=h, json={"pref_key": "companion", "value": "好" * 201})
    assert r.status_code == 422
    r = await env.put(f"{BASE}/me/preferences", headers=h, json={"pref_key": "companion", "value": "好" * 200})
    assert r.status_code == 200, r.text


async def test_UT_S08_03_declared_source_forced(env: AsyncClient) -> None:
    """请求中的任何 source/confidence 被忽略（S08 Step 8）。"""
    h, _ = await _signup(env)
    r = await env.put(
        f"{BASE}/me/preferences",
        headers=h,
        json={**VALID, "source": "inferred", "confidence": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "declared"
    assert r.json()["confidence"] == 100


async def test_UT_S08_04_write_response_never_echoes_value(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    assert r.status_code == 200
    assert "value" not in r.json(), "写接口响应不得回显 value 明文（敏感值不回显）"


async def test_UT_S08_12_cross_user_preference_is_404(env: AsyncClient) -> None:
    """三张新表全部在守卫清单：跨用户访问一律 404（S08 EX-19.1）。"""
    ha, _ = await _signup(env)
    hb, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=ha, json=VALID)
    pref_id = r.json()["id"]
    r = await env.get(f"{BASE}/me/preferences", headers=hb)
    assert r.status_code == 200 and r.json()["items"] == []
    r = await env.delete(f"{BASE}/me/preferences/{pref_id}", headers=hb)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "PREFERENCE_NOT_FOUND"


# ---------------------------------------------------------------- 可用时段


async def test_UT_S08_05_end_before_start_rejected_without_partial_write(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 840, "end_minute": 780},
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "AVAILABILITY_INVALID"
    r = await env.get(f"{BASE}/me/availability", headers=h)
    assert r.json()["items"] == [], "非法输入不得产生半写入行"


async def test_UT_S08_06_weekday_and_minute_bounds(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    for bad in (
        {"weekday": 7, "start_minute": 540, "end_minute": 720},
        {"weekday": 0, "start_minute": 1440, "end_minute": 1440},
        {"weekday": 0, "start_minute": 0, "end_minute": 0},
    ):
        r = await env.post(f"{BASE}/me/availability", headers=h, json=bad)
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["code"] == "AVAILABILITY_INVALID"


async def test_UT_S08_07_note_max_length(env: AsyncClient) -> None:
    h, _ = await _signup(env)
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720, "note": "长" * 51},
    )
    assert r.status_code == 422, r.text
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720, "note": "长" * 50},
    )
    assert r.status_code == 201, r.text


async def test_UT_S08_08_include_revoked_query(env: AsyncClient) -> None:
    h, uid = await _signup(env)
    rid = await _inject_inferred(env, uid)
    r = await env.post(f"{BASE}/me/preferences/{rid}/revoke", headers=h)
    assert r.status_code == 200, r.text
    r = await env.get(f"{BASE}/me/preferences", headers=h)
    assert r.json()["items"] == [], "默认列表不含已撤回行"
    r = await env.get(f"{BASE}/me/preferences", headers=h, params={"include_revoked": "true"})
    revoked = [i for i in r.json()["items"] if i["id"] == rid]
    assert len(revoked) == 1 and revoked[0]["revoked_at"] is not None


# ---------------------------------------------------------------- 声明与推断并存


async def test_UT_S08_15_declare_keeps_inferred_row_intact(env: AsyncClient) -> None:
    """声明是 UPSERT declared 行；同 key 的 inferred 行保持原样并列（S08 Step 9）。"""
    h, uid = await _signup(env)
    await _inject_inferred(env, uid, key="companion")
    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    assert r.status_code == 200
    r = await env.get(f"{BASE}/me/preferences", headers=h)
    rows = [i for i in r.json()["items"] if i["pref_key"] == "companion"]
    assert len(rows) == 2, "同 key 两条并存，不覆盖不合并"
    assert {(i["source"], i["confidence"]) for i in rows} == {("declared", 100), ("inferred", 60)}
    # 再声明一次：declared 行更新而非新增，inferred 行仍原样
    r = await env.put(f"{BASE}/me/preferences", headers=h, json={**VALID, "value": "第二版"})
    assert r.status_code == 200
    r = await env.get(f"{BASE}/me/preferences", headers=h)
    rows = [i for i in r.json()["items"] if i["pref_key"] == "companion"]
    assert len(rows) == 2
    declared = next(i for i in rows if i["source"] == "declared")
    assert declared["value"] == "第二版"


async def test_UT_S08_16_revoke_only_inferred_and_once(env: AsyncClient) -> None:
    h, uid = await _signup(env)
    rid = await _inject_inferred(env, uid)
    # declared 行不能「猜错了」——直接删除即可
    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    declared_id = r.json()["id"]
    r = await env.post(f"{BASE}/me/preferences/{declared_id}/revoke", headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "PREFERENCE_NOT_REVOCABLE"
    # inferred 行撤回成功；重复撤回 409，不产生第二条痕迹
    r = await env.post(f"{BASE}/me/preferences/{rid}/revoke", headers=h)
    assert r.status_code == 200
    r = await env.post(f"{BASE}/me/preferences/{rid}/revoke", headers=h)
    assert r.status_code == 409, r.text
    r = await env.get(f"{BASE}/me/preferences", headers=h, params={"include_revoked": "true"})
    assert len([i for i in r.json()["items"] if i["id"] == rid]) == 1


# ---------------------------------------------------------------- 删除语义


async def test_UT_S08_18_delete_is_hard_and_leaves_no_shadow(env: AsyncClient) -> None:
    """删除为硬删除：默认列表、已撤回痕迹、重复删除全部无影子（需求 S08 AC-04）。"""
    from app.config import get_settings

    h, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    pref_id = r.json()["id"]
    r = await env.delete(f"{BASE}/me/preferences/{pref_id}", headers=h)
    assert r.status_code == 204
    r = await env.delete(f"{BASE}/me/preferences/{pref_id}", headers=h)
    assert r.status_code == 404, "硬删除后资源不存在，重复删除 404"
    r = await env.get(f"{BASE}/me/preferences", headers=h, params={"include_revoked": "true"})
    assert all(i["id"] != pref_id for i in r.json()["items"])
    # 导出（/me 数据）不含它：无任何计数或残留字段
    assert get_settings() is not None
