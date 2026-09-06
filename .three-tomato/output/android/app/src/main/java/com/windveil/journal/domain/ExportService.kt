package com.windveil.journal.domain

import android.content.Context
import android.os.Environment
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import javax.inject.Singleton

/** 数据导出（standalone-mode）：全量 JSON 写到公共 Documents/windveil/。 */
@Singleton
class ExportService @Inject constructor(
    @ApplicationContext private val context: Context,
    private val repository: StandaloneRepository,
) {
    suspend fun exportToDownloads(context: Context): String = withContext(Dispatchers.IO) {
        val json = repository.exportJson()
        val docsDir = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
            "windveil",
        )
        if (!docsDir.exists()) docsDir.mkdirs()
        val stamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"))
        val out = File(docsDir, "windveil-backup-$stamp.json")
        out.writeText(json, Charsets.UTF_8)
        out.absolutePath
    }
}
