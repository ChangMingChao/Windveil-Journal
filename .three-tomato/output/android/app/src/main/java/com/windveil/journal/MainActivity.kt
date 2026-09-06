package com.windveil.journal

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.windveil.journal.data.local.TokenStore
import com.windveil.journal.presentation.navigation.WindveilApp
import com.windveil.journal.presentation.theme.WindveilTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var tokenStore: TokenStore

    private var startDestination by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lifecycleScope.launch {
            // 有个人空间（access token 曾下发）直接进花园，否则进入首次体验
            startDestination = if (tokenStore.hasSpace.first()) "garden" else "welcome"
        }
        lifecycleScope.launch {
            // 会话不可恢复（refresh 失效）→ 重建 Activity，冷启动回到欢迎页
            tokenStore.sessionExpired.collect { recreate() }
        }
        setContent {
            WindveilTheme {
                startDestination?.let { dest ->
                    WindveilApp(startDestination = dest)
                }
            }
        }
    }
}
