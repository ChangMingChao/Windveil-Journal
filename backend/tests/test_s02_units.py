"""S02 单元测试（不依赖数据库的部分）。

用例 ID 与 logos/resources/test/core-S02-test-cases.md 完全一致。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent import UnderstandResult, WishUnderstanding
from app.asr import TranscribeResult, classify_transcript
from app.config import get_settings
from app.schemas import SeedWishRequest, UploadUrlRequest
from app.services import DomainError, object_key_for, validate_upload_request

AUDIO = "audio/webm"
IMAGE = "image/jpeg"


# ---------------------------------------------------------------- 1.1 API 字段约束


def test_UT_S02_01_kind_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        UploadUrlRequest(kind="video", content_type=AUDIO, size_bytes=1024)
    assert UploadUrlRequest(kind="audio", content_type=AUDIO, size_bytes=1024).kind == "audio"


def test_UT_S02_02_kind_and_content_type_must_match() -> None:
    with pytest.raises(DomainError) as exc:
        validate_upload_request("audio", "image/png", 1024)
    assert exc.value.code == "MEDIA_INVALID"
    validate_upload_request("audio", AUDIO, 1024)
    validate_upload_request("image", IMAGE, 1024)


def test_UT_S02_03_audio_size_boundary() -> None:
    limit = get_settings().AUDIO_MAX_BYTES
    assert limit == 10485760
    validate_upload_request("audio", AUDIO, limit)
    with pytest.raises(DomainError) as exc:
        validate_upload_request("audio", AUDIO, limit + 1)
    assert exc.value.code == "MEDIA_INVALID"


def test_UT_S02_04_image_size_boundary() -> None:
    limit = get_settings().IMAGE_MAX_BYTES
    assert limit == 8388608
    validate_upload_request("image", IMAGE, limit)
    with pytest.raises(DomainError):
        validate_upload_request("image", IMAGE, limit + 1)


def test_UT_S02_05_size_bytes_must_be_positive() -> None:
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            UploadUrlRequest(kind="audio", content_type=AUDIO, size_bytes=bad)


def test_UT_S02_06_presign_ttl_is_ten_minutes(tmp_path) -> None:  # noqa: ANN001
    from app.storage import LocalObjectStorage

    ttl = get_settings().S3_PRESIGN_TTL_SECONDS
    assert ttl == 600
    storage = LocalObjectStorage(tmp_path, "secret", "http://t", ttl)
    url, got = storage.presign_put("k/a.webm", AUDIO, 1024)
    assert got == 600
    assert "exp=" in url and "sig=" in url


@pytest.mark.asyncio
async def test_UT_S02_07_voice_without_media_id_rejected() -> None:
    """source=voice 缺 media_id 在触达数据库之前就被拒。"""
    import uuid

    from app.services import seed_wish

    with pytest.raises(DomainError) as exc:
        await seed_wish(
            None,  # type: ignore[arg-type]  —— 校验发生在任何 DB 访问之前
            uuid.uuid4(),
            source="voice",
            text=None,
            media_id=None,
            photo_media_ids=[],
        )
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.status == 422


def test_UT_S02_09_photo_media_ids_boundary() -> None:
    import uuid

    ids = [uuid.uuid4() for _ in range(10)]
    SeedWishRequest(source="text", text="x", photo_media_ids=ids[:9])
    with pytest.raises(ValidationError):
        SeedWishRequest(source="text", text="x", photo_media_ids=ids)


def test_UT_S02_10_media_id_must_be_uuid() -> None:
    with pytest.raises(ValidationError):
        SeedWishRequest(source="voice", media_id="abc")


def test_UT_S02_08_object_key_layout_is_owner_scoped() -> None:
    """对象键以 owner_id 开头：跨用户引用在存储层面也不会撞车（配合 UT-S02-11）。"""
    import uuid

    owner, media = uuid.uuid4(), uuid.uuid4()
    key = object_key_for(owner, media, "audio", AUDIO)
    assert key == f"{owner}/audio/{media}.webm"
    assert key.startswith(str(owner))


# ---------------------------------------------------------------- 1.3 业务规则


@pytest.mark.asyncio
async def test_UT_S02_20_asr_timeout_returns_failed() -> None:
    """转写超时上限 15 秒；任何异常一律归为 asr_failed，不抛出。"""
    from app.asr import OpenAICompatibleASR

    assert get_settings().ASR_TIMEOUT_SECONDS == 15.0

    provider = OpenAICompatibleASR.__new__(OpenAICompatibleASR)
    provider._model = "mock-asr"  # noqa: SLF001

    class _Raising:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                async def create(**_kwargs: object) -> object:
                    raise TimeoutError("simulated timeout")

    provider._client = _Raising()  # noqa: SLF001
    result = await provider.transcribe(b"\x00", "a.webm")
    assert result.ok is False
    assert result.reason == "asr_failed"


def test_UT_S02_21_audio_object_survives_transcription(tmp_path) -> None:  # noqa: ANN001
    """转写成功后原始音频不被删除（EX-15.1 的重试前提）。"""
    from app.storage import LocalObjectStorage

    storage = LocalObjectStorage(tmp_path, "s", "http://t", 600)
    storage.put("o/audio/a.webm", b"fake-audio")
    assert storage.read("o/audio/a.webm") == b"fake-audio"
    # 转写只读取，不删除
    assert storage.head("o/audio/a.webm") is not None


def test_UT_S02_22_blank_transcript_classified_as_empty() -> None:
    assert classify_transcript(None) == TranscribeResult(None, "asr_failed")
    assert classify_transcript("   ") == TranscribeResult(None, "asr_empty")
    assert classify_transcript("  想去看海 ") == TranscribeResult("想去看海", None)


def test_UT_S02_23_near_term_todo_is_a_first_class_kind() -> None:
    """当下日程不是「非法输入」，而是 understanding 的一个合法取值（EX-18.2）。"""
    result = UnderstandResult(
        understanding=WishUnderstanding(kind="near_term_todo"),
        question="这更像是这几天要办的事，还是你想在未来发生的事？",
    )
    assert result.understanding.kind == "near_term_todo"
    with pytest.raises(ValidationError):
        WishUnderstanding(kind="invalid_input")


@pytest.mark.skip(reason="「直传不经过 API 进程」是 S3 特有属性；本地文件系统后端无法断言")
def test_UT_S02_25_upload_bypasses_api_process() -> None:
    """需要真实 S3 兼容端点才能断言 upload_url 不指向 API 主机。

    本地环境用 LocalObjectStorage，预签名 URL 必然落在 API 上，
    因此本用例写入 skip（按 logos/spec/test-results.md 计为有效通过并保留在
    skipped_cases 中），待 staging 上由 SMOKE-core-15 覆盖真实直传。
    """
