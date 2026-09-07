package com.windveil.journal.data.remote

import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 心语：OpenAI 兼容 /chat/completions 客户端（客户端直连，不经后端）。
 * url / api key / 模型名来自用户在「我的」页的配置（[com.windveil.journal.data.local.LlmConfigStore]）。
 */
@Singleton
class HeartVoiceClient @Inject constructor() {

    data class Turn(val role: String, val content: String)

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()
    private val json = Gson()
    private val mediaType = "application/json; charset=utf-8".toMediaType()

    suspend fun chat(
        config: com.windveil.journal.data.local.LlmConfig,
        systemPrompt: String,
        history: List<Turn>,
    ): String = withContext(Dispatchers.IO) {
        val messages = mutableListOf(mapOf("role" to "system", "content" to systemPrompt))
        messages.addAll(history.map { mapOf("role" to it.role, "content" to it.content) })
        val body = mapOf(
            "model" to config.model,
            "messages" to messages,
            "temperature" to 0.4,
        )
        val request = Request.Builder()
            .url(config.baseUrl.trimEnd('/') + "/chat/completions")
            .header("Authorization", "Bearer ${config.apiKey}")
            .post(json.toJson(body).toRequestBody(mediaType))
            .build()
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("模型请求失败（${response.code}）")
            }
            val parsed = json.fromJson(raw, ChatCompletionsResponse::class.java)
            parsed.choices.firstOrNull()?.message?.content
                ?: throw IllegalStateException("模型返回为空")
        }
    }

    private class ChatCompletionsResponse {
        val choices: List<Choice> = emptyList()
        class Choice {
            val message: Message? = null
        }
        class Message {
            val content: String? = null
        }
    }
}
