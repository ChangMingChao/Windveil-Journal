"""S06 场景测试（端到端 HTTP）。

覆盖 UT-S06-01 ~ UT-S06-15（HTTP 层字段与状态断言）与 ST-S06-01 ~ ST-S06-13。
ST-S06-14 / ST-S06-15 为 [manual]（纸质背景对比度与屏幕阅读器、书页合起动效与
reduced-motion），按规范不写 JSONL。

时间线：愿望种在 2026-09-01，事情发生在 10 月，记忆写在 2026-10-19。
`_write_day()` 负责推时钟并换一张新的 access token——固定时钟跨过 15 分钟有效期后
旧令牌必然过期，这不是被测行为，只是测试自己要处理的事。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

BASE = "/api/v1"
T_SEED = "2026-09-01T12:00:00+08:00"
T_WRITE = "2026-10-19T12:00:00+08:00"


class FakeLLM:
    """mode="down" 时 draft_memory 返回 None，用于 EX-7.1 的降级路径。"""

    def __init__(self) -> None:
        self.mode = "ok"
        self.draft_calls = 0

    async def understand_wish(self, text: str):  # noqa: ANN201
        from app.agent import UnderstandResult

        return UnderstandResult.model_validate(
            {
                "understanding": {
                    "kind": "future_wish",
                    "feeling": "喘口气",
                    "conditions": {"title": text[:40] or "一件还没发生的事"},
                    "smallest_step": "先只是想一想",
                },
                "question": "更像一次独处吗？",
            }
        )

    async def next_step(self, *, original_text, feeling, rejected):  # noqa: ANN001, ANN201, ARG002
        from app.agent import StepSuggestion

        return StepSuggestion(
            text=f"只是想一想那片海（第 {len(rejected) + 1} 次）",
            est_minutes=2,
            involves_cost=False,
            involves_others=False,
        )

    async def classify_message(self, *, text, original_text):  # noqa: ANN001, ANN201, ARG002
        from app.agent import MessageReply

        return MessageReply(intent="chat", reply="嗯，我记着")

    async def draft_memory(self, *, original_text, feeling, timeline):  # noqa: ANN001, ANN201
        from app.agent import MemoryDraft

        self.draft_calls += 1
        if self.mode == "down":
            return None
        return MemoryDraft(
            title="那两天你真的去了海边",
            cause=f"你原本想{feeling or '喘口气'}。",
            process="；".join(timeline) if timeline else None,
        )


@pytest.fixture
async def env(app_env: None, tmp_path) -> AsyncIterator[tuple[AsyncClient, FakeLLM]]:  # noqa: ANN001
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
        await client.post("/api/test/clock", json={"now": T_SEED})
        yield client, llm
    clock.set_fixed(None)
    set_llm_provider(None)
    set_senders(None, None)
    set_storage(None)
    await dispose_engines()


# ---------------------------------------------------------------- HTTP 助手


def _fresh(uid: str) -> dict:
    from app.security import issue_access_token

    return {"Authorization": f"Bearer {issue_access_token(uuid.UUID(uid))}"}


async def _signup(client: AsyncClient) -> tuple[dict, str]:
    r = await client.post(f"{BASE}/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


async def _write_day(client: AsyncClient, uid: str) -> dict:
    """推到写记忆的那天，并换一张新令牌（旧的已经跨过 15 分钟有效期）。"""
    assert (
        await client.post("/api/test/clock", json={"now": T_WRITE})
    ).status_code == 204
    return _fresh(uid)


async def _seed(client: AsyncClient, h: dict, text: str) -> str:
    r = await client.post(f"{BASE}/wishes", headers=h, json={"source": "text", "text": text})
    assert r.status_code == 201, r.text
    return r.json()["wish"]["id"]


async def _complete_step(client: AsyncClient, h: dict, wid: str) -> None:
    detail = (await client.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    step = (await client.post(f"{BASE}/wishes/{wid}/steps/next", headers=h)).json()["step"]
    r = await client.post(
        f"{BASE}/wishes/{wid}/steps/{step['id']}/done",
        headers={**h, "If-Match": str(detail["version"])},
    )
    assert r.status_code == 200, r.text


async def _going(client: AsyncClient, h: dict, text: str, steps: int = 1) -> str:
    """种下 → 设时机 → ready → 完成 N 步，得到 state=going 且 timeline 有 N 条。"""
    wid = await _seed(client, h, text)
    assert (
        await client.put(f"{BASE}/wishes/{wid}/timing", headers=h, json={"type": "free_weekend"})
    ).status_code == 200
    assert (await client.post(f"{BASE}/wishes/{wid}/ready", headers=h)).status_code == 200
    for _ in range(steps):
        await _complete_step(client, h, wid)
    return wid


async def _upload_photo(client: AsyncClient, h: dict) -> str:
    r = await client.post(
        f"{BASE}/media/upload-url",
        headers=h,
        json={"kind": "image", "content_type": "image/jpeg", "size_bytes": 2048},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    put = await client.put(data["upload_url"], content=b"\xff\xd8\xff" + b"x" * 2045)
    assert put.status_code == 200, put.text
    assert (
        await client.post(f"{BASE}/media/{data['media_id']}/complete", headers=h)
    ).status_code == 204
    return data["media_id"]


async def _happened(client: AsyncClient, h: dict, wid: str, **body) -> tuple[int, dict]:  # noqa: ANN003
    r = await client.post(f"{BASE}/wishes/{wid}/happened", headers=h, json=body)
    return r.status_code, r.json() if r.content else {}


async def _draft(client: AsyncClient, h: dict, wid: str, **body) -> dict:  # noqa: ANN003
    body.setdefault("happened_from", "2026-10-17")
    status, payload = await _happened(client, h, wid, **body)
    assert status == 201, payload
    return payload


async def _pending_count(owner_id: str, wish_id: str) -> int:
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models import ReminderOutbox

    owner = uuid.UUID(owner_id)
    async with session_scope(owner) as s:
        return await s.scalar(
            select(func.count())
            .select_from(ReminderOutbox)
            .where(
                ReminderOutbox.owner_id == owner,
                ReminderOutbox.wish_id == uuid.UUID(wish_id),
                ReminderOutbox.status == "pending",
            )
        )


async def _add_pending(owner_id: str, wish_id: str, count: int) -> None:
    from app.db import session_scope
    from app.models import ReminderOutbox

    owner = uuid.UUID(owner_id)
    async with session_scope(owner) as s:
        for n in range(count):
            s.add(
                ReminderOutbox(
                    id=uuid.uuid4(),
                    owner_id=owner,
                    wish_id=uuid.UUID(wish_id),
                    kind="timing",
                    timing_occurrence=f"pending-{n}",
                    body_enc="到了那个时候",
                    status="pending",
                )
            )


async def _row_count(table: str, column: str, value: str) -> int:
    from sqlalchemy import text as sql_text

    from app.db import owner_guard_bypass, session_scope

    # 计数只为断言级联结果，与 owner 维度无关；显式声明一次跨 owner 查询
    with owner_guard_bypass():
        async with session_scope() as s:
            return (
                await s.execute(
                    sql_text(f"SELECT count(*) FROM {table} WHERE {column} = :v"),  # noqa: S608
                    {"v": value},
                )
            ).scalar_one()


# ---------------------------------------------------------------- UT（HTTP 层）


async def test_UT_S06_01_happened_from_is_required(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    status, body = await _happened(client, h, wid)
    assert status == 422
    assert body["code"] == "VALIDATION_FAILED"


async def test_UT_S06_02_happened_from_must_be_a_date(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    status, body = await _happened(client, h, wid, happened_from="2026/10/17")
    assert status == 422
    assert body["code"] == "VALIDATION_FAILED"


async def test_UT_S06_03_happened_to_may_be_omitted(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    body = await _draft(client, h, wid, happened_from="2026-10-17")
    assert body["memory"]["happened_to"] is None


async def test_UT_S06_04_future_date_is_rejected(env) -> None:  # noqa: ANN001
    """今天是 2026-09-01，明天还没有到。"""
    client, _ = env
    h, _ = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    status, body = await _happened(client, h, wid, happened_from="2026-09-02")
    assert status == 422
    assert body["code"] == "HAPPENED_DATE_IN_FUTURE"


async def test_UT_S06_05_today_is_accepted(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _ = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    body = await _draft(client, h, wid, happened_from="2026-09-01")
    assert body["memory"]["happened_from"] == "2026-09-01"
    assert body["warning"] is None


async def test_UT_S06_06_inverted_range_is_rejected(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    status, body = await _happened(
        client, h, wid, happened_from="2026-10-18", happened_to="2026-10-17"
    )
    assert status == 422
    assert body["code"] == "HAPPENED_RANGE_INVALID"


async def test_UT_S06_07_equal_range_is_accepted(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    body = await _draft(client, h, wid, happened_from="2026-10-17", happened_to="2026-10-17")
    assert body["memory"]["happened_to"] == "2026-10-17"


async def _fresh_draft(
    client: AsyncClient, text: str = "想一个人去海边待两天"
) -> tuple[dict, str, str]:
    """建号 → going → 推到写记忆的那天 → 建草稿。返回 (headers, uid, memory_id)。"""
    h, uid = await _signup(client)
    wid = await _going(client, h, text)
    h = await _write_day(client, uid)
    body = await _draft(client, h, wid)
    return h, uid, body["memory"]["id"]


async def test_UT_S06_08_mood_enum_is_closed(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _, memory_id = await _fresh_draft(client)
    r = await client.patch(f"{BASE}/memories/{memory_id}", headers=h, json={"mood": "excited"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S06_09_mood_may_be_null(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _, memory_id = await _fresh_draft(client)
    assert (
        await client.patch(f"{BASE}/memories/{memory_id}", headers=h, json={"mood": "calm"})
    ).json()["mood"] == "calm"
    r = await client.patch(f"{BASE}/memories/{memory_id}", headers=h, json={"mood": None})
    assert r.status_code == 200, r.text
    assert r.json()["mood"] is None


async def test_UT_S06_10_all_fields_may_be_cleared(env) -> None:  # noqa: ANN001
    """「跳过全部补充内容」是明确的验收条件，所以不存在任何非空校验。"""
    client, _ = env
    h, _, memory_id = await _fresh_draft(client)
    r = await client.patch(
        f"{BASE}/memories/{memory_id}",
        headers=h,
        json={
            "title": None,
            "cause": None,
            "process": None,
            "mood": None,
            "last_line": None,
            "voice_media_id": None,
            "photo_media_ids": [],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == ""  # title_enc 是 NOT NULL，清空落库为空字符串
    assert body["cause"] is None
    assert body["process"] is None
    assert body["last_line"] is None
    assert body["photo_media_ids"] == []


async def test_UT_S06_11_patch_requires_at_least_one_field(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _, memory_id = await _fresh_draft(client)
    r = await client.patch(f"{BASE}/memories/{memory_id}", headers=h, json={})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S06_12_field_length_boundaries(env) -> None:  # noqa: ANN001
    client, _ = env
    h, _, memory_id = await _fresh_draft(client)
    for field, limit in (("title", 80), ("cause", 2000), ("process", 4000), ("last_line", 300)):
        ok = await client.patch(
            f"{BASE}/memories/{memory_id}", headers=h, json={field: "字" * limit}
        )
        assert ok.status_code == 200, f"{field}={limit}: {ok.text}"
        too_long = await client.patch(
            f"{BASE}/memories/{memory_id}", headers=h, json={field: "字" * (limit + 1)}
        )
        assert too_long.status_code == 422, f"{field}={limit + 1}"
        assert too_long.json()["code"] == "VALIDATION_FAILED"


async def test_UT_S06_13_photo_count_boundary(env) -> None:  # noqa: ANN001
    """maxItems: 9。第 10 张由长度先拦，不会掩饰成 404。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    photos = [await _upload_photo(client, h) for _ in range(9)]
    h = await _write_day(client, uid)
    memory_id = (await _draft(client, h, wid))["memory"]["id"]

    ok = await client.patch(
        f"{BASE}/memories/{memory_id}", headers=h, json={"photo_media_ids": photos}
    )
    assert ok.status_code == 200, ok.text
    assert len(ok.json()["photo_media_ids"]) == 9

    too_many = await client.patch(
        f"{BASE}/memories/{memory_id}",
        headers=h,
        json={"photo_media_ids": [*photos, str(uuid.uuid4())]},
    )
    assert too_many.status_code == 422
    assert too_many.json()["code"] == "MEDIA_LIMIT_EXCEEDED"


