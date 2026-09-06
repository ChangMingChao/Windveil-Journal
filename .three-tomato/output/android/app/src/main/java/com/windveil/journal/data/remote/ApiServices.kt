package com.windveil.journal.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Retrofit 接口 — 端点与 operationId 一一对应 logos/resources/api 目录下各 yaml 契约。
 * 认证：Bearer access token（15 分钟）；refresh token 走 httpOnly Cookie（由 CookieJar 持久化）。
 */
interface AuthApi {
    @POST("api/v1/auth/anonymous")
    suspend fun createAnonymousSpace(@Body body: AnonymousRequest): Response<AuthResult>

    @POST("api/v1/auth/link-email")
    suspend fun linkEmail(@Body body: LinkEmailRequest): Response<UserProfile>

    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): Response<AuthResult>

    @POST("api/v1/auth/refresh")
    suspend fun refreshToken(): Response<AuthResult>

    @POST("api/v1/auth/logout")
    suspend fun logout(): Response<Unit>

    @GET("api/v1/me")
    suspend fun getMe(): Response<UserProfile>

    @POST("api/v1/onboarding/answers")
    suspend fun submitOnboardingAnswers(@Body body: OnboardingAnswersRequest): Response<Unit>

    @PATCH("api/v1/me/notification-channels")
    suspend fun updateNotificationChannels(@Body body: ChannelsUpdateRequest): Response<NotificationChannels>
}

/** S08：偏好与可用时段（「它记得我什么」）。 */
interface PreferenceApi {
    @GET("api/v1/me/preferences")
    suspend fun listPreferences(@Query("include_revoked") includeRevoked: Boolean = false): Response<PreferenceListResponse>

    @PUT("api/v1/me/preferences")
    suspend fun declarePreference(@Body body: PreferenceDeclareRequest): Response<PreferenceMeta>

    @POST("api/v1/me/preferences/{pref_id}/revoke")
    suspend fun revokePreference(@Path("pref_id") prefId: String): Response<PreferenceItem>

    @DELETE("api/v1/me/preferences/{pref_id}")
    suspend fun deletePreference(@Path("pref_id") prefId: String): Response<Unit>

    @GET("api/v1/me/availability")
    suspend fun listAvailability(): Response<AvailabilityListResponse>

    @POST("api/v1/me/availability")
    suspend fun createAvailability(@Body body: AvailabilityCreateRequest): Response<AvailabilityWindow>

    @DELETE("api/v1/me/availability/{window_id}")
    suspend fun deleteAvailability(@Path("window_id") windowId: String): Response<Unit>
}

/** 愿望：种下、浏览、整理、时机、最小步骤与对话。 */
interface WishesApi {
    @POST("api/v1/wishes")
    suspend fun seedWish(@Body body: SeedWishRequest): Response<SeedWishResult>

    @GET("api/v1/wishes")
    suspend fun listWishes(
        @Query("state") state: String? = null,
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
    ): Response<WishListResponse>

    @GET("api/v1/wishes/{wish_id}")
    suspend fun getWish(@Path("wish_id") wishId: String): Response<WishDetail>

    @PATCH("api/v1/wishes/{wish_id}")
    suspend fun amendWish(@Path("wish_id") wishId: String, @Body body: AmendWishRequest): Response<WishDetail>

    @DELETE("api/v1/wishes/{wish_id}")
    suspend fun deleteWishPermanently(@Path("wish_id") wishId: String, @Query("confirm") confirm: Boolean): Response<Unit>

    @POST("api/v1/wishes/{wish_id}/answer")
    suspend fun answerQuestion(@Path("wish_id") wishId: String, @Body body: AnswerRequest): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/understanding")
    suspend fun retryUnderstanding(@Path("wish_id") wishId: String): Response<SeedWishResult>

    @POST("api/v1/wishes/{wish_id}/transcription")
    suspend fun retryTranscription(@Path("wish_id") wishId: String): Response<SeedWishResult>

    @PUT("api/v1/wishes/{wish_id}/timing")
    suspend fun setTiming(@Path("wish_id") wishId: String, @Body body: TimingInput): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/ready")
    suspend fun markReady(@Path("wish_id") wishId: String): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/defer")
    suspend fun defer(@Path("wish_id") wishId: String, @Body body: Map<String, Int> = emptyMap()): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/pause")
    suspend fun pauseReminders(@Path("wish_id") wishId: String): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/back-to-brewing")
    suspend fun backToBrewing(@Path("wish_id") wishId: String): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/let-go")
    suspend fun letGo(@Path("wish_id") wishId: String): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/recall")
    suspend fun recall(@Path("wish_id") wishId: String): Response<WishDetail>

