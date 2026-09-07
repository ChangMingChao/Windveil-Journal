package com.windveil.journal.presentation.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.windveil.journal.data.local.db.LiteEventEntity
import com.windveil.journal.data.local.db.MemoryEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MemoryBookViewModel @Inject constructor(
    private val repository: StandaloneRepository,
) : ViewModel() {
    /** 愿望区：已发布的记忆页。 */
    val memories: StateFlow<List<MemoryEntity>> =
        repository.observePublishedMemories()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val livedPages: StateFlow<Int> =
        repository.observeLivedPages()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0)

    /** 随手记区：已划掉（done）的轻事件——它们进入了书的随手记部分。 */
    val doneLiteEvents: StateFlow<List<LiteEventEntity>> =
        repository.observeDoneLiteEvents()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun updateLiteEvent(id: String, text: String, note: String?, photos: String?) =
        viewModelScope.launch { repository.updateLiteEvent(id, text, note, photos) }
}

/** S06 Step 20：已发生之书 —— 愿望 | 随手记 两区（android-ux-crud 追加）。 */
@Composable
fun MemoryBookScreen(
    onBack: () -> Unit,
    onOpen: (String) -> Unit,
    viewModel: MemoryBookViewModel = hiltViewModel(),
) {
    val memories by viewModel.memories.collectAsState()
    val livedPages by viewModel.livedPages.collectAsState()
    val doneEvents by viewModel.doneLiteEvents.collectAsState()
    var tab by remember { mutableStateOf(0) }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        TextButton(onClick = onBack) { Text("← 回到未发生之地") }
        Text("已发生之书", style = MaterialTheme.typography.titleLarge)
        Text(
            "你已经活过的 $livedPages 页",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("愿望") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("随手记") })
        }

        if (tab == 0) {
            if (memories.isEmpty()) {
                Text(
                    "还一页都没有。发生过的事，值得写下来。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 12.dp),
                )
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(top = 12.dp)) {
                    items(memories, key = { it.id }) { memory ->
                        Card(Modifier.fillMaxWidth().clickable { onOpen(memory.id) }) {
                            Column(Modifier.padding(16.dp)) {
                                Text(memory.title, style = MaterialTheme.typography.titleMedium)
                                Text(
                                    memory.happenedTo?.let { "${memory.happenedFrom} 至 $it" } ?: memory.happenedFrom,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        } else {
            if (doneEvents.isEmpty()) {
                Text(
                    "划掉的随手记会收进这里，也支持备注和照片。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 12.dp),
                )
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(top = 12.dp)) {
                    items(doneEvents, key = { it.id }) { event ->
                        var showEdit by remember(event.id) { mutableStateOf(false) }
                        Card(Modifier.fillMaxWidth().clickable { showEdit = true }) {
                            Column(Modifier.padding(16.dp)) {
                                Text(event.text, style = MaterialTheme.typography.titleMedium)
                                Text(
                                    "划掉于 " + (event.closedAt?.take(10) ?: ""),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                event.note?.let {
                                    Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 3)
                                }
                                val photos = event.photos?.let { parsePhotos(it) }.orEmpty()
                                if (photos.isNotEmpty()) {
                                    Text("附 ${photos.size} 张照片", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
                                }
                            }
                        }
                        if (showEdit) {
                            LiteEventEditDialog(
                                initialText = event.text,
                                initialNote = event.note.orEmpty(),
                                initialPhotos = event.photos,
                                onSave = { newText, newNote, newPhotos ->
                                    viewModel.updateLiteEvent(event.id, newText, newNote, newPhotos)
                                    showEdit = false
                                },
                                onDismiss = { showEdit = false },
                            )
                        }
                    }
                }
            }
        }
    }
}
