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

    val accessToken: Flow<String?> = context.dataStore.data.map { it[accessTokenKey] }

    /** 是否已在本机建立过个人空间（决定冷启动进 welcome 还是 garden）。 */
    val hasSpace: Flow<Boolean> = context.dataStore.data.map { it[hasSpaceKey] ?: false }

    /** 会话不可恢复（refresh 失效）时发出，MainActivity 收到后回欢迎页。 */
    val sessionExpired = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    fun notifySessionExpired() {
        sessionExpired.tryEmit(Unit)
    }

    suspend fun save(access: String) {
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