    @POST("api/v1/wishes/{wish_id}/timing-proposals")
    suspend fun createTimingProposal(@Path("wish_id") wishId: String): Response<ProposalResponse>

    @GET("api/v1/wishes/{wish_id}/timing-proposals")
    suspend fun listTimingProposals(@Path("wish_id") wishId: String): Response<ProposalListResponse>

    @POST("api/v1/wishes/{wish_id}/timing-proposals/{proposal_id}/confirm")
    suspend fun confirmProposal(
        @Path("wish_id") wishId: String,
        @Path("proposal_id") proposalId: String,
    ): Response<ConfirmProposalResponse>

    @POST("api/v1/wishes/{wish_id}/timing-proposals/{proposal_id}/reject")
    suspend fun rejectProposal(
        @Path("wish_id") wishId: String,
        @Path("proposal_id") proposalId: String,
    ): Response<RejectProposalResponse>

    @POST("api/v1/wishes/{wish_id}/convert-to-lite")
    suspend fun convertToLite(@Path("wish_id") wishId: String): Response<LiteEvent>

    @POST("api/v1/wishes/{wish_id}/steps/next")
    suspend fun requestNextStep(@Path("wish_id") wishId: String, @Body body: NextStepRequest = NextStepRequest()): Response<NextStepResponse>

    @POST("api/v1/wishes/{wish_id}/steps/{step_id}/done")
    suspend fun markStepDone(
        @Path("wish_id") wishId: String,
        @Path("step_id") stepId: String,
        @Header("If-Match") ifMatch: String,
    ): Response<StepDoneResponse>

    @POST("api/v1/wishes/{wish_id}/messages")
    suspend fun sendMessage(@Path("wish_id") wishId: String, @Body body: SendMessageRequest): Response<SendMessageResponse>
}

/** heart-voice-holiday-timing：法定节假日枚举（自己选时机用）。 */
interface HolidaysApi {
    @GET("api/v1/holidays")
    suspend fun holidays(@Query("year") year: Int? = null): Response<com.windveil.journal.data.remote.HolidaysResponse>
}

/** S06：已发生之书。 */
interface MemoriesApi {
    @POST("api/v1/wishes/{wish_id}/happened")
    suspend fun markHappened(@Path("wish_id") wishId: String, @Body body: MarkHappenedRequest): Response<MarkHappenedResponse>

    @GET("api/v1/memories")
    suspend fun listMemories(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
    ): Response<MemoryListResponse>

    @GET("api/v1/memories/{memory_id}")
    suspend fun getMemory(@Path("memory_id") memoryId: String): Response<Memory>

    @PATCH("api/v1/memories/{memory_id}")
    suspend fun updateMemory(@Path("memory_id") memoryId: String, @Body body: MemoryUpdateRequest): Response<Memory>

    @POST("api/v1/memories/{memory_id}/publish")
    suspend fun publishMemory(@Path("memory_id") memoryId: String): Response<PublishMemoryResponse>
}

/** S09：轻事件 — 纯记录、无 Agent、无提醒路径。 */
interface LiteEventsApi {
    @POST("api/v1/lite-events")
    suspend fun create(@Body body: LiteEventCreateRequest): Response<LiteEvent>

    @GET("api/v1/lite-events")
    suspend fun list(@Query("include_done") includeDone: Boolean = false): Response<LiteEventListResponse>

    @POST("api/v1/lite-events/{event_id}/done")
    suspend fun markDone(@Path("event_id") eventId: String): Response<LiteEvent>

    @DELETE("api/v1/lite-events/{event_id}")
    suspend fun delete(@Path("event_id") eventId: String): Response<Unit>
}

/** S02：媒体预签名直传（不经本服务转发）。 */
interface MediaApi {
    @POST("api/v1/media/upload-url")
    suspend fun createUploadUrl(@Body body: MediaUploadUrlRequest): Response<MediaUploadUrlResponse>

    @POST("api/v1/media/{media_id}/complete")
    suspend fun completeUpload(@Path("media_id") mediaId: String): Response<Unit>
}

interface SystemApi {
    @GET("api/v1/health")
    suspend fun health(): Response<HealthResponse>
}
