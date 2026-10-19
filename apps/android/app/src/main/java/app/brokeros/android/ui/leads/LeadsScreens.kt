package app.brokeros.android.ui.leads

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
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.core.Phone
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ConvertLead
import app.brokeros.android.data.Lead
import app.brokeros.android.data.LeadInput
import app.brokeros.android.data.LeadPipeline
import app.brokeros.android.data.Money
import app.brokeros.android.data.convertLead
import app.brokeros.android.data.createLead
import app.brokeros.android.data.lead
import app.brokeros.android.data.leads
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.sendOrQueue
import app.brokeros.android.data.pipeline
import app.brokeros.android.data.updateLead
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.DateField
import app.brokeros.android.ui.components.Detail
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.MultiChoices
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class LeadsState(val pipeline: LeadPipeline? = null, val leads: Load<List<Lead>> = Load.Loading)

class LeadsViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow(LeadsState())
    val state = _state.asStateFlow()
    var stage: String? = null
        private set
    var query: String = ""
        private set

    init { load() }

    fun filter(stage: String?, query: String = this.query) {
        this.stage = stage
        this.query = query
        load()
    }

    fun load() = viewModelScope.launch {
        _state.value = _state.value.copy(leads = Load.Loading)
        _state.value = try {
            LeadsState(pipeline = runCatching { api.pipeline() }.getOrNull(), leads = Load.Ready(api.leads(stage, query)))
        } catch (e: AppException) {
            _state.value.copy(leads = Load.Failed(e.message ?: "Try again."))
        }
    }
}

@Composable
fun LeadsScreen(viewModel: LeadsViewModel, onOpen: (String) -> Unit, onAdd: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var stage by rememberSaveable { mutableStateOf(viewModel.stage) }
    var query by rememberSaveable { mutableStateOf(viewModel.query) }
    LaunchedEffect(query) {
        delay(300)
        if (query != viewModel.query) viewModel.filter(stage, query)
    }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = stage == null, onClick = { stage = null; viewModel.filter(null) }, label = { Text("All") })
                Labels.leadStages.forEach { s ->
                    val summary = state.pipeline?.stages?.firstOrNull { it.stage == s }
                    FilterChip(
                        selected = stage == s,
                        onClick = { stage = s; viewModel.filter(s) },
                        label = { Text("${Labels.of(s)} ${summary?.count ?: ""}".trim()) },
                    )
                }
            }
            state.pipeline?.let { p ->
                val open = p.stages.filter { it.stage !in listOf("won", "lost") }
                val total = open.sumOf { it.estimatedPremium.amount.toBigDecimalOrNull() ?: java.math.BigDecimal.ZERO }
                Text(
                    "Open pipeline: ${money(total.toPlainString(), open.firstOrNull()?.estimatedPremium?.currency ?: "KES")}" +
                        if (p.followUpsDue > 0) " · ${p.followUpsDue} follow-ups due" else "",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search leads") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            )
            PullToRefreshBox(isRefreshing = state.leads is Load.Loading, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
                Loaded(state.leads, onRetry = { viewModel.load() }) { list ->
                    if (list.isEmpty()) Empty("No leads here. Add one from a call, WhatsApp or referral.")
                    LazyColumn(Modifier.fillMaxSize()) {
                        items(list, key = { it.id }) { lead ->
                            ListItem(
                                headlineContent = { Text(lead.name) },
                                supportingContent = {
                                    Text(listOfNotNull(
                                        lead.interests.joinToString(", ") { Labels.of(it) }.ifBlank { null },
                                        lead.estimatedPremium?.let { money(it.amount, it.currency) },
                                        lead.nextFollowUpAt?.let { "follow up ${Dates.relative(it)}" },
                                    ).joinToString(" · "))
                                },
                                trailingContent = { Text(Labels.of(lead.stage), style = MaterialTheme.typography.labelMedium) },
                                modifier = Modifier.clickable { onOpen(lead.id) },
                            )
                            HorizontalDivider()
                        }
                        item { Box(Modifier.padding(40.dp)) }
                    }
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = onAdd,
            icon = { Icon(Icons.Default.Add, contentDescription = null) },
            text = { Text("Add lead") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        )
    }
}

class LeadViewModel(private val api: BrokerApi, private val id: String) : ViewModel() {
    private val _state = MutableStateFlow<Load<Lead>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.lead(id)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun move(lead: Lead, stage: String, lostReason: String? = null) {
        _state.value = Load.Ready(api.updateLead(lead, LeadInput(stage = stage, lostReason = lostReason)))
    }

    suspend fun convert(lead: Lead): String {
        val parts = lead.name.trim().split(" ")
        return api.convertLead(
            lead.id,
            ConvertLead(firstName = parts.first(), lastName = parts.drop(1).joinToString(" ").ifBlank { parts.first() }, allowDuplicate = true),
        ).clientId
    }
}

@Composable
fun LeadScreen(viewModel: LeadViewModel, agentName: String, onEdit: () -> Unit, onOpenClient: (String) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    var losing by remember { mutableStateOf(false) }
    Loaded(state, onRetry = { viewModel.load() }) { lead ->
        FormColumn {
            Text(lead.name, style = MaterialTheme.typography.headlineSmall)
            Text(Labels.of(lead.stage) + (lead.lostReason?.let { ": $it" } ?: ""), color = MaterialTheme.colorScheme.onSurfaceVariant)
            lead.phone?.let { phone ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { context.open(Phone.dialUri(phone), Intent.ACTION_DIAL) }) {
                        Icon(Icons.Default.Call, contentDescription = null, modifier = Modifier.padding(end = 8.dp)); Text("Call")
                    }
                    OutlinedButton(onClick = { context.open(Phone.whatsAppUrl(phone, "Hello ${lead.name.substringBefore(' ')}, this is $agentName.")) }) {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null, modifier = Modifier.padding(end = 8.dp)); Text("WhatsApp")
                    }
                }
            }
            Detail("Phone", lead.phone?.let(Phone::display))
            Detail("Email", lead.email)
            Detail("Interested in", lead.interests.joinToString(", ") { Labels.of(it) }.ifBlank { null })
            Detail("Estimated yearly premium", lead.estimatedPremium?.let { money(it.amount, it.currency) })
            Detail("Next follow-up", lead.nextFollowUpAt?.let { "${Dates.date(it)} (${Dates.relative(it)})" })
            Detail("Source", Labels.of(lead.source))
            Detail("Notes", lead.notes)
            if (lead.clientId == null) {
                Text("Move to", style = MaterialTheme.typography.labelLarge)
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Labels.leadStages.filter { it != lead.stage }.forEach { s ->
                        FilterChip(selected = false, onClick = {
                            when (s) {
                                "lost" -> losing = true
                                "won" -> scope.launch {
                                    try {
                                        val clientId = viewModel.convert(lead)
                                        toast("${lead.name} is now a client")
                                        onOpenClient(clientId)
                                    } catch (e: AppException) { toast(e.message ?: "Try again.") }
                                }
                                else -> scope.launch {
                                    try { viewModel.move(lead, s); toast("Moved to ${Labels.of(s)}") } catch (e: AppException) { toast(e.message ?: "Try again.") }
                                }
                            }
                        }, label = { Text(if (s == "won") "Won (make client)" else Labels.of(s)) })
                    }
                }
            } else {
                TextButton(onClick = { onOpenClient(lead.clientId) }) { Text("Open the client") }
            }
            OutlinedButton(onClick = onEdit, modifier = Modifier.fillMaxWidth()) { Text("Edit lead") }
        }
        if (losing) {
            var reason by remember { mutableStateOf("") }
            AlertDialog(
                onDismissRequest = { losing = false },
                title = { Text("Mark as lost") },
                text = { Field("Reason", reason, { reason = it }, hint = "e.g. went with another agent") },
                confirmButton = {
                    TextButton(enabled = reason.isNotBlank(), onClick = {
                        scope.launch {
                            try { viewModel.move(lead, "lost", reason.trim()); losing = false; toast("Marked as lost") } catch (e: AppException) { toast(e.message ?: "Try again.") }
                        }
                    }) { Text("Mark as lost") }
                },
                dismissButton = { TextButton(onClick = { losing = false }) { Text("Cancel") } },
            )
        }
    }
}

