"""S02 场景测试（端到端 HTTP）。

覆盖 ST-S02-01~11、14。对象存储用 LocalObjectStorage（文件系统 + 自签 HMAC），
因此预签名的签名与过期校验是真实走一遍的；ASR 与 LLM 用可控替身。
ST-S02-12/13 为 [manual]，不产出 JSONL。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

VALID_UNDERSTANDING = {
    "understanding": {
        "kind": "future_wish",
        "feeling": "喘口气",
        "conditions": {"season": "winter", "title": "学会滑雪"},
        "smallest_step": "先看一段滑雪入门视频",
    },
    "question": "想在哪座山？还是还没想到？",
}
NEAR_TERM = {
    "understanding": {"kind": "near_term_todo", "feeling": None, "conditions": {}, "smallest_step": None},
    "question": "这更像是这几天要办的事，还是你想在未来发生的事？",
}


class FakeLLM:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode

    async def understand_wish(self, text: str):  # noqa: ANN201, ARG002
        from app.agent import UnderstandResult

        if self.mode == "none":
            return None
        payload = NEAR_TERM if self.mode == "near_term" else VALID_UNDERSTANDING
        return UnderstandResult.model_validate(payload)


class FakeASR:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.calls = 0

    async def transcribe(self, audio: bytes, filename: str):  # noqa: ANN201, ARG002
        from app.asr import classify_transcript

        self.calls += 1
        if self.mode == "error":
            return classify_transcript(None)
        if self.mode == "empty":
            return classify_transcript("   ")
        return classify_transcript("想在冬天学会滑雪")


@pytest.fixture
async def env(app_env: None, tmp_path) -> AsyncIterator[tuple]:  # noqa: ANN001
    import os

    os.environ["APP_BASE_URL"] = "http://t"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "objects")

    from app.agent import set_llm_provider
    from app.asr import set_asr_provider
    from app.config import get_settings
    from app.db import dispose_engines
    from app.main import create_app
    from app.storage import set_storage

    get_settings.cache_clear()
    set_storage(None)  # 让 storage 按新配置重建
    llm, asr = FakeLLM(), FakeASR()
    set_llm_provider(llm)
    set_asr_provider(asr)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, llm, asr
    set_llm_provider(None)
    set_asr_provider(None)
    set_storage(None)
    await dispose_engines()


async def _signup(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/api/v1/auth/anonymous", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _upload(client: AsyncClient, h: dict, *, kind: str, ctype: str, size: int, body: bytes):  # noqa: ANN202
    r = await client.post(
        "/api/v1/media/upload-url",
        headers=h,
        json={"kind": kind, "content_type": ctype, "size_bytes": size},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    put = await client.put(data["upload_url"], content=body)
    assert put.status_code == 200, put.text
    done = await client.post(f"/api/v1/media/{data['media_id']}/complete", headers=h)
    assert done.status_code == 204, done.text
    return data["media_id"]


@pytest.mark.asyncio
async def test_ST_S02_01_voice_path_and_skip_question(env) -> None:  # noqa: ANN001
    client, _, asr = env
    h = await _signup(client)
    media_id = await _upload(
        client, h, kind="audio", ctype="audio/webm", size=18432, body=b"\x1a\x45\xdf\xa3fake"
    )

    r = await client.post("/api/v1/wishes", headers=h, json={"source": "voice", "media_id": media_id})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["degraded"] is False
    # wishes.yaml 的 WishDetail 不含 source 字段——前端靠 audio_media_id 判断有无语音
    assert body["wish"]["audio_media_id"] == media_id
    assert body["wish"]["original_text"] == "想在冬天学会滑雪"
    assert body["wish"]["understanding"] is not None
    assert body["question"] is not None
    assert asr.calls == 1
    wish_id = body["wish"]["id"]

    r = await client.post(f"/api/v1/wishes/{wish_id}/answer", headers=h, json={"skipped": True})
    assert r.status_code == 200
    assert r.json()["pending_question"] is True
    assert r.json()["audio_media_id"] == media_id


@pytest.mark.asyncio
async def test_ST_S02_02_text_path_extracts_conditions(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h = await _signup(client)
    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想在冬天学会滑雪"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["wish"]["title"] == "学会滑雪"
    assert body["wish"]["understanding"]["conditions"]["season"] == "winter"
    assert body["wish"]["understanding"]["smallest_step"] is not None
    assert body["question"] is not None


@pytest.mark.asyncio
async def test_ST_S02_03_seed_with_photos(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h = await _signup(client)
    p1 = await _upload(client, h, kind="image", ctype="image/jpeg", size=2048, body=b"\xff\xd8jpg")
    p2 = await _upload(client, h, kind="image", ctype="image/jpeg", size=2048, body=b"\xff\xd8jpg")
    r = await client.post(
        "/api/v1/wishes",
        headers=h,
        json={"source": "text", "text": "想去看一次海上日出", "photo_media_ids": [p1, p2]},
    )
    assert r.status_code == 201
    assert len(r.json()["wish"]["photo_media_ids"]) == 2


@pytest.mark.asyncio
async def test_ST_S02_04_tampered_presign_is_rejected(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h = await _signup(client)
    r = await client.post(
        "/api/v1/media/upload-url",
        headers=h,
        json={"kind": "audio", "content_type": "audio/webm", "size_bytes": 18432},
    )
    data = r.json()
    put = await client.put(data["upload_url"] + "tampered", content=b"x")
    assert put.status_code == 403
    assert put.json()["code"] == "PRESIGN_INVALID"

    # 未 complete 的媒体不能被引用，也不创建愿望
    seed = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "voice", "media_id": data["media_id"]}
    )
    assert seed.status_code == 422
    assert seed.json()["code"] == "MEDIA_INVALID"
    listed = await client.get("/api/v1/wishes", headers=h)
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_ST_S02_05_object_validation_rejects_and_marks(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h = await _signup(client)
    r = await client.post(
        "/api/v1/media/upload-url",
        headers=h,
        json={"kind": "audio", "content_type": "audio/webm", "size_bytes": 1024},
    )
    data = r.json()
    # 声明 1KB，实际传 11MB（超过 10485760 上限）
    await client.put(data["upload_url"], content=b"0" * (10 * 1024 * 1024 + 1))
    done = await client.post(f"/api/v1/media/{data['media_id']}/complete", headers=h)
    assert done.status_code == 422
    assert done.json()["code"] == "MEDIA_INVALID"


@pytest.mark.asyncio
async def test_ST_S02_06_transcription_failure_and_retry(env) -> None:  # noqa: ANN001
    client, _, asr = env
    h = await _signup(client)
    asr.mode = "error"
    media_id = await _upload(
        client, h, kind="audio", ctype="audio/webm", size=18432, body=b"fake-audio"
    )
    r = await client.post("/api/v1/wishes", headers=h, json={"source": "voice", "media_id": media_id})
    assert r.status_code == 201
    body = r.json()
    assert body["degraded"] is True
    assert body["wish"]["title"] == "一段还没被读懂的话"
    assert body["wish"]["original_text"] is None
    assert body["wish"]["degraded_reason"] == "asr_failed"
    assert body["wish"]["audio_media_id"] == media_id
    wish_id = body["wish"]["id"]

    asr.mode = "ok"
    retry = await client.post(f"/api/v1/wishes/{wish_id}/transcription", headers=h)
    assert retry.status_code == 200
    assert retry.json()["wish"]["original_text"] == "想在冬天学会滑雪"
    assert retry.json()["wish"]["degraded_reason"] is None


@pytest.mark.asyncio
async def test_ST_S02_07_empty_transcript_is_distinguished(env) -> None:  # noqa: ANN001
    client, _, asr = env
    h = await _signup(client)
    asr.mode = "empty"
    media_id = await _upload(
        client, h, kind="audio", ctype="audio/webm", size=18432, body=b"silence"
    )
    r = await client.post("/api/v1/wishes", headers=h, json={"source": "voice", "media_id": media_id})
    assert r.status_code == 201
    assert r.json()["wish"]["degraded_reason"] == "asr_empty"
    assert r.json()["wish"]["original_text"] is None


@pytest.mark.asyncio
async def test_ST_S02_08_llm_failure_keeps_original_text(env) -> None:  # noqa: ANN001
    client, llm, _ = env
    h = await _signup(client)
    llm.mode = "none"
    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "想带父母去一次南方"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["degraded"] is True
    assert body["wish"]["original_text"] == "想带父母去一次南方"
    assert body["wish"]["understanding"] is None
    assert body["wish"]["degraded_reason"] == "llm_failed"


@pytest.mark.asyncio
async def test_ST_S02_09_near_term_todo_offers_two_actions(env) -> None:  # noqa: ANN001
    client, llm, _ = env
    h = await _signup(client)
    llm.mode = "near_term"
    r = await client.post(
        "/api/v1/wishes", headers=h, json={"source": "text", "text": "今天下午 3 点开会"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["wish"]["understanding"]["kind"] == "near_term_todo"
    # s02-lite-conversion：EX-18.2 的选项由两个扩展为三个（新增 save_as_lite）
    assert body["actions"] == ["keep_as_future", "save_as_lite", "delete"]
    assert "未来" in body["question"]
    assert "格式错误" not in body["question"]
    wish_id = body["wish"]["id"]

    keep = await client.post(
        f"/api/v1/wishes/{wish_id}/answer", headers=h, json={"action": "keep_as_future"}
    )
    assert keep.status_code == 200
    assert keep.json()["understanding"]["kind"] == "future_wish"

    gone = await client.delete(f"/api/v1/wishes/{wish_id}?confirm=true", headers=h)
    assert gone.status_code == 204
    assert (await client.get(f"/api/v1/wishes/{wish_id}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_ST_S02_10_orphan_media_is_cleaned_after_24h(env) -> None:  # noqa: ANN001
    from datetime import timedelta

    from app.clock import clock
    from app.db import session_scope
    from app.security import decode_access_token
    from app.services import cleanup_orphan_media

    client, _, _ = env
    h = await _signup(client)
    owner = decode_access_token(h["Authorization"].split(" ", 1)[1])
    assert owner is not None
    await _upload(client, h, kind="audio", ctype="audio/webm", size=18432, body=b"orphan")

    base = clock.now()
    try:
        clock.set_fixed(base + timedelta(hours=25))
        async with session_scope(owner) as s:
            assert await cleanup_orphan_media(s, owner) == 1
        async with session_scope(owner) as s:
            assert await cleanup_orphan_media(s, owner) == 0
    finally:
        clock.set_fixed(None)


@pytest.mark.asyncio
async def test_ST_S02_11_microphone_denied_produces_no_server_state(env) -> None:  # noqa: ANN001
    """权限被拒是纯前端处理：服务端不应有任何调用痕迹。"""
    client, _, asr = env
    h = await _signup(client)
    assert (await client.get("/api/v1/wishes", headers=h)).json()["items"] == []
    assert asr.calls == 0


@pytest.mark.asyncio
async def test_ST_S02_14_media_boundaries_and_cross_user(env) -> None:  # noqa: ANN001
    client, _, _ = env
    h = await _signup(client)

    r = await client.post(
        "/api/v1/media/upload-url",
        headers=h,
        json={"kind": "audio", "content_type": "image/png", "size_bytes": 1024},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "MEDIA_INVALID"

    for size, expected in ((10485760, 201), (10485761, 422)):
        r = await client.post(
            "/api/v1/media/upload-url",
            headers=h,
            json={"kind": "audio", "content_type": "audio/webm", "size_bytes": size},
        )
        assert r.status_code == expected, size

    r = await client.post(
        "/api/v1/wishes",
        headers=h,
        json={
            "source": "text",
            "text": "边界测试",
            "photo_media_ids": [str(uuid.uuid4()) for _ in range(10)],
        },
    )
    assert r.status_code == 422

    h_b = await _signup(client)
    mine = await client.post(
        "/api/v1/media/upload-url",
        headers=h,
        json={"kind": "audio", "content_type": "audio/webm", "size_bytes": 1024},
    )
    other = await client.post(
        f"/api/v1/media/{mine.json()['media_id']}/complete", headers=h_b
    )
    assert other.status_code == 404
    assert other.json()["code"] == "MEDIA_NOT_FOUND"
