package com.windveil.journal.domain

import android.Manifest
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 系统日历提醒（standalone-mode）：约定时机时把「待发生事件」写入系统日历，
 * 由系统能力在触发时间提醒（免自建推送/对抗 ROM 杀后台）。
 * 需要用户授权日历权限（WRITE_CALENDAR / READ_CALENDAR）；未授权或失败时降级为
 * 仅 App 内展示（wish.nextTriggerAt 仍在，打开 App 能看到「风来了」）。
 */
@Singleton
class CalendarReminder @Inject constructor(@ApplicationContext private val context: Context) {

    companion object {
        private const val CAL_ID_UNKNOWN = -1L
        private const val EVENT_DESCRIPTION_PREFIX = "windveil:"
    }

    /** 日历权限是否已授予。 */
    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED

    /** 取（或创建）用于本 App 的本地日历账户；失败返回 null。 */
    private fun calendarId(): Long? = try {
        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            arrayOf(CalendarContract.Calendars._ID),
            "${CalendarContract.Calendars.CALENDAR_DISPLAY_NAME} = ?",
            arrayOf("风起簿", "未发生事件管理局"),
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getLong(0) else null
        } ?: createCalendar()
    } catch (e: Exception) {
        null
    }

    private fun createCalendar(): Long? = try {
        // 找一个系统主日历账户挂靠
        val accountName = "windveil.local"
        val values = ContentValues().apply {
            put(CalendarContract.Calendars.NAME, "windveil")
            put(CalendarContract.Calendars.CALENDAR_DISPLAY_NAME, "风起簿")
            put(CalendarContract.Calendars.CALENDAR_COLOR, 0xFF6B8F71.toInt())
            put(CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL, CalendarContract.Calendars.CAL_ACCESS_OWNER)
            put(CalendarContract.Calendars.OWNER_ACCOUNT, accountName)
            put(CalendarContract.Calendars.SYNC_EVENTS, 1)
            put(CalendarContract.Calendars.CALENDAR_TIME_ZONE, ZoneId.systemDefault().id)
            put(CalendarContract.Calendars.ACCOUNT_NAME, accountName)
            put(CalendarContract.Calendars.ACCOUNT_TYPE, CalendarContract.ACCOUNT_TYPE_LOCAL)
        }
        // 建本地日历必须以 sync adapter 身份调用，否则 "Only sync adapters may write to account_name"
        val syncUri = CalendarContract.Calendars.CONTENT_URI.buildUpon()
            .appendQueryParameter(CalendarContract.CALLER_IS_SYNCADAPTER, "true")
            .appendQueryParameter(CalendarContract.Calendars.ACCOUNT_NAME, accountName)
            .appendQueryParameter(CalendarContract.Calendars.ACCOUNT_TYPE, CalendarContract.ACCOUNT_TYPE_LOCAL)
            .build()
        val result = context.contentResolver.insert(syncUri, values)
        result?.let { ContentUris.parseId(it) }
    } catch (e: Exception) {
        null
    }

    /**
     * 写入一条待发生事件（带系统提醒，提前 0 分钟=准时提醒）。
     * 返回日历事件 URI（用于删除）；失败返回 null（降级：仅 App 内展示）。
     */
    suspend fun schedule(
        wishId: String,
        title: String,
        triggerAt: Instant,
        occurrence: String?,
    ): String? = withContext(Dispatchers.IO) {
        if (!hasPermission()) return@withContext null
        val calId = calendarId() ?: return@withContext null
        try {
            val startMillis = triggerAt.toEpochMilli()
            val values = ContentValues().apply {
                put(CalendarContract.Events.CALENDAR_ID, calId)
                put(CalendarContract.Events.TITLE, title)
                put(CalendarContract.Events.DESCRIPTION, "$EVENT_DESCRIPTION_PREFIX$wishId${occurrence?.let { ":$it" } ?: ""}")
                put(CalendarContract.Events.DTSTART, startMillis)
                put(CalendarContract.Events.DTEND, startMillis + 30 * 60 * 1000L) // 30 分钟占位
                put(CalendarContract.Events.EVENT_TIMEZONE, ZoneId.systemDefault().id)
                put(CalendarContract.Events.HAS_ALARM, 1)
            }
            val uri = context.contentResolver.insert(CalendarContract.Events.CONTENT_URI, values) ?: return@withContext null
            // 系统提醒：准时响铃
            val reminderValues = ContentValues().apply {
                put(CalendarContract.Reminders.EVENT_ID, ContentUris.parseId(uri))
                put(CalendarContract.Reminders.MINUTES, 0)
                put(CalendarContract.Reminders.METHOD, CalendarContract.Reminders.METHOD_ALERT)
            }
            context.contentResolver.insert(CalendarContract.Reminders.CONTENT_URI, reminderValues)
            uri.toString()
        } catch (e: Exception) {
            null
        }
    }

    /** 撤销时机（改时机/放下愿望）时删除日历事件。 */
    suspend fun cancel(eventUri: String?) = withContext(Dispatchers.IO) {
        if (eventUri.isNullOrBlank() || !hasPermission()) return@withContext
        runCatching {
            context.contentResolver.delete(android.net.Uri.parse(eventUri), null, null)
        }
    }

    /** 删除某愿望的全部事件（彻底删除愿望时）。 */
    suspend fun cancelAllForWish(wishId: String) = withContext(Dispatchers.IO) {
        if (!hasPermission()) return@withContext
        runCatching {
            context.contentResolver.delete(
                CalendarContract.Events.CONTENT_URI,
                "${CalendarContract.Events.DESCRIPTION} LIKE ?",
                arrayOf("$EVENT_DESCRIPTION_PREFIX$wishId%"),
            )
        }
    }
}
