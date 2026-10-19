package app.brokeros.android.ui.insurance

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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
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
import app.brokeros.android.data.Activate
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientRef
import app.brokeros.android.data.FromQuote
import app.brokeros.android.data.PaymentIn
import app.brokeros.android.data.Policy
import app.brokeros.android.data.PolicyCreate
import app.brokeros.android.data.PolicySummary
import app.brokeros.android.data.Quote
import app.brokeros.android.data.Remind
import app.brokeros.android.data.RenewalQuote
import app.brokeros.android.data.RenewalUpdate
import app.brokeros.android.data.Risk
import app.brokeros.android.data.activatePolicy
import app.brokeros.android.data.createPolicy
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.policies
import app.brokeros.android.data.policy
import app.brokeros.android.data.policyFromQuote
import app.brokeros.android.data.recordPolicyPayment
import app.brokeros.android.data.remind
import app.brokeros.android.data.renewalQuote
import app.brokeros.android.data.renewalStage
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.ClientPicker
import app.brokeros.android.ui.components.DateField
import app.brokeros.android.ui.components.Detail
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.Loading
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

private val POLICY_STATUSES = listOf("active", "pending", "expired", "cancelled")
private val PAYMENT_METHODS = listOf("mpesa", "bank", "cash", "cheque", "card", "other")

