package com.windveil.journal.data.local.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * 愿望（单机模式，Room）。字段语义与后端 wishes 表一致（standalone-mode）。
 * 状态机：seeded → brewing → wind → going → happened（终态）/ let_go。
 */
@Entity(tableName = "wishes")
data class WishEntity(
    @PrimaryKey val id: String, // UUID
    val title: String,
    val originalText: String?, // 用户原话；ASR/理解降级时仍保留
    val source: String, // text | voice（当前仅 text）
    val state: String,
    // 时机
    val timingType: String?, // season | month_day | after_months | free_weekend | when_tired | none | holiday
    val timingValue: String?, // spring / 2027-03-15 / 3 / 国庆节
    val triggerKind: String, // time | signal | none
    val nextTriggerAt: String?, // ISO-8601 UTC；由 TimingCalculator 端上计算
    val timingOccurrence: String?,
    val softDeferred: Boolean = false,
    val letGoAt: String? = null,
    val seededAt: String,
    val lastActivityAt: String,
    val understanding: String? = null, // AnalysisService 产出的 JSON（kind/feeling/smallest_step）
    val pendingQuestion: String? = null, // Agent 的一句追问；已答/跳过后清空
    val currentStep: String? = null, // 当前最小步骤 JSON（text/status/source）
    val timeline: String? = null, // 准备过程时间线 JSON 数组
    val amendedFrom: String? = null, // 最初你说的是……
    val calendarEventUri: String? = null, // 系统日历事件 URI，与时间线分开保存
)

/** 轻事件（S09）：纯记录、无提醒路径。 */
@Entity(tableName = "lite_events")
data class LiteEventEntity(
    @PrimaryKey val id: String,
    val text: String,
    val status: String, // open | done
    val createdAt: String,
    val closedAt: String? = null,
    // 相关信息（android-ux-crud 第 8 条）：文字备注 + 照片（本地路径，JSON 数组）
    val note: String? = null,
    val photos: String? = null, // JSON array of path
)

/** 记忆页（S06）：草稿 → 发布。 */
@Entity(tableName = "memories")
data class MemoryEntity(
    @PrimaryKey val id: String,
    val wishId: String,
    val title: String,
    val happenedFrom: String, // YYYY-MM-DD
    val happenedTo: String? = null,
    val cause: String? = null,
    val process: String? = null,
    val mood: String? = null,
    val lastLine: String? = null,
    val status: String, // draft | published
    val publishedAt: String? = null,
    val createdAt: String,
)


/** 用户画像条目（user-profile）：来源分层，可查看可删除。 */
@Entity(tableName = "preferences")
data class PreferenceEntity(
    @PrimaryKey val id: String, // UUID
    val prefKey: String, //有空时间 | 运动偏好 | 饮食倾向 | 其他偏好
    val value: String, // 条目内容（≤50 字）
    val source: String, // declared（用户明说）| inferred（模型推断）
    val createdAt: String,
)
