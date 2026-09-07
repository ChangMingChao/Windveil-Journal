package com.windveil.journal.data.remote

import com.google.gson.annotations.SerializedName

/**
 * 数据模型 — 严格对齐 logos/resources/api 目录下各 yaml 契约 契约。
 * 约定（来自 wishes.yaml 契约说明）：
 * 1. 越权访问返回 404 而非 403；
 * 2. 愿望相关响应不含 total / completed_count / overdue_days 等统计字段。
 */

// ---------- 通用 ----------

data class ErrorResponse(
    val code: String,
    val message: String,
    val details: Map<String, Any?>? = null,
)

/** 契约约定：HTTP 404 一律视为「不存在或不属于你」；HTTP 409 视为状态不允许。 */
class ApiException(
    val httpCode: Int,
    val error: ErrorResponse,
) : Exception(error.message)

// ---------- auth.yaml ----------

data class AuthResult(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String,
    @SerializedName("expires_in") val expiresIn: Int,
    val user: UserProfile,
)

data class UserProfile(
    val id: String,
    val email: String? = null,
    @SerializedName("is_anonymous") val isAnonymous: Boolean,
    @SerializedName("onboarded_at") val onboardedAt: String? = null,
    val timezone: String,
    @SerializedName("push_enabled") val pushEnabled: Boolean = false,
    @SerializedName("email_enabled") val emailEnabled: Boolean = false,
    @SerializedName("created_at") val createdAt: String? = null,
)

data class AnonymousRequest(val timezone: String = "Asia/Shanghai")
data class LinkEmailRequest(val email: String, val password: String)
data class LoginRequest(val email: String, val password: String)
data class OnboardingAnswer(val question_key: String, val answer_text: String? = null)
data class OnboardingAnswersRequest(val answers: List<OnboardingAnswer>)

data class NotificationChannels(
    @SerializedName("push_enabled") val pushEnabled: Boolean,
    @SerializedName("email_enabled") val emailEnabled: Boolean,
)

data class ChannelsUpdateRequest(
    @SerializedName("push_enabled") val pushEnabled: Boolean? = null,
    @SerializedName("email_enabled") val emailEnabled: Boolean? = null,
)

data class PreferenceItem(
    val id: String,
    val kind: String, // entry | digest
    @SerializedName("pref_key") val prefKey: String,
    val source: String, // declared | inferred
    val confidence: Int? = null,
    val value: String,
    @SerializedName("revoked_at") val revokedAt: String? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
)

data class PreferenceListResponse(
    val items: List<PreferenceItem>,
    val digest: PreferenceItem? = null,
)

data class PreferenceMeta(
    val id: String,
    val kind: String,
    @SerializedName("pref_key") val prefKey: String,
    val source: String,
    val confidence: Int? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
)

data class PreferenceDeclareRequest(
    @SerializedName("pref_key") val prefKey: String,
    val value: String,
)

data class AvailabilityWindow(
    val id: String,
    val weekday: Int, // 0=周一（ISO），6=周日
    @SerializedName("start_minute") val startMinute: Int,
    @SerializedName("end_minute") val endMinute: Int,
    val note: String? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
)

data class AvailabilityListResponse(val items: List<AvailabilityWindow>)

data class AvailabilityCreateRequest(
    val weekday: Int,
    @SerializedName("start_minute") val startMinute: Int,
    @SerializedName("end_minute") val endMinute: Int,
    val note: String? = null,
)

// ---------- wishes.yaml ----------

data class SeedWishRequest(
    val source: String, // text | voice
    val text: String? = null,
    @SerializedName("media_id") val mediaId: String? = null,
    @SerializedName("photo_media_ids") val photoMediaIds: List<String>? = null,
)

data class SeedWishResult(
    val wish: WishDetail,
    val question: String? = null,
    // 契约中 actions 为可选字段：降级路径可能不返回；Gson 不走 Kotlin 默认值，须显式可空
    val actions: List<String>? = null, // keep_as_future | save_as_lite | delete
    val degraded: Boolean,
)

data class WishListResponse(
    val items: List<WishCard>,
    @SerializedName("next_cursor") val nextCursor: String? = null,
)

data class WishCard(
    val id: String,
    val title: String,
    @SerializedName("original_text_excerpt") val originalTextExcerpt: String? = null,
    @SerializedName("seeded_at") val seededAt: String,
    @SerializedName("let_go_at") val letGoAt: String? = null,
    val state: String, // seeded | brewing | wind | going | happened | let_go
    val timing: Timing,
    @SerializedName("soft_deferred") val softDeferred: Boolean = false,
    @SerializedName("degraded_reason") val degradedReason: String? = null,
    val version: Int,
)

