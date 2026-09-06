package com.windveil.journal.presentation.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Button
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
import com.windveil.journal.data.local.db.LiteEventEntity
import com.windveil.journal.data.repository.StandaloneRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class LiteEventsViewModel @Inject constructor(
    private val repository: StandaloneRepository,
) : ViewModel() {
    /** Room 流：本地库变更自动刷新。 */
    val events = repository.observeOpenLiteEvents()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun create(text: String, onCreated: () -> Unit) {
        if (text.isBlank() || text.length > 200) return
        viewModelScope.launch {
            repository.createLiteEvent(text)
            onCreated()
        }
    }

    fun markDone(eventId: String) = viewModelScope.launch { repository.markLiteEventDone(eventId) }
    fun delete(eventId: String) = viewModelScope.launch { repository.deleteLiteEvent(eventId) }
}

/** S09：先记一下并随手划掉 —— 无 Agent、无提醒路径、不占提醒额度。 */
@Composable
fun LiteEventsScreen(
    onBack: () -> Unit = {},
    embedded: Boolean = false,
    viewModel: LiteEventsViewModel = hiltViewModel(),
) {
    val events by viewModel.events.collectAsState()
    var text by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        if (!embedded) {
            TextButton(onClick = onBack) { Text("← 回到未发生之地") }
        }
        if (!embedded) {
            Text("随手记", style = MaterialTheme.typography.titleLarge)
        }
        Text(
            "还不值得变成愿望的念头，先记在这里。它们不会被提醒，也不会被催。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                placeholder = { Text("先记一下（今晚吃什么、周末取快递）") },
                modifier = Modifier.weight(1f),
                singleLine = true,
            )
            Button(
                onClick = {
                    viewModel.create(text) { text = "" }
                },
                enabled = text.isNotBlank() && text.length <= 200,
                modifier = Modifier.padding(start = 8.dp),
            ) { Text("记下") }
        }
        LazyColumn(
            Modifier.padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            items(events, key = { it.id }) { event ->
                Card(Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(event.text, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                        IconButton(onClick = { viewModel.markDone(event.id) }) {
                            Icon(Icons.Filled.Check, contentDescription = "划掉了")
                        }
                        IconButton(onClick = { viewModel.delete(event.id) }) {
                            Icon(Icons.Filled.Close, contentDescription = "收走")
                        }
                    }
                }
            }
        }
    }
}
