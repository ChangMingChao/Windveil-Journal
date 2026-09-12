package com.windveil.journal

import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.remote.HeartVoiceClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

/**
 * HeartVoiceClient 契约测试：OpenAI 兼容解析 / 错误分类 / 取消语义。
 * v0.3.0 起 chat 走 enqueue + invokeOnCancellation，「停」必须能真正中断底层请求。
 */
class HeartVoiceClientTest {

    private lateinit var server: MockWebServer
    private lateinit var client: HeartVoiceClient

    private val config: LlmConfig
        get() = LlmConfig(server.url("/v1").toString(), "test-key", "test-model")

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = HeartVoiceClient()
    }

    @After
    fun tearDown() {
        // 取消用例里服务端还挂着延迟 body 的连接，shutdown 可能「等不到队列关闭」——收尾失败不影响断言
        runCatching { server.shutdown() }
    }

    @Test
    fun chat_解析OpenAI兼容响应_并带上鉴权头() {
        server.enqueue(
            MockResponse().setBody("""{"choices":[{"message":{"content":"嗯，我记下了。"}}]}"""),
        )
        val reply = runBlocking { client.chat(config, "系统提示", emptyList()) }
        assertEquals("嗯，我记下了。", reply)
        val recorded = server.takeRequest()
        assertEquals("/v1/chat/completions", recorded.path)
        assertEquals("Bearer test-key", recorded.getHeader("Authorization"))
        assertTrue(recorded.body.readUtf8().contains("\"model\":\"test-model\""))
    }

    @Test
    fun chat_非2xx_抛带状态码的IllegalState() {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"bad key"}"""))
        try {
            runBlocking { client.chat(config, "系统提示", emptyList()) }
            throw AssertionError("should throw")
        } catch (e: IllegalStateException) {
            assertTrue(e.message!!.contains("401"))
        }
    }

    @Test
    fun chat_协程取消会中断底层请求_不悬挂到读超时() {
        // 10 秒后才吐 body；取消必须立刻中断请求，而不是等读超时
        server.enqueue(
            MockResponse()
                .setBody("""{"choices":[{"message":{"content":"慢回复"}}]}""")
                .setBodyDelay(10, TimeUnit.SECONDS),
        )
        runBlocking {
            var caught: Throwable? = null
            val job = launch {
                try {
                    client.chat(config, "系统提示", emptyList())
                } catch (t: Throwable) {
                    caught = t
                }
            }
            yield() // 让 launch 的协程先跑起来（进入 chat 并发出请求），再等请求到达
            assertTrue("请求应在 2 秒内发出", server.takeRequest(2, TimeUnit.SECONDS) != null)
            val start = System.currentTimeMillis()
            job.cancelAndJoin()
            val elapsed = System.currentTimeMillis() - start
            assertTrue("取消应在 8 秒内完成（实际 ${elapsed}ms）", elapsed < 8000)
            assertTrue("应是被取消或已正常完成，而非悬挂到超时", caught is CancellationException || caught == null)
        }
    }
}