data class Timing(
    val type: String,
    val label: String,
    @SerializedName("trigger_kind") val triggerKind: String, // time | signal | none
    @SerializedName("next_trigger_at") val nextTriggerAt: String? = null,
)

data class TimingInput(
    // season | month_day | after_months | free_weekend | when_tired | none | holiday
    val type: String,
    val season: String? = null, // spring | summer | autumn | winter
    @SerializedName("month_day") val monthDay: String? = null, // YYYY-MM 或 YYYY-MM-DD
    @SerializedName("after_months") val afterMonths: Int? = null, // 1 | 3 | 6 | 12
    // type=holiday：所选法定节假日名（heart-voice-holiday-timing）
    val holidays: List<String>? = null,
)

data class WishUnderstanding(
    val kind: String, // future_wish | near_term_todo
    val feeling: String? = null,
    val conditions: Map<String, Any?>? = null,
    @SerializedName("smallest_step") val smallestStep: String? = null,
)

data class WishStep(
    val id: String,
    val text: String,
    val status: String, // proposed | done | rejected
    @SerializedName("est_minutes") val estMinutes: Int? = null,
    @SerializedName("involves_cost") val involvesCost: Boolean = false,
    @SerializedName("involves_others") val involvesOthers: Boolean = false,
    val source: String, // llm | fallback
    @SerializedName("completed_at") val completedAt: String? = null,
)

data class TimelineEntry(
    val id: String,
    val text: String,
    @SerializedName("completed_at") val completedAt: String,
)

data class WishMessage(
    val id: String,
    val role: String, // user | agent
    val text: String,
    val intent: String? = null, // chat | amend | assist | fatigue
    @SerializedName("created_at") val createdAt: String,
)

data class TimingProposal(
    val id: String,
    @SerializedName("wish_id") val wishId: String,
    val status: String, // pending | confirmed | rejected | expired
    @SerializedName("timing_type") val timingType: String, // season | month_day | after_months | free_weekend
    @SerializedName("timing_value") val timingValue: String? = null,
    @SerializedName("proposed_trigger_at") val proposedTriggerAt: String? = null,
    val reason: String? = null,
    val confidence: Int? = null,
    val evidence: List<EvidenceRef> = emptyList(),
    val validation: ProposalValidation,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("expires_at") val expiresAt: String? = null,
    @SerializedName("decided_at") val decidedAt: String? = null,
)

data class EvidenceRef(val kind: String, val id: String)

data class ProposalValidation(val valid: Boolean, @SerializedName("reason_code") val reasonCode: String? = null)

data class WishDetail(
    // WishCard 部分
    val id: String,
    val title: String,
    @SerializedName("original_text_excerpt") val originalTextExcerpt: String? = null,
    @SerializedName("seeded_at") val seededAt: String,
    @SerializedName("let_go_at") val letGoAt: String? = null,
    val state: String,
    val timing: Timing,
    @SerializedName("soft_deferred") val softDeferred: Boolean = false,
    @SerializedName("degraded_reason") val degradedReason: String? = null,
    val version: Int,
    // WishDetail 扩展
    @SerializedName("original_text") val originalText: String? = null,
    @SerializedName("audio_media_id") val audioMediaId: String? = null,
    @SerializedName("photo_media_ids") val photoMediaIds: List<String> = emptyList(),
    val understanding: WishUnderstanding? = null,
    @SerializedName("pending_question") val pendingQuestion: Boolean = false,
    @SerializedName("timing_proposal") val timingProposal: TimingProposal? = null,
    @SerializedName("amended_from") val amendedFrom: String? = null,
    @SerializedName("current_step") val currentStep: WishStep? = null,
    val timeline: List<TimelineEntry>? = null,
    val messages: List<WishMessage>? = null,
)

data class AmendWishRequest(
    val title: String? = null,
    @SerializedName("original_text") val originalText: String? = null,
)

data class AnswerRequest(
    val answer: String? = null,
    val skipped: Boolean? = null,
    val action: String? = null, // keep_as_future
)

data class NextStepRequest(@SerializedName("rejected_step_id") val rejectedStepId: String? = null)

data class NextStepResponse(val step: WishStep?, val degraded: Boolean)

data class StepDoneResponse(
    @SerializedName("timeline_entry") val timelineEntry: TimelineEntry,
    val wish: WishDetail,
)

