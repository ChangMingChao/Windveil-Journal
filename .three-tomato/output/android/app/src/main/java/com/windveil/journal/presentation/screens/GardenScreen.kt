package com.windveil.journal.presentation.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import com.windveil.journal.data.remote.WishCard
import com.windveil.journal.data.repository.WishRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** 愿望状态 → 卡面文案（无任何逾期/计数语言，对应 PRD 设计原则）。 */
fun stateLabel(state: String): String = when (state) {
    "seeded" -> "刚种下"
    "brewing" -> "正在酝酿"
    "wind" -> "风来了"
    "going" -> "正在发生"
    "happened" -> "已经发生"
    "let_go" -> "安静放下"
    else -> state
}

@HiltViewModel
class GardenViewModel @Inject constructor(
    private val wishRepository: WishRepository,
) : ViewModel() {
    val wishes = MutableStateFlow<List<WishCard>>(emptyList())
    val loading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    private var nextCursor: String? = null

    fun refresh() {
        viewModelScope.launch {
            loading.value = true
            error.value = null
            runCatching {
                val page = wishRepository.list()
                nextCursor = page.nextCursor
                page.items
            }.onSuccess { wishes.value = it }
                .onFailure { error.value = it.message ?: "打不开了，再试试" }
            loading.value = false
        }
    }

    fun loadMore() {
        val cursor = nextCursor ?: return
        viewModelScope.launch {
            runCatching { wishRepository.list(cursor = cursor) }
                .onSuccess { page ->
                    nextCursor = page.nextCursor
                    wishes.value = wishes.value + page.items
                }
        }
    }
}

/** S05.1：未发生之地 —— 河流式列表，空状态温柔呈现。 */
@Composable
fun GardenScreen(
    onSeed: () -> Unit,
    onOpenWish: (String) -> Unit,
    viewModel: GardenViewModel = hiltViewModel(),
) {
    val wishes by viewModel.wishes.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val error by viewModel.error.collectAsState()
    var tab by remember { mutableStateOf(0) }

    LaunchedEffect(Unit) { viewModel.refresh() }

    Scaffold(
        floatingActionButton = {
            if (tab == 0) {
                ExtendedFloatingActionButton(onClick = onSeed) {
                    Icon(Icons.Filled.Add, contentDescription = null)
                    Text("种下一个", modifier = Modifier.padding(start = 4.dp))
                }
            }
        }
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Text(
                "未发生之地",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            // 顶部切换：愿望 | 随手记（heart-voice-holiday-timing：随手记收进未发生之地）
            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("愿望") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("随手记") })
            }
            if (tab == 1) {
                LiteEventsScreen(embedded = true)
                return@Scaffold
            }
            when {
                loading && wishes.isEmpty() -> CircularProgressIndicator(Modifier.padding(32.dp))
                wishes.isEmpty() && error == null -> EmptyGarden()
                else -> LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                ) {
                    items(wishes, key = { it.id }) { wish ->
                        WishCardItem(wish) { onOpenWish(wish.id) }
                    }
                    if (error != null) {
                        item {
                            Text(
                                error.orEmpty(),
                                color = MaterialTheme.colorScheme.error,
                                modifier = Modifier.padding(8.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyGarden() {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("这里还空着。", style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Text(
            "想到一件想在未来发生的事，就先种下来吧。它不急，这里替你记着。",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}

@Composable
private fun WishCardItem(wish: WishCard, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp)) {
            Text(wish.title, style = MaterialTheme.typography.titleMedium)
            wish.originalTextExcerpt?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                )
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    stateLabel(wish.state),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    wish.timing.label,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (wish.softDeferred) {
                Text(
                    "本周先不打扰你",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
