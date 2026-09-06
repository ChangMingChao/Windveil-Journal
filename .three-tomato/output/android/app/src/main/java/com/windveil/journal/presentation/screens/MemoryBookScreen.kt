package com.windveil.journal.presentation.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.windveil.journal.data.local.db.MemoryEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

@HiltViewModel
class MemoryBookViewModel @Inject constructor(
    repository: StandaloneRepository,
) : ViewModel() {
    val memories: StateFlow<List<MemoryEntity>> =
        repository.observePublishedMemories()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val livedPages: StateFlow<Int> =
        repository.observeLivedPages()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0)
}

/** S06 Step 20：已发生之书书架。lived_pages 是产品内唯一允许的计数。 */
@Composable
fun MemoryBookScreen(
    onBack: () -> Unit,
    onOpen: (String) -> Unit,
    viewModel: MemoryBookViewModel = hiltViewModel(),
) {
    val memories by viewModel.memories.collectAsState()
    val livedPages by viewModel.livedPages.collectAsState()

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        TextButton(onClick = onBack) { Text("← 回到未发生之地") }
        Text("已发生之书", style = MaterialTheme.typography.titleLarge)
        Text(
            "你已经活过的 $livedPages 页",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        if (memories.isEmpty()) {
            Text(
                "还一页都没有。发生过的事，值得写下来。",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
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
    }
}
