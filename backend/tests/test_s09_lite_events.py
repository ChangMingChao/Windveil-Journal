"""S09 轻量事件测试（lightweight-events）。

覆盖用例（批前声明）：
  - UT-S09-01 ~ UT-S09-12（12 个）
  - ST-S09-01 ~ ST-S09-04（4 个，编排 delta 同名 flow 的执行实现）
  - ST-S09-05 为 [manual]（P1 展开与空态文案走查），按规范不写 JSONL
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BASE = "/api/v1"


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
    assert r.status_code == 201
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


# ---------------------------------------------------------------- UT（HTTP）


async def test_UT_S09_01_text_length_bounds(env: AsyncClient) -> None:
    """text 必填且 1–200 字：空 / 201 字 / 200 字。"""
    h, _ = await _signup(env)
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": ""})
    assert r.status_code == 422
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "长" * 201})
    assert r.status_code == 422
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "长" * 200})
    assert r.status_code == 201, r.text


async def test_UT_S09_02_whitespace_only_rejected(env: AsyncClient) -> None:
    """全空白文本被拒（服务端双层防御），且不产生写入。"""
    h, _ = await _signup(env)
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "   "})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_FAILED"
    r = await env.get(f"{BASE}/lite-events", headers=h)
    assert r.json()["items"] == []


async def test_UT_S09_03_default_list_open_only(env: AsyncClient) -> None:
    """默认列表只含 open；include_done=true 时 done 也返回且 closed_at 非空。"""
    h, _ = await _signup(env)
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "第一条"})
    open_id = r.json()["id"]
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "第二条"})
    done_id = r.json()["id"]
    await env.post(f"{BASE}/lite-events/{done_id}/done", headers=h)
    r = await env.get(f"{BASE}/lite-events", headers=h)
    assert [i["id"] for i in r.json()["items"]] == [open_id]
    r = await env.get(f"{BASE}/lite-events", headers=h, params={"include_done": "true"})
    done = [i for i in r.json()["items"] if i["id"] == done_id]
    assert len(done) == 1 and done[0]["status"] == "done" and done[0]["closed_at"] is not None


async def test_UT_S09_04_post_echoes_save_confirmation(env: AsyncClient) -> None:
    """POST 响应回显保存确认：text 与提交一致（与偏好 value 的不回显策略不同）。"""
    h, _ = await _signup(env)
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "今晚吃火锅"})
    assert r.status_code == 201
    assert r.json()["text"] == "今晚吃火锅"
    assert r.json()["status"] == "open" and r.json()["closed_at"] is None


async def test_UT_S09_09_done_sets_closed_at(env: AsyncClient) -> None:
    """划掉置 done 并记 closed_at（S09 Step 15→17）。"""
    h, _ = await _signup(env)
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "一条"})
    eid = r.json()["id"]
    r = await env.post(f"{BASE}/lite-events/{eid}/done", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "done" and r.json()["closed_at"] is not None


async def test_UT_S09_10_double_done_conflict(env: AsyncClient) -> None:
    """对已划掉的事件重复 done → 409（幂等保护而非静默重放）。"""
    h, _ = await _signup(env)
    eid = (await env.post(f"{BASE}/lite-events", headers=h, json={"text": "一条"})).json()["id"]
    await env.post(f"{BASE}/lite-events/{eid}/done", headers=h)
    r = await env.post(f"{BASE}/lite-events/{eid}/done", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "LITE_EVENT_ALREADY_CLOSED"


async def test_UT_S09_11_delete_is_hard(env: AsyncClient) -> None:
    """删除为硬删除：重复 DELETE 404，include_done 也不返回。"""
    h, _ = await _signup(env)
    eid = (await env.post(f"{BASE}/lite-events", headers=h, json={"text": "一条"})).json()["id"]
    assert (await env.delete(f"{BASE}/lite-events/{eid}", headers=h)).status_code == 204
    r = await env.delete(f"{BASE}/lite-events/{eid}", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "LITE_EVENT_NOT_FOUND"
    r = await env.get(f"{BASE}/lite-events", headers=h, params={"include_done": "true"})
    assert all(i["id"] != eid for i in r.json()["items"])


async def test_UT_S09_12_cross_user_404(env: AsyncClient) -> None:
    """跨用户访问一律 404，不暴露存在性。"""
    ha, _ = await _signup(env)
    eid = (await env.post(f"{BASE}/lite-events", headers=ha, json={"text": "只给 A"})).json()["id"]
    hb, _ = await _signup(env)
    assert (await env.get(f"{BASE}/lite-events", headers=hb)).json()["items"] == []
    r = await env.post(f"{BASE}/lite-events/{eid}/done", headers=hb)
    assert r.status_code == 404 and r.json()["code"] == "LITE_EVENT_NOT_FOUND"
    r = await env.delete(f"{BASE}/lite-events/{eid}", headers=hb)
    assert r.status_code == 404


# ---------------------------------------------------------------- UT（DB）


def test_UT_S09_05_status_enum(raw_db) -> None:
    """status 只允许 open/done（lite_events.status CHECK）。"""
    uid = "00000000-0000-0000-0000-00000000e001"
    raw_db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    with pytest.raises(Exception, match="status IN"):
        raw_db.execute(
            "INSERT INTO lite_events (id, owner_id, text_enc, status)"
            " VALUES (?, ?, x'00', 'sent')",
            ("00000000-0000-0000-0000-00000000e0aa", uid),
        )
    raw_db.rollback()


def test_UT_S09_06_closed_state_pairing(raw_db) -> None:
    """done 与 closed_at 配对：缺一即违反 CHECK（两个方向都测）。"""
    uid = "00000000-0000-0000-0000-00000000e001"
    eid = "00000000-0000-0000-0000-00000000e0aa"
    raw_db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    base = (
        "INSERT INTO lite_events (id, owner_id, text_enc, status, closed_at)"
        " VALUES (?, ?, x'00', ?, ?)"
    )
    raw_db.execute(base, (eid, uid, "done", "2026-09-05T00:00:00.000Z"))
    with pytest.raises(Exception, match="lite_events_closed_state_pairing"):
        raw_db.execute(base, ("00000000-0000-0000-0000-00000000e0ab", uid, "done", None))
    with pytest.raises(Exception, match="lite_events_closed_state_pairing"):
        raw_db.execute(base, ("00000000-0000-0000-0000-00000000e0ac", uid, "open", "2026-09-05T00:00:00.000Z"))
    raw_db.rollback()


def test_UT_S09_07_partial_index_open_only(raw_db) -> None:
    """部分索引仅覆盖 status='open' 行（UT-S09-07）。"""
    uid = "00000000-0000-0000-0000-00000000e001"
    raw_db.execute("INSERT INTO users (id, is_anonymous) VALUES (?, 1)", (uid,))
    row = raw_db.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_lite_events_owner_open'"
    ).fetchone()
    assert row is not None, "idx_lite_events_owner_open 索引不存在"
    assert "WHERE status = 'open'" in (row[0] or ""), row[0]


def test_UT_S09_08_no_reminder_path_by_structure(raw_db) -> None:
    """三重无提醒路径（结构性，UT-S09-08）：无触发字段、调度扫描不引用、outbox 无关联。"""
    cols = {row[1] for row in raw_db.execute("PRAGMA table_info(lite_events)")}
    assert not any("trigger" in c or "reminder" in c for c in cols), cols
    assert not any("next_" in c for c in cols)
    # 调度扫描 SQL（app/scheduler.py）不引用 lite_events
    from pathlib import Path

    sched = Path(__file__).resolve().parents[1] / "app" / "scheduler.py"
    assert "lite_events" not in sched.read_text(encoding="utf-8")
    # outbox 外键指向 wishes，无轻事件关联路径
    fks = raw_db.execute("PRAGMA foreign_key_list(reminder_outbox)").fetchall()
    assert all(fk[2] != "lite_events" for fk in fks), "outbox 不得关联轻事件表"


# ---------------------------------------------------------------- ST


async def test_ST_S09_01_full_chain(env: AsyncClient) -> None:
    """记下 → 列表 → 划掉 → 收走全链路；outbox 全程无轻事件记录。"""
    h, uid = await _signup(env)
    r = await env.post(f"{BASE}/lite-events", headers=h, json={"text": "今晚吃火锅"})
    assert r.status_code == 201 and r.json()["text"] == "今晚吃火锅"
    event_a = r.json()["id"]
    event_b = (await env.post(f"{BASE}/lite-events", headers=h, json={"text": "周末取快递"})).json()["id"]
    r = await env.get(f"{BASE}/lite-events", headers=h)
    assert [i["text"] for i in r.json()["items"]] == ["周末取快递", "今晚吃火锅"]
    r = await env.post(f"{BASE}/lite-events/{event_a}/done", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    r = await env.get(f"{BASE}/lite-events", headers=h)
    assert [i["id"] for i in r.json()["items"]] == [event_b]
    assert (await env.delete(f"{BASE}/lite-events/{event_b}", headers=h)).status_code == 204
    r = await env.delete(f"{BASE}/lite-events/{event_b}", headers=h)
    assert r.status_code == 404
    # AC-02：outbox 全程无任何记录
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.status_code == 200 and r.json()["items"] == []


async def test_ST_S09_02_empty_and_too_long(env: AsyncClient) -> None:
    """空内容与超长内容双层拒绝，无任何写入。"""
    h, _ = await _signup(env)
    for bad in ({}, {"text": ""}, {"text": "   "}, {"text": "长" * 201}):
        r = await env.post(f"{BASE}/lite-events", headers=h, json=bad)
        assert r.status_code == 422, (bad, r.text)
    r = await env.get(f"{BASE}/lite-events", headers=h)
    assert r.json()["items"] == []


async def test_ST_S09_03_wishes_unaffected(env: AsyncClient) -> None:
    """轻事件与愿望互不干扰：操作轻事件后愿望与 outbox 全部不变。"""
    h, uid = await _signup(env)
    r = await env.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": "想在冬天学会滑雪"})
    wid = r.json()["wish"]["id"]
    before = (await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)).json()["items"]
    eid = (await env.post(f"{BASE}/lite-events", headers=h, json={"text": "随手记一条"})).json()["id"]
    await env.post(f"{BASE}/lite-events/{eid}/done", headers=h)
    r = await env.get(f"{BASE}/wishes/{wid}", headers=h)
    assert r.json()["state"] == "seeded" and r.json()["timing"]["label"] != ""
    r = await env.get("/api/test/outbox", params={"user_id": uid}, headers=h)
    assert r.json()["items"] == before


async def test_ST_S09_04_cross_user_isolated(env: AsyncClient) -> None:
    """跨用户隔离：B 的列表为空，对 A 的轻事件 done/delete 全部 404。"""
    ha, _ = await _signup(env)
    eid = (await env.post(f"{BASE}/lite-events", headers=ha, json={"text": "只给 A"})).json()["id"]
    hb, _ = await _signup(env)
    assert (await env.get(f"{BASE}/lite-events", headers=hb)).json()["items"] == []
    r = await env.post(f"{BASE}/lite-events/{eid}/done", headers=hb)
    assert r.status_code == 404 and r.json()["code"] == "LITE_EVENT_NOT_FOUND"
    r = await env.delete(f"{BASE}/lite-events/{eid}", headers=hb)
    assert r.status_code == 404