/** Add a lead, or edit one. */
@Composable
fun LeadFormScreen(api: BrokerApi, existing: Lead?, onSaved: (String) -> Unit) {
    val outbox = app.brokeros.android.ui.components.LocalOutbox.current
    var name by rememberSaveable { mutableStateOf(existing?.name ?: "") }
    var phone by rememberSaveable { mutableStateOf(existing?.phone ?: "") }
    var email by rememberSaveable { mutableStateOf(existing?.email ?: "") }
    var interests by rememberSaveable { mutableStateOf(existing?.interests ?: emptyList()) }
    var source by rememberSaveable { mutableStateOf(existing?.source) }
    var premium by rememberSaveable { mutableStateOf(existing?.estimatedPremium?.amount?.substringBefore('.') ?: "") }
    var followUp by remember { mutableStateOf(existing?.nextFollowUpAt?.let { Dates.parseInstant(it)?.atZone(Dates.zone())?.toLocalDate() }) }
    var notes by rememberSaveable { mutableStateOf(existing?.notes ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    FormColumn {
        Field("Name", name, { name = it })
        Field("Phone", phone, { phone = it }, keyboard = KeyboardType.Phone)
        Field("Email", email, { email = it }, keyboard = KeyboardType.Email, hint = "Optional")
        MultiChoices("Interested in", Labels.interests, interests, { interests = it })
        Field("Estimated yearly premium (KES)", premium, { premium = it.filter(Char::isDigit) }, keyboard = KeyboardType.Number, hint = "Optional")
        DateField("Next follow-up", followUp, { followUp = it })
        Choices("Where they came from", Labels.leadSources, source, { source = it }, allowNone = true)
        Field("Notes", notes, { notes = it }, singleLine = false, minLines = 3)
        FormError(error)
        SubmitButton(if (existing == null) "Add lead" else "Save lead", busy, name.isNotBlank()) {
            busy = true
            scope.launch {
                try {
                    val input = LeadInput(
                        name = name.trim(),
                        phone = phone.trim().ifBlank { null },
                        email = email.trim().ifBlank { null },
                        interests = interests,
                        source = source,
                        estimatedPremium = premium.takeIf { it.isNotBlank() }?.let { Money(it, "KES") },
                        nextFollowUpAt = followUp?.let(Dates::morningOf),
                        notes = notes.trim().ifBlank { null },
                    )
                    if (existing == null && outbox != null) {
                        val sent = api.sendOrQueue(outbox, "POST", "/leads", input, "Lead: ${input.name}", idempotencyKey = key)
                        toast(if (sent) "Lead added" else "Saved. It will be sent when you're back online.")
                        onSaved("") // the list; the new lead has no page yet if it is waiting to be sent
                    } else {
                        val saved = if (existing == null) api.createLead(input, key) else api.updateLead(existing, input)
                        toast(if (existing == null) "Lead added" else "Lead saved")
                        onSaved(saved.id)
                    }
                } catch (e: AppException) {
                    error = e.message
                } finally {
                    busy = false
                }
            }
        }
    }
}
