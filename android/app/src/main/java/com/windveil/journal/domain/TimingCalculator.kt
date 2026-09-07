package com.windveil.journal.domain

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.time.Instant
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/**
 * 时机计算（timing.py 的 Kotlin 移植，standalone-mode）。
 *
 * 硬约束沿用：触发时刻一律端上按本机时区确定性计算，不由 UI 随手传值。
 * 6+1 种类型：season / month_day / after_months / free_weekend / holiday /
 * when_tired（信号类，不计算时刻）/ none（永不提醒）。
 * 错误语义对齐后端 TimingError → UI 显示 TIMING_INVALID 文案。
 */
object TimingCalculator {

    const val REMIND_HOUR = 9 // 本地上午 9 点

    private val SEASON_START_MONTH = mapOf("spring" to 3, "summer" to 6, "autumn" to 9, "winter" to 12)
    val ALLOWED_AFTER_MONTHS = listOf(1, 3, 6, 12)
    private val MONTH_DAY_RE = Regex("^\\d{4}-\\d{2}(-\\d{2})?$")

    class TimingInvalid(message: String) : Exception(message)

    data class Plan(
        val timingType: String,
        val timingValue: String?,
        val triggerKind: String, // time | signal | none
        val nextTriggerAt: Instant?, // null = signal/none
        val occurrence: String?, // 去重键
    )

    /** 节假日数据（assets/holidays_{year}.json 的 holidays 映射）。 */
    class HolidayData(private val byYear: Map<Int, Pair<Map<String, String>, Map<String, String>>>) {
        fun holidaysOf(year: Int): Map<String, String> = byYear[year]?.first.orEmpty()

        /** 该日期是否为法定调休上班日（数据缺失时恒 false——安全退化，同后端）。 */
        fun isWorkday(day: LocalDate): Boolean = byYear[day.year]?.second?.containsKey(day.toString()) == true

        companion object {
            fun parse(jsonByYear: Map<Int, String>): HolidayData {
                val gson = Gson()
                val parsed = jsonByYear.mapValues { (_, text) ->
                    runCatching {
                        val root = gson.fromJson<Map<String, Any>>(text, object : TypeToken<Map<String, Any>>() {}.type)
                        @Suppress("UNCHECKED_CAST")
                        val holidays = (root["holidays"] as? Map<String, String>) ?: emptyMap()
                        @Suppress("UNCHECKED_CAST")
                        val workdays = (root["workdays"] as? Map<String, String>) ?: emptyMap()
                        Pair(holidays, workdays)
                    }.getOrDefault(Pair(emptyMap(), emptyMap()))
                }
                return HolidayData(parsed)
            }
        }
    }

