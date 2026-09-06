package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.windveil.journal.data.remote.HolidaysResponse
import com.windveil.journal.data.remote.MarkHappenedRequest
import com.windveil.journal.data.remote.TimingInput
import com.windveil.journal.data.remote.TimingProposal
import com.windveil.journal.data.remote.WishDetail
import com.windveil.journal.data.remote.WishMessage
import com.windveil.journal.data.remote.HolidaysApi
import com.windveil.journal.data.repository.MemoryRepository
import com.windveil.journal.data.repository.WishRepository
import com.windveil.journal.data.remote.bodyOrThrow
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

@HiltViewModel
class WishDetailViewModel @Inject constructor(
    private val wishRepository: WishRepository,
    private val memoryRepository: MemoryRepository,
    private val holidaysApi: HolidaysApi,
) : ViewModel() {
    val wish = MutableStateFlow<WishDetail?>(null)
    val holidayNames = MutableStateFlow<List<String>>(emptyList())
    val holidaysAvailable = MutableStateFlow(true)
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val degradedNote = MutableStateFlow<String?>(null)
    val memoryDraftId = MutableStateFlow<String?>(null)
    val proposal = MutableStateFlow<TimingProposal?>(null)

    /** 加载法定节假日枚举（自己选时机用，heart-voice-holiday-timing）。 */
    fun loadHolidays() {
        viewModelScope.launch {
            runCatching { holidaysApi.holidays().bodyOrThrow() }
                .onSuccess { res: HolidaysResponse ->
                    holidaysAvailable.value = res.available
                    holidayNames.value = res.names
                }
                .onFailure { holidaysAvailable.value = false }
        }
    }

    fun load(wishId: String) {
        viewModelScope.launch {
            loading.value = true
            runCatching { wishRepository.get(wishId) }
                .onSuccess {
                    wish.value = it
                    proposal.value = it.timingProposal
                }
                .onFailure { error.value = it.message }
            loading.value = false
        }
    }

    private fun <T> run(action: suspend () -> T, onSuccess: (T) -> Unit = {}) {
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching { action() }
                .onSuccess { onSuccess(it) }
                .onFailure { error.value = it.message ?: "没成功，再试一次" }
            loading.value = false
        }
    }

    /** S03：六选项手动约定时机；next_trigger_at 一律由服务端计算。 */
    fun setTiming(wishId: String, timing: TimingInput) = run({
        wishRepository.setTiming(wishId, timing)
    }) { wish.value = it }

    fun ready(wishId: String) = run({ wishRepository.markReady(wishId) }) { wish.value = it }
    fun defer(wishId: String) = run({ wishRepository.defer(wishId) }) { wish.value = it }
    fun pause(wishId: String) = run({ wishRepository.pauseReminders(wishId) }) { wish.value = it }
    fun backToBrewing(wishId: String) = run({ wishRepository.backToBrewing(wishId) }) { wish.value = it }
    fun letGo(wishId: String) = run({ wishRepository.letGo(wishId) }) { wish.value = it }
    fun recall(wishId: String) = run({ wishRepository.recall(wishId) }) { wish.value = it }

    fun deletePermanently(wishId: String, onDeleted: () -> Unit) = run({
        wishRepository.deletePermanently(wishId)
    }) { onDeleted() }

    /** S03 分支 P1 → P15：让 Agent 提个时候 → 采纳 / 先不定。 */
    fun proposeTiming(wishId: String) = run({ wishRepository.proposeTiming(wishId) }) { res ->
        proposal.value = res.proposal
        if (res.degraded) degradedNote.value = "它暂时没想出来，你可以自己选一个时候。"
    }

    fun confirmProposal(wishId: String) = run({
        val p = proposal.value?.id ?: return@run null
        wishRepository.confirmProposal(wishId, p)
    }) { res ->
        if (res != null) {
            wish.value = res.wish
            proposal.value = null
        }
    }

    fun rejectProposal(wishId: String) = run({
        val p = proposal.value?.id ?: return@run null
        wishRepository.rejectProposal(wishId, p)
    }) { res ->
        if (res != null) proposal.value = null
    }

    /** S04：最小下一步；带 rejected_step_id 即「换一个更小的」。 */
    fun nextStep(wishId: String, rejectedStepId: String? = null) = run({
        wishRepository.nextStep(wishId, rejectedStepId)
    }) { res ->
        if (res.step == null || res.degraded) {
            degradedNote.value = "它暂时没想出步骤，你说了算。"
        }
        load(wishId)
    }

    fun stepDone(wishId: String) = run({
        val step = wish.value?.currentStep ?: return@run null
        val version = wish.value?.version ?: return@run null
        wishRepository.markStepDone(wishId, step.id, version)
    }) { res ->
        if (res != null) wish.value = res.wish
    }

    fun sendMessage(wishId: String, text: String) = run({
        wishRepository.sendMessage(wishId, text)
    }) { res ->
        wish.value = res.wish
        if (res.degraded || res.reply == null) degradedNote.value = "它这会儿没说上话。"
    }

    /** S06 Step 3 → Step 10：它已经发生了（生成记忆页草稿）。 */
    fun markHappened(wishId: String, date: String, onOpenMemory: (String) -> Unit) = run({
        memoryRepository.markHappened(wishId, MarkHappenedRequest(happenedFrom = date))
    }) { res ->
        memoryDraftId.value = res.memory.id
        onOpenMemory(res.memory.id)
    }
}

