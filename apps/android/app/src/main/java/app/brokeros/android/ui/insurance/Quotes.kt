package app.brokeros.android.ui.insurance

import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Files
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientRef
import app.brokeros.android.data.Detail
import app.brokeros.android.data.Quote
import app.brokeros.android.data.QuoteCreate
import app.brokeros.android.data.QuoteSent
import app.brokeros.android.data.QuoteSummary
import app.brokeros.android.data.Risk
import app.brokeros.android.data.SendQuote
import app.brokeros.android.data.createQuote
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.quote
import app.brokeros.android.data.quotes
import app.brokeros.android.data.sendQuote
import app.brokeros.android.data.withdrawQuote
import app.brokeros.android.ui.components.ClientPicker
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.Loading
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.jsonPrimitive

private val QUOTE_STATUSES = listOf("draft", "sent", "accepted", "declined", "withdrawn", "expired")

class QuotesViewModel(private val api: BrokerApi, private val clientId: String? = null) : ViewModel() {
    private val _state = MutableStateFlow<Load<List<QuoteSummary>>>(Load.Loading)
    val state = _state.asStateFlow()
    var status: String? = null

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = Load.Loading
        _state.value = try { Load.Ready(api.quotes(clientId, status)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }
}

@Composable
fun QuoteRow(q: QuoteSummary, onOpen: () -> Unit) {
    ListItem(
        headlineContent = { Text(q.title) },
        supportingContent = {
            Text(listOfNotNull(q.client.displayName, q.number, q.lowestTotal?.let { "from ${money(it, q.currency)}" }).joinToString(" · "))
        },
        trailingContent = { Text(Labels.of(q.status), style = MaterialTheme.typography.labelMedium) },
        modifier = Modifier.clickable(onClick = onOpen),
    )
    HorizontalDivider()
}

@Composable
fun QuotesScreen(viewModel: QuotesViewModel, onOpen: (String) -> Unit, onNew: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var status by rememberSaveable { mutableStateOf(viewModel.status) }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = status == null, onClick = { status = null; viewModel.status = null; viewModel.load() }, label = { Text("All") })
                QUOTE_STATUSES.forEach { s ->
                    FilterChip(selected = status == s, onClick = { status = s; viewModel.status = s; viewModel.load() }, label = { Text(Labels.of(s)) })
                }
            }
            PullToRefreshBox(isRefreshing = state is Load.Loading, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
                Loaded(state, onRetry = { viewModel.load() }) { list ->
                    if (list.isEmpty()) Empty("No quotes here yet.")
                    LazyColumn(Modifier.fillMaxSize()) {
                        items(list, key = { it.id }) { q -> QuoteRow(q) { onOpen(q.id) } }
                        item { Box(Modifier.padding(40.dp)) }
                    }
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = onNew,
            icon = { Icon(Icons.Default.Add, contentDescription = null) },
            text = { Text("New quote") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        )
    }
}

class QuoteViewModel(private val api: BrokerApi, val id: String) : ViewModel() {
    private val _state = MutableStateFlow<Load<Quote>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.quote(id)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun send(email: String?, message: String): QuoteSent = api.sendQuote(id, SendQuote(email?.trim()?.ifBlank { null }, message)).also {
        _state.value = Load.Ready(it.quote)
    }

    suspend fun withdraw() { _state.value = Load.Ready(api.withdrawQuote(id)) }

    suspend fun pdf(): ByteArray = api.bytes("/quotes/$id/pdf")
}

