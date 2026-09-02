"""应用配置。全部来自环境变量，见部署方案 3.1 / 3.2。"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 运行环境。决定 /api/test/* 是否注册路由（部署方案 3.1）
    APP_ENV: Literal["local", "test", "staging", "production"] = "local"
    APP_BASE_URL: str = "http://localhost:8000"

    # 数据库：SQLite 单文件。无角色概念，因此没有 app / auth / scheduler 三套连接串
    DATABASE_URL: str = "sqlite+aiosqlite:///./unhappened.db"

    JWT_SECRET: str = "dev-only-change-me"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_TTL_SECONDS: int = 900  # 与 auth.yaml 的 expires_in 一致
    REFRESH_TOKEN_TTL_DAYS: int = 30

    # 加密列密钥（应用层 AES-256-GCM）。丢失后全部用户内容永久不可读
    ENCRYPTION_KEY: str = "dev-only-encryption-key"

    # LLM / ASR 一律走 OpenAI 兼容端点，代码中不出现任何厂商名
    LLM_BASE_URL: str = "http://localhost:9100/v1"
    LLM_API_KEY: str = "mock"
    LLM_MODEL: str = "mock-model"
    LLM_TIMEOUT_SECONDS: float = 5.0  # 与 S01/S02 验收条件「≤5 秒」对齐，不可调大
    ASR_BASE_URL: str = "http://localhost:9100/v1"
    ASR_API_KEY: str = "mock"
    ASR_MODEL: str = "mock-asr"
    ASR_TIMEOUT_SECONDS: float = 15.0

    S3_ENDPOINT: str = "http://localhost:9000"
    S3_BUCKET: str = "unhappened-media"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_PUBLIC_BASE: str = "http://localhost:8000/media"
    S3_PRESIGN_TTL_SECONDS: int = 600  # media.yaml：有效期 10 分钟
    # local / test 用文件系统后端，避免为跑测试而拉起 MinIO
    LOCAL_STORAGE_DIR: str = "./.local-objects"

    # 允许的 MIME 白名单（media.yaml → createMediaUploadUrl.content_type）
    AUDIO_MIME_WHITELIST: tuple[str, ...] = ("audio/webm", "audio/mp4", "audio/mpeg")
    IMAGE_MIME_WHITELIST: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
    ORPHAN_MEDIA_TTL_HOURS: int = 24  # S02 EX-13.1

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "noreply@unhappened.local"
    VAPID_SUBJECT: str = "mailto:ops@unhappened.local"

    REMINDER_WEEKLY_BUDGET: int = 3
    REMINDER_BACKOFF_SECONDS: tuple[int, ...] = (300, 1800, 7200)
    REMINDER_MAX_ATTEMPTS: int = 3
    STALE_CARE_DAYS: int = 60
    SCHEDULER_INTERVAL_SECONDS: int = 300
    # 空值表示按 DATABASE_URL 推导，见 scheduler_lock_path
    SCHEDULER_LOCK_PATH: str = ""

    WISH_TEXT_MAX_LEN: int = 500
    WISH_TITLE_FALLBACK_LEN: int = 20  # 降级时标题回退为原话前 20 字
    ONBOARDING_MAX_ANSWERS: int = 10
    AUDIO_MAX_BYTES: int = 10 * 1024 * 1024
    IMAGE_MAX_BYTES: int = 8 * 1024 * 1024
    PHOTO_MAX_PER_OWNER_OBJECT: int = 9

    @property
    def test_backdoor_enabled(self) -> bool:
        """/api/test/* 仅在 APP_ENV=test 时注册（system.yaml + 部署方案 §7-6）。"""
        return self.APP_ENV == "test"

    @property
    def local_object_receiver_enabled(self) -> bool:
        """本地对象存储的接收端在 local 与 test 都要有。

        `get_storage()` 在 local 下就返回 `LocalObjectStorage`，它签出的预签名 URL
        指向 `/api/test/object/{key}`。如果只在 test 下注册这个路由，
        本地开发上传媒体会 404——预签名签出来了，收件的地方却不存在。
        它不是测试后门：不读写任何业务数据，只按自签 HMAC 收一个文件。
        """
        return self.APP_ENV in ("local", "test")


    @property
    def scheduler_lock_path(self) -> str:
        """单活文件锁的位置。

        默认放在**数据库文件旁边**：锁守护的正是对这个文件的写入，
        而那个目录一定是应用可写的（否则数据库自己也写不进去）。

        原实现按 `LOCAL_STORAGE_DIR` 的父目录推导，在容器里落到了 `/app`——
        镜像的工作目录属 root，非 root 运行的进程创建锁文件时直接 PermissionError，
        每一轮扫描都失败，而且只能通过心跳超时间接发现。
        """
        if self.SCHEDULER_LOCK_PATH:
            return self.SCHEDULER_LOCK_PATH
        if "///" in self.DATABASE_URL:
            from pathlib import Path

            return str(Path(self.DATABASE_URL.split("///", 1)[1]).parent / ".scheduler.lock")
        return ".scheduler.lock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
