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
import com.windveil.journal.data.remote.SeedWishResult
import com.windveil.journal.data.repository.LiteEventRepository
import com.windveil.journal.data.repository.WishRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SeedWishViewModel @Inject constructor(
    private val wishRepository: WishRepository,
    private val liteEventRepository: LiteEventRepository,
) : ViewModel() {
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val result = MutableStateFlow<SeedWishResult?>(null)
    val savedAsLite = MutableStateFlow(false)

    /** S02 Step 12 → Step 21：source=text 种下；degraded=true 时跳过轻问直接进花园。 */
    fun seed(text: String, onSeeded: (String) -> Unit) {
        if (text.isBlank()) return
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching { wishRepository.seed(com.windveil.journal.data.remote.SeedWishRequest(source = "text", text = text)) }
                .onSuccess { res ->
                    result.value = res
                    if (res.degraded) onSeeded(res.wish.id) // 降级：跳过轻问
                }
                .onFailure { error.value = it.message ?: "没种上，再试一次" }
            loading.value = false
        }
    }

    fun answer(wishId: String, answer: String, onSeeded: (String) -> Unit) {
        viewModelScope.launch {
            loading.value = true
            runCatching { wishRepository.answer(wishId, com.windveil.journal.data.remote.AnswerRequest(answer = answer)) }
                .onSuccess { onSeeded(wishId) }
                .onFailure { error.value = it.message }
            loading.value = false
        }
    }

    fun skip(wishId: String, onSeeded: (String) -> Unit) {
        viewModelScope.launch {
            runCatching { wishRepository.answer(wishId, com.windveil.journal.data.remote.AnswerRequest(skipped = true)) }
            onSeeded(wishId)
        }
    }

    /** S02 EX-18.2：把「当下日程」当作未来的事保留。 */
    fun keepAsFuture(wishId: String, onSeeded: (String) -> Unit) {
        viewModelScope.launch {
            runCatching { wishRepository.answer(wishId, com.windveil.journal.data.remote.AnswerRequest(action = "keep_as_future")) }
            onSeeded(wishId)
        }
    }

    /** S02 EX-18.2 / s02-lite-conversion：先记一下（转轻事件）。 */
    fun saveAsLite(wishId: String, onClose: () -> Unit) {
        viewModelScope.launch {
            runCatching { wishRepository.convertToLite(wishId) }
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
                        current.question ?: "已经记下了。",
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
                        TextButton(onClick = { viewModel.skip(current.wish.id, onSeeded) }) { Text("先不展开") }
                        if (current.actions.orEmpty().contains("keep_as_future")) {
                            TextButton(onClick = { viewModel.keepAsFuture(current.wish.id, onSeeded) }) {
                                Text("就当成未来的事")
                            }
                        }
                        if (current.actions.orEmpty().contains("save_as_lite")) {
                            OutlinedButton(onClick = { viewModel.saveAsLite(current.wish.id, onClose) }) {
                                Text("先记一下")
                            }
                        }
                        Button(
                            onClick = { viewModel.answer(current.wish.id, answer, onSeeded) },
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
