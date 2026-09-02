"""FastAPI 应用入口。

错误响应统一为 {code, message, details?}（api-designer 的统一约定）：
HTTPException 的 detail 已按该结构构造，这里把它原样展开为响应体。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import local_router, router, test_router
from app.config import get_settings
from app.db import dispose_engines
from app.obs import configure_logging, new_request_id, request_id_var

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engines()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="未发生事件管理局 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[s.APP_BASE_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):  # noqa: ANN001, ANN202
        """每个请求一个 id，进日志也回响应头。

        沿用上游传来的 `X-Request-ID`（反代或客户端可能已经生成过一个），
        没有就自己造——这样一条链路上的日志能对齐，而不是每一跳换一个号。
        """
        rid = request.headers.get("X-Request-ID") or new_request_id()
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    # /api/test/* 仅在 APP_ENV=test 时注册；生产构建下这些路由不存在
    # （部署方案 §7-6、SMOKE-core-04）
    if s.test_backdoor_enabled:
        app.include_router(test_router)
    # 本地对象存储的接收端在 local 也要有，否则 local 下预签名签得出来、收不到
    if s.local_object_receiver_enabled:
        app.include_router(local_router)

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        from sqlalchemy import text as sql_text

        from app.db import session_scope

        db_status = "ok"
        try:
            async with session_scope() as session:
                await session.execute(sql_text("SELECT 1"))
        except Exception:  # noqa: BLE001
            db_status = "degraded"
        age: float | None = None
        if db_status == "ok":
            try:
                from app.scheduler import heartbeat_age_seconds

                age = await heartbeat_age_seconds()
            except Exception:  # noqa: BLE001 —— 心跳读不到不该让健康检查本身挂掉
                age = None
        return {
            "status": "ok" if db_status == "ok" else "degraded",
            "database": db_status,
            "scheduler_heartbeat_age_seconds": age,
        }

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": "HTTP_ERROR", "message": str(detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 统一为 422 VALIDATION_FAILED；不回显用户内容，只回显字段位置
        fields = [".".join(str(p) for p in e["loc"]) for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_FAILED",
                "message": "有些内容还不太对",
                "details": {"fields": fields},
            },
        )

    return app


app = create_app()
