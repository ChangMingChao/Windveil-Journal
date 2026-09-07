# -*- coding: utf-8 -*-
import io

p = 'F:/AI-learn/Windveil-Journal/.three-tomato/output/android/app/src/main/java/com/windveil/journal/presentation/screens/WishDetailScreen.kt'
t = io.open(p, encoding='utf-8').read()

old = '''@Composable
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
}'''

new = '''@Composable
private fun TimingSection(
    wishId: String,
    viewModel: WishDetailViewModel,
    proposal: AnalysisService.TimingDraft?,
    timingLabel: String,
) {
    val holidayNames by viewModel.holidayNames.collectAsState()
    val holidaysAvailable by viewModel.holidaysAvailable.collectAsState()

    // 定时机统一经「确认写日历」流程：先请求权限，再弹确认，用户同意才写日历
    var pending by remember { mutableStateOf<((Boolean) -> Unit)?>(null) }
    var showConfirm by remember { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        if (viewModel.hasCalendarPermission()) showConfirm = true
        else pending?.invoke(false) // 未授权 → 不写日历，仅应用内展示
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
                        onClick = { requestSet { wc -> viewModel.setTiming(wishId, "holiday", holidays = selected.value.toList(), writeCalendar = wc) } },
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
                        onClick = { requestSet { wc -> viewModel.setTiming(wishId, "month_day", monthDay = dateText.trim(), writeCalendar = wc) } },
                        enabled = dateText.matches(Regex("\\d{4}-\\d{2}-\\d{2}")),
                        modifier = Modifier.padding(start = 8.dp),
                    ) { Text("定在这天") }
                }
            }
        }
    }
}'''

assert old in t, 'TimingSection old not found'
t = t.replace(old, new)

t = t.replace('''    fun loadHolidays() {''', '''    fun hasCalendarPermission(): Boolean = repository.hasCalendarPermission()

    fun loadHolidays() {''')

io.open(p, 'w', encoding='utf-8', newline='\n').write(t)
print('calendar confirm flow wired')
