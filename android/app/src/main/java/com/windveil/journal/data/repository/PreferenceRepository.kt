package com.windveil.journal.data.repository

import com.windveil.journal.data.remote.AvailabilityCreateRequest
import com.windveil.journal.data.remote.AvailabilityListResponse
import com.windveil.journal.data.remote.AvailabilityWindow
import com.windveil.journal.data.remote.LiteEvent
import com.windveil.journal.data.remote.LiteEventCreateRequest
import com.windveil.journal.data.remote.LiteEventListResponse
import com.windveil.journal.data.remote.LiteEventsApi
import com.windveil.journal.data.remote.PreferenceApi
import com.windveil.journal.data.remote.PreferenceDeclareRequest
import com.windveil.journal.data.remote.PreferenceListResponse
import com.windveil.journal.data.remote.PreferenceMeta
import com.windveil.journal.data.remote.bodyOrThrow
import com.windveil.journal.data.remote.okOrThrow
import javax.inject.Inject
import javax.inject.Singleton

/** S08：「它记得我什么」——偏好与可用时段。 */
@Singleton
class PreferenceRepository @Inject constructor(
    private val preferenceApi: PreferenceApi,
) {
    suspend fun list(includeRevoked: Boolean = false): PreferenceListResponse =
        preferenceApi.listPreferences(includeRevoked).bodyOrThrow()

    /** 服务端强制 source=declared、confidence=100；响应只含元数据，value 明文不回显。 */
    suspend fun declare(prefKey: String, value: String): PreferenceMeta =
        preferenceApi.declarePreference(PreferenceDeclareRequest(prefKey, value)).bodyOrThrow()

    /** 仅 inferred 行可撤回（猜错了）；declared 行走删除。 */
    suspend fun revoke(prefId: String) = preferenceApi.revokePreference(prefId).bodyOrThrow()

    suspend fun delete(prefId: String) = preferenceApi.deletePreference(prefId).okOrThrow()

    suspend fun availability(): AvailabilityListResponse = preferenceApi.listAvailability().bodyOrThrow()

    suspend fun addAvailability(request: AvailabilityCreateRequest): AvailabilityWindow =
        preferenceApi.createAvailability(request).bodyOrThrow()

    suspend fun deleteAvailability(windowId: String) = preferenceApi.deleteAvailability(windowId).okOrThrow()
}

/** S09：轻事件 —— 纯记录、无 Agent、无提醒路径。 */
@Singleton
class LiteEventRepository @Inject constructor(
    private val liteEventsApi: LiteEventsApi,
) {
    suspend fun create(text: String): LiteEvent = liteEventsApi.create(LiteEventCreateRequest(text)).bodyOrThrow()

    suspend fun list(includeDone: Boolean = false): LiteEventListResponse =
        liteEventsApi.list(includeDone).bodyOrThrow()

    suspend fun markDone(eventId: String): LiteEvent = liteEventsApi.markDone(eventId).bodyOrThrow()

    suspend fun delete(eventId: String) = liteEventsApi.delete(eventId).okOrThrow()
}
