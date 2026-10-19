package app.brokeros.android.ui.clients

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Email
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.PrimaryScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Files
import app.brokeros.android.core.Labels
import app.brokeros.android.core.Phone
import app.brokeros.android.core.Picked
import app.brokeros.android.data.ActivityInput
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Client
import app.brokeros.android.data.ClientRef
import app.brokeros.android.data.Document
import app.brokeros.android.data.DocumentStart
import app.brokeros.android.data.EntityRef
import app.brokeros.android.data.Task
import app.brokeros.android.data.TimelineItem
import app.brokeros.android.data.Versioned
import app.brokeros.android.data.client
import app.brokeros.android.data.documents
import app.brokeros.android.data.downloadUrl
import app.brokeros.android.data.logActivity
import app.brokeros.android.data.timeline
import app.brokeros.android.data.uploadDocument
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.DateField
import app.brokeros.android.ui.components.Detail
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.insurance.PoliciesViewModel
import app.brokeros.android.ui.insurance.PolicyRow
import app.brokeros.android.ui.insurance.QuoteRow
import app.brokeros.android.ui.insurance.QuotesViewModel
import app.brokeros.android.data.account
import app.brokeros.android.ui.home.money
import app.brokeros.android.ui.money.DocumentRow
import app.brokeros.android.ui.money.DocumentsViewModel
import app.brokeros.android.ui.tasks.TaskRow
import app.brokeros.android.ui.tasks.TaskSheet
import app.brokeros.android.ui.tasks.TasksViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class ClientViewModel(private val api: BrokerApi, val id: String) : ViewModel() {
    private val _client = MutableStateFlow<Load<Versioned<Client>>>(Load.Loading)
    val client = _client.asStateFlow()
    private val _timeline = MutableStateFlow<Load<List<TimelineItem>>>(Load.Loading)
    val timeline = _timeline.asStateFlow()
    private val _documents = MutableStateFlow<Load<List<Document>>>(Load.Loading)
    val documents = _documents.asStateFlow()
    val tasks = TasksViewModelHolder(api, EntityRef("client", id))

    init { load() }

    fun load() = viewModelScope.launch {
        _client.value = Load.Loading
        _client.value = try { Load.Ready(api.client(id)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    fun loadTimeline() = viewModelScope.launch {
        _timeline.value = try { Load.Ready(api.timeline(id)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    fun loadDocuments() = viewModelScope.launch {
        _documents.value = try { Load.Ready(api.documents("client", id).items) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun log(kind: String, body: String) {
        api.logActivity(id, ActivityInput(kind, body.trim()))
        loadTimeline()
    }

    suspend fun upload(picked: Picked, category: String, title: String, expires: java.time.LocalDate?) {
        api.uploadDocument(
            DocumentStart(
                filename = picked.name,
                sizeBytes = picked.bytes.size.toLong(),
                category = category,
                title = title.trim().ifBlank { null },
                expiresOn = expires?.toString(),
                links = listOf(EntityRef("client", id)),
            ),
            picked.bytes,
            picked.mime,
        )
        loadDocuments()
    }

    suspend fun link(documentId: String): String = api.downloadUrl(documentId)
}

/** The client's tasks, inside the client's view model (so they share its lifetime). */
class TasksViewModelHolder(api: BrokerApi, entity: EntityRef) {
    val viewModel = TasksViewModel(api, entity)
}

/** Hooks into other areas (insurance, invoicing) shown as client tabs when the plan includes them. */
class ClientLinks(
    val insurance: Boolean,
    val onOpenQuote: (String) -> Unit,
    val onNewQuote: (ClientRef) -> Unit,
    val onOpenPolicy: (String) -> Unit,
    val onNewPolicy: (ClientRef) -> Unit,
    val billing: Boolean = false,
    val onOpenDocument: (String) -> Unit = {},
    val onNewInvoice: (ClientRef) -> Unit = {},
    val onNewSalesQuote: (ClientRef) -> Unit = {},
)

@Composable
fun ClientScreen(
    viewModel: ClientViewModel,
    api: BrokerApi,
    siteUrl: String,
    agentName: String,
    canEdit: Boolean,
    onEdit: () -> Unit,
    links: ClientLinks,
) {
    val state by viewModel.client.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf("Overview") }
    val tabs = listOf("Overview", "Timeline", "Tasks") + (if (links.insurance) listOf("Quotes", "Policies") else emptyList()) +
        (if (links.billing) listOf("Billing") else emptyList()) + listOf("Documents")
    Loaded(state, onRetry = { viewModel.load() }) { versioned ->
        val client = versioned.value
        Column(Modifier.fillMaxSize()) {
            Column(Modifier.padding(horizontal = 16.dp)) {
                Text(client.displayName, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AssistChip(onClick = {}, label = { Text(Labels.of(client.kind)) })
                    if (client.archivedAt != null) AssistChip(onClick = {}, label = { Text("Archived") })
                }
            }
            PrimaryScrollableTabRow(selectedTabIndex = tabs.indexOf(tab).coerceAtLeast(0), edgePadding = 8.dp) {
                tabs.forEach { label -> Tab(selected = tab == label, onClick = { tab = label }, text = { Text(label) }) }
            }
            val ref = ClientRef(client.id, client.displayName, client.phone, client.email)
            when (tab) {
                "Overview" -> Overview(client, siteUrl, agentName, canEdit, onEdit)
                "Timeline" -> TimelineTab(viewModel)
                "Tasks" -> ClientTasks(viewModel, api)
                "Quotes" -> ClientQuotes(api, client.id, onOpen = links.onOpenQuote) { links.onNewQuote(ref) }
                "Policies" -> ClientPolicies(api, client.id, onOpen = links.onOpenPolicy) { links.onNewPolicy(ref) }
                "Billing" -> ClientBilling(api, client.id, links, ref)
                "Documents" -> DocumentsTab(viewModel)
            }
        }
    }
}

@Composable
private fun Overview(client: Client, siteUrl: String, agentName: String, canEdit: Boolean, onEdit: () -> Unit) {
    val context = LocalContext.current
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        client.phone?.let { phone ->
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                    Button(onClick = { context.open(Phone.dialUri(phone), Intent.ACTION_DIAL) }) {
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
            Detail("ID", client.idType?.let { "${Labels.of(it)}${client.idNumberHint?.let { h -> " ($h)" } ?: ""}" })
            Detail("Date of birth", Dates.date(client.dateOfBirth).ifBlank { null })
            Detail("Occupation", client.occupation)
            Detail("Prefers", client.preferredChannel?.let(Labels::of))
            Detail("Town", listOfNotNull(client.address?.town, client.address?.county).joinToString(", ").ifBlank { null })
            Detail("Tags", client.tags.joinToString(", ").ifBlank { null })
            Detail("Notes", client.notes)
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 12.dp)) {
                if (canEdit) OutlinedButton(onClick = onEdit) {
                    Icon(Icons.Default.Edit, contentDescription = null, modifier = Modifier.padding(end = 8.dp))
                    Text("Edit")
                }
                client.email?.let { email ->
                    TextButton(onClick = { context.open("mailto:$email", Intent.ACTION_SENDTO) }) {
                        Icon(Icons.Default.Email, contentDescription = null, modifier = Modifier.padding(end = 8.dp))
                        Text("Email")
                    }
                }
            }
            TextButton(onClick = { context.open("$siteUrl/clients/${client.id}") }) { Text("Open on the web") }
        }
    }
}

@Composable
private fun ClientQuotes(api: BrokerApi, clientId: String, onOpen: (String) -> Unit, onNew: () -> Unit) {
    val vm: QuotesViewModel = viewModel(key = "client-quotes-$clientId", factory = viewModelFactory { initializer { QuotesViewModel(api, clientId) } })
    val state by vm.state.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize()) {
        TextButton(onClick = onNew, modifier = Modifier.padding(horizontal = 8.dp)) {
            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.padding(end = 6.dp)); Text("New quote")
        }
        Loaded(state, onRetry = { vm.load() }) { list ->
            if (list.isEmpty()) Empty("No quotes for this client yet.")
            LazyColumn { items(list, key = { it.id }) { q -> QuoteRow(q) { onOpen(q.id) } } }
        }
    }
}

@Composable
private fun ClientPolicies(api: BrokerApi, clientId: String, onOpen: (String) -> Unit, onNew: () -> Unit) {
    val vm: PoliciesViewModel = viewModel(key = "client-policies-$clientId", factory = viewModelFactory { initializer { PoliciesViewModel(api, clientId) } })
    val state by vm.state.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize()) {
        TextButton(onClick = onNew, modifier = Modifier.padding(horizontal = 8.dp)) {
            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.padding(end = 6.dp)); Text("Add policy")
        }
        Loaded(state, onRetry = { vm.load() }) { list ->
            if (list.isEmpty()) Empty("No policies for this client yet.")
            LazyColumn { items(list, key = { it.id }) { p -> PolicyRow(p) { onOpen(p.id) } } }
        }
    }
}

@Composable
private fun ClientBilling(api: BrokerApi, clientId: String, links: ClientLinks, ref: ClientRef) {
    val invoices: DocumentsViewModel = viewModel(key = "client-invoices-$clientId", factory = viewModelFactory { initializer { DocumentsViewModel(api, false, clientId) } })
    val quotes: DocumentsViewModel = viewModel(key = "client-squotes-$clientId", factory = viewModelFactory { initializer { DocumentsViewModel(api, true, clientId) } })
    val inv by invoices.state.collectAsStateWithLifecycle()
    val qs by quotes.state.collectAsStateWithLifecycle()
    var account by remember { mutableStateOf<app.brokeros.android.data.ClientAccount?>(null) }
    androidx.compose.runtime.LaunchedEffect(clientId) { account = runCatching { api.account(clientId) }.getOrNull() }
    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Row(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TextButton(onClick = { links.onNewInvoice(ref) }) { Text("New invoice") }
                TextButton(onClick = { links.onNewSalesQuote(ref) }) { Text("New sales quote") }
            }
            account?.let { a ->
                Text(
                    "Owes ${money(a.owed, a.currency, decimals = true)}" + if ((a.credit.toBigDecimalOrNull() ?: java.math.BigDecimal.ZERO).signum() > 0) " · credit ${money(a.credit, a.currency, decimals = true)}" else "",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
        }
        item { app.brokeros.android.ui.components.SectionTitle("Invoices", Modifier.padding(horizontal = 16.dp)) }
        when (val s = inv) {
            is Load.Ready -> { if (s.value.isEmpty()) item { Empty("No invoices yet.") }; items(s.value, key = { "i" + it.id }) { d -> DocumentRow(d) { links.onOpenDocument(d.id) } } }
            is Load.Failed -> item { app.brokeros.android.ui.components.ErrorMessage(s.message, { invoices.load() }) }
            Load.Loading -> item { app.brokeros.android.ui.components.Loading(Modifier.padding(16.dp)) }
        }
        item { app.brokeros.android.ui.components.SectionTitle("Sales quotes", Modifier.padding(horizontal = 16.dp)) }
        when (val s = qs) {
            is Load.Ready -> { if (s.value.isEmpty()) item { Empty("No sales quotes yet.") }; items(s.value, key = { "q" + it.id }) { d -> DocumentRow(d) { links.onOpenDocument(d.id) } } }
            is Load.Failed -> item { app.brokeros.android.ui.components.ErrorMessage(s.message, { quotes.load() }) }
            Load.Loading -> item { app.brokeros.android.ui.components.Loading(Modifier.padding(16.dp)) }
        }
    }
}

@Composable
private fun TimelineTab(viewModel: ClientViewModel) {
    val state by viewModel.timeline.collectAsStateWithLifecycle()
    androidx.compose.runtime.LaunchedEffect(Unit) { viewModel.loadTimeline() }
    var kind by rememberSaveable { mutableStateOf("call") }
    var body by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 12.dp)) {
                Choices(null, Labels.activityKinds, kind, { kind = it ?: "call" })
                Field("What happened", body, { body = it }, singleLine = false, minLines = 2)
                FormError(error)
                SubmitButton("Log", busy, body.isNotBlank()) {
                    busy = true
                    scope.launch {
                        try {
                            viewModel.log(kind, body)
                            body = ""
                            error = null
                            toast("Logged")
                        } catch (e: AppException) {
                            error = e.message
                        } finally {
                            busy = false
                        }
                    }
                }
            }
            HorizontalDivider()
        }
        when (val s = state) {
            Load.Loading -> item { app.brokeros.android.ui.components.Loading(Modifier.padding(24.dp)) }
            is Load.Failed -> item { app.brokeros.android.ui.components.ErrorMessage(s.message, { viewModel.loadTimeline() }) }
            is Load.Ready -> {
                if (s.value.isEmpty()) item { Empty("Nothing yet. Log a call or a note above.") }
                items(s.value) { entry ->
                    ListItem(
                        headlineContent = { Text(entry.title) },
                        supportingContent = entry.detail?.let { { Text(it) } },
                        trailingContent = { Text(Dates.relative(entry.at), style = MaterialTheme.typography.labelSmall) },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun ClientTasks(viewModel: ClientViewModel, api: BrokerApi) {
    val tasksVm = viewModel.tasks.viewModel
    val state by tasksVm.state.collectAsStateWithLifecycle()
    var adding by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Task?>(null) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    Column(Modifier.fillMaxSize()) {
        TextButton(onClick = { adding = true }, modifier = Modifier.padding(horizontal = 8.dp)) {
            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.padding(end = 6.dp))
            Text("Add task")
        }
        Loaded(state, onRetry = { tasksVm.load() }) { list ->
            if (list.isEmpty()) Empty("No open tasks for this client.")
            LazyColumn {
                items(list, key = { it.id }) { task ->
                    TaskRow(task, onToggle = {
                        scope.launch {
                            try { tasksVm.toggle(task); toast("Done: ${task.title}") } catch (e: AppException) { toast(e.message ?: "Try again.") }
                        }
                    }, onOpen = { editing = task })
                    HorizontalDivider()
                }
            }
        }
    }
    if (adding || editing != null) {
        TaskSheet(api, editing, EntityRef("client", viewModel.id), onDismiss = { adding = false; editing = null }) {
            adding = false; editing = null; tasksVm.load()
        }
    }
}

@Composable
private fun DocumentsTab(viewModel: ClientViewModel) {
    val state by viewModel.documents.collectAsStateWithLifecycle()
    androidx.compose.runtime.LaunchedEffect(Unit) { viewModel.loadDocuments() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    var picked by remember { mutableStateOf<Picked?>(null) }
    var captureUri by remember { mutableStateOf<Uri?>(null) }

    val read: (Uri) -> Unit = { uri ->
        scope.launch {
            picked = try {
                withContext(Dispatchers.IO) { Files.read(context, uri) }
            } catch (e: Exception) {
                toast("That file could not be read."); null
            }
        }
    }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) captureUri?.let(read) }
    val chooser = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(read) }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 12.dp)) {
                Button(onClick = { Files.newCapture(context).also { captureUri = it; camera.launch(it) } }) { Text("Take photo") }
                OutlinedButton(onClick = { chooser.launch(arrayOf("image/*", "application/pdf")) }) { Text("Choose file") }
            }
            Text(
                "Upload PDFs without a password, or colleagues will need the password to open them.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        when (val s = state) {
            Load.Loading -> item { app.brokeros.android.ui.components.Loading(Modifier.padding(24.dp)) }
            is Load.Failed -> item { app.brokeros.android.ui.components.ErrorMessage(s.message, { viewModel.loadDocuments() }) }
            is Load.Ready -> {
                if (s.value.isEmpty()) item { Empty("No documents yet. Photograph an ID, KRA PIN or logbook.") }
                items(s.value, key = { it.id }) { doc ->
                    ListItem(
                        headlineContent = { Text(doc.title) },
                        supportingContent = {
                            Text(listOfNotNull(Labels.of(doc.category), doc.expiresOn?.let { "expires ${Dates.date(it)}" }).joinToString(" · "))
                        },
                        modifier = Modifier.clickable {
                            scope.launch {
                                try { context.open(viewModel.link(doc.id)) } catch (e: AppException) { toast(e.message ?: "Try again.") }
                            }
                        },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
    picked?.let { file ->
        UploadDialog(file, onDismiss = { picked = null }) { category, title, expires ->
            viewModel.upload(file, category, title, expires)
            picked = null
            toast("Uploaded")
        }
    }
}

@Composable
private fun UploadDialog(file: Picked, onDismiss: () -> Unit, onUpload: suspend (String, String, java.time.LocalDate?) -> Unit) {
    var category by rememberSaveable { mutableStateOf("kyc_id") }
    var title by rememberSaveable { mutableStateOf("") }
    var expires by remember { mutableStateOf<java.time.LocalDate?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Upload ${file.name}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${file.bytes.size / 1024} KB", style = MaterialTheme.typography.bodySmall)
                Choices("What is it", Labels.documentCategories, category, { category = it ?: "other" })
                Field("Title", title, { title = it }, hint = "Optional, e.g. Logbook KDA 123A")
                DateField("Expires", expires, { expires = it })
                FormError(error)
            }
        },
        confirmButton = {
            Box(Modifier.fillMaxWidth()) {
                SubmitButton("Upload", busy) {
                    busy = true
                    scope.launch {
                        try { onUpload(category, title, expires) } catch (e: AppException) { error = e.message } finally { busy = false }
                    }
                }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } },
    )
}
