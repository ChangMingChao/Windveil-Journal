package com.windveil.journal.data.repository

import com.windveil.journal.data.remote.AmendWishRequest
import com.windveil.journal.data.remote.AnswerRequest
import com.windveil.journal.data.remote.ConfirmProposalResponse
import com.windveil.journal.data.remote.LiteEvent
import com.windveil.journal.data.remote.MarkHappenedRequest
import com.windveil.journal.data.remote.MarkHappenedResponse
import com.windveil.journal.data.remote.Memory
import com.windveil.journal.data.remote.MemoryListResponse
import com.windveil.journal.data.remote.MemoryUpdateRequest
import com.windveil.journal.data.remote.NextStepRequest
import com.windveil.journal.data.remote.NextStepResponse
import com.windveil.journal.data.remote.ProposalListResponse
import com.windveil.journal.data.remote.ProposalResponse
import com.windveil.journal.data.remote.PublishMemoryResponse
import com.windveil.journal.data.remote.RejectProposalResponse
import com.windveil.journal.data.remote.SeedWishRequest
import com.windveil.journal.data.remote.SeedWishResult
import com.windveil.journal.data.remote.SendMessageRequest
import com.windveil.journal.data.remote.SendMessageResponse
import com.windveil.journal.data.remote.StepDoneResponse
import com.windveil.journal.data.remote.TimingInput
import com.windveil.journal.data.remote.WishCard
import com.windveil.journal.data.remote.WishDetail
import com.windveil.journal.data.remote.WishListResponse
import com.windveil.journal.data.remote.WishesApi
import com.windveil.journal.data.remote.MemoriesApi
import com.windveil.journal.data.remote.bodyOrThrow
import com.windveil.journal.data.remote.okOrThrow
import javax.inject.Inject
import javax.inject.Singleton

/** 愿望全生命周期：种下（S02）、时机（S03）、最小步骤（S04）、整理与放下（S05/S07）。 */
@Singleton
class WishRepository @Inject constructor(
    private val wishesApi: WishesApi,
) {
    suspend fun seed(request: SeedWishRequest): SeedWishResult = wishesApi.seedWish(request).bodyOrThrow()

    suspend fun list(state: String? = null, cursor: String? = null): WishListResponse =
        wishesApi.listWishes(state = state, cursor = cursor).bodyOrThrow()

    suspend fun get(wishId: String): WishDetail = wishesApi.getWish(wishId).bodyOrThrow()

    suspend fun amend(wishId: String, title: String? = null, originalText: String? = null): WishDetail =
        wishesApi.amendWish(wishId, AmendWishRequest(title, originalText)).bodyOrThrow()

    suspend fun deletePermanently(wishId: String) =
        wishesApi.deleteWishPermanently(wishId, confirm = true).okOrThrow()

    suspend fun answer(wishId: String, request: AnswerRequest): WishDetail =
        wishesApi.answerQuestion(wishId, request).bodyOrThrow()

    suspend fun setTiming(wishId: String, timing: TimingInput): WishDetail =
        wishesApi.setTiming(wishId, timing).bodyOrThrow()

    suspend fun markReady(wishId: String): WishDetail = wishesApi.markReady(wishId).bodyOrThrow()

    suspend fun defer(wishId: String, afterMonths: Int = 3): WishDetail =
        wishesApi.defer(wishId, mapOf("after_months" to afterMonths)).bodyOrThrow()

    suspend fun pauseReminders(wishId: String): WishDetail = wishesApi.pauseReminders(wishId).bodyOrThrow()

    suspend fun backToBrewing(wishId: String): WishDetail = wishesApi.backToBrewing(wishId).bodyOrThrow()

    suspend fun letGo(wishId: String): WishDetail = wishesApi.letGo(wishId).bodyOrThrow()

    suspend fun recall(wishId: String): WishDetail = wishesApi.recall(wishId).bodyOrThrow()

    suspend fun proposeTiming(wishId: String): ProposalResponse =
        wishesApi.createTimingProposal(wishId).bodyOrThrow()

    suspend fun proposalHistory(wishId: String): ProposalListResponse =
        wishesApi.listTimingProposals(wishId).bodyOrThrow()

    suspend fun confirmProposal(wishId: String, proposalId: String): ConfirmProposalResponse =
        wishesApi.confirmProposal(wishId, proposalId).bodyOrThrow()

    suspend fun rejectProposal(wishId: String, proposalId: String): RejectProposalResponse =
        wishesApi.rejectProposal(wishId, proposalId).bodyOrThrow()

    suspend fun convertToLite(wishId: String): LiteEvent = wishesApi.convertToLite(wishId).bodyOrThrow()

    suspend fun nextStep(wishId: String, rejectedStepId: String? = null): NextStepResponse =
        wishesApi.requestNextStep(wishId, NextStepRequest(rejectedStepId)).bodyOrThrow()

    /** If-Match 承载乐观锁版本号（契约 EX-15.1）。 */
    suspend fun markStepDone(wishId: String, stepId: String, version: Int): StepDoneResponse =
        wishesApi.markStepDone(wishId, stepId, ifMatch = version.toString()).bodyOrThrow()

    suspend fun sendMessage(wishId: String, text: String): SendMessageResponse =
        wishesApi.sendMessage(wishId, SendMessageRequest(text)).bodyOrThrow()
}

/** S06：已发生之书。 */
@Singleton
class MemoryRepository @Inject constructor(
    private val memoriesApi: MemoriesApi,
) {
    suspend fun markHappened(wishId: String, request: MarkHappenedRequest): MarkHappenedResponse =
        memoriesApi.markHappened(wishId, request).bodyOrThrow()

    suspend fun list(cursor: String? = null): MemoryListResponse =
        memoriesApi.listMemories(cursor = cursor).bodyOrThrow()

    suspend fun get(memoryId: String): Memory = memoriesApi.getMemory(memoryId).bodyOrThrow()

    suspend fun update(memoryId: String, request: MemoryUpdateRequest): Memory =
        memoriesApi.updateMemory(memoryId, request).bodyOrThrow()

    suspend fun publish(memoryId: String): Memory =
        memoriesApi.publishMemory(memoryId).bodyOrThrow().memory
}
