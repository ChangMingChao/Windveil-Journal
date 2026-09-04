"""S08 场景测试：真实 HTTP 闭环（ST-S08-01 / 04 / 05）+ 加密落地（UT-S08-13）+ 跨午夜（UT-S08-14）。

ST-S08-06（摘要支线走 scheduler tick）与 ST-S08-02 / ST-S08-03（提议联动）在 Batch 9
随 proposals 服务同批交付；ST-S08-07 / ST-S08-08 为 [manual]，按规范不写 JSONL。
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


# ---------------------------------------------------------------- ST-S08-01


async def test_ST_S08_01_empty_then_declare_then_read_back(env: AsyncClient) -> None:
    """查看记忆：空 → 声明 → 读回（写响应不回显；GET 回显明文，仅本人）。"""
    h, _ = await _signup(env)
    r = await env.get(f"{BASE}/me/preferences", headers=h)
    assert r.status_code == 200
    assert r.json()["items"] == [] and r.json()["digest"] is None

    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["source"] == "declared" and meta["confidence"] == 100
    assert "value" not in meta

    r = await env.get(f"{BASE}/me/preferences", headers=h)
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["value"] == VALID["value"]
    assert items[0]["pref_key"] == "companion"


# ---------------------------------------------------------------- ST-S08-04


async def test_ST_S08_04_delete_leaves_no_shadow(env: AsyncClient) -> None:
    """删除偏好为硬删除，不留影子：重复删除 404、include_revoked 也不返回。"""
    h, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    pref_id = r.json()["id"]

    r = await env.delete(f"{BASE}/me/preferences/{pref_id}", headers=h)
    assert r.status_code == 204
    r = await env.delete(f"{BASE}/me/preferences/{pref_id}", headers=h)
    assert r.status_code == 404, r.text
    r = await env.get(f"{BASE}/me/preferences", headers=h, params={"include_revoked": "true"})
    assert all(i["id"] != pref_id for i in r.json()["items"])


# ---------------------------------------------------------------- ST-S08-05


async def test_ST_S08_05_availability_crud_and_invalid_input(env: AsyncClient) -> None:
    """时段管理与非法输入：201 → 422 无写入 → PATCH → DELETE 204 / 重复 404。"""
    h, _ = await _signup(env)
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720, "note": "上午有空"},
    )
    assert r.status_code == 201, r.text
    window = r.json()
    assert window["weekday"] == 5
    assert window["note"] == "上午有空", "note 是用户刚写下的备忘，保存响应原样返回"

    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 840, "end_minute": 780},
    )
    assert r.status_code == 422 and r.json()["code"] == "AVAILABILITY_INVALID"

    r = await env.patch(
        f"{BASE}/me/availability/{window['id']}", headers=h, json={"end_minute": 780}
    )
    assert r.status_code == 200, r.text
    assert r.json()["end_minute"] == 780

    r = await env.get(f"{BASE}/me/availability", headers=h)
    assert r.json()["items"][0]["note"] == "上午有空"

    r = await env.delete(f"{BASE}/me/availability/{window['id']}", headers=h)
    assert r.status_code == 204
    r = await env.delete(f"{BASE}/me/availability/{window['id']}", headers=h)
    assert r.status_code == 404


# ---------------------------------------------------------------- UT-S08-13


async def test_UT_S08_13_values_encrypted_at_rest(env: AsyncClient, sqlite_path: Path) -> None:
    """value_enc / note_enc 落库为密文：明文不进数据库（S08 加密落地）。"""
    import sqlite3

    h, _ = await _signup(env)
    r = await env.put(f"{BASE}/me/preferences", headers=h, json=VALID)
    assert r.status_code == 200
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 540, "end_minute": 720, "note": "孩子出门前都可以"},
    )
    assert r.status_code == 201

    raw = sqlite3.connect(sqlite_path)
    try:
        pv = raw.execute("SELECT value_enc FROM user_preferences").fetchone()[0]
        an = raw.execute("SELECT note_enc FROM availability_windows").fetchone()[0]
    finally:
        raw.close()
    if isinstance(pv, str):
        pv = pv.encode("utf-8", errors="ignore")
    if isinstance(an, str):
        an = an.encode("utf-8", errors="ignore")
    assert "朋友".encode() not in pv, "偏好值以密文落库，不得含明文子串"
    assert "孩子".encode() not in an, "时段备注以密文落库，不得含明文子串"


# ---------------------------------------------------------------- UT-S08-14


async def test_UT_S08_14_overnight_window_as_two_rows(env: AsyncClient) -> None:
    """跨午夜段拆两行提交（22:30–24:00 与 00:00–06:30），各自合法（S08 Step 23）。"""
    h, _ = await _signup(env)
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 5, "start_minute": 1350, "end_minute": 1440},
    )
    assert r.status_code == 201, r.text
    r = await env.post(
        f"{BASE}/me/availability",
        headers=h,
        json={"weekday": 6, "start_minute": 0, "end_minute": 390},
    )
    assert r.status_code == 201, r.text
    r = await env.get(f"{BASE}/me/availability", headers=h)
    assert len(r.json()["items"]) == 2
