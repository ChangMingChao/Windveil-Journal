package com.windveil.journal.presentation.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Check
import androidx.compose.foundation.clickable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import coil.compose.AsyncImage
import com.windveil.journal.data.local.db.LiteEventEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject
import java.io.File

@HiltViewModel
class LiteEventsViewModel @Inject constructor(
    private val repository: StandaloneRepository,
) : ViewModel() {
    /** Room 流：本地库变更自动刷新。 */
    val events = repository.observeOpenLiteEvents()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun create(text: String, onCreated: () -> Unit) {
        if (text.isBlank() || text.length > 200) return
        viewModelScope.launch {
            repository.createLiteEvent(text)
            onCreated()
        }
    }

    fun markDone(eventId: String) = viewModelScope.launch { repository.markLiteEventDone(eventId) }
    fun delete(eventId: String) = viewModelScope.launch { repository.deleteLiteEvent(eventId) }
    fun update(eventId: String, text: String, note: String?, photos: String?) =
        viewModelScope.launch { repository.updateLiteEvent(eventId, text, note, photos) }

    /** 删除单张照片时顺带清理本机文件（避免 filesDir 里堆积孤儿文件）。 */
    fun removePhoto(eventId: String, path: String) {
        viewModelScope.launch {
            val event = repository.getLiteEvent(eventId) ?: return@launch
            val remaining = parsePhotos(event.photos.orEmpty()) - path
            repository.updateLiteEvent(
                eventId,
                event.text,
                event.note,
                remaining.takeIf { it.isNotEmpty() }?.let { com.google.gson.Gson().toJson(it) },
            )
            runCatching { File(path).delete() }
        }
    }
}

/** S09：先记一下并随手划掉 —— 无 Agent、无提醒路径、不占提醒额度。 */
@Composable
fun LiteEventsScreen(
    onBack: () -> Unit = {},
    embedded: Boolean = false,
    viewModel: LiteEventsViewModel = hiltViewModel(),
) {
    val events by viewModel.events.collectAsState()
    var text by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        if (!embedded) {
            TextButton(onClick = onBack) { Text("← 回到未发生之地") }
        }
        if (!embedded) {
            Text("随手记", style = MaterialTheme.typography.titleLarge)
        }
        Text(
            "还不值得变成愿望的念头，先记在这里。它们不会被提醒，也不会被催。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                placeholder = { Text("先记一下（今晚吃什么、周末取快递）") },
                modifier = Modifier.weight(1f),
                singleLine = true,
            )
            Button(
                onClick = {
                    viewModel.create(text) { text = "" }
                },
                enabled = text.isNotBlank() && text.length <= 200,
                modifier = Modifier.padding(start = 8.dp),
            ) { Text("记下") }
        }
        LazyColumn(
            Modifier.padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            items(events, key = { it.id }) { event ->
                var showEdit by remember(event.id) { mutableStateOf(false) }
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f).clickable { showEdit = true }) {
                                Text(event.text, style = MaterialTheme.typography.bodyMedium)
                                event.note?.let {
                                    Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
                                }
                            }
                            IconButton(onClick = { viewModel.markDone(event.id) }) {
                                Icon(Icons.Filled.Check, contentDescription = "划掉了")
                            }
                            IconButton(onClick = { viewModel.delete(event.id) }) {
                                Icon(Icons.Filled.Close, contentDescription = "收走")
                            }
                        }
                        val photos = event.photos?.let { parsePhotos(it) }.orEmpty()
                        if (photos.isNotEmpty()) {
                            PhotoStrip(photos)
                        }
                    }
                }
                if (showEdit) {
                    LiteEventEditDialog(
                        initialText = event.text,
                        initialNote = event.note.orEmpty(),
                        initialPhotos = event.photos,
                        onSave = { newText, newNote, newPhotos ->
                            viewModel.update(event.id, newText, newNote, newPhotos)
                            showEdit = false
                        },
                        onDismiss = { showEdit = false },
                        onRemovePhoto = { path -> viewModel.removePhoto(event.id, path) },
                    )
                }
            }
        }
    }
}

