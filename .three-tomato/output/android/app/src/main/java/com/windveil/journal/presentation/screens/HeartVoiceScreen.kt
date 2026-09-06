package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
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
import com.google.gson.Gson
import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.local.LlmConfigStore
import com.windveil.journal.data.remote.HeartVoiceClient
import com.windveil.journal.data.remote.HeartVoiceResult
import com.windveil.journal.data.repository.LiteEventRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** 心语系统提示词：识别「对未来安排有用的事实」，无关不记。 */
private const val SYSTEM_PROMPT = """你是「未发生事件管理局」的心语助手。这个应用帮用户保存那些还没发生、但值得被认真对待的事。
你的任务：分析用户这条消息，判断是否包含对未来安排有用的事实（时间安排、计划、想去的地方、想做的事、偏好、承诺等）。
- 有用：lite_event 用一句不超过 30 字的中性记录概括（例如用户说「我明天做点什么好呢」，隐含明天有空，可记为「明天可能有空」）。
- 无关（闲聊、情绪抒发、与未来安排无关）：useful=false，lite_event 给 null。
- 语气温柔，不催促，不评判。禁止出现「任务」「逾期」「未完成」等词。
只输出 JSON，不要输出其他内容：{"reply":"给你的回应（1-2 句）","useful":true/false,"lite_event":"记录内容或 null"}"""

data class HeartVoiceMessage(
    val role: String, // user | assistant
    val text: String,
    val recorded: String? = null, // 本条自动记下的轻事件
)

@HiltViewModel
class HeartVoiceViewModel @Inject constructor(
    private val llmConfigStore: LlmConfigStore,
    private val heartVoiceClient: HeartVoiceClient,
    private val liteEventRepository: LiteEventRepository,
) : ViewModel() {
    val messages = MutableStateFlow<List<HeartVoiceMessage>>(emptyList())
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val config = MutableStateFlow<LlmConfig?>(null)

    init {
        viewModelScope.launch { config.value = llmConfigStore.current() }
    }

    fun refreshConfig() {
        viewModelScope.launch { config.value = llmConfigStore.current() }
    }

    fun send(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty() || loading.value) return
        val cfg = config.value
        if (cfg == null || !cfg.usable) {
            error.value = "先到「我的」页配置大模型（地址、API Key、模型名），心语才能开始。"
            return
        }
        messages.value = messages.value + HeartVoiceMessage("user", trimmed)
        loading.value = true
        error.value = null
        viewModelScope.launch {
            runCatching {
                val history = messages.value.map { HeartVoiceClient.Turn(it.role, it.text) }
                val content = heartVoiceClient.chat(cfg, SYSTEM_PROMPT, history)
                val cleaned = content.trim().removePrefix("```json").removePrefix("```").removeSuffix("```").trim()
                Gson().fromJson(cleaned, HeartVoiceResult::class.java)
            }.onSuccess { result ->
                var recorded: String? = null
                if (result.useful && !result.liteEvent.isNullOrBlank()) {
                    // 有用信息自动记为轻事件（纯记录，无提醒路径）
                    runCatching { liteEventRepository.create(result.liteEvent.take(200)) }
                        .onSuccess { recorded = result.liteEvent }
                }
                messages.value = messages.value + HeartVoiceMessage(
                    role = "assistant",
                    text = result.reply ?: "嗯，我听到了。",
                    recorded = recorded,
                )
            }.onFailure { e ->
                messages.value = messages.value + HeartVoiceMessage("assistant", "这会儿没连上模型，等一下再试试。")
                error.value = e.message
            }
            loading.value = false
        }
    }
}

/** 心语：调用大模型的聊天框，负责接收用户输入并分析有用信息。 */
@Composable
fun HeartVoiceScreen(viewModel: HeartVoiceViewModel = hiltViewModel()) {
    val messages by viewModel.messages.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val config by viewModel.config.collectAsState()
    var input by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    // 每次进入心语页都重读配置（用户可能在「我的」页刚改过 url/key/model）
    LaunchedEffect(Unit) { viewModel.refreshConfig() }
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("心语", style = MaterialTheme.typography.titleLarge)
        Text(
            "想到什么就说说。我会记下对未来有用的事，无关的不记。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
        )
        if (config == null || !config!!.usable) {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Text(
                    "还没有配置大模型。到「我的」页填好地址、API Key 和模型名，心语就能开始。",
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).padding(top = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(messages) { msg ->
                Column(
                    Modifier.fillMaxWidth(),
                    horizontalAlignment = if (msg.role == "user") Alignment.End else Alignment.Start,
                ) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = if (msg.role == "user") MaterialTheme.colorScheme.primaryContainer
                            else MaterialTheme.colorScheme.surfaceVariant,
                        )
                    ) {
                        Text(msg.text, modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodyMedium)
                    }
                    if (msg.recorded != null) {
                        AssistChip(
                            onClick = {},
                            label = { Text("已记下：${msg.recorded}") },
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                }
            }
            if (loading) {
                item { CircularProgressIndicator(Modifier.padding(8.dp)) }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                placeholder = { Text("说说你的想法……") },
                modifier = Modifier.weight(1f),
                maxLines = 3,
            )
            Button(
                onClick = {
                    viewModel.send(input)
                    input = ""
                },
                enabled = input.isNotBlank() && !loading,
                modifier = Modifier.padding(start = 8.dp),
            ) { Text("说") }
        }
        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
        }
    }
}
