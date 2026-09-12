package com.windveil.journal.presentation.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoStories
import androidx.compose.material.icons.filled.Forum
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Spa
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.windveil.journal.presentation.screens.GardenScreen
import com.windveil.journal.presentation.screens.HeartVoiceScreen
import com.windveil.journal.presentation.screens.MemoryBookScreen
import com.windveil.journal.presentation.screens.MemoryPageScreen
import com.windveil.journal.presentation.screens.SeedWishScreen
import com.windveil.journal.presentation.screens.SettingsScreen
import com.windveil.journal.presentation.screens.WishDetailScreen

/** 导航路由（单层扁平结构，避免嵌套 NavHost）。 */
object Routes {
    const val HEART_VOICE = "heart_voice"
    const val GARDEN = "garden"
    const val MEMORIES = "memories"
    const val SETTINGS = "settings"
    const val SEED = "seed"
    const val WISH_DETAIL = "wish/{wishId}"
    const val MEMORY_PAGE = "memory/{memoryId}"

    fun wishDetail(wishId: String) = "wish/$wishId"
    fun memoryPage(memoryId: String) = "memory/$memoryId"
}

/** 底部四 Tab：心语 / 未发生之地 / 已发生之书 / 我的。 */
private val TAB_ROUTES = setOf(Routes.HEART_VOICE, Routes.GARDEN, Routes.MEMORIES, Routes.SETTINGS)

/**
 * 主导航。单层 NavHost：四个常驻区域（未发生之地/已发生之书/随手记/我的）
 * 在这些路由上显示底部栏；welcome/seed/wish/memory 等覆盖页不显示。
 */
@Composable
fun WindveilApp(startDestination: String, navController: NavHostController = rememberNavController()) {
    val nav = navController
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    Scaffold(
        bottomBar = {
            if (currentRoute in TAB_ROUTES) {
                NavigationBar {
                    NavigationBarItem(
                        selected = currentRoute == Routes.HEART_VOICE,
                        onClick = { nav.navigate(Routes.HEART_VOICE) { popUpTo(Routes.GARDEN) { saveState = true }; launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Filled.Forum, null) },
                        label = { Text("心语") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == Routes.GARDEN,
                        onClick = { nav.navigate(Routes.GARDEN) { popUpTo(Routes.GARDEN) { saveState = true }; launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Filled.Spa, null) },
                        label = { Text("未发生之地") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == Routes.MEMORIES,
                        onClick = { nav.navigate(Routes.MEMORIES) { popUpTo(Routes.GARDEN) { saveState = true }; launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Filled.AutoStories, null) },
                        label = { Text("已发生之书") },
                    )
                        NavigationBarItem(
                        selected = currentRoute == Routes.SETTINGS,
                        onClick = { nav.navigate(Routes.SETTINGS) { popUpTo(Routes.GARDEN) { saveState = true }; launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Filled.Person, null) },
                        label = { Text("我的") },
                    )
                }
            }
        }
    ) { padding ->
        NavHost(nav, startDestination = startDestination, modifier = Modifier.padding(padding)) {
            composable(Routes.GARDEN) {
                GardenScreen(
                    onSeed = { nav.navigate(Routes.SEED) },
                    onOpenWish = { id -> nav.navigate(Routes.wishDetail(id)) },
                )
            }
            composable(Routes.HEART_VOICE) { HeartVoiceScreen() }
            composable(Routes.MEMORIES) {
                MemoryBookScreen(onBack = { nav.popBackStack() }, onOpen = { id -> nav.navigate(Routes.memoryPage(id)) })
            }
            composable(Routes.SETTINGS) {
                SettingsScreen(onBack = { nav.popBackStack() }, onLoggedOut = {})
            }
            composable(Routes.SEED) {
                SeedWishScreen(
                    onClose = { nav.popBackStack() },
                    onSeeded = { id ->
                        nav.navigate(Routes.wishDetail(id)) { popUpTo(Routes.SEED) { inclusive = true } }
                    },
                )
            }
            composable(
                Routes.WISH_DETAIL,
                arguments = listOf(navArgument("wishId") { type = NavType.StringType }),
            ) {
                WishDetailScreen(
                    wishId = it.arguments?.getString("wishId").orEmpty(),
                    onBack = { nav.popBackStack() },
                    onOpenMemory = { id -> nav.navigate(Routes.memoryPage(id)) },
                )
            }
            composable(
                Routes.MEMORY_PAGE,
                arguments = listOf(navArgument("memoryId") { type = NavType.StringType }),
            ) {
                MemoryPageScreen(
                    memoryId = it.arguments?.getString("memoryId").orEmpty(),
                    onBack = { nav.popBackStack() },
                    onPublished = {
                        // 收进书里后跳到已发生之书：返回栈里有 memories 就弹回去；
                        // 从愿望详情进入（garden→wish→memory）时栈里没有 memories，
                        // popBackStack 返回 false，改按 Tab 语义导航过去
                        if (!nav.popBackStack(Routes.MEMORIES, false)) {
                            nav.navigate(Routes.MEMORIES) {
                                popUpTo(Routes.GARDEN) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    },
                )
            }
        }
    }
}
