package com.windveil.journal.presentation.screens

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
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.windveil.journal.data.local.LlmConfig
import com.windveil.journal.data.local.LlmConfigStore
import com.windveil.journal.data.remote.AvailabilityCreateRequest
import com.windveil.journal.data.remote.AvailabilityWindow
import com.windveil.journal.data.remote.PreferenceItem
import com.windveil.journal.data.remote.UserProfile
import com.windveil.journal.data.repository.AuthRepository
import com.windveil.journal.data.repository.PreferenceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val preferenceRepository: PreferenceRepository,
    private val llmConfigStore: LlmConfigStore,
) : ViewModel() {
    val profile = MutableStateFlow<UserProfile?>(null)
    val preferences = MutableStateFlow<List<PreferenceItem>>(emptyList())
    val digest = MutableStateFlow<PreferenceItem?>(null)
    val availability = MutableStateFlow<List<AvailabilityWindow>>(emptyList())
    val llmConfig = MutableStateFlow<LlmConfig?>(null)
    val error = MutableStateFlow<String?>(null)

    fun refresh() {
        viewModelScope.launch {
            llmConfig.value = llmConfigStore.current()
            runCatching { authRepository.getMe() }.onSuccess { profile.value = it }
            runCatching { preferenceRepository.list() }.onSuccess {
                preferences.value = it.items.filter { item -> item.kind == "entry" && item.revokedAt == null }
                digest.value = it.digest
            }
            runCatching { preferenceRepository.availability() }.onSuccess { availability.value = it.items }
        }
    }

    fun linkEmail(email: String, password: String) {
        viewModelScope.launch {
            runCatching { authRepository.linkEmail(email, password) }
                .onSuccess { profile.value = it }
                .onFailure { error.value = it.message }
        }
    }

    fun toggleChannels(push: Boolean?, email: Boolean?) {
        viewModelScope.launch {
            runCatching { authRepository.updateChannels(push, email) }
                .onSuccess {
                    profile.value = profile.value?.copy(
                        pushEnabled = it.pushEnabled,
                        emailEnabled = it.emailEnabled,
                    )
                }
                .onFailure { error.value = it.message }
        }
    }

    fun revokePreference(prefId: String) {
        viewModelScope.launch {
            runCatching { preferenceRepository.revoke(prefId) }
                .onSuccess { refresh() }
                .onFailure { error.value = it.message }
        }
    }

    fun deletePreference(prefId: String) {
        viewModelScope.launch {
            runCatching { preferenceRepository.delete(prefId) }
                .onSuccess { refresh() }
                .onFailure { error.value = it.message }
        }
    }

    fun addAvailability(weekday: Int, startMinute: Int, endMinute: Int, note: String?) {
        viewModelScope.launch {
            runCatching {
                preferenceRepository.addAvailability(
                    AvailabilityCreateRequest(weekday, startMinute, endMinute, note?.ifBlank { null })
                )
            }.onSuccess { refresh() }
                .onFailure { error.value = it.message }
        }
    }

    fun deleteAvailability(windowId: String) {
        viewModelScope.launch {
            runCatching { preferenceRepository.deleteAvailability(windowId) }
                .onSuccess { refresh() }
                .onFailure { error.value = it.message }
        }
    }

    fun saveLlmConfig(baseUrl: String, apiKey: String, model: String) {
        viewModelScope.launch {
            llmConfigStore.save(LlmConfig(baseUrl.trim(), apiKey.trim(), model.trim()))
            llmConfig.value = llmConfigStore.current()
        }
    }

    fun logout(onLoggedOut: () -> Unit) {
        viewModelScope.launch {
            authRepository.logout()
            onLoggedOut()
        }
    }
}

/** 「我的」二级页路由（heart-voice-holiday-timing 追加：二级化）。 */
private enum class SettingsSection { ROOT, HEART_MODEL, MEMORY, REMIND, ACCOUNT }

