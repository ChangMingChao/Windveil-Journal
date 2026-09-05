"""FastAPI 路由。路径、方法、状态码、错误码与 logos/resources/api/*.yaml 严格一致。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.clock import clock
from app.config import get_settings
from app.db import session_scope
from app.schemas import (
    AnonymousRequest,
    NotificationChannels,
    NotificationChannelsUpdate,
    AvailabilityCreateRequest,
    AvailabilityListResponse,
    AvailabilityOut,
    AvailabilityUpdateRequest,
    DeclarePreferenceRequest,
    LiteEventCreate,
    LiteEventListResponse,
    LiteEventOut,
    PreferenceListResponse,
    PreferenceMeta,
    ProposalConfirmResult,
    ProposalGenerateResult,
    ProposalListResponse,
    ProposalRejectResult,
    TimingProposalOut,
    AnswerRequest,
    AuthResult,
    HappenedRequest,
    LinkEmailRequest,
    MemoryListResponse,
    MemoryOut,
    MemoryResult,
    OnboardingAnswersRequest,
    PublishResult,
    SeedWishRequest,
    SeedWishResult,
    UploadUrlRequest,
    UploadUrlResult,
    UserProfile,
    WishDetail,
    WishListResponse,
)
from app.security import decode_access_token
from app.services import (
    DomainError,
    answer_question,
    complete_upload,
    create_anonymous_space,
    create_upload_url,
    enrich_wish,
    link_email,
    list_wishes,
    photo_ids_of,
    revoke_session,
    save_onboarding_answers,
    seed_wish,
    to_card,
    to_detail,
    transcribe_wish_audio,
)

router = APIRouter(prefix="/api/v1")


def _err(exc: DomainError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


async def current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "还没有进入你的未发生之地"},
        )
    user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "这次进入已经过期了"},
        )
    return user_id


CurrentUser = Annotated[UUID, Depends(current_user_id)]

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        httponly=True,
        secure=s.APP_ENV in ("staging", "production"),
        samesite="lax",
        max_age=s.REFRESH_TOKEN_TTL_DAYS * 86400,
        path="/api/v1/auth",
    )


# ------------------------------------------------------------------ auth


@router.post("/auth/anonymous", status_code=201, response_model=AuthResult)
async def create_anonymous(payload: AnonymousRequest, response: Response) -> AuthResult:
    """来源：S01 Step 3 → Step 6。走 auth 角色连接池（部署方案 3.3）。"""
    import logging

    from sqlalchemy.exc import SQLAlchemyError

    try:
        async with session_scope() as session:
            user, access, refresh = await create_anonymous_space(session, payload.timezone)
            profile = UserProfile.model_validate(user, from_attributes=True)
    except DomainError as exc:
        raise _err(exc) from exc
    except SQLAlchemyError as exc:
        # EX-3.1：响应里不带堆栈、不带 SQL——一个主打私密的应用尤其不能把内部细节回显
        logging.getLogger("app.auth").error(
            "anonymous_space_create_failed", extra={"error_type": type(exc).__name__}
        )
        raise HTTPException(
            503,
            detail={
                "code": "SPACE_CREATE_FAILED",
                "message": "这里暂时打不开，你写的还在这台设备上",
            },
        ) from exc
    _set_refresh_cookie(response, refresh)
    return AuthResult(access_token=access, user=profile)


@router.post("/auth/link-email", response_model=UserProfile)
async def post_link_email(payload: LinkEmailRequest, user_id: CurrentUser) -> UserProfile:
    """来源：S01「待补设计 1」。"""
    try:
        async with session_scope() as session:
            user = await link_email(session, user_id, str(payload.email), payload.password)
            return UserProfile.model_validate(user, from_attributes=True)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/auth/logout", status_code=204)
async def post_logout(
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    if refresh_token:
        async with session_scope() as session:
            await revoke_session(session, refresh_token)
    resp = Response(status_code=204)
    resp.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return resp


@router.get("/me", response_model=UserProfile)
async def get_me(user_id: CurrentUser) -> UserProfile:
    """来源：S01 EX-12.1。前端据 onboarded_at 决定进 /welcome 还是 /garden。"""
    from app.models import User

    async with session_scope(user_id) as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "找不到这个人"})
        return UserProfile.model_validate(user, from_attributes=True)


@router.post("/onboarding/answers", status_code=204)
async def post_onboarding_answers(
    payload: OnboardingAnswersRequest, user_id: CurrentUser
) -> Response:
    """来源：S01 Step 9 → Step 11。写入失败也返回 204（EX-10.1）。"""
    import logging

    try:
        async with session_scope(user_id) as session:
            await save_onboarding_answers(session, user_id, payload.answers)
    except Exception as exc:  # noqa: BLE001 —— 初始记忆是增强项，不为它中断首次体验
        logging.getLogger("app.onboarding").error(
            "onboarding_answers_write_failed", extra={"error_type": type(exc).__name__}
        )
    return Response(status_code=204)
async def get_wish_or_404(session, wish_id: UUID, user_id: UUID):  # noqa: ANN001, ANN201
    from app.audit import log_denied_resource_access
    from app.models import Wish

    wish = await session.get(Wish, wish_id)
    if wish is None or wish.owner_id != user_id:
        log_denied_resource_access(user_id, "wish", wish_id)
        raise HTTPException(404, detail={"code": "WISH_NOT_FOUND", "message": "找不到这件事"})
    return wish


# ------------------------------------------------------------------ wishes


@router.post("/wishes", status_code=201, response_model=SeedWishResult)
async def post_wishes(payload: SeedWishRequest, user_id: CurrentUser) -> SeedWishResult:
    """来源：S01 Step 13 → Step 19、S02 Step 12 → Step 21。

    两个事务：先落库原话并提交，再调用 LLM 回填。第二步失败不回滚第一步。
    """
    try:
        async with session_scope(user_id) as session:
            wish, photos, _, _ = await seed_wish(
                session,
                user_id,
                source=payload.source,
                text=payload.text,
                media_id=payload.media_id,
                photo_media_ids=payload.photo_media_ids,
            )
            wish_id = wish.id
    except DomainError as exc:
        raise _err(exc) from exc

    # 第二个事务：语音先转写（S02 Step 15 → 17）
    asr_reason: str | None = None
    if payload.source == "voice":
        async with session_scope(user_id) as session:
            _, asr_reason = await transcribe_wish_audio(session, wish_id, user_id)
    if asr_reason is not None:
        # 转写失败：跳过 Step 18–20，直接返回降级结果（EX-15.1 / EX-15.2）
        async with session_scope(user_id) as session:
            wish = await get_wish_or_404(session, wish_id, user_id)
            return SeedWishResult(
                wish=to_detail(wish, photos), question=None, degraded=True
            )

    # 第三个事务：理解与回填
    async with session_scope(user_id) as session:
        wish, degraded = await enrich_wish(session, wish_id, user_id)
        detail = to_detail(wish, photos)
        question = wish.question_enc
        near_term = bool(
            wish.understanding and wish.understanding.get("kind") == "near_term_todo"
        )
    return SeedWishResult(
        wish=detail,
        question=None if degraded else question,
        actions=["keep_as_future", "delete"] if near_term else None,
        degraded=degraded,
    )


@router.post("/wishes/{wish_id}/understanding", response_model=SeedWishResult)
async def post_understanding(wish_id: UUID, user_id: CurrentUser) -> SeedWishResult:
    """来源：S01 EX-16.1。用户手动重试或 Scheduler 补做。"""
    try:
        async with session_scope(user_id) as session:
            wish, degraded = await enrich_wish(session, wish_id, user_id)
            photos = await photo_ids_of(session, wish_id)
            detail = to_detail(wish, photos)
            question = wish.question_enc
    except DomainError as exc:
        raise _err(exc) from exc
    return SeedWishResult(
        wish=detail, question=None if degraded else question, degraded=degraded
    )


@router.post("/wishes/{wish_id}/answer", response_model=WishDetail)
async def post_answer(
    wish_id: UUID, payload: AnswerRequest, user_id: CurrentUser
) -> WishDetail:
    """来源：S01 Step 22 → Step 24、S02 Step 24 → Step 26。"""
    try:
        async with session_scope(user_id) as session:
            wish = await answer_question(
                session,
                user_id,
                wish_id,
                answer=payload.answer,
                skipped=payload.skipped,
                action=payload.action,
            )
            photos = await photo_ids_of(session, wish_id)
            return to_detail(wish, photos)
    except DomainError as exc:
        raise _err(exc) from exc


@router.get("/wishes", response_model=WishListResponse)
async def get_wishes(
    user_id: CurrentUser,
    state: Annotated[str, Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> WishListResponse:
    """来源：S05.1 Step 2 → Step 5。响应刻意只有 items 与 next_cursor 两个键。"""
    from app.services import list_wishes_page

    try:
        async with session_scope(user_id) as session:
            page, next_cursor = await list_wishes_page(
                session, user_id, state=state, limit=limit, cursor=cursor
            )
            return WishListResponse(
                items=[to_card(w) for w in page], next_cursor=next_cursor
            )
    except DomainError as exc:
        raise _err(exc) from exc


@router.get("/wishes/{wish_id}", response_model=WishDetail)
async def get_wish(wish_id: UUID, user_id: CurrentUser) -> WishDetail:
    """来源：S03 Step 1。越权时返回 404 而非 403（S05 EX-3.1）。"""
    from app.audit import log_denied_resource_access
    from app.models import Wish

    async with session_scope(user_id) as session:
        wish = await session.get(Wish, wish_id)
        if wish is None or wish.owner_id != user_id:
            # 403 会泄露「这个 ID 确实存在」，所以对外一律 404，只在审计日志里留痕
            log_denied_resource_access(user_id, "wish", wish_id)
            raise HTTPException(
                404, detail={"code": "WISH_NOT_FOUND", "message": "找不到这件事"}
            )
        from app.services import detail_of

        return await detail_of(session, wish)


@router.patch("/wishes/{wish_id}", response_model=WishDetail)
async def patch_wish(wish_id: UUID, payload: dict, user_id: CurrentUser) -> WishDetail:
    """来源：S05.2 Step 15「改一改它」。至少改一个字段（minProperties: 1）。"""
    from app.services import amend_wish, detail_of

    try:
        async with session_scope(user_id) as session:
            wish = await amend_wish(
                session,
                user_id,
                wish_id,
                title=(payload or {}).get("title"),
                original_text=(payload or {}).get("original_text"),
            )
            return await detail_of(session, wish)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/let-go", response_model=WishDetail)
async def post_let_go(wish_id: UUID, user_id: CurrentUser) -> WishDetail:
    """来源：S05.2 Step 17 → Step 21。文案与响应中不得出现失败/放弃/未完成。"""
    from app.services import detail_of, let_go_wish

    try:
        async with session_scope(user_id) as session:
            wish = await let_go_wish(session, user_id, wish_id)
            return await detail_of(session, wish)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/recall", response_model=WishDetail)
async def post_recall(wish_id: UUID, user_id: CurrentUser) -> WishDetail:
    """S07：从安静放下区唤回愿望，不调用 Agent 或 ASR。"""
    from app.services import detail_of, recall_wish

    try:
        async with session_scope(user_id) as session:
            wish = await recall_wish(session, user_id, wish_id)
            return await detail_of(session, wish)
    except DomainError as exc:
        raise _err(exc) from exc


@router.delete("/wishes/{wish_id}", status_code=204)
async def delete_wish(
    wish_id: UUID, user_id: CurrentUser, confirm: Annotated[bool, Query()] = False
) -> Response:
    """来源：S05.2 Step 25 → Step 31。服务端强制二次确认（EX-25.1）。"""
    from app.models import Wish

    if confirm is not True:
        raise HTTPException(
            400,
            detail={
                "code": "CONFIRMATION_REQUIRED",
                "message": "彻底删除不可恢复，需要再确认一次",
            },
        )
    from app.services import delete_wish_permanently

    async with session_scope(user_id) as session:
        await delete_wish_permanently(session, user_id, wish_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ media（S02）


@router.post("/media/upload-url", status_code=201, response_model=UploadUrlResult)
async def post_upload_url(payload: UploadUrlRequest, user_id: CurrentUser) -> UploadUrlResult:
    """来源：S02 Step 3 → Step 4。有效期 10 分钟。"""
    from datetime import timedelta

    try:
        async with session_scope(user_id) as session:
            media, url, ttl = await create_upload_url(
                session,
                user_id,
                kind=payload.kind,
                content_type=payload.content_type,
                size_bytes=payload.size_bytes,
            )
            return UploadUrlResult(
                media_id=media.id,
                upload_url=url,
                expires_at=clock.now() + timedelta(seconds=ttl),
            )
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/media/{media_id}/complete", status_code=204)
async def post_media_complete(media_id: UUID, user_id: CurrentUser) -> Response:
    """来源：S02 Step 7 → Step 11。校验不通过时删对象并置 rejected（EX-8.1）。"""
    try:
        async with session_scope(user_id) as session:
            await complete_upload(session, user_id, media_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return Response(status_code=204)


@router.post("/wishes/{wish_id}/transcription", response_model=SeedWishResult)
async def post_transcription(wish_id: UUID, user_id: CurrentUser) -> SeedWishResult:
    """来源：S02 EX-15.1、EX-15.2。原始音频永久保留，因此重试始终可用。"""
    try:
        async with session_scope(user_id) as session:
            wish, reason = await transcribe_wish_audio(session, wish_id, user_id)
            transcribed = reason is None
    except DomainError as exc:
        raise _err(exc) from exc

    if not transcribed:
        async with session_scope(user_id) as session:
            wish = await get_wish_or_404(session, wish_id, user_id)
            photos = await photo_ids_of(session, wish_id)
            return SeedWishResult(wish=to_detail(wish, photos), question=None, degraded=True)

    # 转写成功后继续理解（第二段事务，失败不回滚转写结果）
    async with session_scope(user_id) as session:
        wish, degraded = await enrich_wish(session, wish_id, user_id)
        photos = await photo_ids_of(session, wish_id)
        detail = to_detail(wish, photos)
        question = wish.question_enc
    return SeedWishResult(
        wish=detail, question=None if degraded else question, degraded=degraded
    )


# ------------------------------------------------------------------ timing（S03）


@router.put("/wishes/{wish_id}/timing", response_model=WishDetail)
async def put_timing(wish_id: UUID, payload: dict, user_id: CurrentUser) -> WishDetail:
    """来源：S03 Step 4 → Step 7。幂等；参数非法返回 422 TIMING_INVALID（EX-4.2）。"""
    from app.services import set_timing

    try:
        async with session_scope(user_id) as session:
            wish = await set_timing(session, user_id, wish_id, payload)
            photos = await photo_ids_of(session, wish_id)
            return to_detail(wish, photos)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/ready", response_model=WishDetail)
async def post_ready(wish_id: UUID, user_id: CurrentUser) -> WishDetail:
    """来源：S03 Step 20 → Step 22、S04 Step 2 → Step 4。"""
    from app.services import mark_ready

    try:
        async with session_scope(user_id) as session:
            wish = await mark_ready(session, user_id, wish_id)
            photos = await photo_ids_of(session, wish_id)
            return to_detail(wish, photos)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/defer", response_model=WishDetail)
async def post_defer(wish_id: UUID, user_id: CurrentUser, payload: dict | None = None) -> WishDetail:
    """来源：S03 EX-20.1。默认顺延 3 个月；库中不存在顺延次数字段。"""
    from app.services import defer_wish

    months = (payload or {}).get("after_months", 3)
    if months not in (1, 3, 6, 12):
        raise HTTPException(422, detail={"code": "TIMING_INVALID", "message": "只能顺延 1/3/6/12 个月"})
    try:
        async with session_scope(user_id) as session:
            wish = await defer_wish(session, user_id, wish_id, months)
            photos = await photo_ids_of(session, wish_id)
            return to_detail(wish, photos)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/pause", response_model=WishDetail)
async def post_pause(wish_id: UUID, user_id: CurrentUser) -> WishDetail:
    """来源：S05.2 Step 15 的整理半屏第 2 项。"""
    from app.services import pause_reminders

    try:
        async with session_scope(user_id) as session:
            wish = await pause_reminders(session, user_id, wish_id)
            photos = await photo_ids_of(session, wish_id)
            return to_detail(wish, photos)
    except DomainError as exc:
        raise _err(exc) from exc


# ------------------------------------------------------------------ steps / messages（S04）


@router.post("/wishes/{wish_id}/steps/next", status_code=200)
async def post_next_step(
    wish_id: UUID, user_id: CurrentUser, payload: dict | None = None
) -> dict:
    """来源：S04 Step 5 → Step 11、Step 19 → Step 23。"""
    from app.services import detail_of, request_next_step

    raw = (payload or {}).get("rejected_step_id")
    try:
        rejected = UUID(raw) if raw else None
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            422, detail={"code": "VALIDATION_FAILED", "message": "步骤标识格式不对"}
        ) from exc
    try:
        async with session_scope(user_id) as session:
            step, degraded = await request_next_step(session, user_id, wish_id, rejected)
            if step is None:
                return {"step": None, "degraded": degraded}
            detail = await detail_of(session, await get_wish_or_404(session, wish_id, user_id))
            return {"step": detail.current_step, "degraded": degraded}
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/steps/{step_id}/done", status_code=200)
async def post_step_done(
    wish_id: UUID,
    step_id: UUID,
    user_id: CurrentUser,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> dict:
    """来源：S04 Step 14 → Step 17。缺 If-Match 返回 412，版本不符返回 409。"""
    from app.services import detail_of, mark_step_done

    if if_match is None:
        raise HTTPException(
            412, detail={"code": "PRECONDITION_REQUIRED", "message": "需要带上当前版本号"}
        )
    try:
        expected = int(if_match.strip('"'))
    except ValueError as exc:
        raise HTTPException(
            412, detail={"code": "PRECONDITION_REQUIRED", "message": "版本号格式不对"}
        ) from exc
    try:
        async with session_scope(user_id) as session:
            step, wish = await mark_step_done(session, user_id, wish_id, step_id, expected)
            detail = await detail_of(session, wish)
            entry = {
                "id": str(step.id),
                "text": step.text_enc,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            }
            return {"timeline_entry": entry, "wish": detail.model_dump(mode="json")}
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/messages", status_code=200)
async def post_message(wish_id: UUID, payload: dict, user_id: CurrentUser) -> dict:
    """来源：S04 EX-23.1。amend / assist / fatigue / chat 四种意图同一通道。"""
    from app.services import detail_of, send_message

    text = (payload or {}).get("text", "")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise HTTPException(422, detail={"code": "VALIDATION_FAILED", "message": "这句话收不下"})
    try:
        async with session_scope(user_id) as session:
            reply, intent, wish, degraded = await send_message(session, user_id, wish_id, text)
            detail = await detail_of(session, wish)
            return {
                "reply": reply,
                "intent": intent,
                "wish": detail.model_dump(mode="json"),
                "degraded": degraded,
            }
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/wishes/{wish_id}/back-to-brewing", response_model=WishDetail)
async def post_back_to_brewing(wish_id: UUID, user_id: CurrentUser) -> WishDetail:
    """来源：S05.2 整理半屏第 3 项、S04 EX-15.2 三选项之一。"""
    from app.services import back_to_brewing, detail_of

    try:
        async with session_scope(user_id) as session:
            wish = await back_to_brewing(session, user_id, wish_id)
            return await detail_of(session, wish)
    except DomainError as exc:
        raise _err(exc) from exc


# ------------------------------------------------------------------ memories（S06）


@router.post("/wishes/{wish_id}/happened", status_code=201, response_model=MemoryResult)
async def post_happened(
    wish_id: UUID, payload: HappenedRequest, user_id: CurrentUser
) -> MemoryResult:
    """来源：S06 Step 3 → Step 10。本步即停提醒，但状态要到 publish 才转 happened。"""
    from app.services import mark_wish_happened, to_memory_out

    try:
        async with session_scope(user_id) as session:
            memory, degraded, warning = await mark_wish_happened(
                session,
                user_id,
                wish_id,
                happened_from=payload.happened_from,
                happened_to=payload.happened_to,
                acknowledged_before_seeded=payload.acknowledged_before_seeded,
            )
            return MemoryResult(
                memory=await to_memory_out(session, memory),
                degraded=degraded,
                warning=warning,
            )
    except DomainError as exc:
        raise _err(exc) from exc


@router.get("/memories", response_model=MemoryListResponse)
async def get_memories(
    user_id: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> MemoryListResponse:
    """来源：S06 Step 20。lived_pages 是产品内唯一允许的计数。"""
    from app.services import list_memories, to_memory_card

    try:
        async with session_scope(user_id) as session:
            page, next_cursor, lived = await list_memories(
                session, user_id, limit=limit, cursor=cursor
            )
            return MemoryListResponse(
                items=[await to_memory_card(session, m) for m in page],
                next_cursor=next_cursor,
                lived_pages=lived,
            )
    except DomainError as exc:
        raise _err(exc) from exc


@router.get("/memories/{memory_id}", response_model=MemoryOut)
async def get_memory_page(memory_id: UUID, user_id: CurrentUser) -> MemoryOut:
    """来源：S06 Step 20。草稿与已发布共用同一端点，由 status 区分。"""
    from app.services import get_memory, to_memory_out

    try:
        async with session_scope(user_id) as session:
            memory = await get_memory(session, user_id, memory_id)
            return await to_memory_out(session, memory)
    except DomainError as exc:
        raise _err(exc) from exc


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
async def patch_memory(memory_id: UUID, payload: dict, user_id: CurrentUser) -> MemoryOut:
    """来源：S06 Step 12 → Step 14。所有字段均可置 null，不做任何非空校验。"""
    from app.services import to_memory_out, update_memory

    try:
        async with session_scope(user_id) as session:
            memory = await update_memory(session, user_id, memory_id, payload or {})
            return await to_memory_out(session, memory)
    except DomainError as exc:
        raise _err(exc) from exc


@router.post("/memories/{memory_id}/publish", response_model=PublishResult)
async def post_publish(memory_id: UUID, user_id: CurrentUser) -> PublishResult:
    """来源：S06 Step 16 → Step 19。幂等，重复提交不重复计数（EX-17.1）。"""
    from app.services import publish_memory, to_memory_out

    try:
        async with session_scope(user_id) as session:
            memory = await publish_memory(session, user_id, memory_id)
            return PublishResult(memory=await to_memory_out(session, memory))
    except DomainError as exc:
        raise _err(exc) from exc


# ------------------------------------------------------------------ preferences（S08）


@router.get("/me/preferences", response_model=PreferenceListResponse)
async def get_preferences(
    user_id: CurrentUser, include_revoked: Annotated[bool, Query()] = False
) -> PreferenceListResponse:
    """来源：S08 Step 2 → Step 6。默认不含已撤回行；摘要随列表返回。"""
    from app.preferences import list_preferences

    data = await list_preferences(user_id, include_revoked=include_revoked)
    return PreferenceListResponse(**data)


@router.put("/me/preferences", response_model=PreferenceMeta)
async def put_preference(user_id: CurrentUser, payload: DeclarePreferenceRequest) -> PreferenceMeta:
    """来源：S08 Step 7 → Step 11。响应只含元数据，不回显 value 明文（UT-S08-04）。"""
    from app.preferences import declare_preference

    try:
        meta = await declare_preference(user_id, payload.pref_key, payload.value)
    except DomainError as exc:
        raise _err(exc) from exc
    return PreferenceMeta(**meta)


@router.post("/me/preferences/{pref_id}/revoke", response_model=dict)
async def post_preference_revoke(user_id: CurrentUser, pref_id: UUID) -> dict:
    """来源：S08 Step 12 → Step 16。仅 inferred 且未撤回可撤回（EX-14.1）。"""
    from app.preferences import revoke_preference

    try:
        item = await revoke_preference(user_id, pref_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return item


@router.delete("/me/preferences/{pref_id}", status_code=204)
async def delete_preference(user_id: CurrentUser, pref_id: UUID) -> Response:
    """来源：S08 Step 17 → Step 20。硬删除；同事务失效引用它的 pending 建议（EX-19.1）。"""
    from app.preferences import delete_preference

    try:
        await delete_preference(user_id, pref_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return Response(status_code=204)


@router.get("/me/availability", response_model=AvailabilityListResponse)
async def get_availability(user_id: CurrentUser) -> AvailabilityListResponse:
    """来源：S08 Step 2 → Step 6。free_weekend 类时机计算以本表为依据。"""
    from app.preferences import list_availability

    data = await list_availability(user_id)
    return AvailabilityListResponse(items=[AvailabilityOut(**i) for i in data["items"]])


@router.post("/me/availability", status_code=201, response_model=AvailabilityOut)
async def post_availability(user_id: CurrentUser, payload: AvailabilityCreateRequest) -> AvailabilityOut:
    """来源：S08 Step 21 → Step 25。响应不回显 note 明文。"""
    from app.preferences import create_availability

    try:
        item = await create_availability(
            user_id, payload.weekday, payload.start_minute, payload.end_minute, payload.note
        )
    except DomainError as exc:
        raise _err(exc) from exc
    return AvailabilityOut(**item)


@router.patch("/me/availability/{window_id}", response_model=AvailabilityOut)
async def patch_availability(
    user_id: CurrentUser, window_id: UUID, payload: AvailabilityUpdateRequest
) -> AvailabilityOut:
    """来源：S08 设计文档「可用时段」区的编辑动作。校验规则与 POST 相同。"""
    from app.preferences import update_availability

    changes = payload.model_dump(exclude_unset=True)
    try:
        item = await update_availability(user_id, window_id, changes)
    except DomainError as exc:
        raise _err(exc) from exc
    return AvailabilityOut(**item)


@router.delete("/me/availability/{window_id}", status_code=204)
async def delete_availability(user_id: CurrentUser, window_id: UUID) -> Response:
    """来源：S08 Step 17 → Step 20。硬删除；同事务失效引用它的 pending 建议。"""
    from app.preferences import delete_availability

    try:
        await delete_availability(user_id, window_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return Response(status_code=204)


# ------------------------------------------------------------------ timing proposals（S08 增补）


@router.post("/wishes/{wish_id}/timing-proposals", status_code=200)
async def post_timing_proposal(wish_id: UUID, user_id: CurrentUser) -> dict:
    """来源：S03 时机提议分支 P1 → P11。LLM 只产出草稿；degraded=true 表示不可用（EX-P.1）。"""
    from app.db import session_scope
    from app.proposals import create_proposal

    try:
        async with session_scope(user_id) as session:
            proposal = await create_proposal(session, user_id, wish_id)
    except DomainError as exc:
        raise _err(exc) from exc
    if proposal is None:
        return {"proposal": None, "degraded": True}
    return {"proposal": TimingProposalOut(**proposal), "degraded": False}


@router.get("/wishes/{wish_id}/timing-proposals", response_model=ProposalListResponse)
async def get_timing_proposals(wish_id: UUID, user_id: CurrentUser) -> ProposalListResponse:
    """来源：S03 分支 P10 与四层边界第 2 层的审计要求。含全部决策与过期记录。"""
    from app.db import session_scope
    from app.proposals import list_proposals

    try:
        async with session_scope(user_id) as session:
            items = await list_proposals(session, user_id, wish_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return ProposalListResponse(items=[TimingProposalOut(**i) for i in items])


@router.post("/wishes/{wish_id}/timing-proposals/{proposal_id}/confirm", response_model=ProposalConfirmResult)
async def post_proposal_confirm(
    wish_id: UUID, proposal_id: UUID, user_id: CurrentUser, payload: dict | None = None
) -> ProposalConfirmResult:
    """来源：S03 分支 P12 → P15。body 必须为空——只接受已校验的提议（EX-P.4）。"""
    from app.db import session_scope
    from app.proposals import confirm_proposal
    from app.steps import detail_of

    if payload:
        raise HTTPException(
            422, detail={"code": "PROPOSAL_CONFIRM_BODY_FORBIDDEN", "message": "确认就好，不用再填时间"}
        )
    try:
        async with session_scope(user_id) as session:
            wish, proposal = await confirm_proposal(session, user_id, wish_id, proposal_id)
            detail = await detail_of(session, wish)
    except DomainError as exc:
        raise _err(exc) from exc
    return ProposalConfirmResult(
        wish=detail, proposal=TimingProposalOut(**_proposal_out_of(proposal))
    )


@router.post("/wishes/{wish_id}/timing-proposals/{proposal_id}/reject", response_model=ProposalRejectResult)
async def post_proposal_reject(
    wish_id: UUID, proposal_id: UUID, user_id: CurrentUser
) -> ProposalRejectResult:
    """来源：S03 分支 P16 / EX-P.3。不写 wishes 任何字段。"""
    from app.db import session_scope
    from app.proposals import reject_proposal

    try:
        async with session_scope(user_id) as session:
            proposal = await reject_proposal(session, user_id, wish_id, proposal_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return ProposalRejectResult(proposal=TimingProposalOut(**_proposal_out_of(proposal)))


def _proposal_out_of(row) -> dict:
    """TimingProposal ORM 行 → TimingProposalOut dict（reason 解密由 EncryptedText 完成）。"""
    return {
        "id": row.id,
        "wish_id": row.wish_id,
        "status": row.status,
        "timing_type": row.timing_type,
        "timing_value": row.timing_value,
        "proposed_trigger_at": row.proposed_trigger_at,
        "reason": row.reason_enc,
        "confidence": row.confidence,
        "evidence": row.evidence or [],
        "validation": row.validation_result or {"valid": True, "reason_code": None},
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "decided_at": row.decided_at,
    }


# ------------------------------------------------------------------ notification channels（S10）


@router.patch("/me/notification-channels", response_model=NotificationChannels)
async def patch_notification_channels(
    user_id: CurrentUser, payload: NotificationChannelsUpdate
) -> NotificationChannels:
    """来源：S10 Step 6 → Step 10。切换立即生效；全关时 outbox 的 pending 顺延保留（EX-D2.1）。"""
    from sqlalchemy import update as sa_update

    from app.db import session_scope
    from app.models import User

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            422, detail={"code": "VALIDATION_FAILED", "message": "至少要提交一个开关"}
        )
    async with session_scope(user_id) as session:
        await session.execute(
            sa_update(User).where(User.id == user_id).values(**changes)
        )
        row = await session.get(User, user_id)
    return NotificationChannels(push_enabled=row.push_enabled, email_enabled=row.email_enabled)


# ------------------------------------------------------------------ lite events（S09）


@router.post("/lite-events", status_code=201, response_model=LiteEventOut)
async def post_lite_event(user_id: CurrentUser, payload: LiteEventCreate) -> LiteEventOut:
    """来源：S09 Step 8 → Step 13。纯写入：无 Agent、无提醒、无任何副作用扩散。"""
    from app.db import session_scope
    from app.lite_events import create

    try:
        async with session_scope(user_id) as session:
            item = await create(session, user_id, payload.text)
    except DomainError as exc:
        raise _err(exc) from exc
    return LiteEventOut(**item)


@router.get("/lite-events", response_model=LiteEventListResponse)
async def get_lite_events(
    user_id: CurrentUser, include_done: Annotated[bool, Query()] = False
) -> LiteEventListResponse:
    """来源：S09 Step 3 → Step 7。默认只取 open 状态；无分页、无计数字段。"""
    from app.db import session_scope
    from app.lite_events import list_events

    async with session_scope(user_id) as session:
        items = await list_events(session, user_id, include_done=include_done)
    return LiteEventListResponse(items=[LiteEventOut(**i) for i in items])


@router.post("/lite-events/{event_id}/done", response_model=LiteEventOut)
async def post_lite_event_done(user_id: CurrentUser, event_id: UUID) -> LiteEventOut:
    """来源：S09 Step 14 → Step 18。已关闭的事件重复 done 返回 409（EX-14.1）。"""
    from app.db import session_scope
    from app.lite_events import mark_done

    try:
        async with session_scope(user_id) as session:
            item = await mark_done(session, user_id, event_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return LiteEventOut(**item)


@router.delete("/lite-events/{event_id}", status_code=204)
async def delete_lite_event(user_id: CurrentUser, event_id: UUID) -> Response:
    """来源：S09 Step 19 → Step 22。硬删除；重复或跨用户一律 404（EX-22.1）。"""
    from app.db import session_scope
    from app.lite_events import delete as delete_event

    try:
        async with session_scope(user_id) as session:
            await delete_event(session, user_id, event_id)
    except DomainError as exc:
        raise _err(exc) from exc
    return Response(status_code=204)


# ------------------------------------------------------------------ 测试后门

test_router = APIRouter(prefix="/api/test")
# 本地对象存储的接收端单独一个 router：它在 local 也要注册，而 test_router 不。
# 两者共用 /api/test 前缀，因此 staging / production 下两个都不存在（SMOKE-core-04）。
local_router = APIRouter(prefix="/api/test")


@test_router.post("/faults", status_code=204)
async def arm_faults(payload: dict) -> Response:
    """武装 / 解除故障注入点。仅 APP_ENV in (local, test) 注册（SMOKE-core-04）。

    ST-S01-03 与 ST-S01-04 依赖它：数据库连不上、某张表写入失败这类故障
    无法用输入构造，只能从外部注入。
    """
    from app.faults import set_armed

    try:
        set_armed(list(payload.get("armed") or []))
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "VALIDATION_FAILED", "message": str(exc)}
        ) from exc
    return Response(status_code=204)


@test_router.post("/clock", status_code=204)
async def set_clock(payload: dict) -> Response:
    """来源：system.yaml → testSetClock。仅 APP_ENV=test 注册。"""
    from datetime import datetime

    raw = payload.get("now")
    clock.set_fixed(datetime.fromisoformat(raw) if raw else None)
    return Response(status_code=204)


@local_router.put("/object/{object_key:path}", status_code=200)
async def put_local_object(
    object_key: str,
    request: Request,
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query()],
) -> Response:
    """本地对象存储的接收端。仅 APP_ENV in (local, test) 时存在。

    它替代 S3 的预签名 PUT：签名与过期校验走 LocalObjectStorage 自己的
    HMAC 逻辑，因此 S02 EX-5.1「预签名被篡改 / 过期」是真实可测的。
    唯一测不出的是「直传不经过 API 进程」——那是 S3 才有的属性（UT-S02-25）。
    """
    from app.storage import LocalObjectStorage, get_storage

    storage = get_storage()
    if not isinstance(storage, LocalObjectStorage):
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "not available"})
    failure = storage.verify(object_key, exp, sig)
    if failure is not None:
        raise HTTPException(
            403, detail={"code": "PRESIGN_INVALID", "message": failure}
        )
    storage.put(object_key, await request.body())
    return Response(status_code=200)



@test_router.post("/scheduler/tick", status_code=200)
async def trigger_scheduler_tick() -> dict:
    """来源：system.yaml → testTriggerSchedulerTick。同步跑一轮扫描并返回统计。"""
    from dataclasses import asdict

    from app.scheduler import run_tick

    return asdict(await run_tick())


@test_router.get("/outbox", status_code=200)
async def read_outbox(user_id: Annotated[UUID, Query(alias="user_id")]) -> dict:
    """来源：system.yaml → testReadOutbox。断言周预算与去重用。"""
    from sqlalchemy import select as sa_select

    from app.models import ReminderOutbox, ReminderWeeklyCounter, User
    from app.timing import week_start

    async with session_scope(user_id) as session:
        rows = list(
            (
                await session.scalars(
                    sa_select(ReminderOutbox)
                    .where(ReminderOutbox.owner_id == user_id)
                    .order_by(ReminderOutbox.created_at)
                )
            ).all()
        )
        user = await session.get(User, user_id)
        wk = week_start(clock.now(), user.timezone if user else "Asia/Shanghai").isoformat()
        counter = await session.get(ReminderWeeklyCounter, (user_id, wk))
        return {
            "items": [
                {
                    "wish_id": str(r.wish_id),
                    "kind": r.kind,
                    "channel": r.channel,
                    "status": r.status,
                    "timing_occurrence": r.timing_occurrence,
                    "body": r.body_enc,
                    "attempts": r.attempts,
                }
                for r in rows
            ],
            "delivered_count_this_week": counter.delivered_count if counter else 0,
        }


@test_router.get("/latest-email", status_code=200)
async def read_latest_email(to: Annotated[str, Query()]) -> dict:
    """来源：system.yaml → testReadLatestEmail。"""
    from app.notify import InMemoryEmailSender, get_email_sender

    sender = get_email_sender()
    if not isinstance(sender, InMemoryEmailSender):
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "not available"})
    item = sender.latest(to)
    if item is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "no email"})
    return {
        "to": item.to,
        "subject": item.subject,
        "body": item.body,
        "sent_at": item.sent_at.isoformat(),
    }


@test_router.post("/push-subscription", status_code=204)
async def register_push_subscription(payload: dict) -> Response:
    """测试夹具用：注册一个 push 订阅，以便断言 push 优先于邮件（EX-16.1）。"""
    import uuid as _uuid

    from app.models import PushSubscription

    owner = UUID(payload["user_id"])
    async with session_scope(owner) as session:
        session.add(
            PushSubscription(
                id=_uuid.uuid4(),
                owner_id=owner,
                endpoint=payload.get("endpoint", f"https://push.test/{owner}"),
                p256dh="k",
                auth_secret="a",
            )
        )
    return Response(status_code=204)
