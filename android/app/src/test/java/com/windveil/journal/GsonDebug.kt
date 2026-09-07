package com.windveil.journal


import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

class GsonDebugKt { companion object { @JvmStatic fun main(args: Array<String>) {
    val text = """{"holidays": {"2026-10-01": "a"}, "workdays": {"2026-10-10": "w", "2026-10-11": "w2"}}"""
    val gson = Gson()
    val root: Map<String, Any> = gson.fromJson(text, object : TypeToken<Map<String, Any>>() {}.type)
    @Suppress("UNCHECKED_CAST")
    val workdays = root["workdays"] as? Map<String, String>
    println("workdays = " + workdays)
} } }