async def test_UT_S06_14_foreign_media_returns_404(env) -> None:  # noqa: ANN001
    client, _ = env
    h_b, _ = await _signup(client)
    foreign = await _upload_photo(client, h_b)

    h_a, _, memory_id = await _fresh_draft(client)
    r = await client.patch(
        f"{BASE}/memories/{memory_id}", headers=h_a, json={"photo_media_ids": [foreign]}
    )
    assert r.status_code == 404
    assert r.json()["code"] == "MEDIA_NOT_FOUND"


async def test_UT_S06_15_one_memory_per_wish(env) -> None:  # noqa: ANN001
    """memories.wish_id UNIQUE：重复标记已发生返回既有草稿，不新建、也不重新花一次 LLM。"""
    client, llm = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)

    first = await _draft(client, h, wid, happened_from="2026-10-17")
    calls_after_first = llm.draft_calls
    second = await _draft(client, h, wid, happened_from="2026-10-18")

    assert second["memory"]["id"] == first["memory"]["id"]
    assert llm.draft_calls == calls_after_first  # 没有再草拟一次
    assert second["memory"]["happened_to"] is None
    assert second["memory"]["happened_from"] == "2026-10-18"  # 重复提交视为改日期
    assert await _row_count("memories", "wish_id", wid) == 1


