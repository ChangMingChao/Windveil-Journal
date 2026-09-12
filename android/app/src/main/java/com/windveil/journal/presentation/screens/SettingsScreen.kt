package com.windveil.journal.presentation.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.local.LlmConfigStore
import com.windveil.journal.domain.CalendarReminder
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val llmConfigStore: LlmConfigStore,
    private val calendarReminder: CalendarReminder,
    private val exportService: com.windveil.journal.domain.ExportService,
    private val repository: com.windveil.journal.data.repository.StandaloneRepository,
) : ViewModel() {
    val llmConfig = MutableStateFlow<LlmConfig?>(null)
    val calendarGranted = MutableStateFlow(false)
    val exportPath = MutableStateFlow<String?>(null)
    val importResult = MutableStateFlow<String?>(null)
    val preferencesFlow = repository.observePreferences()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val savedFlag = MutableStateFlow(0) // 每次保存 +1，UI 据此弹「已保存」
    val error = MutableStateFlow<String?>(null)
    /** 导出/导入进行中：按钮置灰防重复触发（照片多时耗时明显）。 */
    val busy = MutableStateFlow(false)

    fun refresh(context: android.content.Context) {
        viewModelScope.launch { llmConfig.value = llmConfigStore.current() }
        calendarGranted.value = calendarReminder.hasPermission()
    }

    fun saveLlmConfig(baseUrl: String, apiKey: String, model: String) {
        viewModelScope.launch {
            runCatching {
                llmConfigStore.save(LlmConfig(baseUrl.trim(), apiKey.trim(), model.trim()))
            }.onSuccess {
                llmConfig.value = llmConfigStore.current()
                savedFlag.value = savedFlag.value + 1
            }.onFailure {
                error.value = it.message ?: "模型配置没保存上"
            }
        }
    }

    fun deletePreference(id: String) {
        viewModelScope.launch { repository.deletePreference(id) }
    }

    /** 刷新日历授权状态（权限请求回调 / 从系统设置返回时触发 refresh 亦可）。 */
    fun refreshCalendarGranted() {
        calendarGranted.value = calendarReminder.hasPermission()
    }

    fun export(context: android.content.Context, uri: android.net.Uri) {
        if (busy.value) return
        viewModelScope.launch {
            busy.value = true
            runCatching {
                exportService.exportToUri(uri)
                displayNameOf(context, uri)
            }
                .onSuccess { exportPath.value = "已导出：$it" }
                .onFailure { error.value = it.message ?: "导出失败" }
            busy.value = false
        }
    }

    /** 用户选择的保存位置的文件名（OpenableColumns），查不到就返回兜底文案。 */
    private fun displayNameOf(context: android.content.Context, uri: android.net.Uri): String =
        runCatching {
            context.contentResolver.query(
                uri,
                arrayOf(android.provider.OpenableColumns.DISPLAY_NAME),
                null, null, null,
            )?.use { if (it.moveToFirst()) it.getString(0) else null }
        }.getOrNull() ?: "备份文件"

    fun import(context: android.content.Context, uri: android.net.Uri) {
        if (busy.value) return
        viewModelScope.launch {
            busy.value = true
            runCatching { exportService.importFromUri(context, uri) }
                .onSuccess { (w, l, m) ->
                    importResult.value = "导入完成：愿望 $w、随手记 $l、记忆页 $m"
                }
                .onFailure { error.value = it.message ?: "导入失败" }
            busy.value = false
        }
    }

    fun clearError() {
        error.value = null
    }
}

/** 「我的」二级页路由。 */
private enum class SettingsSection { ROOT, HEART_MODEL, PROFILE, REMIND, DATA }

/** 「我的」主页：分类菜单（单机模式：无账号页、无邮件通道）。 */
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    var section by remember { mutableStateOf(SettingsSection.ROOT) }
    val llmConfig by viewModel.llmConfig.collectAsState()
    val calendarGranted by viewModel.calendarGranted.collectAsState()
    val context = LocalContext.current

    LaunchedEffect(Unit) { viewModel.refresh(context) }

    when (section) {
        SettingsSection.ROOT -> Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            TextButton(onClick = onBack) { Text("← 回到未发生之地") }
            Text("我的", style = MaterialTheme.typography.titleLarge)

            SettingsEntry(
                title = "心语与模型",
                subtitle = if (llmConfig?.usable == true) "模型已就绪" else "还没配置模型",
                onClick = { section = SettingsSection.HEART_MODEL },
            )
            SettingsEntry(
                title = "提醒（系统日历）",
                subtitle = if (calendarGranted) "已授权：时机写入系统日历提醒" else "未授权日历：只在打开应用时看到风来了",
                onClick = { section = SettingsSection.REMIND },
            )
            SettingsEntry(
                title = "数据",
                subtitle = "导出 JSON 备份",
                onClick = { section = SettingsSection.DATA },
            )
        }
        SettingsSection.HEART_MODEL -> SectionScaffold("心语与模型", onBackToRoot = { section = SettingsSection.ROOT }) {
            HeartModelSection(viewModel)
            ProfileEntryButton { section = SettingsSection.PROFILE }
        }
        SettingsSection.PROFILE -> SectionScaffold("用户画像", onBackToRoot = { section = SettingsSection.ROOT }) {
            ProfileSection(viewModel)
        }
        SettingsSection.REMIND -> SectionScaffold("提醒（系统日历）", onBackToRoot = { section = SettingsSection.ROOT }) {
            RemindSection(viewModel)
        }
        SettingsSection.DATA -> SectionScaffold("数据", onBackToRoot = { section = SettingsSection.ROOT }) {
            DataSection(viewModel, context)
        }
    }
}

