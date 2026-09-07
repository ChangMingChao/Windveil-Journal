package com.windveil.journal

import com.windveil.journal.data.remote.ApiException
import com.windveil.journal.data.remote.SeedWishRequest
import com.windveil.journal.data.remote.WishesApi
import com.windveil.journal.data.remote.bodyOrThrow
import com.windveil.journal.data.remote.okOrThrow
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

/**
 * API 层行为测试（MockWebServer）：
 * 1. 端点路径与契约一致；
 * 2. 错误响应 → ApiException（契约约定：越权一律 404 WISH_NOT_FOUND）。
 */
class WishesApiTest {

    private lateinit var server: MockWebServer
    private lateinit var api: WishesApi

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(WishesApi::class.java)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `种下愿望走 POST wishes 端点且请求体含 source`() = runBlocking {
        server.enqueue(
            MockResponse().setResponseCode(201).setBody(
                """
                {"wish": {"id": "w1", "title": "去看海", "seeded_at": "2026-09-01T08:00:00Z",
                 "state": "seeded", "timing": {"type": "none", "label": "l", "trigger_kind": "none", "next_trigger_at": null}, "version": 1},
                 "question": "是想要那种海边的安静吗？", "actions": [], "degraded": false}
                """.trimIndent()
            )
        )

        val result = api.seedWish(SeedWishRequest(source = "text", text = "想一个人去看海")).bodyOrThrow()

        assertEquals("去看海", result.wish.title)
        assertEquals("是想要那种海边的安静吗？", result.question)

        val recorded = server.takeRequest()
        assertEquals("/api/v1/wishes", recorded.path)
        assertTrue(recorded.body.readUtf8().contains("\"source\":\"text\""))
    }

    @Test
    fun `越权访问按契约返回 404 WISH_NOT_FOUND 并映射为 ApiException`() = runBlocking {
        server.enqueue(
            MockResponse().setResponseCode(404).setBody(
                """{"code": "WISH_NOT_FOUND", "message": "这条愿望不在这里。"}"""
            )
        )

        val exception = assertThrows(ApiException::class.java) {
            runBlocking { api.getWish("not-yours").bodyOrThrow() }
        }
        assertEquals(404, exception.httpCode)
        assertEquals("WISH_NOT_FOUND", exception.error.code)
    }

    @Test
    fun `彻底删除必须带 confirm 为 true（契约 EX-25_1）`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(204))
        api.deleteWishPermanently("w1", confirm = true).okOrThrow()
        assertEquals("/api/v1/wishes/w1?confirm=true", server.takeRequest().path)
    }
}