class PoliciesViewModel(private val api: BrokerApi, private val clientId: String? = null) : ViewModel() {
    private val _state = MutableStateFlow<Load<List<PolicySummary>>>(Load.Loading)
    val state = _state.asStateFlow()
    var status: String? = null
    var query: String = ""

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = Load.Loading
        _state.value = try { Load.Ready(api.policies(clientId, status, query)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }
}

@Composable
fun PolicyRow(p: PolicySummary, onOpen: () -> Unit) {
    ListItem(
        headlineContent = { Text(p.description) },
        supportingContent = {
            Text(listOfNotNull(p.client.displayName, p.insurerName, "ends ${Dates.date(p.endDate)} (${Dates.relative(p.endDate)})").joinToString(" · "))
        },
        trailingContent = {
            Column(horizontalAlignment = Alignment.End) {
                Text(Labels.of(p.status), style = MaterialTheme.typography.labelMedium)
                if ((p.balance.toBigDecimalOrNull() ?: java.math.BigDecimal.ZERO).signum() > 0) {
                    Text("owes ${money(p.balance, p.currency)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        modifier = Modifier.clickable(onClick = onOpen),
    )
    HorizontalDivider()
}

@Composable
fun PoliciesScreen(viewModel: PoliciesViewModel, onOpen: (String) -> Unit, onNew: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var status by rememberSaveable { mutableStateOf(viewModel.status) }
    var query by rememberSaveable { mutableStateOf(viewModel.query) }
    LaunchedEffect(query) { delay(300); if (query != viewModel.query) { viewModel.query = query; viewModel.load() } }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = status == null, onClick = { status = null; viewModel.status = null; viewModel.load() }, label = { Text("All") })
                POLICY_STATUSES.forEach { s ->
                    FilterChip(selected = status == s, onClick = { status = s; viewModel.status = s; viewModel.load() }, label = { Text(Labels.of(s)) })
                }
            }
            OutlinedTextField(
                value = query, onValueChange = { query = it }, singleLine = true,
                placeholder = { Text("Search policy, client or registration") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            PullToRefreshBox(isRefreshing = state is Load.Loading, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
                Loaded(state, onRetry = { viewModel.load() }) { list ->
                    if (list.isEmpty()) Empty("No policies here yet.")
                    LazyColumn(Modifier.fillMaxSize()) {
                        items(list, key = { it.id }) { p -> PolicyRow(p) { onOpen(p.id) } }
                        item { Box(Modifier.padding(40.dp)) }
                    }
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = onNew,
            icon = { Icon(Icons.Default.Add, contentDescription = null) },
            text = { Text("Add policy") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        )
    }
}

class PolicyViewModel(private val api: BrokerApi, val id: String) : ViewModel() {
    private val _state = MutableStateFlow<Load<Policy>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.policy(id)) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun pay(input: PaymentIn) { _state.value = Load.Ready(api.recordPolicyPayment(id, input)) }
    suspend fun activate() { _state.value = Load.Ready(api.activatePolicy(id, Activate())) }
    suspend fun stage(stage: String, lostReason: String? = null) { _state.value = Load.Ready(api.renewalStage(id, RenewalUpdate(stage, lostReason))) }
    suspend fun remindWhatsApp(): String? = api.remind(id, Remind("whatsapp")).whatsappUrl
    suspend fun remindEmail(): String? = api.remind(id, Remind("email")).emailedTo
    suspend fun renewalQuote(productIds: List<String>, sumInsured: String?): String =
        api.renewalQuote(id, RenewalQuote(productIds, Risk(sumInsured = sumInsured, renewal = true))).id
}

@Composable
fun PolicyScreen(viewModel: PolicyViewModel, api: BrokerApi, canPay: Boolean, onOpenClient: (String) -> Unit, onOpenQuote: (String) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    var paying by remember { mutableStateOf(false) }
    var losing by remember { mutableStateOf(false) }
    var renewing by remember { mutableStateOf(false) }
    fun act(done: String, block: suspend () -> Unit) = scope.launch {
        try { block(); toast(done) } catch (e: AppException) { toast(e.message ?: "Try again.") }
    }
    Loaded(state, onRetry = { viewModel.load() }) { p ->
        FormColumn {
            Text(p.description, style = MaterialTheme.typography.headlineSmall)
            Text(listOfNotNull(Labels.of(p.status), p.policyNumber, p.insurerName).joinToString(" · "), color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick = { onOpenClient(p.client.id) }) { Text(p.client.displayName) }
            Card {
                Column(Modifier.padding(14.dp)) {
                    Detail("Cover", "${Dates.date(p.startDate)} to ${Dates.date(p.endDate)} (ends ${Dates.relative(p.endDate)})")
                    Detail("Premium", money(p.totalPremium, p.currency, decimals = true))
                    Detail("Paid", money(p.paid, p.currency, decimals = true))
                    Detail("Balance", money(p.balance, p.currency, decimals = true))
                    Detail("Sum insured", p.sumInsured?.let { money(it, p.currency) })
                    Detail("Product", p.productName)
                }
            }
            p.details.forEach { Detail(it.label, it.value) }
            if (p.status == "pending") {
                Button(onClick = { act("Policy active") { viewModel.activate() } }, modifier = Modifier.fillMaxWidth()) { Text("Insurer confirmed: make active") }
            }
            if (canPay && (p.balance.toBigDecimalOrNull() ?: java.math.BigDecimal.ZERO).signum() > 0) {
                Button(onClick = { paying = true }, modifier = Modifier.fillMaxWidth()) { Text("Record payment") }
            }
            SectionTitle("Renewal: ${Labels.of(p.renewalStage)}")
            p.lostReason?.let { Text("Lost: $it") }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { scope.launch { try { viewModel.remindWhatsApp()?.let(context::open) ?: toast("No phone number for this client") } catch (e: AppException) { toast(e.message ?: "Try again.") } } }) { Text("WhatsApp reminder") }
                OutlinedButton(onClick = { scope.launch { try { toast(viewModel.remindEmail()?.let { "Reminder emailed to $it" } ?: "No email for this client") } catch (e: AppException) { toast(e.message ?: "Try again.") } } }) { Text("Email reminder") }
            }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (p.renewalStage == "due") OutlinedButton(onClick = { act("Marked as contacted") { viewModel.stage("contacted") } }) { Text("Contacted") }
                if (p.renewalStage !in listOf("renewed", "lost")) OutlinedButton(onClick = { losing = true }) { Text("Lost") }
                if (p.renewalStage == "lost") OutlinedButton(onClick = { act("Reopened") { viewModel.stage("due") } }) { Text("Reopen") }
                val renewalQuote = p.renewalQuoteId
                if (renewalQuote != null) {
                    OutlinedButton(onClick = { onOpenQuote(renewalQuote) }) { Text("Open renewal quote") }
                } else if (p.renewalStage !in listOf("renewed", "lost")) {
                    OutlinedButton(onClick = { renewing = true }) { Text("Quote renewal") }
                }
            }
            if (p.payments.isNotEmpty()) {
                SectionTitle("Payments")
                p.payments.forEach { pay ->
                    ListItem(
                        headlineContent = { Text(money(pay.amount, pay.currency, decimals = true) + if (pay.voidedAt != null) " (voided)" else "") },
                        supportingContent = { Text(listOfNotNull(Dates.date(pay.paidOn), Labels.of(pay.method), pay.reference, "paid to ${pay.paidTo}").joinToString(" · ")) },
                    )
                }
            }
            p.notes?.let { Detail("Notes", it) }
        }
        if (paying) PaymentDialog(p.balance, onDismiss = { paying = false }) { input -> viewModel.pay(input); paying = false; toast("Payment recorded") }
        if (losing) {
            var reason by remember { mutableStateOf("") }
            AlertDialog(
                onDismissRequest = { losing = false },
                title = { Text("Renewal lost") },
                text = { Field("Reason", reason, { reason = it }, hint = "e.g. sold the car") },
                confirmButton = { TextButton(enabled = reason.isNotBlank(), onClick = { losing = false; act("Marked as lost") { viewModel.stage("lost", reason.trim()) } }) { Text("Mark as lost") } },
                dismissButton = { TextButton(onClick = { losing = false }) { Text("Cancel") } },
            )
        }
        if (renewing) {
            RenewalQuoteDialog(api, p, onDismiss = { renewing = false }) { productIds, sum ->
                val quoteId = viewModel.renewalQuote(productIds, sum)
                renewing = false
                toast("Renewal quote created")
                onOpenQuote(quoteId)
            }
        }
    }
}

@Composable
fun PaymentDialog(balance: String, onDismiss: () -> Unit, onSave: suspend (PaymentIn) -> Unit) {
    var amount by remember { mutableStateOf(balance.substringBefore('.').let { if (balance.contains('.') && !balance.endsWith(".00") && !balance.endsWith(".0000")) balance else it }) }
    var method by remember { mutableStateOf("mpesa") }
    var reference by remember { mutableStateOf("") }
    var on by remember { mutableStateOf<LocalDate?>(LocalDate.now()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Record payment") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Field("Amount (KES)", amount, { amount = amountOf(it) }, keyboard = KeyboardType.Decimal)
                Choices("Paid by", PAYMENT_METHODS, method, { method = it ?: "mpesa" })
                Field("Reference", reference, { reference = it.uppercase() }, hint = "e.g. M-Pesa code")
                DateField("Paid on", on, { on = it })
                FormError(error)
            }
        },
        confirmButton = {
            SubmitButton("Record payment", busy, amount.isNotBlank() && on != null) {
                busy = true
                scope.launch {
                    try { onSave(PaymentIn(amount, on!!.toString(), method, reference = reference.trim().ifBlank { null })) } catch (e: AppException) { error = e.message } finally { busy = false }
                }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } },
    )
}

@Composable
private fun RenewalQuoteDialog(api: BrokerApi, policy: Policy, onDismiss: () -> Unit, onCreate: suspend (List<String>, String?) -> Unit) {
    var catalogue by remember { mutableStateOf<Catalogue?>(null) }
    var classCode by remember { mutableStateOf<String?>(policy.classCode.ifBlank { null }) }
    var selected by remember { mutableStateOf<List<String>>(emptyList()) }
    var sum by remember { mutableStateOf(policy.sumInsured?.substringBefore('.') ?: "") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        try {
            catalogue = api.catalogue()
            selected = catalogue!!.products.filter { it.classCode == classCode }.map { it.id }
        } catch (e: AppException) { error = e.message }
    }
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Quote the renewal") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val c = catalogue
                if (c == null) { FormError(error); if (error == null) Loading() } else {
                    ProductPicker(c, classCode, { classCode = it; selected = c.products.filter { p -> p.classCode == it }.map { p -> p.id } }, selected, { selected = it })
                    Field("Sum insured (KES)", sum, { sum = amountOf(it) }, keyboard = KeyboardType.Number)
                    FormError(error)
                }
            }
        },
        confirmButton = {
            SubmitButton("Create renewal quote", busy, selected.isNotEmpty()) {
                busy = true
                scope.launch { try { onCreate(selected, sum.ifBlank { null }) } catch (e: AppException) { error = e.message } finally { busy = false } }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } },
    )
}

