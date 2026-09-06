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
import com.windveil.journal.data.local.db.WishEntity
import com.windveil.journal.data.repository.StandaloneRepository
import com.windveil.journal.domain.AnalysisService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

@HiltViewModel
class WishDetailViewModel @Inject constructor(
    private val repository: StandaloneRepository,
) : ViewModel() {
    val wish = MutableStateFlow<WishEntity?>(null)
    val holidayNames = MutableStateFlow<List<String>>(emptyList())
    val holidaysAvailable = MutableStateFlow(true)
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val degradedNote = MutableStateFlow<String?>(null)
    val proposal = MutableStateFlow<AnalysisService.TimingDraft?>(null)

    fun loadHolidays() {
        holidayNames.value = repository.holidayNames()
        holidaysAvailable.value = repository.holidaysAvailable()
    }

    fun load(wishId: String) {
        viewModelScope.launch {
            repository.observeWish(wishId).collect { wish.value = it }
        }
    }

    fun setTiming(
        wishId: String,
        timingType: String,
        season: String? = null,
        monthDay: String? = null,
        afterMonths: Int? = null,
        holidays: List<String>? = null,
    ) {
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching { repository.setTiming(wishId, timingType, season, monthDay, afterMonths, holidays) }
                .onFailure { error.value = it.message ?: "这个时机我还没法记下来" }
            loading.value = false
        }
    }

    fun proposeTiming(wishId: String) {
        viewModelScope.launch {
            loading.value = true
            val draft = repository.proposeTiming(wishId)
            proposal.value = draft
            if (draft == null) degradedNote.value = "它暂时没想出来，你可以自己选一个时候。"
            loading.value = false
        }
    }

    fun confirmProposal(wishId: String) {
        viewModelScope.launch {
            proposal.value?.let { repository.applyTimingDraft(wishId, it) }
            proposal.value = null
        }
    }

    fun rejectProposal() {
        proposal.value = null
    }

    fun ready(wishId: String) = viewModelScope.launch { repository.markReady(wishId) }
    fun defer(wishId: String) = viewModelScope.launch { repository.defer(wishId) }
    fun letGo(wishId: String) = viewModelScope.launch { repository.letGo(wishId) }
    fun recall(wishId: String) = viewModelScope.launch { repository.recall(wishId) }

    fun deletePermanently(wishId: String, onDeleted: () -> Unit) = viewModelScope.launch {
        repository.deleteWishPermanently(wishId)
        onDeleted()
    }

    fun nextStep(wishId: String, rejectedStep: String? = null) = viewModelScope.launch {
        loading.value = true
        val step = repository.nextStep(wishId, rejectedStep)
        if (step == null) degradedNote.value = "它暂时没想出步骤，你说了算。"
        loading.value = false
    }

    fun stepDone(wishId: String) = viewModelScope.launch { repository.stepDone(wishId) }

    fun sendMessage(wishId: String, text: String) = viewModelScope.launch {
        val reply = repository.chat(wishId, text)
        if (reply == null) degradedNote.value = "它这会儿没说上话。"
    }

    fun markHappened(wishId: String, date: String, onOpenMemory: (String) -> Unit) = viewModelScope.launch {
        loading.value = true
        val memoryId = repository.markHappened(wishId, date)
        loading.value = false
        if (memoryId.isNotBlank()) onOpenMemory(memoryId)
    }
}

/** 愿望详情枢纽页（单机版）。 */
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
    LaunchedEffect(Unit) { viewModel.loadHolidays() }

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
            DetailBody(current, viewModel, proposal, degradedNote, error, loading, wishId, onBack, onOpenMemory)
        }
    }
}

