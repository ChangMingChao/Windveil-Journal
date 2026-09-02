"""加密列：应用层 AES-256-GCM。

schema.sql 约定：所有「用户自己说的话」以 *_enc BLOB 存储，
加解密在**应用层**完成，密钥来自环境变量 ENCRYPTION_KEY。
业务代码看到的是普通 str —— 由这里的 TypeDecorator 透明转换。

相对原 pgcrypto 方案的变化：明文不再作为 SQL 参数传输，
因此不存在「打开语句日志就泄露原文」的风险（部署方案 3.4 的强制要求随之取消）。

已知边界不变：这些列不可用于 WHERE / ORDER BY / JOIN。
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary, TypeDecorator

from app.config import get_settings

_NONCE_LEN = 12


def _key() -> bytes:
    """把任意长度的 ENCRYPTION_KEY 归一为 32 字节。

    生产环境应直接提供 32 字节的 base64 随机密钥；这里的哈希归一是为了
    让本地开发不必先生成密钥。
    """
    raw = get_settings().ENCRYPTION_KEY.encode("utf-8")
    return hashlib.sha256(raw).digest()


def encrypt_text(plaintext: str) -> bytes:
    nonce = os.urandom(_NONCE_LEN)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)


def decrypt_text(blob: bytes) -> str:
    data = bytes(blob)
    nonce, payload = data[:_NONCE_LEN], data[_NONCE_LEN:]
    return AESGCM(_key()).decrypt(nonce, payload, None).decode("utf-8")


class EncryptedText(TypeDecorator[str]):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:  # noqa: ARG002
        return None if value is None else encrypt_text(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> str | None:  # noqa: ARG002
        return None if value is None else decrypt_text(value)
