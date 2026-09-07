package com.windveil.journal.presentation.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * 纸色主题 —— 对应 PRD 设计原则：「不制造焦虑」。
 * 纸色背景、低饱和的苔绿与暖褐，无红黄告警色。
 */
val Paper = Color(0xFFF7F3EB)
val PaperDeep = Color(0xFFEFE8DB)
val Ink = Color(0xFF3E3A34)
val Moss = Color(0xFF6B8F71)
val MossDeep = Color(0xFF52735A)
val WarmBrown = Color(0xFFA78A6F)
val Mist = Color(0xFF8C8578)

private val LightColors = lightColorScheme(
    primary = Moss,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD8E6DA),
    onPrimaryContainer = MossDeep,
    secondary = WarmBrown,
    onSecondary = Color.White,
    background = Paper,
    onBackground = Ink,
    surface = Paper,
    onSurface = Ink,
    surfaceVariant = PaperDeep,
    onSurfaceVariant = Mist,
    error = Color(0xFF9A6A6A), // 低饱和的红褐，替代告警红
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF9DBBA2),
    onPrimary = Color(0xFF1F2C21),
    secondary = Color(0xFFC7AB8E),
    background = Color(0xFF211F1B),
    onBackground = Color(0xFFE8E2D6),
    surface = Color(0xFF211F1B),
    onSurface = Color(0xFFE8E2D6),
    surfaceVariant = Color(0xFF2E2B26),
    onSurfaceVariant = Color(0xFFA29A8C),
    error = Color(0xFFC09A9A),
)

@Composable
fun WindveilTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
