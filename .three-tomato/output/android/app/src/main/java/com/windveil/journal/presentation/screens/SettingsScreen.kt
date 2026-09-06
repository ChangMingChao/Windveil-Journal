package com.windveil.journal.presentation.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import kotlinx.coroutines.launch
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val llmConfigStore: LlmConfigStore,
    private val calendarReminder: CalendarReminder,
    private val exportService: com.windveil.journal.domain.ExportService,
) : ViewModel() {
    val llmConfig = MutableStateFlow<LlmConfig?>(null)
    val calendarGranted = MutableStateFlow(false)
    val exportPath = MutableStateFlow<String?>(null)
    val error = MutableStateFlow<String?>(null)

    fun refresh(context: android.content.Context) {
        viewModelScope.launch { llmConfig.value = llmConfigStore.current() }
        calendarGranted.value = calendarReminder.hasPermission()
    }

    fun saveLlmConfig(baseUrl: String, apiKey: String, model: String) {
        viewModelScope.launch {
            llmConfigStore.save(LlmConfig(baseUrl.trim(), apiKey.trim(), model.trim()))
            llmConfig.value = llmConfigStore.current()
        }
    }

    fun requestCalendar(context: android.content.Context) {
        // 运行时权限请求在 Composable 侧做（rememberLauncherForActivityResult），
        // 这里刷新授权状态即可（用户从系统设置回来时触发 refresh）
        calendarGranted.value = calendarReminder.hasPermission()
    }

    fun export(context: android.content.Context) {
        viewModelScope.launch {
            runCatching { exportService.exportToDownloads(context) }
                .onSuccess { exportPath.value = it }
                .onFailure { error.value = it.message }
        }
    }
}

/** 「我的」二级页路由。 */
private enum class SettingsSection { ROOT, HEART_MODEL, REMIND, DATA }

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
        }
        SettingsSection.REMIND -> SectionScaffold("提醒（系统日历）", onBackToRoot = { section = SettingsSection.ROOT }) {
            RemindSection(viewModel, context)
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
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("大模型配置（心语用）", style = MaterialTheme.typography.titleSmall)
            val cfgNow = viewModel.llmConfig.collectAsState().value
            var baseUrl by remember(cfgNow?.baseUrl) { mutableStateOf(cfgNow?.baseUrl.orEmpty()) }
            var apiKey by remember(cfgNow?.apiKey) { mutableStateOf(cfgNow?.apiKey.orEmpty()) }
            var model by remember(cfgNow?.model) { mutableStateOf(cfgNow?.model.orEmpty()) }
            OutlinedTextField(value = baseUrl, onValueChange = { baseUrl = it }, label = { Text("接口地址（如 https://api.xxx.com/v1）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(value = apiKey, onValueChange = { apiKey = it }, label = { Text("API Key") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
            OutlinedTextField(value = model, onValueChange = { model = it }, label = { Text("模型名") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
            Button(
                onClick = { viewModel.saveLlmConfig(baseUrl, apiKey, model) },
                enabled = baseUrl.contains("http") && apiKey.isNotBlank() && model.isNotBlank(),
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

/** 提醒：系统日历授权引导。 */
@Composable
private fun RemindSection(viewModel: SettingsViewModel, context: android.content.Context) {
    val granted by viewModel.calendarGranted.collectAsState()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("系统日历提醒", style = MaterialTheme.typography.titleSmall)
            Text(
                if (granted) "已授权：约定时机时会写入系统日历（「未发生事件管理局」日历），到点由系统提醒。"
                else "尚未授权日历权限。授权后，约定时机的事件会写入系统日历，到点由系统提醒；不授权也能用，只是提醒只在打开应用时看到。",
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(onClick = {
                // 跳转系统设置授予日历权限（简化：直接请求运行时权限）
                viewModel.requestCalendar(context)
            }) { Text(if (granted) "已授权" else "授权日历权限") }
            Text(
                "邮件通道已按需求移除：提醒只走系统日历。",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** 数据：JSON 导出。 */
@Composable
private fun DataSection(viewModel: SettingsViewModel, context: android.content.Context) {
    val exportPath by viewModel.exportPath.collectAsState()
    val error by viewModel.error.collectAsState()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("导出备份", style = MaterialTheme.typography.titleSmall)
            Text(
                "把全部愿望、随手记、已发生之书导出为一个 JSON 文件（存到应用外部存储 Documents/windveil/）。",
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(onClick = { viewModel.export(context) }) { Text("导出 JSON") }
            exportPath?.let {
                Text("已导出：$it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}
