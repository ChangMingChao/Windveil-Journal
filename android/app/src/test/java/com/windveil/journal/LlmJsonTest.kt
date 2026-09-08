package com.windveil.journal

import com.windveil.journal.domain.LlmJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * LLM 返回内容严格解析（#11）：
 * 覆盖裸 JSON / Markdown 围栏 / 前后杂文 / 转义变体 / 结构坏损等模型常见返回形态。
 */
class LlmJsonTest {

    private data class Intent(val intent: String = "chat")

    @Test
    fun `裸 JSON 对象直接解析`() {
        val result = LlmJson.parse("""{"intent":"ask"}""", Intent::class.java)
        assertEquals("ask", result?.intent)
    }

    @Test
    fun `Markdown 围栏包裹的 JSON 可解析`() {
        val raw = "```json\n{\"intent\":\"record\"}\n```"
        assertEquals("record", LlmJson.parse(raw, Intent::class.java)?.intent)
    }

    @Test
    fun `前后夹说明文字仍可解析`() {
        val raw = "好的，分类结果如下：\n{\"intent\":\"ask\"}\n希望对你有帮助！"
        assertEquals("ask", LlmJson.parse(raw, Intent::class.java)?.intent)
    }

    @Test
    fun `字符串转义一层的 JSON 变体可解析`() {
        val raw = "\"{\\\"intent\\\":\\\"ask\\\"}\""
        assertEquals("ask", LlmJson.parse(raw, Intent::class.java)?.intent)
    }

    @Test
    fun `多个围栏块取第一个合法对象`() {
        val raw = "说明\n```json\n{\"intent\":\"record\"}\n```\n```json\n{\"intent\":\"chat\"}\n```"
        assertEquals("record", LlmJson.parse(raw, Intent::class.java)?.intent)
    }

    @Test
    fun `纯文本无 JSON 返回 null`() {
        assertNull(LlmJson.parse("今天天气不错", Intent::class.java))
        assertNull(LlmJson.parse(null, Intent::class.java))
        assertNull(LlmJson.parse("", Intent::class.java))
    }

    @Test
    fun `结构坏损的 JSON 返回 null`() {
        assertNull(LlmJson.parse("{\"intent\":", Intent::class.java))
        assertNull(LlmJson.parse("{intent: ask}", Intent::class.java))
    }

    @Test
    fun `数组外层不被当对象解析`() {
        assertNull(LlmJson.parse("""["intent"]""", Intent::class.java))
    }

    @Test
    fun `extractArray 提取数组`() {
        val raw = "items: [{\"a\":1},{\"a\":2}] 以上。"
        assertEquals("[{\"a\":1},{\"a\":2}]", LlmJson.extractArray(raw))
    }

    @Test
    fun `extractObject 对数组返回 null`() {
        assertNull(LlmJson.extractObject("""[{"a":1}]"""))
    }
}
