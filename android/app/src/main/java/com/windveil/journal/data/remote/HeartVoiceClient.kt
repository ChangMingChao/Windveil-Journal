package com.windveil.journal.data.remote

import com.google.gson.Gson
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 心语：OpenAI 兼容 /chat/completions 客户端（客户端直连，不经后端）。
 * url / api key / 模型名来自用户在「我的」页的配置（[com.windveil.journal.data.local.LlmConfigStore]）。
 * 用 enqueue + invokeOnCancellation 桥接协程：用户点「停」或离开页面时同步中断底层请求。
 */
@Singleton
class HeartVoiceClient @Inject constructor() {

    data class Turn(val role: String, val content: String)

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(120, TimeUnit.SECONDS)
        .build()
    private val json = Gson()
    private val mediaType = "application/json; charset=utf-8".toMediaType()

    suspend fun chat(
        config: com.windveil.journal.data.local.LlmConfig,
        systemPrompt: String,
        history: List<Turn>,
    ): String = suspendCancellableCoroutine { cont ->
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
        val call = client.newCall(request)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (cont.isActive) cont.resumeWith(Result.failure(e))
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val result = runCatching {
                        val raw = it.body?.string().orEmpty()
                        if (!it.isSuccessful) throw IllegalStateException("模型请求失败（${it.code}）")
                        val parsed = json.fromJson(raw, ChatCompletionsResponse::class.java)
                        parsed.choices.firstOrNull()?.message?.content
                            ?: throw IllegalStateException("模型返回为空")
                    }
                    if (cont.isActive) cont.resumeWith(result)
                }
            }
        })
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
