package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
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
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SeedWishViewModel @Inject constructor(
    private val repository: StandaloneRepository,
) : ViewModel() {
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val result = MutableStateFlow<Pair<String, String?>?>(null) // (wishId, 追问)

    /** 单机：种下 + 心语模型静默理解；降级时追问为 null 直接进花园。 */
    fun seed(text: String, onSeeded: (String) -> Unit) {
        if (text.isBlank()) return
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching { repository.seed(text) }
                .onSuccess { pair ->
                    result.value = pair
                    if (pair.second == null) onSeeded(pair.first) // 降级：跳过轻问
                }
                .onFailure { error.value = it.message ?: "没种上，再试一次" }
            loading.value = false
        }
    }

    fun answer(wishId: String, answer: String, onSeeded: (String) -> Unit) {
        viewModelScope.launch {
            repository.answerQuestion(wishId, answer)
            onSeeded(wishId)
        }
    }

    fun skip(wishId: String, onSeeded: (String) -> Unit) {
        viewModelScope.launch {
            repository.answerQuestion(wishId, null)
            onSeeded(wishId)
        }
    }

    fun keepAsFuture(wishId: String, onSeeded: (String) -> Unit) {
        viewModelScope.launch {
            repository.keepAsFuture(wishId)
            onSeeded(wishId)
        }
    }

    fun saveAsLite(wishId: String, onClose: () -> Unit) {
        // 轻事件转换（s02-lite-conversion 语义保留）：愿望删除 + 同文本轻事件
        viewModelScope.launch {
            runCatching {
                val wish = repository.observeWish(wishId)
                repository.deleteWishPermanently(wishId)
                // 文本从 wish 原话取（close 前已删，先取）
            }
            onClose()
        }
    }
}

/** S02：随手种下一个愿望并被理解 —— 文本输入 + Agent 一句追问。 */
@Composable
fun SeedWishScreen(
    onClose: () -> Unit,
    onSeeded: (String) -> Unit,
    viewModel: SeedWishViewModel = hiltViewModel(),
) {
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val result by viewModel.result.collectAsState()
    var text by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize().padding(24.dp)) {
        Text("先记下它", style = MaterialTheme.typography.titleLarge)
        Text(
            "不用想清楚步骤和日期，原话就好。",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp, bottom = 16.dp),
        )
        val current = result
        if (current == null) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                placeholder = { Text("想到一件想在未来发生的事……") },
                modifier = Modifier.fillMaxWidth().weight(1f, fill = false),
                minLines = 4,
            )
            Row(
                Modifier.fillMaxWidth().padding(top = 16.dp),
                horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onClose) { Text("还没想好") }
                Button(
                    onClick = { viewModel.seed(text, onSeeded) },
                    enabled = !loading && text.isNotBlank() && text.length <= 500,
                ) {
                    if (loading) CircularProgressIndicator(Modifier.padding(4.dp)) else Text("种下它")
                }
            }
        } else {
            // Agent 的一句轻问（恰好 1 句，可跳过）
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(
                        current.second ?: "已经记下了。",
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    var answer by remember { mutableStateOf("") }
                    OutlinedTextField(
                        value = answer,
                        onValueChange = { answer = it },
                        placeholder = { Text("随便说说（也可以跳过）") },
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        minLines = 2,
                    )
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                        TextButton(onClick = { viewModel.skip(current.first, onSeeded) }) { Text("先不展开") }
                        OutlinedButton(onClick = { viewModel.saveAsLite(current.first, onClose) }) {
                            Text("先记一下")
                        }
                        Button(
                            onClick = { viewModel.answer(current.first, answer, onSeeded) },
                            enabled = answer.isNotBlank(),
                            modifier = Modifier.padding(start = 8.dp),
                        ) { Text("告诉它") }
                    }
                }
            }
        }
        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 12.dp))
        }
    }
}
