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
import com.windveil.journal.data.local.HeartVoiceHistoryEntry
import com.windveil.journal.data.local.HeartVoiceHistoryStore
import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.local.LlmConfigStore
import com.windveil.journal.data.remote.HeartVoiceClient
import com.windveil.journal.data.repository.StandaloneRepository
import com.windveil.journal.domain.LlmJson
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 心语两阶段设计（用户 2026-09-06 反馈）：
 * 阶段1 意图分类：用户在「提问求建议」还是在「陈述可记录的事实」？
 *   - 提问（如「明天中午吃什么」）→ 检索个人记忆，基于历史给建议（不记录）
 *   - 陈述（如「我想去吃自助」）→ 记为轻事件
 * 阶段2 记录或建议：提问时注入个人上下文（轻事件/愿望标题），模型引用记忆给出带排序的建议。
 */
private const val CLASSIFY_PROMPT = """你是「风起簿」的意图分类器。判断用户这条消息属于哪类：
- "ask"：在提问、征求建议（吃什么、做什么、去哪里、怎么选……）——用户想要基于他的历史记录的建议
- "record"：在陈述一个事实、计划、想去的地方、偏好或承诺——值得记下来供以后参考
- "chat"：纯闲聊或情绪抒发，与安排无关

只输出 JSON：{"intent":"ask 或 record 或 chat"}"""

private const val RECORD_PROMPT = """你是「风起簿」的心语助手。用户陈述了一件想记录的事，先判断它属于哪类：
- "wish"：未来想做的事、愿望、计划（想去滑雪、想去看海、想学画画）→ 记到「未发生之地」
- "lite"：当下的小事、随手记（今晚取快递、想吃自助）→ 记到「随手记」

只输出 JSON：
{"target":"wish 或 lite","title":"愿望标题 ≤30字（wish 时给，lite 时 null）","lite_event":"中性记录 ≤30字（lite 时给，wish 时 null）","reply":"给用户的一句话回应"}

语气温柔不评判，禁止出现「任务」「逾期」「未完成」等词。"""

private fun askPrompt(contextBlock: String) = """你是「风起簿」的心语助手。用户在征求建议，请基于他的个人记录回答。

用户的个人记录（轻事件=随手的记录，愿望=还没发生但想做的事）：
$contextBlock

回答要求：
- 用户画像（如有）是最强的排序依据：与画像冲突的选项靠后并说明原因（如画像有「在减肥」，自助类要排后），一致的优先
- 其次从记录里找依据建议（如记录过「想吃自助」就提示可以考虑），引用时说「你某天记过/你想过……」
- 记录之间有冲突（如既想「吃自助」又在「减肥」），温柔地都摆出来给排序与理由，不评判
- 记录为空或与当前问题无关时：理解用户其实想要「换个思路、新选择」，直接给出该话题下 3 个左右具体的常识性建议，不要说「没找到记录」
- 即使有记录，也可在合适时补 1 个记录之外的新想法，但必须标注「这是记录之外的新想法」，且把与记录相关的排在前面
- 语气温柔不催促，禁止出现「任务」「逾期」「未完成」等词
- 回答控制在 5 句以内
直接输出建议文本，不要 JSON。"""

data class HeartVoiceMessage(
    val role: String, // user | assistant
    val text: String,
    val recorded: String? = null,
)

