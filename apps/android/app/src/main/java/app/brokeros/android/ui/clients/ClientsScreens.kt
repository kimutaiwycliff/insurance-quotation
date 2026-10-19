package app.brokeros.android.ui.clients

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Phone
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Client
import app.brokeros.android.data.ClientSummary
import app.brokeros.android.ui.components.ErrorMessage
import app.brokeros.android.ui.components.Loading
import app.brokeros.android.ui.components.open
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

    fun retry() = viewModelScope.launch { load(query.value, cursor = null) }

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
fun ClientsScreen(viewModel: ClientsViewModel, onOpen: (String) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val list = rememberLazyListState()
    val nearEnd by remember { derivedStateOf { (list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0) >= list.layoutInfo.totalItemsCount - 5 } }
    LaunchedEffect(nearEnd) { if (nearEnd) viewModel.loadMore() }

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
            state.items.isEmpty() && state.error != null -> ErrorMessage(state.error!!, { viewModel.retry() })
            state.items.isEmpty() && state.loading -> Loading()
            state.items.isEmpty() -> ErrorMessage(
                if (state.query.isBlank()) "No clients yet. Add your first client on the web." else "No client matches “${state.query}”.",
                onRetry = null,
            )
            else -> LazyColumn(state = list) {
                items(state.items, key = { it.id }) { client ->
                    ListItem(
                        headlineContent = { Text(client.displayName) },
                        supportingContent = { Text(client.phone?.let(Phone::display) ?: client.email ?: "No contact details") },
                        trailingContent = {
                            if (client.kind != "individual") Text(client.kind.replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.labelMedium)
                        },
                        modifier = Modifier.clickable { onOpen(client.id) },
                    )
                    HorizontalDivider()
                }
                if (state.loading) item { Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator() } }
            }
        }
    }
}

data class ClientState(val client: Client? = null, val error: String? = null)

class ClientViewModel(private val api: BrokerApi, private val id: String) : ViewModel() {
    private val _state = MutableStateFlow(ClientState())
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = ClientState()
        _state.value = try {
            ClientState(client = api.client(id))
        } catch (e: AppException) {
            ClientState(error = e.message)
        }
    }
}

@Composable
private fun Detail(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Column(Modifier.padding(vertical = 6.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
fun ClientScreen(viewModel: ClientViewModel, siteUrl: String, agentName: String) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val client = state.client
    when {
        client == null && state.error != null -> ErrorMessage(state.error!!, { viewModel.load() })
        client == null -> Loading()
        else -> LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
            item {
                Text(client.displayName, style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(top = 8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                    AssistChip(onClick = {}, label = { Text(client.kind.replaceFirstChar { it.uppercase() }) })
                    AssistChip(onClick = {}, label = { Text(client.status.replaceFirstChar { it.uppercase() }) })
                }
            }
            client.phone?.let { phone ->
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                        Button(onClick = { context.open(Phone.dialUri(phone), android.content.Intent.ACTION_DIAL) }) {
                            Icon(Icons.Default.Call, contentDescription = null, modifier = Modifier.padding(end = 8.dp))
                            Text("Call")
                        }
                        OutlinedButton(onClick = { context.open(Phone.whatsAppUrl(phone, "Hello ${client.displayName.substringBefore(' ')}, this is $agentName.")) }) {
                            Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null, modifier = Modifier.padding(end = 8.dp))
                            Text("WhatsApp")
                        }
                    }
                }
            }
            item {
                Detail("Phone", client.phone?.let(Phone::display))
                Detail("Other phone", client.altPhone?.let(Phone::display))
                Detail("Email", client.email)
                Detail("KRA PIN", client.kraPin)
                Detail("Occupation", client.occupation)
                Detail("Tags", client.tags.joinToString(", ").ifBlank { null })
                Detail("Notes", client.notes)
            }
            client.email?.let { email ->
                item {
                    TextButton(onClick = { context.open("mailto:$email", android.content.Intent.ACTION_SENDTO) }) {
                        Icon(Icons.Default.Email, contentDescription = null, modifier = Modifier.padding(end = 8.dp))
                        Text("Send an email")
                    }
                }
            }
            item {
                TextButton(onClick = { context.open("$siteUrl/clients/${client.id}") }) {
                    Text("Open the full client page on the web")
                }
            }
        }
    }
}