@Composable
fun QuoteScreen(viewModel: QuoteViewModel, showCommission: Boolean, canSend: Boolean, onCreatePolicy: (Quote) -> Unit, onOpenClient: (String) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    var sending by remember { mutableStateOf(false) }
    var sent by remember { mutableStateOf<QuoteSent?>(null) }
    Loaded(state, onRetry = { viewModel.load() }) { q ->
        FormColumn {
            Text(q.title, style = MaterialTheme.typography.headlineSmall)
            Text(
                listOfNotNull(q.number, Labels.of(q.status), q.validUntil?.let { "valid until ${Dates.date(it)}" }).joinToString(" · "),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TextButton(onClick = { onOpenClient(q.client.id) }) { Text(q.client.displayName) }
            q.acceptedPosition?.let { pos ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Text(
                        "Accepted option $pos" + (q.response?.get("name")?.jsonPrimitive?.content?.let { " by $it" } ?: "") +
                            (q.respondedAt?.let { ", ${Dates.dateTime(it)}" } ?: ""),
                        modifier = Modifier.padding(14.dp),
                    )
                }
            }
            q.details.forEach { app.brokeros.android.ui.components.Detail(it.label, it.value) }
            q.optionList.sortedBy { it.clientTotal.toBigDecimalOrNull() }.forEach { o ->
                Card(colors = CardDefaults.cardColors(containerColor = if (o.position == q.acceptedPosition) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("${o.position}. ${o.insurerName}" + if (o.recommended) " · recommended" else "", style = MaterialTheme.typography.titleMedium)
                        Text(o.productName, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(money(o.clientTotal, q.currency, decimals = true), style = MaterialTheme.typography.titleLarge)
                        o.excessText?.let { Text("Excess: $it", style = MaterialTheme.typography.bodySmall) }
                        if (showCommission) o.commission?.get("gross")?.jsonPrimitive?.content?.let {
                            Text("Your commission: ${money(it, q.currency, decimals = true)}", color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
            q.notes?.let { app.brokeros.android.ui.components.Detail("Notes", it) }
            if (canSend && q.status in listOf("draft", "sent")) {
                Button(onClick = { sending = true }, modifier = Modifier.fillMaxWidth()) { Text(if (q.status == "draft") "Send to client" else "Send again") }
            }
            if (q.status == "accepted") {
                Button(onClick = { onCreatePolicy(q) }, modifier = Modifier.fillMaxWidth()) { Text("Create policy") }
            }
            OutlinedButton(onClick = {
                scope.launch {
                    try {
                        val bytes = viewModel.pdf()
                        val opened = kotlinx.coroutines.withContext(Dispatchers.IO) { Files.openPdf(context, bytes, q.number ?: "quote") }
                        if (!opened) toast("Install a PDF viewer to open quotes.")
                    } catch (e: AppException) { toast(e.message ?: "Try again.") }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Open PDF") }
            if (canSend && q.status in listOf("draft", "sent")) {
                TextButton(onClick = {
                    scope.launch { try { viewModel.withdraw(); toast("Quote withdrawn") } catch (e: AppException) { toast(e.message ?: "Try again.") } }
                }) { Text("Withdraw quote", color = MaterialTheme.colorScheme.error) }
            }
        }
        if (sending) {
            var email by remember { mutableStateOf(q.client.email ?: "") }
            var message by remember { mutableStateOf("") }
            var busy by remember { mutableStateOf(false) }
            var error by remember { mutableStateOf<String?>(null) }
            AlertDialog(
                onDismissRequest = { if (!busy) sending = false },
                title = { Text("Send quote") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("You get a link to share on WhatsApp. Add an email to send it there too.")
                        Field("Client's email", email, { email = it }, keyboard = KeyboardType.Email, hint = "Optional")
                        Field("Message", message, { message = it }, singleLine = false, minLines = 2, hint = "Optional")
                        FormError(error)
                    }
                },
                confirmButton = {
                    SubmitButton("Send quote", busy) {
                        busy = true
                        scope.launch {
                            try { sent = viewModel.send(email, message); sending = false } catch (e: AppException) { error = e.message } finally { busy = false }
                        }
                    }
                },
                dismissButton = { TextButton(onClick = { sending = false }, enabled = !busy) { Text("Cancel") } },
            )
        }
        sent?.let { s ->
            AlertDialog(
                onDismissRequest = { sent = null },
                title = { Text("Quote sent") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        s.emailedTo?.let { Text("Emailed to $it.") }
                        Text(s.url, style = MaterialTheme.typography.bodySmall)
                        s.whatsappUrl?.let { Button(onClick = { context.open(it) }, modifier = Modifier.fillMaxWidth()) { Text("Share on WhatsApp") } }
                        OutlinedButton(onClick = { clipboard.setText(AnnotatedString(s.url)); toast("Link copied") }, modifier = Modifier.fillMaxWidth()) { Text("Copy link") }
                        OutlinedButton(onClick = {
                            context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, s.url), "Share quote"))
                        }, modifier = Modifier.fillMaxWidth()) { Text("Share another way") }
                    }
                },
                confirmButton = { TextButton(onClick = { sent = null }) { Text("Done") } },
            )
        }
    }
}

/** A new quote: pick the client, the class and insurers, the sum insured and what is covered. */
@Composable
fun NewQuoteScreen(api: BrokerApi, client: ClientRef?, onCreated: (String) -> Unit) {
    var catalogue by remember { mutableStateOf<Catalogue?>(null) }
    var who by remember { mutableStateOf(client) }
    var classCode by rememberSaveable { mutableStateOf<String?>(null) }
    var selected by rememberSaveable { mutableStateOf<List<String>>(emptyList()) }
    var sumInsured by rememberSaveable { mutableStateOf("") }
    var covered by rememberSaveable { mutableStateOf("") }
    var notes by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    LaunchedEffect(Unit) { try { catalogue = api.catalogue() } catch (e: AppException) { error = e.message } }
    FormColumn {
        ClientPicker(api, who) { who = it }
        val c = catalogue ?: run { FormError(error); if (error == null) Loading(); return@FormColumn }
        ProductPicker(c, classCode, { classCode = it; selected = c.products.filter { p -> p.classCode == it }.map { p -> p.id } }, selected, { selected = it })
        Field("Sum insured (KES)", sumInsured, { sumInsured = amountOf(it) }, keyboard = KeyboardType.Number)
        Field("What is covered", covered, { covered = it }, hint = "e.g. KDA 123A, Toyota Axio 2019")
        Field("Notes for the client", notes, { notes = it }, singleLine = false, minLines = 2, hint = "Optional")
        FormError(error)
        SubmitButton("Create quote", busy, who != null && selected.isNotEmpty()) {
            busy = true
            scope.launch {
                try {
                    val label = c.pack.classes.firstOrNull { it.code == classCode }?.name ?: "Vehicle"
                    val quote = api.createQuote(
                        QuoteCreate(
                            clientId = who!!.id,
                            productIds = selected,
                            risk = Risk(sumInsured = sumInsured.ifBlank { null }),
                            details = listOfNotNull(covered.trim().ifBlank { null }?.let { Detail(if (classCode?.startsWith("motor") == true) "Vehicle" else label, it) }),
                            notes = notes.trim().ifBlank { null },
                        ),
                        key,
                    )
                    toast("Quote created")
                    onCreated(quote.id)
                } catch (e: AppException) { error = e.message } finally { busy = false }
            }
        }
    }
}
