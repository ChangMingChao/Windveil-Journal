package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
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
    fun publish(memoryId: String) {
        viewModelScope.launch {
            loading.value = true
            runCatching { repository.publishMemory(memoryId) }
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

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Button(onClick = { viewModel.save(memoryId, title, cause, process, lastLine) }) { Text("保存") }
                if (current.status == "draft") {
                    Button(onClick = { viewModel.publish(memoryId) }) { Text("收进书里") }
                } else {
                    Text("已入册", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                }
            }
            if (loading) CircularProgressIndicator(Modifier.padding(8.dp))
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}
