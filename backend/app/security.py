"""认证原语：Argon2id 密码哈希 + JWT。

架构 3.2：access token 15 分钟，refresh 30 天且只经 httpOnly Cookie 传输，
refresh 在库中只存 SHA-256 哈希（schema.sql sessions.refresh_hash）。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.clock import clock
from app.config import get_settings

_hasher = PasswordHasher()


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except VerifyMismatchError:
        return False
    except Exception:
        # 哈希格式损坏等同凭证不匹配；不向调用方泄露内部原因
        return False


def issue_access_token(user_id: UUID) -> str:
    s = get_settings()
    now = clock.now()
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=s.ACCESS_TOKEN_TTL_SECONDS)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALG)


def decode_access_token(token: str) -> UUID | None:
    s = get_settings()
    try:
        # 过期与签发时间判定全部交给 Clock 抽象，而不是 PyJWT 内部的 time.time()：
        # 架构第七节要求所有时间来自 Clock，否则注入固定时间的测试会与
        # 真实墙上时钟打架（这个不一致由 S03 的时钟注入场景暴露）。
        payload = jwt.decode(
            token, s.JWT_SECRET, algorithms=[s.JWT_ALG], options={"verify_exp": False, "verify_iat": False, "verify_nbf": False}
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int | float) or clock.now().timestamp() >= exp:
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def new_refresh_token() -> tuple[str, str]:
    """返回 (明文, SHA-256 哈希)。明文只下发到 httpOnly Cookie，不落库。"""
    raw = secrets.token_urlsafe(48)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