/** 「我的」主页：分类菜单，内容收入四个二级页。 */
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    var section by remember { mutableStateOf(SettingsSection.ROOT) }
    val profile by viewModel.profile.collectAsState()
    val llmConfig by viewModel.llmConfig.collectAsState()
    val preferences by viewModel.preferences.collectAsState()

    LaunchedEffect(Unit) { viewModel.refresh() }

    when (section) {
        SettingsSection.ROOT -> SettingsRootScreen(
            onBack = onBack,
            profile = profile,
            llmReady = llmConfig?.usable == true,
            preferenceCount = preferences.size,
            onOpen = { section = it },
        )
        SettingsSection.HEART_MODEL -> SectionScaffold("心语与模型", onBackToRoot = { section = SettingsSection.ROOT }) {
            HeartModelSection(viewModel)
        }
        SettingsSection.MEMORY -> SectionScaffold("它记得我什么", onBackToRoot = { section = SettingsSection.ROOT }) {
            MemorySection(viewModel)
        }
        SettingsSection.REMIND -> SectionScaffold("提醒", onBackToRoot = { section = SettingsSection.ROOT }) {
            RemindSection(viewModel)
        }
        SettingsSection.ACCOUNT -> SectionScaffold("账号", onBackToRoot = { section = SettingsSection.ROOT }) {
            AccountSection(viewModel, onLoggedOut)
        }
    }
}

@Composable
private fun SettingsRootScreen(
    onBack: () -> Unit,
    profile: UserProfile?,
    llmReady: Boolean,
    preferenceCount: Int,
    onOpen: (SettingsSection) -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        TextButton(onClick = onBack) { Text("← 回到未发生之地") }
        Text("我的", style = MaterialTheme.typography.titleLarge)

        SettingsEntry(
            title = "心语与模型",
            subtitle = if (llmReady) "模型已就绪" else "还没配置模型",
            onClick = { onOpen(SettingsSection.HEART_MODEL) },
        )
        SettingsEntry(
            title = "它记得我什么",
            subtitle = if (preferenceCount > 0) "$preferenceCount 条记录" else "还没有记住什么",
            onClick = { onOpen(SettingsSection.MEMORY) },
        )
        SettingsEntry(
            title = "提醒",
            subtitle = remindSummary(profile),
            onClick = { onOpen(SettingsSection.REMIND) },
        )
        SettingsEntry(
            title = "账号",
            subtitle = if (profile?.isAnonymous == false) "已绑定：${profile.email}" else "匿名空间（换设备前记得绑定邮箱）",
            onClick = { onOpen(SettingsSection.ACCOUNT) },
        )
    }
}

private fun remindSummary(profile: UserProfile?): String = when {
    profile == null -> "加载中…"
    profile.pushEnabled && profile.emailEnabled -> "推送 + 邮件"
    profile.pushEnabled -> "仅推送"
    profile.emailEnabled -> "仅邮件"
    else -> "完全安静"
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

// ---------------- 二级页内容（既有卡片按类归位） ----------------

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
                "仅保存在这台设备上，心语直接连接它，不经服务端转发。",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
    val error by viewModel.error.collectAsState()
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}

