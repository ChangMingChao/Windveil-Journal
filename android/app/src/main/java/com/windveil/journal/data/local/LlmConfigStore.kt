package com.windveil.journal.data.local

import android.content.Context
import android.net.Uri
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.llmDataStore by preferencesDataStore(name = "windveil_llm")

/** 心语用的大模型配置（用户在「我的」页填写，仅存本地，不经服务端）。 */
data class LlmConfig(
    val baseUrl: String,
    val apiKey: String,
    val model: String,
) {
    val usable: Boolean get() = baseUrl.isNotBlank() && apiKey.isNotBlank() && model.isNotBlank()
}

@Singleton
class LlmConfigStore @Inject constructor(@ApplicationContext private val context: Context) {

    private val baseUrlKey = stringPreferencesKey("base_url")
    private val apiKeyKey = stringPreferencesKey("api_key")
    private val modelKey = stringPreferencesKey("model")

    val config: Flow<LlmConfig?> = context.llmDataStore.data.map { prefs ->
        val baseUrl = prefs[baseUrlKey].orEmpty()
        val apiKey = prefs[apiKeyKey].orEmpty()
        val model = prefs[modelKey].orEmpty()
        if (baseUrl.isBlank()) null else LlmConfig(baseUrl, apiKey, model)
    }

    suspend fun current(): LlmConfig? = runCatching { config.first() }.getOrNull()

    suspend fun save(config: LlmConfig) {
        requireBaseUrl(config.baseUrl)
        context.llmDataStore.edit {
            it[baseUrlKey] = config.baseUrl
            it[apiKeyKey] = config.apiKey
            it[modelKey] = config.model
        }
    }

    private fun requireBaseUrl(rawUrl: String) {
        val url = runCatching { Uri.parse(rawUrl) }.getOrNull()
        val scheme = url?.scheme?.lowercase()
        val host = url?.host
        if (scheme != "https" || host.isNullOrBlank() || rawUrl.contains(Regex("\\s"))) {
            throw IllegalArgumentException("接口地址必须是完整的 HTTPS 地址")
        }
    }
}