@Composable
private fun SettingsEntry(title: String, subtitle: String, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

/** 二级页通用骨架。 */
@Composable
private fun SectionScaffold(title: String, onBackToRoot: () -> Unit, content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBackToRoot) { Text("← 我的") }
        Text(title, style = MaterialTheme.typography.titleLarge)
        content()
    }
}

/** 心语与模型：LLM 配置。 */
@Composable
private fun HeartModelSection(viewModel: SettingsViewModel) {
    val savedFlag by viewModel.savedFlag.collectAsState()
    val context = LocalContext.current
    LaunchedEffect(savedFlag) {
        if (savedFlag > 0) {
            android.widget.Toast.makeText(context, "已保存", android.widget.Toast.LENGTH_SHORT).show()
        }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("大模型配置（心语用）", style = MaterialTheme.typography.titleSmall)
            val cfgNow = viewModel.llmConfig.collectAsState().value
            var baseUrl by remember(cfgNow?.baseUrl) { mutableStateOf(cfgNow?.baseUrl.orEmpty()) }
            var apiKey by remember(cfgNow?.apiKey) { mutableStateOf(cfgNow?.apiKey.orEmpty()) }
            var model by remember(cfgNow?.model) { mutableStateOf(cfgNow?.model.orEmpty()) }
            OutlinedTextField(
                value = baseUrl,
                onValueChange = {
                    baseUrl = it
                    viewModel.clearError()
                },
                label = { Text("接口地址（如 https://api.xxx.com/v1）") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = apiKey,
                onValueChange = {
                    apiKey = it
                    viewModel.clearError()
                },
                label = { Text("API Key") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            )
            OutlinedTextField(
                value = model,
                onValueChange = {
                    model = it
                    viewModel.clearError()
                },
                label = { Text("模型名") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            )
            Button(
                onClick = { viewModel.saveLlmConfig(baseUrl, apiKey, model) },
                enabled = baseUrl.startsWith("https://") && apiKey.isNotBlank() && model.isNotBlank(),
                modifier = Modifier.padding(top = 8.dp),
            ) { Text("保存") }
            Text(
                "仅保存在这台设备上。心语与愿望理解、步骤生成、时机建议都直连它，不经任何服务端转发。",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
    val error by viewModel.error.collectAsState()
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}

/** 画像入口按钮（放在心语与模型页内）。 */
@Composable
private fun ProfileEntryButton(onClick: () -> Unit) {
    TextButton(onClick = onClick) { Text("查看/管理用户画像 →") }
}

/** 用户画像：条目列表，可删除（declared/inferred 都可删）。 */
@Composable
private fun ProfileSection(viewModel: SettingsViewModel) {
    val preferences by viewModel.preferencesFlow.collectAsState()

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("它从对话里提炼的你的偏好（仅存本机）", style = MaterialTheme.typography.titleSmall)
            if (preferences.isEmpty()) {
                Text(
                    "还没有画像条目。聊到的偏好（如「在减肥」「周末有空」）会自动记在这里，建议时会用上。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            preferences.forEach { item ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(item.value, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "${item.prefKey} · " + if (item.source == "declared") "你说过的" else "我猜的",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    TextButton(onClick = { viewModel.deletePreference(item.id) }) { Text("删掉") }
                }
            }
        }
    }
}

/** 提醒：系统日历授权引导。 */
@Composable
private fun RemindSection(viewModel: SettingsViewModel) {
    val granted by viewModel.calendarGranted.collectAsState()
    val permissionLauncher = rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        // 授权结果（允许/拒绝）都刷新状态；被永久拒绝时按钮仍在，点击会引导到系统设置
        viewModel.refreshCalendarGranted()
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("系统日历提醒", style = MaterialTheme.typography.titleSmall)
            Text(
                if (granted) "已授权：约定时机时会写入系统日历（「风起簿」日历），到点由系统提醒。"
                else "尚未授权日历权限。授权后，约定时机的事件会写入系统日历，到点由系统提醒；不授权也能用，只是提醒只在打开应用时看到。",
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = {
                    permissionLauncher.launch(
                        arrayOf(
                            android.Manifest.permission.READ_CALENDAR,
                            android.Manifest.permission.WRITE_CALENDAR,
                        )
                    )
                },
                enabled = !granted,
            ) { Text(if (granted) "已授权" else "授权日历权限") }
            Text(
                "邮件通道已按需求移除：提醒只走系统日历。",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** 数据：JSON 导出 + 导入。 */
@Composable
private fun DataSection(viewModel: SettingsViewModel, context: android.content.Context) {
    val exportPath by viewModel.exportPath.collectAsState()
    val importResult by viewModel.importResult.collectAsState()
    val error by viewModel.error.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val filePicker = rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.OpenDocument()
    ) { uri ->
        uri?.let { viewModel.import(context, it) }
    }
    val exportLauncher = rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        uri?.let { viewModel.export(context, it) }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("导出备份", style = MaterialTheme.typography.titleSmall)
            Text(
                "把全部愿望、随手记（含照片）、已发生之书导出为一个 JSON 文件。保存位置由你选择。",
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = {
                    val stamp = java.time.LocalDateTime.now()
                        .format(java.time.format.DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"))
                    exportLauncher.launch("windveil-backup-$stamp.json")
                },
                enabled = !busy,
            ) { Text(if (busy) "正在导出…" else "导出 JSON") }
            exportPath?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("导入备份", style = MaterialTheme.typography.titleSmall)
            Text(
                "选择之前导出的 JSON 文件。按 ID 合并：已有条目会被备份内容覆盖，不会删除现有数据。",
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = { filePicker.launch(arrayOf("application/json")) },
                enabled = !busy,
            ) { Text(if (busy) "正在导入…" else "选择 JSON 文件导入") }
            importResult?.let {
                Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}
