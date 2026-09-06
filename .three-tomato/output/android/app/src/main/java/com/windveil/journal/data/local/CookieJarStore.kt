package com.windveil.journal.data.local

import android.content.Context
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import java.io.File
import java.io.ObjectInputStream
import java.io.ObjectOutputStream

/**
 * 持久化 CookieJar —— 承载 /auth/refresh 与 /auth/anonymous 下发的 httpOnly refresh token。
 * Android 端无法（也不应）读取 httpOnly Cookie 内容，只需原样带回。
 */
class CookieJarStore(context: Context) : CookieJar {

    private val file = File(context.filesDir, "windveil_cookies.bin")
    private val store = LinkedHashMap<String, List<Cookie>>()

    init {
        runCatching {
            if (file.exists()) {
                ObjectInputStream(file.inputStream().buffered()).use { input ->
                    @Suppress("UNCHECKED_CAST")
                    val raw = input.readObject() as Map<String, List<Cookie>>
                    store.putAll(raw)
                }
            }
        }
    }

    @Synchronized
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        if (cookies.isEmpty()) return
        store[url.host] = cookies
        runCatching {
            ObjectOutputStream(file.outputStream().buffered()).use { it.writeObject(store) }
        }
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> =
        store[url.host].orEmpty().filter { it.matches(url) }

    @Synchronized
    fun clear() {
        store.clear()
        file.delete()
    }
}
