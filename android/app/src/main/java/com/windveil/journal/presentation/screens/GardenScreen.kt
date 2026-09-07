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
import com.windveil.journal.data.local.db.WishEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

/** 卡面时机文案（单机：由 timingType/value 推导）。 */
fun timingLabelOf(wish: WishEntity): String = when (wish.timingType) {
    null -> "还没约定时机"
    "none" -> "你说你会自己想起它"
    "when_tired" -> "累了的时候再说"
    "season" -> "正在等待合适的风：" + mapOf("spring" to "春天", "summer" to "夏天", "autumn" to "秋天", "winter" to "入冬").getOrDefault(wish.timingValue, wish.timingValue ?: "")
    "holiday" -> "正在等待合适的风：" + (wish.timingValue ?: "")
    "month_day" -> "正在等待合适的风：" + (wish.timingValue ?: "")
    "after_months" -> (wish.timingValue ?: "") + " 个月后再看"
    "free_weekend" -> "等一个有空闲的周末"
    else -> wish.timingValue ?: ""
}

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
    repository: StandaloneRepository,
) : ViewModel() {
    /** Room 流：本地库变更自动刷新，无分页（单机量级）。 */
    val wishes: kotlinx.coroutines.flow.StateFlow<List<WishEntity>> =
        repository.observeGarden()
            .stateIn(viewModelScope, kotlinx.coroutines.flow.SharingStarted.WhileSubscribed(5000), emptyList())
}

/** S05.1：未发生之地 —— 河流式列表，空状态温柔呈现。 */
@Composable
fun GardenScreen(
    onSeed: () -> Unit,
    onOpenWish: (String) -> Unit,
    viewModel: GardenViewModel = hiltViewModel(),
) {
    val wishes by viewModel.wishes.collectAsState()
    var tab by remember { mutableStateOf(0) }

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
            if (wishes.isEmpty()) {
                EmptyGarden()
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                ) {
                    items(wishes, key = { it.id }) { wish ->
                        WishCardItem(wish) { onOpenWish(wish.id) }
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
private fun WishCardItem(wish: WishEntity, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp)) {
            Text(wish.title, style = MaterialTheme.typography.titleMedium)
            wish.originalText?.let {
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
                    timingLabelOf(wish),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
