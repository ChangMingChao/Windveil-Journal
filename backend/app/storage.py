"""对象存储抽象。

架构第七节把对象存储列为外部依赖，S3 兼容为硬约束（可换 MinIO / R2 / 云 OSS）。
两个实现：

  S3ObjectStorage    —— staging / production，真实预签名 PUT，前端直传不经过 API
  LocalObjectStorage —— local / test，文件系统 + 自签 HMAC URL，零外部服务

LocalObjectStorage 不是「假的」：预签名的签名与过期校验是我们自己的逻辑，
它照样被真实地走一遍（S02 EX-5.1 的签名被篡改场景因此可测）。
它唯一测不出的是「直传不经过 API 进程」——那是 S3 才有的属性，
对应 UT-S02-25 在本地环境下写入 skip。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlencode

from app.config import get_settings


@dataclass(frozen=True)
class ObjectMeta:
    key: str
    size_bytes: int
    content_type: str


class ObjectStorage(Protocol):
    def presign_put(self, key: str, content_type: str, size_bytes: int) -> tuple[str, int]:
        """返回 (upload_url, expires_in_seconds)。"""
        ...

    def head(self, key: str) -> ObjectMeta | None: ...

    def delete_many(self, keys: list[str]) -> list[str]:
        """返回删除失败的 key（S05.2 EX-28.1：部分失败不阻塞删除意图）。"""
        ...


class LocalObjectStorage:
    """文件系统后端。上传落到 root/<key>，元数据从文件本身读。"""

    def __init__(self, root: Path, secret: str, base_url: str, ttl: int) -> None:
        self._root = root
        self._secret = secret.encode("utf-8")
        self._base = base_url.rstrip("/")
        self._ttl = ttl
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 防目录穿越：key 由服务端生成，这里再兜一层
        safe = key.replace("..", "").lstrip("/")
        p = self._root / safe
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def sign(self, key: str, expires_at: int) -> str:
        msg = f"{key}:{expires_at}".encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()[:32]

    def verify(self, key: str, expires_at: int, signature: str) -> str | None:
        """返回 None 表示通过，否则返回失败原因。"""
        if not hmac.compare_digest(self.sign(key, expires_at), signature):
            return "signature_mismatch"
        if expires_at < int(time.time()):
            return "expired"
        return None

    def presign_put(self, key: str, content_type: str, size_bytes: int) -> tuple[str, int]:
        del content_type, size_bytes
        expires_at = int(time.time()) + self._ttl
        query = urlencode({"exp": expires_at, "sig": self.sign(key, expires_at)})
        return f"{self._base}/api/test/object/{quote(key)}?{query}", self._ttl

    def put(self, key: str, data: bytes) -> None:
        self._path(key).write_bytes(data)

    def read(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def head(self, key: str) -> ObjectMeta | None:
        p = self._path(key)
        if not p.exists():
            return None
        # 本地后端不保存 Content-Type，按扩展名回推（仅用于校验流程连通）
        suffix = p.suffix.lower()
        ctype = {
            ".webm": "audio/webm",
            ".m4a": "audio/mp4",
            ".mp3": "audio/mpeg",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "application/octet-stream")
        return ObjectMeta(key=key, size_bytes=p.stat().st_size, content_type=ctype)

    def delete_many(self, keys: list[str]) -> list[str]:
        failed: list[str] = []
        for key in keys:
            try:
                self._path(key).unlink(missing_ok=True)
            except OSError:
                failed.append(key)
        return failed


class S3ObjectStorage:
    """staging / production：真实 S3 兼容端点，前端直传不经过 API。

    签名用的 endpoint 是 `S3_PUBLIC_BASE` 而不是 `S3_ENDPOINT`：预签名 URL 要交给
    浏览器，而浏览器解析不了 `http://minio:9000` 这种 compose 网络内的主机名。
    SigV4 把 Host 头也签进去了，所以**必须按对外主机签名**，再由 Caddy 反代到
    MinIO 并原样保留 Host（见 Caddyfile 的 `header_up Host {host}`）——
    反过来（按内网主机签名再改 Host）签名一定校验失败。

    部署方案 §2 的取舍 1 正是为此：经 Caddy 暴露 `/media/*` 让预签名与站点同源，
    既不必多一个域名和证书，MinIO 也不必对公网开放。
    """

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        s = get_settings()
        self._bucket = s.S3_BUCKET
        self._ttl = s.S3_PRESIGN_TTL_SECONDS
        # 两个 client：签名用对外地址，服务端自己的读写用内网地址（更快且不绕代理）
        self._presign_client = boto3.client(
            "s3",
            endpoint_url=s.S3_PUBLIC_BASE,
            aws_access_key_id=s.S3_ACCESS_KEY,
            aws_secret_access_key=s.S3_SECRET_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=s.S3_ENDPOINT,
            aws_access_key_id=s.S3_ACCESS_KEY,
            aws_secret_access_key=s.S3_SECRET_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def presign_put(self, key: str, content_type: str, size_bytes: int) -> tuple[str, int]:
        del size_bytes
        url = self._presign_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self._ttl,
        )
        return url, self._ttl

    def read(self, key: str) -> bytes | None:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except Exception:  # noqa: BLE001
            return None

    def head(self, key: str) -> ObjectMeta | None:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception:  # noqa: BLE001 —— 对象不存在与网络错误都按「查不到」处理
            return None
        return ObjectMeta(
            key=key,
            size_bytes=int(resp.get("ContentLength", 0)),
            content_type=resp.get("ContentType", "application/octet-stream"),
        )

    def delete_many(self, keys: list[str]) -> list[str]:
        failed: list[str] = []
        for key in keys:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=key)
            except Exception:  # noqa: BLE001
                failed.append(key)
        return failed


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.APP_ENV in ("local", "test"):
            _storage = LocalObjectStorage(
                root=Path(s.LOCAL_STORAGE_DIR),
                secret=s.JWT_SECRET,
                base_url=s.APP_BASE_URL,
                ttl=s.S3_PRESIGN_TTL_SECONDS,
            )
        else:
            _storage = S3ObjectStorage()
    return _storage


def set_storage(storage: ObjectStorage | None) -> None:
    global _storage
    _storage = storage