    fun plan(
        timingType: String,
        today: LocalDate = LocalDate.now(),
        zone: ZoneId = ZoneId.systemDefault(),
        season: String? = null,
        monthDay: String? = null,
        afterMonths: Int? = null,
        holidays: List<String>? = null,
        holidayData: HolidayData? = null,
    ): Plan {
        return when (timingType) {
            "none" -> Plan("none", null, "none", null, null)

            "when_tired" -> Plan("when_tired", null, "signal", null, null)

            "season" -> {
                val s = season ?: throw TimingInvalid("season is required")
                val month = SEASON_START_MONTH[s]
                    ?: throw TimingInvalid("season must be one of spring/summer/autumn/winter")
                val year = if (YearMonth.of(today.year, month).atDay(1) > today) today.year else today.year + 1
                val whenAt = localAt(zone, LocalDate.of(year, month, 1))
                Plan("season", s, "time", whenAt.toInstant(), "season:$s:$year")
            }

            "month_day" -> {
                val md = monthDay ?: throw TimingInvalid("month_day is required")
                if (!MONTH_DAY_RE.matches(md)) {
                    throw TimingInvalid("month_day format must be YYYY-MM or YYYY-MM-DD")
                }
                val parts = md.split("-")
                val target = try {
                    if (parts.size == 2) LocalDate.of(parts[0].toInt(), parts[1].toInt(), 1)
                    else LocalDate.of(parts[0].toInt(), parts[1].toInt(), parts[2].toInt())
                } catch (e: Exception) {
                    throw TimingInvalid("month_day is not a real date")
                }
                if (target < today) throw TimingInvalid("month_day is in the past")
                val whenAt = localAt(zone, target)
                Plan("month_day", md, "time", whenAt.toInstant(), "month_day:$md")
            }

            "after_months" -> {
                val m = afterMonths ?: throw TimingInvalid("after_months is required")
                if (m !in ALLOWED_AFTER_MONTHS) throw TimingInvalid("after_months must be one of 1/3/6/12")
                val target = addMonths(today, m)
                val whenAt = localAt(zone, target)
                Plan("after_months", m.toString(), "time", whenAt.toInstant(), "after_months:$target")
            }

            "free_weekend" -> {
                // 下一个「真周末」：周六/周日、非调休上班日、且不在法定假期内
                //（假期本身天天在放假，不算「等来的空闲周末」）；无数据时退化为「第一个周末」
                fun inHoliday(day: LocalDate): Boolean =
                    holidayData?.holidaysOf(day.year)?.containsKey(day.toString()) == true
                var target: LocalDate? = null
                for (offset in 1..45) {
                    val day = today.plusDays(offset.toLong())
                    if (day.dayOfWeek.value >= 6 && !isWorkday(day, holidayData) && !inHoliday(day)) {
                        target = day
                        break
                    }
                }
                val daysUntilSaturday = ((6 - today.dayOfWeek.value + 7) % 7).let { if (it == 0) 7 else it }
                val chosen = target ?: today.plusDays(daysUntilSaturday.toLong())
                val whenAt = localAt(zone, chosen)
                Plan("free_weekend", null, "time", whenAt.toInstant(), "free_weekend:$chosen")
            }

            "holiday" -> {
                // 多选取最近到来的匹配日；数据缺失/无匹配 → TimingInvalid（拒绝瞎猜，对齐 UT-S03-57）
                val wanted = (holidays ?: emptyList()).filter { it.isNotBlank() }
                if (wanted.isEmpty()) throw TimingInvalid("holidays is required")
                val data = holidayData ?: throw TimingInvalid("holiday data unavailable")
                var found: Pair<LocalDate, String>? = null
                for (year in listOf(today.year, today.year + 1)) {
                    val hits = data.holidaysOf(year)
                        .map { (dayStr, name) -> Pair(LocalDate.parse(dayStr), name) }
                        .filter { it.second in wanted && it.first >= today }
                    if (hits.isNotEmpty()) {
                        found = hits.minByOrNull { it.first }!!
                        break
                    }
                }
                val (target, name) = found ?: throw TimingInvalid("no upcoming holiday matched in holiday data")
                val whenAt = localAt(zone, target)
                Plan("holiday", name, "time", whenAt.toInstant(), "holiday:$name:$target")
            }

            else -> throw TimingInvalid("unknown timing type: $timingType")
        }
    }

    /** 卡面文案（与后端 timing.label 同语义）。 */
    fun label(plan: Plan, holidays: List<String>? = null): String = when (plan.timingType) {
        "none" -> "你说你会自己想起它"
        "when_tired" -> "累了的时候再说"
        "season" -> "正在等待合适的风：${seasonLabel(plan.timingValue)}"
        "month_day" -> "正在等待合适的风：${plan.timingValue}"
        "after_months" -> "${plan.timingValue} 个月后再看"
        "free_weekend" -> "等一个有空闲的周末"
        "holiday" -> "正在等待合适的风：${plan.timingValue}"
        else -> plan.timingType
    }

    private fun seasonLabel(value: String?): String = when (value) {
        "spring" -> "春天"; "summer" -> "夏天"; "autumn" -> "秋天"; "winter" -> "入冬"
        else -> value ?: ""
    }

    private fun localAt(zone: ZoneId, day: LocalDate): ZonedDateTime =
        ZonedDateTime.of(day.year, day.monthValue, day.dayOfMonth, REMIND_HOUR, 0, 0, 0, zone)

    private fun addMonths(day: LocalDate, months: Int): LocalDate {
        val ym = YearMonth.from(day).plusMonths(months.toLong())
        // 「1 月 31 日 + 1 月」这类不存在的日期逐日回退
        var candidate = day.dayOfMonth
        while (candidate > ym.lengthOfMonth()) candidate--
        return ym.atDay(candidate)
    }

    private fun isWorkday(day: LocalDate, data: HolidayData?): Boolean =
        data?.isWorkday(day) ?: false

    fun isoInstant(instant: Instant): String =
        DateTimeFormatter.ISO_INSTANT.format(instant)

    fun parseIso(text: String): Instant = Instant.parse(text)

    fun epochMillis(instant: Instant, zone: ZoneId = ZoneId.systemDefault()): Long =
        instant.atZone(zone).toInstant().toEpochMilli()
}
