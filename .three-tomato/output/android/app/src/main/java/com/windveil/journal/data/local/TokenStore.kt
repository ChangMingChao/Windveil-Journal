package com.windveil.journal.data.local

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.util.concurrent.atomic.AtomicBoolean
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore by preferencesDataStore(name = "windveil_auth")

/**
 * access token 本地存储（自管 JWT：access 15 分钟 / refresh 30 天）。
 * refresh token 由后端以 httpOnly Cookie 下发，客户端不读取其内容，
 * 持久化交由 [CookieJarStore] 完成 —— 与契约 auth.yaml 的安全设计一致。
 */
@Singleton
class TokenStore @Inject constructor(@ApplicationContext private val context: Context) {

    private val accessTokenKey = stringPreferencesKey("access_token")
    private val hasSpaceKey = booleanPreferencesKey("has_space")

    // 会话过期通知的进程内防抖标志（401 风暴下只发一次）
    private val expiryNotified = AtomicBoolean(false)

    val accessToken: Flow<String?> = context.dataStore.data.map { it[accessTokenKey] }

    /** 是否已在本机建立过个人空间（决定冷启动进 welcome 还是 garden）。 */
    val hasSpace: Flow<Boolean> = context.dataStore.data.map { it[hasSpaceKey] ?: false }

    /** 会话不可恢复（refresh 失效）时发出，MainActivity 收到后回欢迎页。 */
    val sessionExpired = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    fun notifySessionExpired() {
        // 防抖：并发 401 只发一次；recreate 后残留请求再进来也会被拦住，
        // 否则 401 → 清会话 → recreate → 残留请求再 401 → 又 recreate，页面无限闪烁
        if (expiryNotified.compareAndSet(false, true)) {
            sessionExpired.tryEmit(Unit)
        }
    }

    /** 建号/登录成功后重置防抖标志，下一次会话过期仍能通知。 */
    suspend fun save(access: String) {
        expiryNotified.set(false)
        context.dataStore.edit {
            it[accessTokenKey] = access
            it[hasSpaceKey] = true
        }
    }

    suspend fun clear() {
        context.dataStore.edit {
            it.remove(accessTokenKey)
            it[hasSpaceKey] = false
        }
    }

    suspend fun current(): String? = accessToken.first()
}
