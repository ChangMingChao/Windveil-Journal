package com.windveil.journal.presentation.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import com.windveil.journal.data.local.db.MemoryEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MemoryPageViewModel @Inject constructor(
    private val repository: StandaloneRepository,
) : ViewModel() {
    val memory = MutableStateFlow<MemoryEntity?>(null)
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)

    fun load(memoryId: String) {
        viewModelScope.launch {
            repository.observeMemory(memoryId).collect { memory.value = it }
        }
    }

    fun save(memoryId: String, title: String?, cause: String?, process: String?, lastLine: String?) {
        viewModelScope.launch {
            repository.updateMemory(memoryId, title, cause, process, lastLine)
        }
    }

    /** S06 Step 16 → Step 19：收进书里。 */
    fun delete(memoryId: String, onDeleted: () -> Unit) {
        viewModelScope.launch {
            repository.deleteMemory(memoryId)
            onDeleted()
        }
    }

    /** 记忆页照片：新增（UI 侧已 copyToLocal 落盘）→ 追加去重，最多 9 张。 */
    fun addMemoryPhotos(memoryId: String, paths: List<String>) = viewModelScope.launch {
        if (paths.isEmpty()) return@launch
        val existing = parsePhotos(memory.value?.photos.orEmpty())
        repository.replaceMemoryPhotos(memoryId, (existing + paths).distinct().take(9))
    }

    fun removeMemoryPhoto(memoryId: String, path: String) = viewModelScope.launch {
        repository.removeMemoryPhoto(memoryId, path)
    }

    fun publish(memoryId: String, title: String?, cause: String?, process: String?, lastLine: String?, onPublished: () -> Unit = {}) {
        viewModelScope.launch {
            loading.value = true
            // 收进书里 = 保存编辑 + 发布（简化：去掉单独的保存按钮）
            repository.updateMemory(memoryId, title, cause, process, lastLine)
            runCatching { repository.publishMemory(memoryId) }
                .onSuccess { onPublished() }
                .onFailure { error.value = it.message }
            loading.value = false
        }
    }
}

/** S06：单页记忆 —— 全部区块可为空仍可发布。 */
@Composable
fun MemoryPageScreen(
    memoryId: String,
    onBack: () -> Unit,
    onPublished: () -> Unit = {},
    viewModel: MemoryPageViewModel = hiltViewModel(),
) {
    val memory by viewModel.memory.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()

    LaunchedEffect(memoryId) { viewModel.load(memoryId) }

    val current = memory
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) { Text("← 回到书架") }
        if (current == null) {
            if (loading) CircularProgressIndicator()
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        } else {
            Text(
                "${current.happenedFrom}${current.happenedTo?.let { " 至 $it" } ?: ""}",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            var title by remember(current.id, current.title) { mutableStateOf(current.title) }
            var cause by remember(current.id, current.cause) { mutableStateOf(current.cause.orEmpty()) }
            var process by remember(current.id, current.process) { mutableStateOf(current.process.orEmpty()) }
            var lastLine by remember(current.id, current.lastLine) { mutableStateOf(current.lastLine.orEmpty()) }

            OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("标题") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(value = cause, onValueChange = { cause = it }, label = { Text("起因") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            OutlinedTextField(
                value = process,
                onValueChange = { process = it },
                label = { Text("经过（若为空，会依据准备过程补一稿）") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
            )
            OutlinedTextField(value = lastLine, onValueChange = { lastLine = it }, label = { Text("最后一行") }, modifier = Modifier.fillMaxWidth())

            PhotosSection(memoryId = memoryId, viewModel = viewModel, current = current)

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                if (current.status == "draft") {
                    Button(onClick = { viewModel.publish(memoryId, title, cause, process, lastLine, onPublished) }) { Text("收进书里") }
                } else {
                    Text("已入册", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                }
                var confirmDelete by remember { mutableStateOf(false) }
                TextButton(onClick = { if (confirmDelete) viewModel.delete(memoryId, onBack) else confirmDelete = true }) {
                    Text(if (confirmDelete) "再点一次：删除这一页" else "删除", color = MaterialTheme.colorScheme.error)
                }
            }
            if (loading) CircularProgressIndicator(Modifier.padding(8.dp))
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}

/** 记忆页照片（DB v7，收进书里时从愿望继承）：草稿可增删，已入册只读展示。 */
@Composable
private fun PhotosSection(memoryId: String, viewModel: MemoryPageViewModel, current: MemoryEntity) {
    val context = LocalContext.current
    val photos = parsePhotos(current.photos.orEmpty())
    if (photos.isEmpty() && current.status != "draft") return
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(9)) { uris ->
        viewModel.addMemoryPhotos(memoryId, uris.mapNotNull { copyToLocal(context, it) })
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("照片", style = MaterialTheme.typography.titleSmall)
            PhotoGrid(
                photos,
                onRemove = if (current.status == "draft") {
                    { path -> viewModel.removeMemoryPhoto(memoryId, path) }
                } else null,
            )
            if (current.status == "draft" && photos.size < 9) {
                OutlinedButton(
                    onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                ) { Text(if (photos.isEmpty()) "添加照片" else "再加照片（${photos.size}/9）") }
            }
        }
    }
}
