package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.AlertDialog
import android.Manifest
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
    val chatMessages = MutableStateFlow<List<com.windveil.journal.data.local.db.ChatMessageEntity>>(emptyList())
    val holidayNames = MutableStateFlow<List<String>>(emptyList())
    val holidaysAvailable = MutableStateFlow(true)
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val degradedNote = MutableStateFlow<String?>(null)
    val proposal = MutableStateFlow<AnalysisService.TimingDraft?>(null)

    fun hasCalendarPermission(): Boolean = repository.hasCalendarPermission()

    fun amend(wishId: String, title: String) {
        viewModelScope.launch { repository.amend(wishId, title, null) }
    }

    fun loadHolidays() {
        holidayNames.value = repository.holidayNames()
        holidaysAvailable.value = repository.holidaysAvailable()
    }

    fun load(wishId: String) {
        viewModelScope.launch {
            repository.observeWish(wishId).collect { wish.value = it }
        }
        // 对话历史与 Room 同步（发送/回应落盘后自动刷新）
        viewModelScope.launch {
            repository.observeChat(wishId).collect { chatMessages.value = it }
        }
    }

    fun setTiming(
        wishId: String,
        timingType: String,
        season: String? = null,
        monthDay: String? = null,
        afterMonths: Int? = null,
        holidays: List<String>? = null,
        writeCalendar: Boolean = true,
    ) {
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching { repository.setTiming(wishId, timingType, season, monthDay, afterMonths, holidays, writeCalendar) }
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
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text(current.title, style = MaterialTheme.typography.headlineSmall)
        var showEdit by remember { mutableStateOf(false) }
        TextButton(onClick = { showEdit = true }) { Text("改一改") }
        if (showEdit) {
            var newTitle by remember { mutableStateOf(current.title) }
            AlertDialog(
                onDismissRequest = { showEdit = false },
                title = { Text("改一改它") },
                text = {
                    OutlinedTextField(
                        value = newTitle,
                        onValueChange = { newTitle = it },
                        label = { Text("标题") },
                        singleLine = true,
                    )
                },
                confirmButton = {
                    Button(onClick = {
                        viewModel.amend(wishId, newTitle)
                        showEdit = false
                    }) { Text("保存") }
                },
                dismissButton = {
                    TextButton(onClick = { showEdit = false }) { Text("取消") }
                },
            )
        }
    }
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

    var pending by remember { mutableStateOf<((Boolean) -> Unit)?>(null) }
    var showConfirm by remember { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        if (viewModel.hasCalendarPermission()) showConfirm = true
        else pending?.invoke(false)
    }
    fun requestSet(action: (Boolean) -> Unit) {
        pending = action
        if (viewModel.hasCalendarPermission()) showConfirm = true
        else permissionLauncher.launch(
            arrayOf(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR)
        )
    }

    if (showConfirm && pending != null) {
        AlertDialog(
            onDismissRequest = { showConfirm = false },
            title = { Text("写进系统日历？") },
            text = { Text("把这件事的提醒写进系统日历，到点由系统提醒你；也可以只在这里看到它。") },
            confirmButton = {
                Button(onClick = {
                    showConfirm = false
                    pending?.invoke(true)
                    pending = null
                }) { Text("写进日历") }
            },
            dismissButton = {
                OutlinedButton(onClick = {
                    showConfirm = false
                    pending?.invoke(false)
                    pending = null
                }) { Text("只在应用里") }
            },
        )
    }

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
                        "法定节假日（下拉选择）：",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    var holidayExpanded by remember { mutableStateOf(false) }
                    var selectedHoliday by remember { mutableStateOf("") }
                    Box {
                        OutlinedButton(onClick = { holidayExpanded = true }) {
                            Text(selectedHoliday.ifBlank { "选一个节假日" })
                        }
                        androidx.compose.material3.DropdownMenu(
                            expanded = holidayExpanded,
                            onDismissRequest = { holidayExpanded = false },
                        ) {
                            holidayNames.forEach { name ->
                                androidx.compose.material3.DropdownMenuItem(
                                    text = { Text(name) },
                                    onClick = {
                                        selectedHoliday = name
                                        holidayExpanded = false
                                    },
                                )
                            }
                        }
                    }
                    Button(
                        onClick = { requestSet { wc -> viewModel.setTiming(wishId, "holiday", holidays = listOf(selectedHoliday), writeCalendar = wc) } },
                        enabled = selectedHoliday.isNotBlank(),
                    ) { Text("就这样定") }
                }

                // 具体日期：年 / 月 / 日 三个下拉
                var yearSel by remember { mutableStateOf("") }
                var monthSel by remember { mutableStateOf("") }
                var daySel by remember { mutableStateOf("") }
                val currentYear = java.time.LocalDate.now().year
                val years = (currentYear..(currentYear + 5)).map { it.toString() }
                val months = (1..12).map { "%02d".format(it) }
                val daysMax = if (monthSel.isNotBlank() && yearSel.isNotBlank()) {
                    java.time.YearMonth.of(yearSel.toInt(), monthSel.toInt()).lengthOfMonth()
                } else 31
                val days = (1..daysMax).map { "%02d".format(it) }

                Text("具体日期（下拉选择）：", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    SimpleDropdown(label = "年", options = years, selected = yearSel, onSelect = { yearSel = it; daySel = "" }, modifier = Modifier.weight(1.2f))
                    SimpleDropdown(label = "月", options = months, selected = monthSel, onSelect = { monthSel = it; daySel = "" }, modifier = Modifier.weight(1f))
                    SimpleDropdown(label = "日", options = days, selected = daySel, onSelect = { daySel = it }, modifier = Modifier.weight(1f))
                }
                Button(
                    onClick = { requestSet { wc -> viewModel.setTiming(wishId, "month_day", monthDay = "$yearSel-$monthSel-$daySel", writeCalendar = wc) } },
                    enabled = yearSel.isNotBlank() && monthSel.isNotBlank() && daySel.isNotBlank(),
                ) { Text("定在这天") }
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
    val messages by viewModel.chatMessages.collectAsState()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("和它聊聊", style = MaterialTheme.typography.titleSmall)
            if (messages.isNotEmpty()) {
                // 历史气泡：用户靠右，它靠左；Room 流驱动，落盘即显示
                Column(
                    Modifier.fillMaxWidth().padding(top = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    messages.forEach { msg ->
                        Column(
                            Modifier.fillMaxWidth(),
                            horizontalAlignment = if (msg.role == "user") androidx.compose.ui.Alignment.End else androidx.compose.ui.Alignment.Start,
                        ) {
                            Card(
                                colors = androidx.compose.material3.CardDefaults.cardColors(
                                    containerColor = if (msg.role == "user") MaterialTheme.colorScheme.primaryContainer
                                    else MaterialTheme.colorScheme.surfaceVariant,
                                )
                            ) {
                                Text(
                                    msg.text,
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                        }
                    }
                }
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


@Composable
private fun SimpleDropdown(
    label: String,
    options: List<String>,
    selected: String,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
            Text(selected.ifBlank { label }, maxLines = 1)
        }
        androidx.compose.material3.DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { opt ->
                androidx.compose.material3.DropdownMenuItem(
                    text = { Text(opt) },
                    onClick = { onSelect(opt); expanded = false },
                )
            }
        }
    }
}
