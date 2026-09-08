package com.windveil.journal.domain

import com.google.gson.Gson
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import java.io.StringReader

/**
 * LLM 返回内容的严格 JSON 解析（standalone-mode）。
 * 模型经常在 JSON 前后夹说明文字、Markdown 围栏（```json … ```）或把 JSON 转义一层的变体，
 * 旧实现 removePrefix/removeSuffix 很脆；这里按顺序尝试多种归一化策略，全部失败返回 null（降级）。
 * 校验直接驱动非宽松 JsonReader 消费全文（JsonParser 会强制 lenient，不能用）：
 * 无引号 key、单引号、截断、尾随内容一律判为无效。
 */
object LlmJson {

    private val gson = Gson()

    /** 从模型原始回复里提取 JSON 对象文本；失败返回 null。 */
    fun extractObject(raw: String?): String? = raw?.let { extract(it, isObject = true) }

    /** 从模型原始回复里提取 JSON 数组文本；失败返回 null。 */
    fun extractArray(raw: String?): String? = raw?.let { extract(it, isObject = false) }

    /**
     * 提取并解析为目标类型；解析失败（缺字段/类型不符/格式坏）返回 null，不抛异常。
     * 保留 [raw] 由调用方决定是否降级展示。
     */
    fun <T> parse(raw: String?, clazz: Class<T>): T? = runCatching {
        gson.fromJson(extractObject(raw) ?: return null, clazz)
    }.getOrNull()

    private fun extract(raw: String, isObject: Boolean): String? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val wanted = if (isObject) '{' else '['
        val outer = trimmed.first { !it.isWhitespace() }
        val candidates = mutableListOf(trimmed)

        // 1) Markdown 围栏块（```json …```、```…```）
        Regex("```(?:json)?\\s*([\\s\\S]*?)```", RegexOption.IGNORE_CASE)
            .findAll(trimmed).forEach { candidates.add(it.groupValues[1].trim()) }

        // 2) 前后夹说明文字：从首个目标括号截到末个目标括号。
        //    整体已是 JSON（outer 是 { 或 [）时绝不切片，避免 [{…}] 误切成 {…}。
        if (outer != '{' && outer != '[') {
            val first = trimmed.indexOf(wanted)
            val last = trimmed.lastIndexOf(if (isObject) '}' else ']')
            if (first in 0 until last) candidates.add(trimmed.substring(first, last + 1))
        }

        // 3) 字符串里再包一层 JSON 的转义变体（如 "{\"intent\":...}"）：先解开再试
        candidates.toList().forEach { c ->
            if (c.startsWith("\"") && c.endsWith("\"")) {
                runCatching { gson.fromJson(c, String::class.java) }.getOrNull()?.let { candidates.add(it) }
            }
        }

        return candidates.firstOrNull { isValidJson(it, isObject) }
    }

    /** 非宽松全文消费校验：语法合法、无尾随内容、外层形态匹配才算数。 */
    private fun isValidJson(text: String, isObject: Boolean): Boolean = runCatching {
        val reader = JsonReader(StringReader(text)).apply { isLenient = false }
        consume(reader)
        reader.peek() == JsonToken.END_DOCUMENT &&
            text.first { !it.isWhitespace() } == if (isObject) '{' else '['
    }.getOrDefault(false)

    private fun consume(reader: JsonReader) {
        when (reader.peek()) {
            JsonToken.BEGIN_ARRAY -> {
                reader.beginArray()
                while (reader.hasNext()) consume(reader)
                reader.endArray()
            }
            JsonToken.BEGIN_OBJECT -> {
                reader.beginObject()
                while (reader.hasNext()) {
                    reader.nextName()
                    consume(reader)
                }
                reader.endObject()
            }
            JsonToken.STRING -> reader.nextString()
            JsonToken.NUMBER -> reader.nextDouble()
            JsonToken.BOOLEAN -> reader.nextBoolean()
            JsonToken.NULL -> reader.nextNull()
            else -> throw IllegalStateException("意外的 JSON 记号")
        }
    }

    /** 解析失败时的用户可见提示（降级文案）。 */
    const val DEGRADED_REPLY: String = "这条我没能读懂，先原样记在下面了；你可以换个说法再试一次。"
}
