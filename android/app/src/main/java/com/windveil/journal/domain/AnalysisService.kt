package com.windveil.journal.domain

import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.remote.HeartVoiceClient
import com.google.gson.Gson
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 分析服务（standalone-mode）：愿望理解 / 一句追问 / 最小步骤 / 时机建议
 * 全部走心语的用户自配模型，在用户使用期间静默完成。
 * 隐私边界：只发送必要的最小上下文（原话 + 摘要），端点本身是用户配置的。
 * 模型未配置或调用失败 → 一律降级（degraded），不阻塞记录。
 */
@Singleton
class AnalysisService @Inject constructor(
    private val heartVoiceClient: HeartVoiceClient,
) {
    /** 愿望理解结果（对齐后端 WishUnderstanding 语义）。 */
    data class Understanding(
        val kind: String, // future_wish | near_term_todo
        val feeling: String?, // 用户真正想要的感受
        val smallestStep: String?, // 首个最小可行动步骤（≤5 分钟）
        val question: String?, // 一句追问（恰好 1 句，可跳过）
        val suggestedTiming: String?, // 时机建议的一句话理由（可选）
    )

    private fun understandingPrompt(wishText: String): String = """你是「风起簿」的温柔分析者。用户写下一件想在未来发生的事：
"$wishText"

分析它并只输出 JSON（不要其他内容）：
{"kind":"future_wish 或 near_term_todo","feeling":"用户真正想要的感受（如 放松/陪伴/勇气/成长，8 字内）","smallest_step":"首个最小可行动步骤（5 分钟内能做的，40 字内；想不出给 null）","question":"对用户的一句追问（恰好 1 句，温柔、不催促；想不出给 null）","suggested_timing":"一句时机建议理由（如「听起来适合秋天」，想不出给 null）"}

规则：
- near_term_todo 表示这更像近期待办而不是未来愿望
- 文案禁止出现「任务」「截止」「逾期」「未完成」等词
- 全部字段可为 null，但 JSON 结构必须完整"""

    /** 静默分析：返回 null = 降级（模型不可用/未配置/解析失败），调用方直接跳过。 */
    suspend fun understandQuietly(config: LlmConfig?, wishText: String): Understanding? {
        if (config?.usable != true) return null
        return runCatching {
            val content = heartVoiceClient.chat(config, understandingPrompt(wishText), emptyList())
            val obj = LlmJson.extractObject(content)?.let { JSONObject(it) } ?: return@runCatching null
            Understanding(
                kind = obj.optString("kind", "future_wish"),
                feeling = obj.optString("feeling", "").takeIf { it.isNotBlank() },
                smallestStep = obj.optString("smallest_step", "").takeIf { it.isNotBlank() },
                question = obj.optString("question", "").takeIf { it.isNotBlank() },
                suggestedTiming = obj.optString("suggested_timing", "").takeIf { it.isNotBlank() },
            )
        }.getOrNull()
    }

    /** 最小步骤再生成（「换一个更小的」）。返回 null = 降级。 */
    suspend fun nextStep(config: LlmConfig?, wishTitle: String, originalText: String?, rejectedStep: String?): String? {
        if (config?.usable != true) return null
        val prompt = """用户的愿望：「$wishTitle」（原话：${originalText ?: "（无）"}）${rejectedStep?.let { "。之前建议的步骤「$it」被拒绝，要更小的" } ?: ""}

给出下一个最小步骤（5 分钟内能做、不花钱优先、不依赖他人优先）。只输出 JSON：
{"step":"步骤描述（40 字内）"}"""
        return runCatching {
            val content = heartVoiceClient.chat(config, prompt, emptyList())
            val obj = LlmJson.extractObject(content)?.let { JSONObject(it) } ?: return@runCatching null
            obj.optString("step", "").takeIf { it.isNotBlank() }
        }.getOrNull()
    }

    /** 时机建议草稿（仅 4 种时间类）。返回 null = 降级。 */
    suspend fun proposeTiming(
        config: LlmConfig?,
        wishTitle: String,
        originalText: String?,
        holidayNames: List<String>,
    ): TimingDraft? {
        if (config?.usable != true) return null
        val prompt = """用户的愿望：「$wishTitle」（原话：${originalText ?: "（无）"}）。
从这些时机类型里提议一个最合适的：
- season：值取 spring/summer/autumn/winter
- month_day：值取 YYYY-MM-DD
- after_months：值取 1/3/6/12
- holiday：值从这些法定节假日里选一个：${holidayNames.joinToString("、").ifBlank { "（无数据）" }}

只输出 JSON（不要其他内容）：
{"type":"season 或 month_day 或 after_months 或 holiday","value":"对应参数","reason":"一句温柔的理由（30 字内）"}"""
        return runCatching {
            val content = heartVoiceClient.chat(config, prompt, emptyList())
            val obj = LlmJson.extractObject(content)?.let { JSONObject(it) } ?: return@runCatching null
            val type = obj.optString("type", "")
            val allowed = setOf("season", "month_day", "after_months", "holiday")
            if (type !in allowed) return@runCatching null
            TimingDraft(
                type = type,
                value = obj.optString("value", "").takeIf { it.isNotBlank() && it != "null" },
                reason = obj.optString("reason", "").takeIf { it.isNotBlank() },
            )
        }.getOrNull()
    }

    data class TimingDraft(val type: String, val value: String?, val reason: String?)

    /**
     * 对话后提炼用户画像条目（user-profile）：一次最多 2 条，可返回空。
     * 只在对话内容自然涉及偏好/习惯/时间安排时提炼，不做主动提问。
     */
    suspend fun extractPreferences(config: LlmConfig?, userText: String): List<PreferenceDraft> {
        if (config?.usable != true) return emptyList()
        val prompt = """你是「风起簿」的画像提炼器。用户刚说了："${userText.take(200)}"

从中提炼关于用户的长期偏好/习惯/时间安排（有空时间、运动偏好、饮食倾向、作息等）。
- 只有明确涉及才提炼，没有就给空数组；一次最多 2 条
- 每条 ≤30 字；value 用中性陈述（如「在减肥」「周末上午通常有空」）
- source：用户明确说的="declared"；从上下文推断的="inferred"

只输出 JSON：{"items":[{"pref_key":"有空时间/运动偏好/饮食倾向/其他偏好","value":"...","source":"declared 或 inferred"}]}"""
        return runCatching {
            val content = heartVoiceClient.chat(config, prompt, emptyList())
            val obj = LlmJson.extractObject(content)?.let { JSONObject(it) } ?: return@runCatching emptyList()
            val items = obj.optJSONArray("items") ?: return@runCatching emptyList()
            (0 until items.length()).mapNotNull { i ->
                val item = items.optJSONObject(i) ?: return@mapNotNull null
                val value = item.optString("value", "").takeIf { it.isNotBlank() } ?: return@mapNotNull null
                PreferenceDraft(
                    prefKey = item.optString("pref_key", "其他偏好"),
                    value = value.take(50),
                    source = if (item.optString("source") == "declared") "declared" else "inferred",
                )
            }.take(2)
        }.getOrDefault(emptyList())
    }

    data class PreferenceDraft(val prefKey: String, val value: String, val source: String)

    /** 愿望详情页的自由对话（chat/推进/疲惫信号由调用方按语义处理）。返回 null = 降级。 */
    suspend fun chat(config: LlmConfig?, wishTitle: String, userText: String): String? {
        if (config?.usable != true) return null
        val prompt = """你是「风起簿」的陪伴者。用户有一个愿望：「$wishTitle」。
用户对你说：「$userText」
温柔回应（1-3 句），不催促、不评判；如果用户表达了疲惫，认可他的感受并提议把时机改成「累了的时候」；禁止出现「任务」「逾期」「未完成」等词。直接输出回应文本，不要 JSON。"""
        return runCatching {
            heartVoiceClient.chat(config, prompt, emptyList()).trim().takeIf { it.isNotBlank() }
        }.getOrNull()
    }
}