@HiltViewModel
class HeartVoiceViewModel @Inject constructor(
    private val llmConfigStore: LlmConfigStore,
    private val heartVoiceClient: HeartVoiceClient,
    private val historyStore: HeartVoiceHistoryStore,
    private val repository: StandaloneRepository,
) : ViewModel() {
    val messages = MutableStateFlow<List<HeartVoiceMessage>>(emptyList())
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val config = MutableStateFlow<LlmConfig?>(null)
    private var sendJob: Job? = null

    init {
        viewModelScope.launch {
            config.value = llmConfigStore.current()
            // 恢复上次对话（杀进程不丢；只恢复普通气泡，不恢复「已记下」标记）
            messages.value = historyStore.load()
                .filter { it.role != null && it.text != null }
                .map { HeartVoiceMessage(it.role, it.text) }
        }
    }

    /** 每次进入重读配置（用户可能在「我的」页改过）。 */
    fun refreshConfig() {
        viewModelScope.launch { config.value = llmConfigStore.current() }
    }

    /** 用户主动停止本轮回答（取消网络协程；已入库的记录保留）。 */
    fun stop() {
        sendJob?.cancel()
        sendJob = null
        loading.value = false
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
        persist("user", trimmed)
        loading.value = true
        error.value = null
        val history = messages.value
            .takeLast(8)
            .map { HeartVoiceClient.Turn(it.role, it.text) }
            .filter { it.role == "user" || it.role == "assistant" }
        sendJob = viewModelScope.launch {
            // 阶段1：意图分类
            val intent = runCatching {
                val content = heartVoiceClient.chat(cfg, CLASSIFY_PROMPT, history)
                LlmJson.parse(content, IntentResult::class.java)?.intent
            }.onFailure { if (it is kotlinx.coroutines.CancellationException) throw it }
                .getOrNull() ?: "chat"

            when (intent) {
                "record" -> {
                    // 阶段2a：二分类记录（未来愿望 → 未发生之地；当下小事 → 随手记）
                    runCatching {
                        val content = heartVoiceClient.chat(cfg, RECORD_PROMPT, history)
                        val result = LlmJson.parse(content, RecordResult::class.java)
                        if (result == null) {
                            // 严格解析失败：不静默丢弃，降级展示原始回复
                            val raw = degradedReply(content)
                            messages.value = messages.value + HeartVoiceMessage("assistant", raw)
                            persist("assistant", raw)
                        } else {
                            val reply = result.reply ?: "嗯，我记下了。"
                            if (result.target == "wish" && !result.title.isNullOrBlank()) {
                                repository.seedWish(result.title.take(60), result.title.take(60))
                                val msg = "记到「未发生之地」了：${result.title}"
                                messages.value = messages.value + HeartVoiceMessage("assistant", msg, null)
                                persist("assistant", msg)
                            } else if (!result.liteEvent.isNullOrBlank()) {
                                var recorded: String? = null
                                runCatching { repository.createLiteEvent(result.liteEvent.take(200)) }
                                    .onSuccess { recorded = result.liteEvent }
                                messages.value = messages.value + HeartVoiceMessage("assistant", reply, recorded)
                                persist("assistant", reply)
                            } else {
                                messages.value = messages.value + HeartVoiceMessage("assistant", reply, null)
                                persist("assistant", reply)
                            }
                        }
                    }.onFailure { e ->
                        if (e is kotlinx.coroutines.CancellationException) throw e
                        messages.value = messages.value + HeartVoiceMessage("assistant", "这会儿没连上模型，等一下再试试。")
                        error.value = e.message
                    }
                }
                "ask" -> {
                    // 阶段2b：检索个人记忆（轻事件 + 愿望标题）作为上下文回答
                    val contextBlock = buildMemoryContext()
                    runCatching {
                        val reply = heartVoiceClient.chat(cfg, askPrompt(contextBlock), history)
                        messages.value = messages.value + HeartVoiceMessage("assistant", reply.trim())
                        persist("assistant", reply.trim())
                    }.onFailure { e ->
                        if (e is kotlinx.coroutines.CancellationException) throw e
                        messages.value = messages.value + HeartVoiceMessage("assistant", "这会儿没连上模型，等一下再试试。")
                        error.value = e.message
                    }
                }
                else -> {
                    // chat：温柔接话，不记录
                    runCatching {
                        val reply = heartVoiceClient.chat(
                            cfg,
                            "你是「风起簿」的温柔陪伴者。用户在闲聊或抒发情绪，温柔回应 1-2 句，不评判不催促。直接输出回应文本。",
                            history,
                        )
                        messages.value = messages.value + HeartVoiceMessage("assistant", reply.trim())
                        persist("assistant", reply.trim())
                    }.onFailure { e ->
                        if (e is kotlinx.coroutines.CancellationException) throw e
                        messages.value = messages.value + HeartVoiceMessage("assistant", "这会儿没连上模型，等一下再试试。")
                        error.value = e.message
                    }
                }
            }
            // 先解锁输入区，再静默提炼画像（user-profile）：提炼不再锁住「说」按钮；
            // 失败跳过；用户点「停」时随 sendJob 一起取消
            loading.value = false
            if (intent != "chat") {
                runCatching { repository.extractAndStorePreferences(trimmed) }
            }
        }
    }

    /** 解析失败时的降级兜底：把原始回复剥壳后尽量以文本展示，不静默丢弃。 */
    private fun degradedReply(raw: String): String = raw.trim().ifBlank { LlmJson.DEGRADED_REPLY }

    /** 对话历史落盘（fire-and-forget：失败不打扰用户）。 */
    private fun persist(role: String, text: String) {
        viewModelScope.launch { runCatching { historyStore.append(role, text) } }
    }

    /** 个人记忆上下文：画像条目 + open 轻事件（最近 20 条）+ 未完成愿望标题（最近 20 条）。 */
    private suspend fun buildMemoryContext(): String {
        val sb = StringBuilder()
        val profileBlock = repository.preferencesBlock()
        if (profileBlock.isNotBlank() && !profileBlock.contains("还没有")) {
            sb.appendLine("【用户画像】")
            sb.appendLine(profileBlock)
            sb.appendLine()
        }
        val liteEvents = repository.observeOpenLiteEvents().first()
        if (liteEvents.isNotEmpty()) {
            sb.appendLine("【随手记】")
            liteEvents.take(20).forEach { sb.appendLine("- ${it.text}") }
        }
        val wishes = repository.observeGarden().first()
            .filter { it.state != "let_go" }
        if (wishes.isNotEmpty()) {
            sb.appendLine("【愿望】")
            wishes.take(20).forEach { sb.appendLine("- ${it.title}") }
        }
        if (sb.isEmpty()) sb.append("（还没有任何记录）")
        return sb.toString()
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
                        Text(msg.text.orEmpty(), modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodyMedium)
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
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.padding(8.dp))
                    }
                }
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
                if (loading) {
                    // 模型回答中：给用户可取消的停止入口（#10）
                    Button(
                        onClick = { viewModel.stop() },
                        modifier = Modifier.padding(start = 8.dp),
                    ) { Text("停") }
                } else {
                    Button(
                        onClick = {
                            viewModel.send(input)
                            input = ""
                        },
                        enabled = input.isNotBlank(),
                        modifier = Modifier.padding(start = 8.dp),
                    ) { Text("说") }
                }
            }
        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

private data class IntentResult(val intent: String = "chat")

/** record 二分类结果。 */
private data class RecordResult(
    val target: String = "lite", // wish | lite
    val title: String? = null,
    @com.google.gson.annotations.SerializedName("lite_event") val liteEvent: String? = null,
    val reply: String? = null,
)

/** 心语 JSON 结果（模型返回）。 */
data class HeartVoiceResult(
    val reply: String? = null,
    val useful: Boolean = false,
    @com.google.gson.annotations.SerializedName("lite_event") val liteEvent: String? = null,
)
