package com.windveil.journal.data.repository

import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.local.LlmConfigStore
import com.windveil.journal.data.local.db.LiteEventEntity
import com.windveil.journal.data.local.db.MemoryEntity
import com.windveil.journal.data.local.db.WindveilDatabase
import com.windveil.journal.data.local.db.WishEntity
import com.windveil.journal.domain.AnalysisService
import com.windveil.journal.domain.CalendarReminder
import com.windveil.journal.domain.HolidayDataSource
import com.windveil.journal.domain.TimingCalculator
import kotlinx.coroutines.flow.Flow
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 单机模式唯一仓库：Room 权威 + 系统日历提醒联动 + 心语模型静默分析。
 * 所有业务规则（状态机/时机计算/降级语义）在此收口，UI 不直接触碰 DAO。
 */
@Singleton
class StandaloneRepository @Inject constructor(
    private val db: WindveilDatabase,
    private val calendarReminder: CalendarReminder,
    private val analysisService: AnalysisService,
    private val holidayDataSource: HolidayDataSource,
    private val llmConfigStore: LlmConfigStore,
) {
    private val wishDao = db.wishDao()
    private val liteDao = db.liteEventDao()
    private val memoryDao = db.memoryDao()
    private val gson = com.google.gson.Gson()

    private fun now(): String = DateTimeFormatter.ISO_INSTANT.format(Instant.now())
    private fun newId(): String = UUID.randomUUID().toString()

    private suspend fun llmConfig(): LlmConfig? = llmConfigStore.current()

    // ---------- 观察 ----------

    fun observeGarden(): Flow<List<WishEntity>> = wishDao.observeGarden()
    fun observeWish(id: String): Flow<WishEntity?> = wishDao.observe(id)
    fun observeOpenLiteEvents(): Flow<List<LiteEventEntity>> = liteDao.observeOpen()
    fun observeDoneLiteEvents(): Flow<List<LiteEventEntity>> = liteDao.observeDone()
    fun observePublishedMemories(): Flow<List<MemoryEntity>> = memoryDao.observePublished()
    fun observeMemory(id: String): Flow<MemoryEntity?> = memoryDao.observe(id)
    fun observeLivedPages(): Flow<Int> = memoryDao.observeLivedPages()

    // ---------- 种愿望（S02）----------

    /**
     * 种下愿望。理解/追问由心语模型静默分析；降级时仅保存原话（degraded 语义）。
     * 返回 (wishId, 追问)；追问为 null 表示降级跳过轻问。
     */
    suspend fun seed(text: String): Pair<String, String?> {
        val id = newId()
        val config = llmConfig()
        val understanding = analysisService.understandQuietly(config, text)
        val wish = WishEntity(
            id = id,
            title = text.take(60), // 标题即原话首行截断（单机简化；后端是 LLM 提炼）
            originalText = text,
            source = "text",
            state = "seeded",
            timingType = null, timingValue = null, triggerKind = "none",
            nextTriggerAt = null, timingOccurrence = null,
            seededAt = now(), lastActivityAt = now(),
            understanding = understanding?.let {
                gson.toJson(mapOf("kind" to it.kind, "feeling" to it.feeling, "smallest_step" to it.smallestStep))
            },
            pendingQuestion = understanding?.question,
        )
        wishDao.insert(wish)
        return Pair(id, understanding?.question)
    }

    /** 回答/跳过一句追问（S01/S02 轻问）。 */
    suspend fun answerQuestion(wishId: String, answer: String?) {
        val wish = wishDao.get(wishId) ?: return
        // 回答内容并入原话尾注（单机简化：后端是独立表）
        wishDao.update(wish.copy(pendingQuestion = null, lastActivityAt = now()))
    }

    /** near_term_todo 确认「就当成未来的事」（语义保留，单机无状态差异）。 */
    suspend fun keepAsFuture(wishId: String) = answerQuestion(wishId, null)

    /** 心语 record 记入「未发生之地」：直接建愿望（心语已分类，不再静默分析）。 */
    suspend fun seedWish(title: String, originalText: String): String {
        val id = newId()
        wishDao.insert(
            WishEntity(
                id = id,
                title = title,
                originalText = originalText,
                source = "text",
                state = "seeded",
                timingType = null, timingValue = null, triggerKind = "none",
                nextTriggerAt = null, timingOccurrence = null,
                seededAt = now(), lastActivityAt = now(),
            )
        )
        return id
    }

    // ---------- 时机（S03）----------

    /** 六选项手动约定；计算成功后写系统日历（失败降级仅本地）。 */
    suspend fun setTiming(
        wishId: String,
        timingType: String,
        season: String? = null,
        monthDay: String? = null,
        afterMonths: Int? = null,
        holidays: List<String>? = null,
        writeCalendar: Boolean = true,
    ) {
        val wish = wishDao.get(wishId) ?: return
        val plan = TimingCalculator.plan(
            timingType,
            zone = ZoneId.systemDefault(),
            season = season, monthDay = monthDay, afterMonths = afterMonths,
            holidays = holidays, holidayData = holidayDataSource.toHolidayData(),
        )
        applyPlan(wish, plan, writeCalendar)
    }

    /** 「让它提个时候」：心语模型建议时机类型（仅 4 种时间类），分析不出降级返回 null。 */
    suspend fun proposeTiming(wishId: String): AnalysisService.TimingDraft? {
        val wish = wishDao.get(wishId) ?: return null
        return analysisService.proposeTiming(
            config = llmConfig(),
            wishTitle = wish.title,
            originalText = wish.originalText,
            holidayNames = holidayDataSource.names(),
        )
    }

    /** 采纳模型建议草稿：按草稿类型计算并落库 + 写日历。 */
    suspend fun applyTimingDraft(wishId: String, draft: AnalysisService.TimingDraft) {
        val wish = wishDao.get(wishId) ?: return
        val plan = when (draft.type) {
            "season" -> TimingCalculator.plan("season", zone = ZoneId.systemDefault(), season = draft.value, holidayData = holidayDataSource.toHolidayData())
            "month_day" -> TimingCalculator.plan("month_day", zone = ZoneId.systemDefault(), monthDay = draft.value, holidayData = holidayDataSource.toHolidayData())
            "after_months" -> TimingCalculator.plan("after_months", zone = ZoneId.systemDefault(), afterMonths = draft.value?.toIntOrNull(), holidayData = holidayDataSource.toHolidayData())
            "holiday" -> TimingCalculator.plan("holiday", zone = ZoneId.systemDefault(), holidays = listOf(draft.value ?: ""), holidayData = holidayDataSource.toHolidayData())
            else -> return
        }
        applyPlan(wish, plan)
    }

    /** 采纳时机计划（写 wish + 可选日历）。 */
    suspend fun applyPlan(wish: WishEntity, plan: TimingCalculator.Plan, writeCalendar: Boolean = true) {
        val updated = wish.copy(
            state = if (plan.timingType == "none") "seeded" else "brewing",
            timingType = plan.timingType,
            timingValue = plan.timingValue,
            triggerKind = plan.triggerKind,
            nextTriggerAt = plan.nextTriggerAt?.let { TimingCalculator.isoInstant(it) },
            timingOccurrence = plan.occurrence,
            softDeferred = false,
            lastActivityAt = now(),
        )
        wishDao.update(updated)
        // 写系统日历（用户确认后写入；未授权/失败降级为仅 App 内展示）
        if (writeCalendar && plan.triggerKind == "time" && plan.nextTriggerAt != null) {
            val uri = calendarReminder.schedule(
                wishId = wish.id,
                title = "风来了：${wish.title}",
                triggerAt = plan.nextTriggerAt,
                occurrence = plan.occurrence,
            )
            // eventUri 存在 timeline JSON 里（复用字段，前缀标记）
            updated.copy(timeline = gson.toJson(mapOf("calendarEvent" to uri)))
                .let { wishDao.update(it) }
        }
    }

    /** 撤销时机（暂时不提醒 / 换时机前调用）。 */
    suspend fun clearTiming(wishId: String) {
        val wish = wishDao.get(wishId) ?: return
        calendarReminder.cancel(calendarUriOf(wish))
        wishDao.update(
            wish.copy(
                timingType = null, timingValue = null, triggerKind = "none",
                nextTriggerAt = null, timingOccurrence = null,
                state = "seeded", lastActivityAt = now(),
            )
        )
    }

    private fun calendarUriOf(wish: WishEntity): String? = runCatching {
        val type = object : com.google.gson.reflect.TypeToken<Map<String, String>>() {}.type
        gson.fromJson<Map<String, String>>(wish.timeline ?: "{}", type)["calendarEvent"]
    }.getOrNull()

    // ---------- 状态动作（S04/S05/S07 语义保留）----------

    suspend fun markReady(wishId: String) {
        val wish = wishDao.get(wishId) ?: return
        if (wish.state == "happened") return
        wishDao.update(wish.copy(state = "wind", lastActivityAt = now()))
    }

    suspend fun defer(wishId: String, afterMonths: Int = 3) {
        val wish = wishDao.get(wishId) ?: return
        val base = wish.nextTriggerAt?.let {
            runCatching { TimingCalculator.parseIso(it).atZone(ZoneId.systemDefault()).toLocalDate() }.getOrNull()
        } ?: LocalDate.now()
        val plan = TimingCalculator.plan(
            "after_months", today = base, zone = ZoneId.systemDefault(), afterMonths = afterMonths,
        )
        // 顺延只重算时刻，状态保持
        wishDao.update(wish.copy(nextTriggerAt = TimingCalculator.isoInstant(plan.nextTriggerAt!!), timingOccurrence = plan.occurrence, lastActivityAt = now()))
    }

    suspend fun letGo(wishId: String) {
        val wish = wishDao.get(wishId) ?: return
        if (wish.state == "happened") return
        calendarReminder.cancel(calendarUriOf(wish))
        wishDao.update(
            wish.copy(state = "let_go", letGoAt = now(), nextTriggerAt = null, timingOccurrence = null, lastActivityAt = now())
        )
    }

    suspend fun recall(wishId: String) {
        val wish = wishDao.get(wishId) ?: return
        if (wish.state != "let_go") return
        wishDao.update(wish.copy(state = "seeded", letGoAt = null, lastActivityAt = now()))
    }

    /** 最小步骤（心语模型生成；降级给内置兜底）。 */
    suspend fun nextStep(wishId: String, rejectedStep: String? = null): String? {
        val wish = wishDao.get(wishId) ?: return null
        val step = analysisService.nextStep(llmConfig(), wish.title, wish.originalText, rejectedStep)
            ?: "打开日历看一眼，这件事里最轻的一步是什么" // 内置兜底（EX-8.2 语义）
        wishDao.update(wish.copy(currentStep = gson.toJson(mapOf("text" to step, "status" to "proposed", "source" to if (step.startsWith("打开日历")) "fallback" else "llm")), lastActivityAt = now()))
        return step
    }

    suspend fun stepDone(wishId: String) {
        val wish = wishDao.get(wishId) ?: return
        val step = wish.currentStep?.let {
            runCatching {
                val type = object : com.google.gson.reflect.TypeToken<Map<String, String>>() {}.type
                gson.fromJson<Map<String, String>>(it, type)
            }.getOrNull()
        } ?: return
        val entry = mapOf("text" to (step["text"] ?: ""), "completed_at" to now())
        val timeline = wish.timeline.let { old ->
            val type = object : com.google.gson.reflect.TypeToken<List<Map<String, String>>>() {}.type
            val list = runCatching { gson.fromJson<List<Map<String, String>>>(old ?: "[]", type) }.getOrDefault(emptyList())
            gson.toJson(list + entry)
        }
        wishDao.update(
            wish.copy(
                state = "going", currentStep = null, timeline = timeline, lastActivityAt = now(),
            )
        )
    }

    suspend fun amend(wishId: String, title: String?, originalText: String?) {
        val wish = wishDao.get(wishId) ?: return
        wishDao.update(
            wish.copy(
                title = title?.takeIf { it.isNotBlank() } ?: wish.title,
                originalText = originalText?.takeIf { it.isNotBlank() } ?: wish.originalText,
                amendedFrom = wish.amendedFrom ?: wish.originalText,
                lastActivityAt = now(),
            )
        )
    }

    /** 与 Agent 对话（单机简化：走心语通道，返回回应文本；降级 null）。 */
    suspend fun chat(wishId: String, text: String): String? {
        val wish = wishDao.get(wishId) ?: return null
        return analysisService.chat(llmConfig(), wish.title, text)
    }

    // ---------- S06 已发生 ----------

    suspend fun markHappened(wishId: String, happenedFrom: String, happenedTo: String? = null): String {
        val wish = wishDao.get(wishId) ?: return ""
        calendarReminder.cancel(calendarUriOf(wish))
        val memoryId = newId()
        memoryDao.insert(
            MemoryEntity(
                id = memoryId, wishId = wishId,
                title = wish.title,
                happenedFrom = happenedFrom, happenedTo = happenedTo,
                // 经过区块：依据准备过程时间线草拟（有则拼接，无则空 = EX-4.1 占位）
                process = wish.timeline?.let { tl ->
                    runCatching {
                        val type = object : com.google.gson.reflect.TypeToken<List<Map<String, String>>>() {}.type
                        gson.fromJson<List<Map<String, String>>>(tl, type)
                            .joinToString("；") { it["text"] ?: "" }
                            .takeIf { it.isNotBlank() }
                    }.getOrNull()
                },
                status = "draft", createdAt = now(),
            )
        )
        wishDao.update(wish.copy(state = "wind", lastActivityAt = now())) // publish 时才转 happened
        return memoryId
    }

    suspend fun updateMemory(memoryId: String, title: String?, cause: String?, process: String?, lastLine: String?) {
        val memory = memoryDao.get(memoryId) ?: return
        memoryDao.update(
            memory.copy(
                title = title ?: memory.title,
                cause = cause ?: memory.cause,
                process = process ?: memory.process,
                lastLine = lastLine ?: memory.lastLine,
            )
        )
    }

    suspend fun publishMemory(memoryId: String) {
        val memory = memoryDao.get(memoryId) ?: return
        memoryDao.update(memory.copy(status = "published", publishedAt = now()))
        wishDao.get(memory.wishId)?.let {
            wishDao.update(it.copy(state = "happened", nextTriggerAt = null, lastActivityAt = now()))
        }
    }

    // ---------- S09 轻事件 ----------

    suspend fun createLiteEvent(text: String) {
        liteDao.insert(LiteEventEntity(id = newId(), text = text, status = "open", createdAt = now()))
    }

    suspend fun markLiteEventDone(id: String) = liteDao.markDone(id, now())
    suspend fun deleteLiteEvent(id: String) = liteDao.delete(id)

    /** 编辑轻事件（文本 + 备注 + 照片 JSON）。 */
    suspend fun updateLiteEvent(id: String, text: String, note: String?, photos: String?) {
        liteDao.get(id)?.let {
            liteDao.update(it.copy(text = text, note = note?.takeIf { n -> n.isNotBlank() }, photos = photos))
        }
    }

    suspend fun getLiteEvent(id: String): com.windveil.journal.data.local.db.LiteEventEntity? = liteDao.get(id)

    /** 删除记忆页（已发生之书 CRUD）。 */
    suspend fun deleteMemory(id: String) = memoryDao.delete(id)

    // ---------- 彻底删除 ----------

    suspend fun deleteWishPermanently(wishId: String) {
        val wish = wishDao.get(wishId) ?: return
        calendarReminder.cancelAllForWish(wishId)
        wishDao.delete(wishId)
    }

    /** 日历权限是否已授予（详情页定时机前的确认弹窗判断）。 */
    fun hasCalendarPermission(): Boolean = calendarReminder.hasPermission()

    // ---------- 节假日枚举（详情页多选器）----------

    fun holidayNames(): List<String> = holidayDataSource.names()
    fun holidaysAvailable(): Boolean = holidayDataSource.available()

    // ---------- 数据导出 ----------

    suspend fun exportJson(): String {
        val payload = mapOf(
            "exported_at" to now(),
            "wishes" to wishDao.all(),
            "lite_events" to liteDao.all(),
            "memories" to memoryDao.all(),
        )
        return gson.toJson(payload)
    }

    /**
     * 导入备份（standalone-mode 补全）：按 ID 合并——同 ID 覆盖、新 ID 插入，不删现有数据。
     * 返回 (wishes, liteEvents, memories) 三类各自导入的条数。
     * 注意：照片路径指向导出设备本机目录，导入时校验文件存在，无效路径丢弃（照片存 null）。
     */
    suspend fun importJson(json: String, sanitizePhotos: (List<String>) -> List<String> = { it }): Triple<Int, Int, Int> {
        val type = object : com.google.gson.reflect.TypeToken<Map<String, Any>>() {}.type
        val payload: Map<String, Any> = gson.fromJson(json, type)

        fun decodeList(raw: Any?): List<Map<String, Any>> {
            val listJson = gson.toJson(raw ?: return emptyList())
            return gson.fromJson(listJson, object : com.google.gson.reflect.TypeToken<List<Map<String, Any>>>() {}.type)
        }

        fun str(m: Map<String, Any>, key: String): String? = (m[key] as? String)?.takeIf { it != "null" }
        fun bool(m: Map<String, Any>, key: String): Boolean = m[key] == true

        var wishCount = 0
        for (m in decodeList(payload["wishes"])) {
            val id = str(m, "id") ?: continue
            wishDao.insert(
                WishEntity(
                    id = id,
                    title = str(m, "title") ?: "",
                    originalText = str(m, "originalText"),
                    source = str(m, "source") ?: "text",
                    state = str(m, "state") ?: "seeded",
                    timingType = str(m, "timingType"),
                    timingValue = str(m, "timingValue"),
                    triggerKind = str(m, "triggerKind") ?: "none",
                    nextTriggerAt = str(m, "nextTriggerAt"),
                    timingOccurrence = str(m, "timingOccurrence"),
                    softDeferred = bool(m, "softDeferred"),
                    letGoAt = str(m, "letGoAt"),
                    seededAt = str(m, "seededAt") ?: now(),
                    lastActivityAt = str(m, "lastActivityAt") ?: now(),
                    understanding = str(m, "understanding"),
                    pendingQuestion = str(m, "pendingQuestion"),
                    currentStep = str(m, "currentStep"),
                    timeline = str(m, "timeline"),
                    amendedFrom = str(m, "amendedFrom"),
                )
            )
            wishCount++
        }

        var liteCount = 0
        for (m in decodeList(payload["lite_events"])) {
            val id = str(m, "id") ?: continue
            // 照片路径指向导出设备的目录：导入时过滤掉本机不存在的文件
            val photosJson = str(m, "photos")?.let { photosStr ->
                val paths = runCatching {
                    gson.fromJson<List<String>>(photosStr, object : com.google.gson.reflect.TypeToken<List<String>>() {}.type)
                }.getOrDefault(emptyList())
                val valid = sanitizePhotos(paths)
                if (valid.isEmpty()) null else gson.toJson(valid)
            }
            liteDao.insert(
                LiteEventEntity(
                    id = id,
                    text = str(m, "text") ?: "",
                    status = str(m, "status") ?: "open",
                    createdAt = str(m, "createdAt") ?: now(),
                    closedAt = str(m, "closedAt"),
                    note = str(m, "note"),
                    photos = photosJson,
                )
            )
            liteCount++
        }

        var memCount = 0
        for (m in decodeList(payload["memories"])) {
            val id = str(m, "id") ?: continue
            memoryDao.insert(
                MemoryEntity(
                    id = id,
                    wishId = str(m, "wishId") ?: "",
                    title = str(m, "title") ?: "",
                    happenedFrom = str(m, "happenedFrom") ?: "",
                    happenedTo = str(m, "happenedTo"),
                    cause = str(m, "cause"),
                    process = str(m, "process"),
                    mood = str(m, "mood"),
                    lastLine = str(m, "lastLine"),
                    status = str(m, "status") ?: "published",
                    publishedAt = str(m, "publishedAt"),
                    createdAt = str(m, "createdAt") ?: now(),
                )
            )
            memCount++
        }
        return Triple(wishCount, liteCount, memCount)
    }
}