/** 它记得我什么：我的理解 + 偏好条目 + 什么时候有空（S08）。 */
@Composable
private fun MemorySection(viewModel: SettingsViewModel) {
    val digest by viewModel.digest.collectAsState()
    val preferences by viewModel.preferences.collectAsState()
    val availability by viewModel.availability.collectAsState()
    val error by viewModel.error.collectAsState()

    digest?.let {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("我的理解", style = MaterialTheme.typography.titleSmall)
                Text(it.value, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp))
                TextButton(onClick = { viewModel.deletePreference(it.id) }) { Text("删掉这句理解") }
            }
        }
    }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("条目", style = MaterialTheme.typography.titleSmall)
            if (preferences.isEmpty()) {
                Text("还没有记住什么。", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            }
            preferences.forEach { item ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(item.value, style = MaterialTheme.typography.bodyMedium)
                        val sourceLabel = if (item.source == "declared") "你说过的" else "我猜的"
                        Text(
                            sourceLabel + (item.confidence?.takeIf { item.source == "inferred" }?.let { c -> if (c >= 70) "（比较确定）" else "（大概猜的）" } ?: ""),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (item.source == "inferred") {
                        TextButton(onClick = { viewModel.revokePreference(item.id) }) { Text("猜错了") }
                    } else {
                        TextButton(onClick = { viewModel.deletePreference(item.id) }) { Text("删掉") }
                    }
                }
            }
        }
    }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("什么时候有空", style = MaterialTheme.typography.titleSmall)
            val weekdays = listOf("周一", "周二", "周三", "周四", "周五", "周六", "周日")
            availability.forEach { w ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    val hhmm = { m: Int -> "%02d:%02d".format(m / 60, m % 60) }
                    Text(
                        "${weekdays[w.weekday]} ${hhmm(w.startMinute)}–${hhmm(w.endMinute)}" + (w.note?.let { " · $it" } ?: ""),
                        Modifier.weight(1f),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    TextButton(onClick = { viewModel.deleteAvailability(w.id) }) { Text("删掉") }
                }
            }
            var weekday by remember { mutableStateOf(5) }
            var start by remember { mutableStateOf("09:00") }
            var end by remember { mutableStateOf("12:00") }
            var note by remember { mutableStateOf("") }
            Text("新增一个时段：", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = weekdays[weekday],
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("周几") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                )
                Button(
                    onClick = { weekday = (weekday + 1) % 7 },
                    modifier = Modifier.padding(start = 4.dp),
                ) { Text("换一天") }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(value = start, onValueChange = { start = it }, label = { Text("开始 HH:MM") }, singleLine = true, modifier = Modifier.weight(1f))
                OutlinedTextField(
                    value = end,
                    onValueChange = { end = it },
                    label = { Text("结束 HH:MM") },
                    singleLine = true,
                    modifier = Modifier.weight(1f).padding(start = 4.dp),
                )
            }
            OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("备注（可选，如「带孩子出门前」）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Button(
                onClick = {
                    val toMinutes = { s: String ->
                        val parts = s.split(":")
                        if (parts.size == 2) parts[0].toIntOrNull()?.times(60)?.plus(parts[1].toIntOrNull() ?: 0) else null
                    }
                    val sm = toMinutes(start)
                    val em = toMinutes(end)
                    if (sm != null && em != null && em > sm) {
                        viewModel.addAvailability(weekday, sm, em, note)
                    }
                }
            ) { Text("保存时段") }
        }
    }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}

/** 提醒：通道开关（S10）。 */
@Composable
private fun RemindSection(viewModel: SettingsViewModel) {
    val profile by viewModel.profile.collectAsState()
    val error by viewModel.error.collectAsState()
    val p = profile
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("提醒通道", style = MaterialTheme.typography.titleSmall)
            Row(
                Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("推送", style = MaterialTheme.typography.bodyMedium)
                Switch(checked = p?.pushEnabled ?: false, onCheckedChange = { viewModel.toggleChannels(it, null) })
            }
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("邮件", style = MaterialTheme.typography.bodyMedium)
                Switch(checked = p?.emailEnabled ?: false, onCheckedChange = { viewModel.toggleChannels(null, it) })
            }
            Text(
                "两个都关就是完全安静，已确认的时机不会丢，重开会继续。",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}

/** 账号：邮箱绑定 + 登出。 */
@Composable
private fun AccountSection(viewModel: SettingsViewModel, onLoggedOut: () -> Unit) {
    val profile by viewModel.profile.collectAsState()
    val error by viewModel.error.collectAsState()
    val p = profile
    if (p == null) {
        Text("加载中…", color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    if (p.isAnonymous) {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("绑定邮箱（换设备后才能找回愿望）", style = MaterialTheme.typography.titleSmall)
                var email by remember { mutableStateOf("") }
                var password by remember { mutableStateOf("") }
                OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("邮箱") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("密码（至少 8 位）") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                )
                Button(
                    onClick = { viewModel.linkEmail(email, password) },
                    enabled = email.contains("@") && password.length >= 8,
                    modifier = Modifier.padding(top = 8.dp),
                ) { Text("绑定") }
            }
        }
    } else {
        Text("已绑定：${p.email}", style = MaterialTheme.typography.bodySmall)
    }

    HorizontalDivider(Modifier.padding(vertical = 8.dp))
    TextButton(onClick = { viewModel.logout(onLoggedOut) }) { Text("登出") }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
}
