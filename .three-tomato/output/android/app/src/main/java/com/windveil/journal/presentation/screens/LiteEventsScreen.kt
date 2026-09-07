package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Check
import androidx.compose.foundation.clickable
import androidx.compose.material3.AlertDialog
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.windveil.journal.data.local.db.LiteEventEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

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
                    Row(
                        Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f).clickable { showEdit = true }) {
                            Text(event.text, style = MaterialTheme.typography.bodyMedium)
                            event.note?.let {
                                Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
                            }
                            val photos = event.photos?.let { parsePhotos(it) }.orEmpty()
                            if (photos.isNotEmpty()) {
                                Text("已附 ${photos.size} 张照片", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
                            }
                        }
                        IconButton(onClick = { viewModel.markDone(event.id) }) {
                            Icon(Icons.Filled.Check, contentDescription = "划掉了")
                        }
                        IconButton(onClick = { viewModel.delete(event.id) }) {
                            Icon(Icons.Filled.Close, contentDescription = "收走")
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
                    )
                }
            }
        }
    }
}


private fun parsePhotos(json: String): List<String> = runCatching {
    com.google.gson.Gson().fromJson(
        json,
        object : com.google.gson.reflect.TypeToken<List<String>>() {}.type,
    ) as List<String>
}.getOrDefault(emptyList())

@Composable
private fun LiteEventEditDialog(
    initialText: String,
    initialNote: String,
    initialPhotos: String?,
    onSave: (String, String?, String?) -> Unit,
    onDismiss: () -> Unit,
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
                Button(onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }) {
                    Text(if (photos.isEmpty()) "添加照片（最多 9 张）" else "再加照片（已选 ${photos.size}/9）")
                }
                if (photos.isNotEmpty()) {
                    Text("已选 ${photos.size} 张照片（存本机）", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onSave(text, note, if (photos.isEmpty()) null else com.google.gson.Gson().toJson(photos)) },
                enabled = text.isNotBlank() && text.length <= 200,
            ) { Text("保存") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

private fun copyToLocal(context: android.content.Context, uri: android.net.Uri): String? = runCatching {
    val dir = java.io.File(context.filesDir, "lite_photos").apply { mkdirs() }
    val name = "photo_${System.currentTimeMillis()}_${(0..9999).random()}.jpg"
    val out = java.io.File(dir, name)
    context.contentResolver.openInputStream(uri)?.use { input ->
        out.outputStream().use { input.copyTo(it) }
    }
    out.absolutePath
}.getOrNull()