# ---------------------------------------------------------------- ST：主路径


async def test_ST_S06_01_draft_enrich_and_publish(env) -> None:  # noqa: ANN001
    """Step 1→20 全链路：草拟 → 补心情/一句话/照片 → 收进书里。"""
    from app.config import get_settings

    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天", steps=3)
    photos = [await _upload_photo(client, h), await _upload_photo(client, h)]
    await _add_pending(uid, wid, 2)
    h = await _write_day(client, uid)

    body = await _draft(client, h, wid, happened_from="2026-10-17", happened_to="2026-10-18")
    memory = body["memory"]
    assert body["degraded"] is False
    assert body["warning"] is None
    assert memory["status"] == "draft"
    assert memory["title"] and memory["cause"] and memory["process"]
    # 「≤5 秒返回」是 LLM 超时预算，落在配置上而不是这条断言上
    assert get_settings().LLM_TIMEOUT_SECONDS <= 5
    # Step 6：标记已发生就停提醒
    assert await _pending_count(uid, wid) == 0

    patched = await client.patch(
        f"{BASE}/memories/{memory['id']}",
        headers=h,
        json={
            "mood": "relieved",
            "last_line": "海比我想的更安静。",
            "photo_media_ids": photos,
        },
    )
    assert patched.status_code == 200, patched.text
    saved = patched.json()
    assert saved["mood"] == "relieved"
    assert saved["last_line"] == "海比我想的更安静。"
    assert saved["photo_media_ids"] == photos
    assert saved["cover_media_id"] == photos[0]
    assert await _row_count("memory_photos", "memory_id", memory["id"]) == 2

    published = await client.post(f"{BASE}/memories/{memory['id']}/publish", headers=h)
    assert published.status_code == 200, published.text
    assert published.json()["memory"]["status"] == "published"
    assert published.json()["memory"]["published_at"] is not None
    assert (await client.get(f"{BASE}/wishes/{wid}", headers=h)).json()["state"] == "happened"

    shelf = await client.get(f"{BASE}/memories", headers=h)
    assert shelf.status_code == 200
    assert shelf.json()["lived_pages"] == 1
    assert [i["id"] for i in shelf.json()["items"]] == [memory["id"]]