/** 已存照片的缩略图条（Coil 加载本机文件；点缩略图进编辑弹窗可删单张）。 */
@Composable
private fun PhotoStrip(photos: List<String>) {
    Row(
        Modifier.padding(top = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        photos.take(3).forEach { path ->
            val file = remember(path) { File(path) }
            if (file.isFile) {
                AsyncImage(
                    model = file,
                    contentDescription = "随手记照片",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.size(64.dp),
                )
            }
        }
        if (photos.size > 3) {
            Column(Modifier.size(64.dp), verticalArrangement = Arrangement.Center) {
                Text(
                    "+${photos.size - 3}",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

internal fun parsePhotos(json: String): List<String> = runCatching {
    com.google.gson.Gson().fromJson(
        json,
        object : com.google.gson.reflect.TypeToken<List<String>>() {}.type,
    ) as List<String>
}.getOrDefault(emptyList())

@Composable
internal fun LiteEventEditDialog(
    initialText: String,
    initialNote: String,
    initialPhotos: String?,
    onSave: (String, String?, String?) -> Unit,
    onDismiss: () -> Unit,
    onRemovePhoto: (String) -> Unit = {},
) {
    var text by remember { mutableStateOf(initialText) }
    var note by remember { mutableStateOf(initialNote) }
    var photos by remember { mutableStateOf(parsePhotos(initialPhotos.orEmpty())) }
    val context = LocalContext.current
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(9)) { uris ->
        if (uris.isNotEmpty()) {
            val newPaths = uris.mapNotNull { uri -> copyToLocal(context, uri) }
            photos = (photos + newPaths).distinct().take(9)
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("编辑这一条") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text("内容") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    label = { Text("相关信息（观后感、备注……）") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                )
                if (photos.isNotEmpty()) {
                    // 缩略图 + 单张删除：点 × 只从这一条里移除并删本机文件
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        photos.forEach { path ->
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Box(Modifier.size(56.dp)) {
                                    AsyncImage(
                                        model = File(path),
                                        contentDescription = "已选照片",
                                        contentScale = ContentScale.Crop,
                                        modifier = Modifier.size(56.dp),
                                    )
                                    Icon(
                                        Icons.Filled.Close,
                                        contentDescription = "移除这张照片",
                                        tint = MaterialTheme.colorScheme.error,
                                        modifier = Modifier
                                            .align(Alignment.TopEnd)
                                            .size(18.dp)
                                            .clickable {
                                                onRemovePhoto(path)
                                                photos = photos - path
                                            },
                                    )
                                }
                            }
                        }
                    }
                }
                Button(onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }) {
                    Text(if (photos.isEmpty()) "添加照片（最多 9 张）" else "再加照片（已选 ${photos.size}/9）")
                }
            }
        },
        // 保存按钮放大为整行宽（修复窄按钮易点空导致照片保存丢失）
        confirmButton = {
            Button(
                onClick = { onSave(text, note, if (photos.isEmpty()) null else com.google.gson.Gson().toJson(photos)) },
                enabled = text.isNotBlank() && text.length <= 200,
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            ) { Text("保存（含 ${photos.size} 张照片）") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

/**
 * 复制选中的图片到应用私有目录（#18）：按 ContentResolver 拿真实 MIME 定扩展名，
 * 不再一律存 .jpg；文件名用时间戳 + 随机后缀。
 */
private fun copyToLocal(context: android.content.Context, uri: android.net.Uri): String? = runCatching {
    val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
    val ext = when (mime) {
        "image/png" -> "png"
        "image/webp" -> "webp"
        "image/gif" -> "gif"
        "image/heic", "image/heif" -> "heic"
        else -> "jpg"
    }
    val dir = java.io.File(context.filesDir, "lite_photos").apply { mkdirs() }
    val name = "photo_${System.currentTimeMillis()}_${(0..9999).random()}.$ext"
    val out = java.io.File(dir, name)
    context.contentResolver.openInputStream(uri)?.use { input ->
        out.outputStream().use { input.copyTo(it) }
    }
    out.absolutePath
}.getOrNull()