/** A policy: from an accepted quote ([quote]), or an existing policy entered by hand. */
@Composable
fun NewPolicyScreen(api: BrokerApi, client: ClientRef?, quote: Quote?, onCreated: (String) -> Unit) {
    var who by remember { mutableStateOf(client ?: quote?.client) }
    var insurer by rememberSaveable { mutableStateOf("") }
    var covered by rememberSaveable { mutableStateOf("") }
    var premium by rememberSaveable { mutableStateOf("") }
    var number by rememberSaveable { mutableStateOf("") }
    var start by remember { mutableStateOf<LocalDate?>(LocalDate.now()) }
    var end by remember { mutableStateOf<LocalDate?>(null) }
    var paid by rememberSaveable { mutableStateOf(false) }
    var paidAmount by rememberSaveable { mutableStateOf("") }
    var method by rememberSaveable { mutableStateOf("mpesa") }
    var reference by rememberSaveable { mutableStateOf("") }
    var paidOn by remember { mutableStateOf<LocalDate?>(LocalDate.now()) }
    var confirmed by rememberSaveable { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    val accepted = quote?.optionList?.firstOrNull { it.position == quote.acceptedPosition }
    LaunchedEffect(accepted) { if (accepted != null && paidAmount.isBlank()) paidAmount = accepted.clientTotal }

    FormColumn {
        if (quote != null && accepted != null) {
            Text("The client accepted option ${accepted.position}: ${accepted.insurerName}, ${money(accepted.clientTotal, quote.currency, decimals = true)}.")
        } else {
            ClientPicker(api, who) { who = it }
            Field("Insurer", insurer, { insurer = it })
            Field("What is covered", covered, { covered = it }, hint = "e.g. KCB 789C Honda Fit")
            Field("Total premium (KES)", premium, { premium = amountOf(it) }, keyboard = KeyboardType.Decimal)
        }
        Field("Policy number", number, { number = it }, hint = "Optional, from the insurer")
        DateField("Cover starts", start, { start = it })
        DateField("Cover ends", end, { end = it })
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { paid = !paid }) {
            Checkbox(checked = paid, onCheckedChange = { paid = it }); Text("The premium has been paid")
        }
        if (paid) {
            Field("Amount (KES)", paidAmount, { paidAmount = amountOf(it) }, keyboard = KeyboardType.Decimal)
            Choices("Paid by", PAYMENT_METHODS, method, { method = it ?: "mpesa" })
            Field("Reference", reference, { reference = it.uppercase() })
            DateField("Paid on", paidOn, { paidOn = it })
        }
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { confirmed = !confirmed }) {
            Checkbox(checked = confirmed, onCheckedChange = { confirmed = it }); Text("The insurer has confirmed cover")
        }
        FormError(error)
        val ready = start != null && (quote != null || (who != null && insurer.isNotBlank() && covered.isNotBlank() && premium.isNotBlank()))
        SubmitButton("Save policy", busy, ready) {
            busy = true
            scope.launch {
                try {
                    val payment = if (paid && paidAmount.isNotBlank() && paidOn != null) PaymentIn(paidAmount, paidOn.toString(), method, reference = reference.trim().ifBlank { null }) else null
                    val policy = if (quote != null) {
                        api.policyFromQuote(FromQuote(quote.id, start.toString(), end?.toString(), accepted?.position, number.trim().ifBlank { null }, insurerConfirmed = confirmed, payment = payment), key)
                    } else {
                        api.createPolicy(
                            PolicyCreate(
                                clientId = who!!.id, startDate = start.toString(), endDate = end?.toString(), totalPremium = premium,
                                insurerName = insurer.trim(), description = covered.trim(), policyNumber = number.trim().ifBlank { null },
                                insurerConfirmed = confirmed, payment = payment,
                            ),
                            key,
                        )
                    }
                    toast("Policy saved")
                    onCreated(policy.id)
                } catch (e: AppException) { error = e.message } finally { busy = false }
            }
        }
    }
}
