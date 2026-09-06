package com.windveil.journal

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.windveil.journal.presentation.navigation.WindveilApp
import com.windveil.journal.presentation.theme.WindveilTheme
import dagger.hilt.android.AndroidEntryPoint

/**
 * 单机模式入口（standalone-mode）：无账号、无欢迎分流，
 * 直接进「未发生之地」。数据全部在本地 Room 库。
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            WindveilTheme {
                WindveilApp(startDestination = "garden")
            }
        }
    }
}
