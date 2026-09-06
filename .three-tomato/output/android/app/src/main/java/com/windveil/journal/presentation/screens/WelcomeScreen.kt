package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.windveil.journal.data.remote.OnboardingAnswer
import com.windveil.journal.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class WelcomeViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val done = MutableStateFlow(false)

    /** S01 Step 3 → Step 11：点「开始」即匿名建号，温柔问题可整体跳过（空数组）。 */
    fun start() {
        if (loading.value) return
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching {
                authRepository.createAnonymousSpace()
                // 跳过全部温柔问题（S01 允许整体跳过）
                authRepository.submitOnboarding(emptyList<OnboardingAnswer>())
            }.onSuccess {
                done.value = true
            }.onFailure { e ->
                // EX-3.1：建号失败不丢内容，提示后可重试
                error.value = e.message ?: "这里暂时打不开，再试一次吧"
            }
            loading.value = false
        }
    }
}

/** 首次体验：无表单，「开始」一个按钮建立个人空间。 */
@Composable
fun WelcomeScreen(onDone: () -> Unit, viewModel: WelcomeViewModel = hiltViewModel()) {
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    val done by viewModel.done.collectAsState()
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }

    if (done) {
        androidx.compose.runtime.LaunchedEffect(Unit) { onDone() }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "未发生事件管理局",
            style = MaterialTheme.typography.headlineMedium,
            textAlign = TextAlign.Center,
        )
        Text(
            "为那些还没发生、但值得被认真对待的事，留一盏灯。",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 16.dp, bottom = 32.dp),
        )
        Button(onClick = { viewModel.start() }, enabled = !loading) {
            if (loading) CircularProgressIndicator(modifier = Modifier.padding(4.dp)) else Text("开始")
        }
        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 16.dp))
        }
        // 可选的跨设备找回入口（S01「待补设计 1」：绑定邮箱后置）
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("以后再绑定邮箱也可以") },
            modifier = Modifier.fillMaxWidth().padding(top = 32.dp),
            singleLine = true,
            readOnly = true,
        )
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("在「我的」页随时可以绑定") },
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            singleLine = true,
            readOnly = true,
        )
    }
}
