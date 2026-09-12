package com.windveil.journal.domain

import android.content.Context
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** 数据导出（standalone-mode）：全量 JSON 写入用户经系统保存器选定的位置（SAF）。 */
@Singleton
class ExportService @Inject constructor(
    @ApplicationContext private val context: Context,
    private val repository: StandaloneRepository,
) {
    /**
     * 导出到用户选定的目标 URI（SAF ACTION_CREATE_DOCUMENT）。
     * 不再直写公共目录（scoped storage 下 File API 不可靠）；失败抛异常，由调用方提示。
     */
    suspend fun exportToUri(uri: android.net.Uri) = withContext(Dispatchers.IO) {
        val json = repository.exportJson { path -> File(path).takeIf { it.isFile }?.readBytes() }
        val out = context.contentResolver.openOutputStream(uri, "wt")
            ?: throw IllegalStateException("写不了这个位置")
        out.bufferedWriter(Charsets.UTF_8).use { it.write(json) }
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
