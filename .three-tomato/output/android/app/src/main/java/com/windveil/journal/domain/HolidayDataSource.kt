package com.windveil.journal.domain

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/** 节假日数据源：assets/holidays_{year}.json（随 APK 打包，standalone-mode）。 */
@Singleton
class HolidayDataSource @Inject constructor(@ApplicationContext private val context: Context) {

    private val cache = mutableMapOf<Int, String>()

    // assets 打包的年份；后续年度更新数据文件时同步扩这里
    private val availableYears = listOf(2026)

    private fun load(year: Int): String? = synchronized(cache) {
        if (cache.containsKey(year)) {
            cache[year]
        } else {
            val text = runCatching {
                context.assets.open("holidays_$year.json").bufferedReader().use { it.readText() }
            }.getOrNull()
            if (text != null) cache[year] = text
            text
        }
    }

    /** 名字去重列表（GET /holidays 语义）。 */
    fun names(year: Int = availableYears.last()): List<String> {
        val data = load(year) ?: return emptyList()
        val obj = JSONObject(data).optJSONObject("holidays") ?: return emptyList()
        val days = obj.keys().asSequence().toList().sorted()
        val seen = mutableListOf<String>()
        for (day in days) {
            val name = obj.optString(day)
            if (name !in seen) seen.add(name)
        }
        return seen
    }

    /** date+name 明细，按日期升序。 */
    fun items(year: Int = availableYears.last()): List<Pair<String, String>> {
        val data = load(year) ?: return emptyList()
        val obj = JSONObject(data).optJSONObject("holidays") ?: return emptyList()
        val days = obj.keys().asSequence().toList().sorted()
        return days.map { it to obj.optString(it) }
    }

    fun available(): Boolean = load(availableYears.last()) != null

    /** 组装 TimingCalculator.HolidayData（全部年份合并）。 */
    fun toHolidayData(): TimingCalculator.HolidayData {
        val map = availableYears.mapNotNull { y -> load(y)?.let { y to it } }.toMap()
        return TimingCalculator.HolidayData.parse(map)
    }
}
