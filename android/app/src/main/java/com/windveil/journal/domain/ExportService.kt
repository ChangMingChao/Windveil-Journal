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
        val json = repository.exportJson { path -> File(path).takeIf { it.isFile }?.readBytes() }
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

    /**
     * 从用户选中的文件导入（系统文件选择器给 Uri）。
     * 照片路径按本机文件存在性校验过滤。
     */
    suspend fun importFromUri(context: Context, uri: android.net.Uri): Triple<Int, Int, Int> = withContext(Dispatchers.IO) {
        val json = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
            ?: throw IllegalStateException("读不了这个文件")
        repository.importJson(
            json,
            writePhoto = { sourcePath, bytes ->
                val suffix = sourcePath.substringAfterLast('.', "jpg")
                val dir = File(context.filesDir, "lite_photos").apply { mkdirs() }
                val target = File.createTempFile("photo_", ".$suffix", dir)
                target.writeBytes(bytes)
                target.absolutePath
            },
            sanitizePhotos = { paths -> paths.filter { File(it).isFile } },
        )
    }
}