async def test_ST_S06_02_publish_without_any_enrichment(env) -> None:  # noqa: ANN001
    """跳过全部补充内容直接发布，并且发布后仍然可以继续补。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    memory = (await _draft(client, h, wid))["memory"]

    r = await client.post(f"{BASE}/memories/{memory['id']}/publish", headers=h)
    assert r.status_code == 200, r.text
    page = r.json()["memory"]
    assert page["status"] == "published"
    assert page["mood"] is None
    assert page["last_line"] is None
    assert page["photo_media_ids"] == []
    assert page["voice_media_id"] is None

    later = await client.patch(
        f"{BASE}/memories/{memory['id']}", headers=h, json={"last_line": "后来我又想起它。"}
    )
    assert later.status_code == 200, later.text
    assert later.json()["last_line"] == "后来我又想起它。"
    assert later.json()["status"] == "published"


async def test_ST_S06_03_single_day(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    memory = (await _draft(client, h, wid, happened_from="2026-10-17"))["memory"]
    assert memory["happened_from"] == "2026-10-17"
    assert memory["happened_to"] is None


async def test_ST_S06_04_shelf_is_ordered_by_happened_date(env) -> None:  # noqa: ANN001
    """Step 20：书架按发生时间倒序；无图的那页 cover_media_id 为 null。"""
    client, _ = env
    h, uid = await _signup(client)
    wids = [await _going(client, h, f"第 {i} 件事") for i in range(3)]
    photo = await _upload_photo(client, h)
    h = await _write_day(client, uid)

    days = ["2026-09-20", "2026-10-05", "2026-10-17"]
    ids = []
    for wid, day in zip(wids, days, strict=True):
        memory = (await _draft(client, h, wid, happened_from=day))["memory"]
        ids.append(memory["id"])
        assert (
            await client.post(f"{BASE}/memories/{memory['id']}/publish", headers=h)
        ).status_code == 200
    assert (
        await client.patch(
            f"{BASE}/memories/{ids[0]}", headers=h, json={"photo_media_ids": [photo]}
        )
    ).status_code == 200

    shelf = (await client.get(f"{BASE}/memories", headers=h)).json()
    assert shelf["lived_pages"] == 3
    assert [i["id"] for i in shelf["items"]] == list(reversed(ids))
    assert [i["happened_from"] for i in shelf["items"]] == list(reversed(days))
    covers = {i["id"]: i["cover_media_id"] for i in shelf["items"]}
    assert covers[ids[0]] == photo
    assert covers[ids[1]] is None
    assert covers[ids[2]] is None


# ---------------------------------------------------------------- ST：异常路径


async def test_ST_S06_05_happened_before_seeded(env) -> None:  # noqa: ANN001
    """EX-3.1：不拦截、不出校验红字，只回一个 warning 让前端询问式确认。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)

    first = await _draft(client, h, wid, happened_from="2026-07-12")
    assert first["warning"] == {
        "code": "HAPPENED_BEFORE_SEEDED",
        "message": "它比你写下它的时候更早发生了吗？",
    }
    assert first["memory"]["note_before_seeded"] is False

    second = await _draft(
        client, h, wid, happened_from="2026-07-12", acknowledged_before_seeded=True
    )
    assert second["warning"] is None
    assert second["memory"]["note_before_seeded"] is True
    assert second["memory"]["id"] == first["memory"]["id"]