data class SendMessageRequest(val text: String)

data class SendMessageResponse(
    val reply: String?,
    val intent: String,
    val wish: WishDetail,
    val degraded: Boolean,
)

data class ProposalResponse(val proposal: TimingProposal?, val degraded: Boolean)

data class ProposalListResponse(val items: List<TimingProposal>)

data class ConfirmProposalResponse(val wish: WishDetail, val proposal: TimingProposal)

data class RejectProposalResponse(val proposal: TimingProposal)

// ---------- memories.yaml ----------

data class MarkHappenedRequest(
    @SerializedName("happened_from") val happenedFrom: String, // YYYY-MM-DD
    @SerializedName("happened_to") val happenedTo: String? = null,
    @SerializedName("acknowledged_before_seeded") val acknowledgedBeforeSeeded: Boolean = false,
)

data class MarkHappenedResponse(
    val memory: Memory,
    val degraded: Boolean,
    val warning: Warning? = null,
)

data class Warning(val code: String, val message: String)

data class MemoryListResponse(
    val items: List<MemoryCard>,
    @SerializedName("next_cursor") val nextCursor: String? = null,
    @SerializedName("lived_pages") val livedPages: Int,
)

data class MemoryCard(
    val id: String,
    @SerializedName("wish_id") val wishId: String,
    val title: String,
    @SerializedName("happened_from") val happenedFrom: String,
    @SerializedName("happened_to") val happenedTo: String? = null,
    @SerializedName("cover_media_id") val coverMediaId: String? = null,
    val status: String, // draft | published
)

data class Memory(
    val id: String,
    @SerializedName("wish_id") val wishId: String,
    val title: String,
    @SerializedName("happened_from") val happenedFrom: String,
    @SerializedName("happened_to") val happenedTo: String? = null,
    @SerializedName("cover_media_id") val coverMediaId: String? = null,
    val status: String,
    val cause: String? = null,
    val process: String? = null,
    val mood: String? = null, // relieved | healed | tearful | calm | proud | unspeakable
    @SerializedName("last_line") val lastLine: String? = null,
    @SerializedName("photo_media_ids") val photoMediaIds: List<String> = emptyList(),
    @SerializedName("voice_media_id") val voiceMediaId: String? = null,
    @SerializedName("note_before_seeded") val noteBeforeSeeded: Boolean = false,
    @SerializedName("edited_fields") val editedFields: List<String> = emptyList(),
    @SerializedName("published_at") val publishedAt: String? = null,
    @SerializedName("created_at") val createdAt: String,
)

data class MemoryUpdateRequest(
    val title: String? = null,
    val cause: String? = null,
    val process: String? = null,
    val mood: String? = null,
    @SerializedName("last_line") val lastLine: String? = null,
    @SerializedName("photo_media_ids") val photoMediaIds: List<String>? = null,
    @SerializedName("voice_media_id") val voiceMediaId: String? = null,
)

data class PublishMemoryResponse(val memory: Memory)

// ---------- lite-events.yaml ----------

data class LiteEvent(
    val id: String,
    val text: String,
    val status: String, // open | done
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("closed_at") val closedAt: String? = null,
)

data class LiteEventListResponse(val items: List<LiteEvent>)

data class LiteEventCreateRequest(val text: String)

// ---------- media.yaml ----------

data class MediaUploadUrlRequest(
    val kind: String, // audio | image
    @SerializedName("content_type") val contentType: String,
    @SerializedName("size_bytes") val sizeBytes: Long,
)

data class MediaUploadUrlResponse(
    @SerializedName("media_id") val mediaId: String,
    @SerializedName("upload_url") val uploadUrl: String,
    @SerializedName("expires_at") val expiresAt: String,
)

// ---------- /holidays（heart-voice-holiday-timing）----------

data class HolidaysResponse(
    val year: Int,
    val available: Boolean,
    val names: List<String> = emptyList(),
    val items: List<HolidayItem> = emptyList(),
)

data class HolidayItem(
    @SerializedName("date") val date: String,
    @SerializedName("name") val name: String,
)

// ---------- 心语：LLM 返回结构（客户端直连，非后端契约）----------

data class HeartVoiceResult(
    val reply: String? = null,
    val useful: Boolean = false,
    @SerializedName("lite_event") val liteEvent: String? = null,
)

// ---------- system.yaml ----------

data class HealthResponse(
    val status: String,
    val database: String,
    @SerializedName("scheduler_heartbeat_age_seconds") val schedulerHeartbeatAgeSeconds: Int? = null,
)
