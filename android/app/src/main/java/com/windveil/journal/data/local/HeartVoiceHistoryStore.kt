package com.windveil.journal.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.heartVoiceHistoryStore by preferencesDataStore(name = "windveil_heart_voice_history")

/** 心语对话历史的一条消息（持久化最小结构）。 */
data class HeartVoiceHistoryEntry(val role: String, val text: String)

/**
 * 心语对话历史持久化（standalone-mode）：杀进程后对话不丢。
 * 只存最近 [MAX_ENTRIES] 条，超出的丢弃（上下文窗口与存储都可控）。
 */
@Singleton
class HeartVoiceHistoryStore @Inject constructor(@ApplicationContext private val context: Context) {

    companion object {
        private val KEY = stringPreferencesKey("messages_json")
        private const val MAX_ENTRIES = 40
    }

    private val gson = Gson()

    suspend fun load(): List<HeartVoiceHistoryEntry> = runCatching {
        context.heartVoiceHistoryStore.data.first()[KEY]?.let { json ->
            // Gson 反射会绕过 Kotlin 非空类型：损坏/半写的 JSON 可能产生 role/text 为 null 的条目，
            // 直接透传会让 UI 渲染时 NPE（用户报"点开心语就闪退"）。这里过滤掉脏条目。
            gson.fromJson<List<HeartVoiceHistoryEntry>>(
                json,
                object : TypeToken<List<HeartVoiceHistoryEntry>>() {}.type,
            )?.filter { it != null && it.role != null && it.text != null }
                ?.map { HeartVoiceHistoryEntry(it.role!!, it.text!!) }
                .orEmpty()
        }.orEmpty()
    }.getOrDefault(emptyList())

    suspend fun append(role: String, text: String) {
        save(load() + HeartVoiceHistoryEntry(role, text))
    }

    private suspend fun save(entries: List<HeartVoiceHistoryEntry>) {
        val trimmed = entries.takeLast(MAX_ENTRIES)
        context.heartVoiceHistoryStore.edit { prefs ->
            prefs[KEY] = gson.toJson(trimmed)
        }
    }
}