@Composable
private fun DetailBody(
    current: WishEntity,
    viewModel: WishDetailViewModel,
    proposal: AnalysisService.TimingDraft?,
    degradedNote: String?,
    error: String?,
    loading: Boolean,
    wishId: String,
    onBack: () -> Unit,
    onOpenMemory: (String) -> Unit,
) {
    Text(current.title, style = MaterialTheme.typography.headlineSmall)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stateLabel(current.state), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
        Text(timingLabelOf(current), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelLarge)
    }
    current.originalText?.let {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("你的原话", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(it, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
    degradedNote?.let {
        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
    }

    TimingSection(wishId = wishId, viewModel = viewModel, proposal = proposal, timingLabel = timingLabelOf(current))
    StepSection(wishId = wishId, viewModel = viewModel, current = current)
    MessagesSection(wishId = wishId, viewModel = viewModel)
    TidySection(wishId = wishId, viewModel = viewModel, current = current, onOpenMemory = onOpenMemory, onBack = onBack)

    if (loading) CircularProgressIndicator(Modifier.padding(4.dp))
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun TimingSection(
    wishId: String,
    viewModel: WishDetailViewModel,
    proposal: AnalysisService.TimingDraft?,
    timingLabel: String,
) {
    val holidayNames by viewModel.holidayNames.collectAsState()
    val holidaysAvailable by viewModel.holidaysAvailable.collectAsState()

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("约定属于它的时机", style = MaterialTheme.typography.titleSmall)
            Text("现在是：$timingLabel", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            if (proposal != null) {
                Text(
                    proposal.reason ?: "它提议：${proposal.type} ${proposal.value ?: ""}",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { viewModel.confirmProposal(wishId) }) { Text("就这样定") }
                    OutlinedButton(onClick = { viewModel.rejectProposal() }) { Text("先不定") }
                }
            } else {
                Button(onClick = { viewModel.proposeTiming(wishId) }) { Text("让它提个时候") }
                Text(
                    "由你配置的心语模型分析；分析不出来时自己选。",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                if (holidaysAvailable && holidayNames.isNotEmpty()) {
                    Text(
                        "法定节假日（可多选）：",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    val selected = remember { mutableStateOf(setOf<String>()) }
                    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        holidayNames.forEach { name ->
                            val checked = name in selected.value
                            FilterChip(
                                selected = checked,
                                onClick = {
                                    selected.value = if (checked) selected.value - name else selected.value + name
                                },
                                label = { Text(name) },
                            )
                        }
                    }
                    Button(
                        onClick = { viewModel.setTiming(wishId, "holiday", holidays = selected.value.toList()) },
                        enabled = selected.value.isNotEmpty(),
                    ) { Text("就这样定") }
                }

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
                        onClick = { viewModel.setTiming(wishId, "month_day", monthDay = dateText.trim()) },
                        enabled = dateText.matches(Regex("\\d{4}-\\d{2}-\\d{2}")),
                        modifier = Modifier.padding(start = 8.dp),
                    ) { Text("定在这天") }
                }
            }
        }
    }
}

@Composable
private fun StepSection(wishId: String, viewModel: WishDetailViewModel, current: WishEntity) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("准备过程", style = MaterialTheme.typography.titleSmall)
            Button(onClick = { viewModel.nextStep(wishId) }) { Text("取下一个最小步骤") }
            if (current.state == "wind" || current.state == "going") {
                current.currentStep?.let { stepJson ->
                    val stepText = runCatching {
                        val map = com.google.gson.Gson().fromJson<Map<String, String>>(
                            stepJson,
                            object : com.google.gson.reflect.TypeToken<Map<String, String>>() {}.type,
                        )
                        map["text"]
                    }.getOrNull()
                    stepText?.let {
                        Text(it, style = MaterialTheme.typography.bodyLarge)
                        Button(onClick = { viewModel.stepDone(wishId) }) { Text("做完了") }
                    }
                }
            } else {
                Text(
                    "风到了就能开始拆解，也可以直接说「我好像准备好了」。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun MessagesSection(wishId: String, viewModel: WishDetailViewModel) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("和它聊聊", style = MaterialTheme.typography.titleSmall)
            var text by remember { mutableStateOf("") }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = { Text("想改、想推进、或者只是有点累……") },
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = { viewModel.sendMessage(wishId, text); text = "" },
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
    current: WishEntity,
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

            if (current.state == "let_go") {
                OutlinedButton(onClick = { viewModel.recall(wishId) }) { Text("重新种下") }
            } else {
                OutlinedButton(onClick = { viewModel.letGo(wishId) }) { Text("安静放下") }
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
