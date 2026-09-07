package com.windveil.journal

import com.windveil.journal.domain.TimingCalculator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * TimingCalculator 移植测试（standalone-mode）。
 * 语义对齐后端 tests/test_holiday_timing.py（UT-S03-55~58）与 timing.py 的既有约定。
 */
class TimingCalculatorTest {

    private val zone = ZoneId.of("Asia/Shanghai")
    private val today = LocalDate.of(2026, 9, 6) // 周日

    private fun holidayData(vararg entries: Pair<String, String>): TimingCalculator.HolidayData {
        // 本地 JVM 的 org.json 是 Android stub（toString 未实现），手工拼 JSON
        fun holidaysJson(pairs: List<Pair<String, String>>): String =
            pairs.joinToString(",", "{", "}") { "\"${it.first}\":\"${it.second}\"" }
        val y2026 = holidaysJson(entries.filter { it.first.startsWith("2026") })
        val y2027 = holidaysJson(entries.filter { it.first.startsWith("2027") })
        return TimingCalculator.HolidayData.parse(
            mapOf(2026 to """{"holidays": $y2026}""", 2027 to """{"holidays": $y2027}"""),
        )
    }

    // ---- none / when_tired ----

    @Test
    fun none_永不提醒() {
        val plan = TimingCalculator.plan("none", today = today, zone = zone)
        assertEquals("none", plan.triggerKind)
        assertNull(plan.nextTriggerAt)
    }

    @Test
    fun when_tired_是信号类不计算时刻() {
        val plan = TimingCalculator.plan("when_tired", today = today, zone = zone)
        assertEquals("signal", plan.triggerKind)
        assertNull(plan.nextTriggerAt)
    }

    // ---- season ----

    @Test
    fun season_入冬_今年未到则取今年12月1日9点() {
        val plan = TimingCalculator.plan("season", today = today, zone = zone, season = "winter")
        assertEquals("winter", plan.timingValue)
        assertEquals("time", plan.triggerKind)
        val at = plan.nextTriggerAt!!.atZone(zone)
        assertEquals(2026, at.year); assertEquals(12, at.monthValue); assertEquals(1, at.dayOfMonth)
        assertEquals(9, at.hour)
        assertEquals("season:winter:2026", plan.occurrence)
    }

    @Test
    fun season_已过则取明年() {
        // 9 月 6 日看春天（今年 3 月已过）→ 明年 3 月 1 日
        val plan = TimingCalculator.plan("season", today = today, zone = zone, season = "spring")
        val at = plan.nextTriggerAt!!.atZone(zone)
        assertEquals(2027, at.year); assertEquals(3, at.monthValue)
        assertEquals("season:spring:2027", plan.occurrence)
    }

    @Test
    fun season_非法季节名_报TimingInvalid() {
        try {
            TimingCalculator.plan("season", today = today, zone = zone, season = "monsoon")
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    // ---- month_day ----

    @Test
    fun month_day_完整日期合法() {
        val plan = TimingCalculator.plan("month_day", today = today, zone = zone, monthDay = "2027-03-15")
        val at = plan.nextTriggerAt!!.atZone(zone)
        assertEquals(2027, at.year); assertEquals(3, at.monthValue); assertEquals(15, at.dayOfMonth)
        assertEquals("month_day:2027-03-15", plan.occurrence)
    }

    @Test
    fun month_day_过去的日期_报TimingInvalid() {
        try {
            TimingCalculator.plan("month_day", today = today, zone = zone, monthDay = "2025-01-01")
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    @Test
    fun month_day_不存在的日期_报TimingInvalid() {
        try {
            TimingCalculator.plan("month_day", today = today, zone = zone, monthDay = "2027-02-30")
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    // ---- after_months ----

    @Test
    fun after_months_三个月后_月底回退() {
        // 9 月 6 日 + 3 个月 = 12 月 6 日
        val plan = TimingCalculator.plan("after_months", today = today, zone = zone, afterMonths = 3)
        val at = plan.nextTriggerAt!!.atZone(zone)
        assertEquals(2026, at.year); assertEquals(12, at.monthValue); assertEquals(6, at.dayOfMonth)
    }

    @Test
    fun after_months_非法数值_报TimingInvalid() {
        try {
            TimingCalculator.plan("after_months", today = today, zone = zone, afterMonths = 5)
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    // ---- holiday（对齐 UT-S03-55~58）----

    @Test
    fun holiday_多选取最近到来的匹配日_对齐UT_S03_55() {
        val data = holidayData(
            "2026-10-01" to "国庆节", "2026-10-02" to "国庆节",
            "2027-01-01" to "元旦",
        )
        val plan = TimingCalculator.plan(
            "holiday", today = today, zone = zone,
            holidays = listOf("国庆节", "元旦"), holidayData = data,
        )
        assertEquals("国庆节", plan.timingValue)
        assertEquals("time", plan.triggerKind)
        val at = plan.nextTriggerAt!!.atZone(zone)
        assertEquals(2026, at.year); assertEquals(10, at.monthValue); assertEquals(1, at.dayOfMonth)
        assertEquals(9, at.hour)
        assertEquals("holiday:国庆节:2026-10-01", plan.occurrence)
    }

    @Test
    fun holiday_空列表_报TimingInvalid_对齐UT_S03_56() {
        val data = holidayData("2026-10-01" to "国庆节")
        try {
            TimingCalculator.plan("holiday", today = today, zone = zone, holidays = emptyList(), holidayData = data)
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
        try {
            TimingCalculator.plan("holiday", today = today, zone = zone, holidayData = data)
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    @Test
    fun holiday_名称无匹配_报TimingInvalid_对齐UT_S03_57() {
        val data = holidayData("2026-10-01" to "国庆节")
        try {
            TimingCalculator.plan("holiday", today = today, zone = zone, holidays = listOf("不存在的节"), holidayData = data)
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    @Test
    fun holiday_跨年命中次年_对齐移植语义() {
        val data = holidayData("2026-10-01" to "国庆节", "2027-01-01" to "元旦")
        val plan = TimingCalculator.plan(
            "holiday", today = today, zone = zone, holidays = listOf("元旦"), holidayData = data,
        )
        assertEquals("元旦", plan.timingValue)
        assertTrue(plan.occurrence!!.contains("2027-01-01"))
    }

    @Test
    fun holiday_数据缺失_报TimingInvalid_不瞎猜() {
        try {
            TimingCalculator.plan("holiday", today = today, zone = zone, holidays = listOf("国庆节"), holidayData = null)
            throw AssertionError("should throw")
        } catch (e: TimingCalculator.TimingInvalid) { /* 期望 */ }
    }

    // ---- free_weekend ----

    @Test
    fun free_weekend_下一个非调休周末() {
        // 2026-09-06 是周日 → 明天起第一个周末是 9/12（周六）
        val plan = TimingCalculator.plan("free_weekend", today = today, zone = zone, holidayData = null)
        val at = plan.nextTriggerAt!!.atZone(zone)
        assertEquals(2026, at.year); assertEquals(9, at.monthValue); assertEquals(12, at.dayOfMonth)
    }

    // ---- 卡面文案 ----

    @Test
    fun label_文案与后端同语义() {
        val none = TimingCalculator.plan("none", today = today, zone = zone)
        assertEquals("你说你会自己想起它", TimingCalculator.label(none))
        val winter = TimingCalculator.plan("season", today = today, zone = zone, season = "winter")
        assertEquals("正在等待合适的风：入冬", TimingCalculator.label(winter))
    }
}