async def test_ST_S06_06_happened_in_the_future(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    status, body = await _happened(client, h, wid, happened_from="2026-12-01")
    assert status == 422
    assert body["code"] == "HAPPENED_DATE_IN_FUTURE"
    assert await _row_count("memories", "wish_id", wid) == 0
    assert uid  # 用户仍在，只是这一页没被创建


async def test_ST_S06_07_inverted_range(env) -> None:  # noqa: ANN001
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    status, body = await _happened(
        client, h, wid, happened_from="2026-10-18", happened_to="2026-10-17"
    )
    assert status == 422
    assert body["code"] == "HAPPENED_RANGE_INVALID"
    assert await _row_count("memories", "wish_id", wid) == 0


async def test_ST_S06_08_happened_without_the_agreed_path(env) -> None:  # noqa: ANN001
    """EX-4.1：事情本来就可能在这个产品之外自然发生，不要求补齐中间状态。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _seed(client, h, "想学会滑雪")  # 无时机、无步骤，state=seeded
    h = await _write_day(client, uid)

    body = await _draft(client, h, wid, happened_from="2026-10-17")
    assert body["degraded"] is False
    assert body["memory"]["process"] is None  # 经过是可选空区块，不是错误
    assert body["memory"]["title"]

    published = await client.post(f"{BASE}/memories/{body['memory']['id']}/publish", headers=h)
    assert published.status_code == 200, published.text
    assert (await client.get(f"{BASE}/wishes/{wid}", headers=h)).json()["state"] == "happened"


async def test_ST_S06_09_llm_draft_failure_degrades(env) -> None:  # noqa: ANN001
    """EX-7.1：草拟失败不回滚写入，标题回退原标题、起因回退原话，并入队补做。"""
    client, llm = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    original = (await client.get(f"{BASE}/wishes/{wid}", headers=h)).json()
    h = await _write_day(client, uid)

    llm.mode = "down"
    body = await _draft(client, h, wid, happened_from="2026-10-17")
    memory = body["memory"]
    assert body["degraded"] is True
    assert memory["title"] == original["title"]
    assert memory["cause"] == original["original_text"]
    assert memory["process"] is None
    assert await _row_count("pending_agent_jobs", "memory_id", memory["id"]) == 1

    # 降级不阻塞发布
    published = await client.post(f"{BASE}/memories/{memory['id']}/publish", headers=h)
    assert published.status_code == 200, published.text


async def test_ST_S06_10_redraft_keeps_user_edits(env) -> None:  # noqa: ANN001
    """EX-7.1：补草拟任务跑过之后，用户改过的段落必须一字不变。"""
    from app.db import session_scope
    from app.services import run_memory_draft_jobs

    client, llm = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天", steps=2)
    h = await _write_day(client, uid)

    llm.mode = "down"
    memory = (await _draft(client, h, wid, happened_from="2026-10-17"))["memory"]
    edited = await client.patch(
        f"{BASE}/memories/{memory['id']}", headers=h, json={"title": "我自己写的标题"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["edited_fields"] == ["title"]

    llm.mode = "ok"
    async with session_scope(uuid.UUID(uid)) as s:
        assert await run_memory_draft_jobs(s, uuid.UUID(uid)) == 1

    after = (await client.get(f"{BASE}/memories/{memory['id']}", headers=h)).json()
    assert after["title"] == "我自己写的标题"
    assert after["process"]  # 未被编辑的段落补上了
    assert after["edited_fields"] == ["title"]
    assert await _row_count("pending_agent_jobs", "memory_id", memory["id"]) == 0


async def test_ST_S06_11_photo_limit_exceeded(env) -> None:  # noqa: ANN001
    """EX-12.1：超限时本次编辑整体不保存，已有内容不受影响。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    photo = await _upload_photo(client, h)
    h = await _write_day(client, uid)
    memory_id = (await _draft(client, h, wid))["memory"]["id"]
    assert (
        await client.patch(
            f"{BASE}/memories/{memory_id}", headers=h, json={"photo_media_ids": [photo]}
        )
    ).status_code == 200

    r = await client.patch(
        f"{BASE}/memories/{memory_id}",
        headers=h,
        json={"photo_media_ids": [str(uuid.uuid4()) for _ in range(10)]},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "MEDIA_LIMIT_EXCEEDED"
    after = (await client.get(f"{BASE}/memories/{memory_id}", headers=h)).json()
    assert after["photo_media_ids"] == [photo]  # 原来那张还在
    assert await _row_count("memory_photos", "memory_id", memory_id) == 1


async def test_ST_S06_12_publish_twice_is_idempotent(env) -> None:  # noqa: ANN001
    """EX-17.1：/book 的页数不会因重复提交而虚增。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    memory_id = (await _draft(client, h, wid))["memory"]["id"]

    first = await client.post(f"{BASE}/memories/{memory_id}/publish", headers=h)
    assert first.status_code == 200
    published_at = first.json()["memory"]["published_at"]

    for _ in range(2):
        again = await client.post(f"{BASE}/memories/{memory_id}/publish", headers=h)
        assert again.status_code == 200
        assert again.json()["memory"]["published_at"] == published_at
    assert (await client.get(f"{BASE}/memories", headers=h)).json()["lived_pages"] == 1


async def test_ST_S06_13_publish_after_wish_deleted(env) -> None:  # noqa: ANN001
    """EX-18.1：愿望在另一端被彻底删除，草稿随之失效。"""
    client, _ = env
    h, uid = await _signup(client)
    wid = await _going(client, h, "想一个人去海边待两天")
    h = await _write_day(client, uid)
    memory_id = (await _draft(client, h, wid))["memory"]["id"]

    assert (
        await client.delete(f"{BASE}/wishes/{wid}", headers=h, params={"confirm": "true"})
    ).status_code == 204
    assert await _row_count("memories", "id", memory_id) == 0  # 已随愿望级联删除

    r = await client.post(f"{BASE}/memories/{memory_id}/publish", headers=h)
    assert r.status_code == 404
    assert r.json()["code"] == "WISH_NOT_FOUND"









