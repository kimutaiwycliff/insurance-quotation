package app.brokeros.android.ui.clients

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Labels
import app.brokeros.android.core.Phone
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientSummary
import app.brokeros.android.data.clients
import app.brokeros.android.ui.components.ErrorMessage
import app.brokeros.android.ui.components.Loading
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch

data class ClientsState(
    val query: String = "",
    val items: List<ClientSummary> = emptyList(),
    val nextCursor: String? = null,
    val loading: Boolean = true,
    val error: String? = null,
)

@OptIn(FlowPreview::class)
class ClientsViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow(ClientsState())
    val state = _state.asStateFlow()
    private val query = MutableStateFlow("")

    init {
        viewModelScope.launch {
            // Search as the person types, once they pause.
            query.debounce(300).distinctUntilChanged().collectLatest { load(it, cursor = null) }
        }
    }

    fun search(text: String) {
        _state.value = _state.value.copy(query = text)
        query.value = text
    }

    fun reload() = viewModelScope.launch { load(query.value, cursor = null) }

    fun loadMore() {
        val s = _state.value
        if (s.loading || s.nextCursor == null) return
        viewModelScope.launch { load(s.query, s.nextCursor) }
    }

    private suspend fun load(text: String, cursor: String?) {
        _state.value = _state.value.copy(loading = true, error = null)
        _state.value = try {
            val page = api.clients(text, cursor)
            _state.value.copy(
                items = if (cursor == null) page.items else _state.value.items + page.items,
                nextCursor = page.nextCursor,
                loading = false,
            )
        } catch (e: AppException) {
            _state.value.copy(loading = false, error = e.message)
        }
    }
}

@Composable
fun ClientsScreen(viewModel: ClientsViewModel, canAdd: Boolean, onOpen: (String) -> Unit, onAdd: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val list = rememberLazyListState()
    val nearEnd by remember { derivedStateOf { (list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0) >= list.layoutInfo.totalItemsCount - 5 } }
    LaunchedEffect(nearEnd) { if (nearEnd) viewModel.loadMore() }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            OutlinedTextField(
                value = state.query,
                onValueChange = viewModel::search,
                placeholder = { Text("Search by name or phone") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                trailingIcon = {
                    if (state.query.isNotEmpty()) {
                        IconButton(onClick = { viewModel.search("") }) { Icon(Icons.Default.Clear, contentDescription = "Clear search") }
                    }
                },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            )
            when {
                state.items.isEmpty() && state.error != null -> ErrorMessage(state.error!!, { viewModel.reload() })
                state.items.isEmpty() && state.loading -> Loading()
                state.items.isEmpty() -> ErrorMessage(
                    if (state.query.isBlank()) "No clients yet. Add your first client." else "No client matches “${state.query}”.",
                    onRetry = null,
                )
                else -> LazyColumn(state = list) {
                    items(state.items, key = { it.id }) { client ->
                        ListItem(
                            headlineContent = { Text(client.displayName) },
                            supportingContent = { Text(client.phone?.let(Phone::display) ?: client.email ?: "No contact details") },
                            trailingContent = {
                                if (client.kind != "individual") Text(Labels.of(client.kind), style = MaterialTheme.typography.labelMedium)
                            },
                            modifier = Modifier.clickable { onOpen(client.id) },
                        )
                        HorizontalDivider()
                    }
                    if (state.loading) item { Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator() } }
                    item { Box(Modifier.padding(40.dp)) }
                }
            }
        }
        if (canAdd) {
            ExtendedFloatingActionButton(
                onClick = onAdd,
                icon = { Icon(Icons.Default.Add, contentDescription = null) },
                text = { Text("Add client") },
                modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
            )
        }
    }
}