/** S03/S04/S05/S07 的详情枢纽页。 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun WishDetailScreen(
    wishId: String,
    onBack: () -> Unit,
    onOpenMemory: (String) -> Unit = {},
    viewModel: WishDetailViewModel = hiltViewModel(),
) {
    val wish by viewModel.wish.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val degradedNote by viewModel.degradedNote.collectAsState()
    val proposal by viewModel.proposal.collectAsState()

    LaunchedEffect(wishId) { viewModel.load(wishId) }

    val current = wish
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) { Text("← 回到未发生之地") }
        if (current == null) {
            if (loading) CircularProgressIndicator()
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        } else {
        Text(current.title, style = MaterialTheme.typography.headlineSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stateLabel(current.state), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
            Text(current.timing.label, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelLarge)
        }
        current.originalText?.let {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("你的原话", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(it, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp))
                }
            }
        }
        current.understanding?.smallestStep?.let {
            Text("它猜的第一小步：$it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        degradedNote?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
        }

        // ---- 时机（S03）----
        TimingSection(
            wishId = wishId,
            viewModel = viewModel,
            proposal = proposal,
            timingLabel = current.timing.label,
        )

        // ---- 最小步骤（S04）----
        StepSection(wishId = wishId, viewModel = viewModel, current = current)

        // ---- 与它聊聊（S04 EX-23.1）----
        MessagesSection(wishId = wishId, viewModel = viewModel, messages = current.messages.orEmpty())

        // ---- 整理与放下（S05.2 / S07）----
        TidySection(wishId = wishId, viewModel = viewModel, current = current, onOpenMemory = onOpenMemory, onBack = onBack)

        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TimingSection(
    wishId: String,
    viewModel: WishDetailViewModel,
    proposal: TimingProposal?,
    timingLabel: String,
) {
    val holidayNames by viewModel.holidayNames.collectAsState()
    val holidaysAvailable by viewModel.holidaysAvailable.collectAsState()
    LaunchedEffect(Unit) { viewModel.loadHolidays() }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("约定属于它的时机", style = MaterialTheme.typography.titleSmall)
            Text("现在是：$timingLabel", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            if (proposal != null && proposal.status == "pending") {
                Text(
                    proposal.reason ?: "它提了一个时候：${proposal.timingValue ?: proposal.timingType}",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { viewModel.confirmProposal(wishId) }) { Text("就这样定") }
                    OutlinedButton(onClick = { viewModel.rejectProposal(wishId) }) { Text("先不定") }
                }
            } else {
                Button(onClick = { viewModel.proposeTiming(wishId) }) { Text("让它提个时候") }
                Text(
                    "需要后端配置可用的模型端点才能真正分析；分析不出来时会提示你自己选。",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                // ---- 自己选 ①：法定节假日（多选，服务端取最近一个）----
                if (holidaysAvailable && holidayNames.isNotEmpty()) {
                    Text(
                        "法定节假日（可多选）：",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    val selected = remember { mutableStateOf(setOf<String>()) }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        holidayNames.forEach { name ->
                            val checked = name in selected.value
                            FilterChip(
                                selected = checked,
                                onClick = {
                                    selected.value =
                                        if (checked) selected.value - name else selected.value + name
                                },
                                label = { Text(name) },
                            )
                        }
                    }
                    Button(
                        onClick = {
                            viewModel.setTiming(
                                wishId,
                                TimingInput(type = "holiday", holidays = selected.value.toList()),
                            )
                        },
                        enabled = selected.value.isNotEmpty(),
                    ) { Text("就这样定") }
                }

                // ---- 自己选 ②：具体年月日 ----
                var dateText by remember { mutableStateOf("") }
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = dateText,
                        onValueChange = { dateText = it },
                        label = { Text("具体年月日（YYYY-MM-DD）") },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                    )
                    Button(
                        onClick = {
                            viewModel.setTiming(wishId, TimingInput(type = "month_day", monthDay = dateText.trim()))
                        },
                        enabled = dateText.matches(Regex("\\d{4}-\\d{2}-\\d{2}")),
                        modifier = Modifier.padding(start = 8.dp),
                    ) { Text("定在这天") }
                }
            }
        }
    }
}

@Composable
private fun StepSection(wishId: String, viewModel: WishDetailViewModel, current: WishDetail) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("准备过程", style = MaterialTheme.typography.titleSmall)
            val step = current.currentStep
            if (step != null && step.status == "proposed") {
                Text(step.text, style = MaterialTheme.typography.bodyLarge)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { viewModel.stepDone(wishId) }) { Text("做完了") }
                    OutlinedButton(onClick = { viewModel.nextStep(wishId, rejectedStepId = step.id) }) {
                        Text("换一个更小的")
                    }
                }
            } else {
                OutlinedButton(onClick = { viewModel.nextStep(wishId) }, enabled = current.state == "wind" || current.state == "going") {
                    Text("取下一个最小步骤")
                }
                if (current.state == "seeded" || current.state == "brewing") {
                    Text(
                        "风到了就能开始拆解，也可以直接说「我好像准备好了」。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            current.timeline.orEmpty().takeLast(3).forEach { entry ->
                Text("· ${entry.text}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun MessagesSection(wishId: String, viewModel: WishDetailViewModel, messages: List<WishMessage>) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("和它聊聊", style = MaterialTheme.typography.titleSmall)
            messages.takeLast(4).forEach { m ->
                Text(
                    (if (m.role == "user") "你：" else "它：") + m.text,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (m.role == "user") MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
            var text by remember { mutableStateOf("") }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = { Text("想改、想推进、或者只是有点累……") },
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = {
                        viewModel.sendMessage(wishId, text)
                        text = ""
                    },
                    enabled = text.isNotBlank(),
                    modifier = Modifier.padding(start = 8.dp),
                ) { Text("说") }
            }
        }
    }
}

@Composable
private fun TidySection(
    wishId: String,
    viewModel: WishDetailViewModel,
    current: WishDetail,
    onOpenMemory: (String) -> Unit,
    onBack: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("记录与删除", style = MaterialTheme.typography.titleSmall)

            var showHappened by remember { mutableStateOf(false) }
            var date by remember { mutableStateOf(LocalDate.now().toString()) }
            Button(onClick = { showHappened = !showHappened }) { Text("它已经发生了") }
            if (showHappened) {
                OutlinedTextField(
                    value = date,
                    onValueChange = { date = it },
                    label = { Text("发生日期（YYYY-MM-DD）") },
                    singleLine = true,
                )
                Button(onClick = { viewModel.markHappened(wishId, date, onOpenMemory) }) { Text("写一页记忆") }
            }

            var confirmDelete by remember { mutableStateOf(false) }
            TextButton(
                onClick = { if (confirmDelete) viewModel.deletePermanently(wishId) { onBack() } else confirmDelete = true },
            ) {
                Text(if (confirmDelete) "再点一次：彻底删除，不可恢复" else "彻底删除")
            }
        }
    }
}
