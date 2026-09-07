package com.windveil.journal.data.remote

import com.windveil.journal.data.local.TokenStore
import kotlinx.coroutines.runBlocking
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route

/**
 * 收到 401 时用 httpOnly Cookie 调 /auth/refresh 换新 access token 并重放请求；
 * 刷新仍失败（REFRESH_INVALID）则放弃重试，让上层回到 welcome 流程。
 */
class TokenAuthenticator constructor(
    private val tokenStore: TokenStore,
    private val apiProvider: RefreshApiProvider,
) : Authenticator {

    override fun authenticate(route: Route?, response: Response): Request? {
        if (responseCount(response) >= 2) return null // 刷新后仍 401，不再循环

        val refreshResponse = runBlocking {
            runCatching { apiProvider.refreshApi().refreshToken() }
        }.getOrNull()

        // 网络层失败（后端暂时不可达等）：保留会话，仅让本次请求报错
        if (refreshResponse == null) return null

        val newToken = refreshResponse.body()?.accessToken
        if (!refreshResponse.isSuccessful || newToken == null) {
            // 后端明确拒绝（refresh 失效或未实现）：会话不可恢复，
            // 清掉本地会话并通知 MainActivity 回到欢迎页
            runBlocking {
                tokenStore.clear()
                tokenStore.notifySessionExpired()
            }
            return null
        }

        runBlocking { tokenStore.save(newToken) }
        return response.request.newBuilder()
            .header("Authorization", "Bearer $newToken")
            .build()
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }

    /** RefreshApi 走独立 OkHttp（无 authenticator），避免刷新请求自身再触发 401 循环。 */
    interface RefreshApiProvider {
        fun refreshApi(): AuthApi
    }
}
