package app.brokeros.android.ui.money

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
import app.brokeros.android.core.Phone
import app.brokeros.android.data.AllocationTo
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BillingDocument
import app.brokeros.android.data.BillingSummary
import app.brokeros.android.data.BillingSummaryRow
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.CreditNoteCreate
import app.brokeros.android.data.DocumentSent
import app.brokeros.android.data.EtimsIn
import app.brokeros.android.data.PaymentCreate
import app.brokeros.android.data.Prompt
import app.brokeros.android.data.SendDocument
import app.brokeros.android.data.Versioned
import app.brokeros.android.data.account
import app.brokeros.android.data.applyCredit
import app.brokeros.android.data.billingDocument
import app.brokeros.android.data.billingSummary
import app.brokeros.android.data.convertSalesQuote
import app.brokeros.android.data.creditNote
import app.brokeros.android.data.invoices
import app.brokeros.android.data.issue
import app.brokeros.android.data.mpesaConnection
import app.brokeros.android.data.mpesaPrompt
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.prompt
import app.brokeros.android.data.recordEtims
import app.brokeros.android.data.recordPayment
import app.brokeros.android.data.salesQuotes
import app.brokeros.android.data.sendDocument
import app.brokeros.android.data.voidDocument
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
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.home.money
import app.brokeros.android.ui.insurance.amountOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal
import java.time.LocalDate

private val INVOICE_STATUSES = listOf("draft", "issued", "part_paid", "paid", "void")
private val QUOTE_STATUSES = listOf("draft", "sent", "accepted", "declined", "converted", "expired")
private val METHODS = listOf("mpesa", "bank", "cash", "cheque", "card", "other")

private fun positive(amount: String) = (amount.toBigDecimalOrNull() ?: BigDecimal.ZERO).signum() > 0

class DocumentsViewModel(private val api: BrokerApi, val quotes: Boolean, private val clientId: String? = null) : ViewModel() {
    private val _state = MutableStateFlow<Load<List<BillingSummaryRow>>>(Load.Loading)
    val state = _state.asStateFlow()
    private val _summary = MutableStateFlow<BillingSummary?>(null)
    val summary = _summary.asStateFlow()
    var status: String? = null

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = Load.Loading
        if (!quotes && clientId == null) _summary.value = runCatching { api.billingSummary() }.getOrNull()
        _state.value = try {
            Load.Ready(if (quotes) api.salesQuotes(clientId, status) else api.invoices(clientId, status))
        } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }
}

@Composable
fun DocumentRow(d: BillingSummaryRow, onOpen: () -> Unit) {
    ListItem(
        headlineContent = { Text(listOfNotNull(d.number ?: "Draft", d.client.displayName).joinToString(" · ")) },
        supportingContent = {
            Text(listOfNotNull(
                money(d.total, d.currency, decimals = true),
                d.dueDate?.takeIf { positive(d.balance) && d.status != "draft" }?.let { "due ${Dates.relative(it)}" },
                d.validUntil?.takeIf { d.status in listOf("draft", "sent") }?.let { "valid until ${Dates.date(it)}" },
            ).joinToString(" · "))
        },
        trailingContent = { Text(Labels.of(d.status), style = MaterialTheme.typography.labelMedium) },
        modifier = Modifier.clickable(onClick = onOpen),
    )
    HorizontalDivider()
}

@Composable
fun DocumentsScreen(viewModel: DocumentsViewModel, onOpen: (String) -> Unit, onNew: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val summary by viewModel.summary.collectAsStateWithLifecycle()
    var status by rememberSaveable { mutableStateOf(viewModel.status) }
    val statuses = if (viewModel.quotes) QUOTE_STATUSES else INVOICE_STATUSES
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            summary?.let { s ->
                Card(Modifier.fillMaxWidth().padding(16.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Detail("Clients owe you", money(s.outstanding, s.currency, decimals = true))
                        Detail("Overdue", "${money(s.overdue, s.currency, decimals = true)} (${s.overdueCount} invoices)")
                        Detail("Collected this month", money(s.collectedThisMonth, s.currency, decimals = true))
                        if (s.etimsPending > 0) Detail("eTIMS details missing", "${s.etimsPending} documents")
                    }
                }
            }
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = status == null, onClick = { status = null; viewModel.status = null; viewModel.load() }, label = { Text("All") })
                statuses.forEach { s -> FilterChip(selected = status == s, onClick = { status = s; viewModel.status = s; viewModel.load() }, label = { Text(Labels.of(s)) }) }
            }
            PullToRefreshBox(isRefreshing = state is Load.Loading, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
                Loaded(state, onRetry = { viewModel.load() }) { list ->
                    if (list.isEmpty()) Empty(if (viewModel.quotes) "No sales quotes here yet." else "No invoices here yet.")
                    LazyColumn(Modifier.fillMaxSize()) {
                        items(list, key = { it.id }) { d -> DocumentRow(d) { onOpen(d.id) } }
                        item { Box(Modifier.padding(40.dp)) }
                    }
                }
            }
        }
        ExtendedFloatingActionButton(
            onClick = onNew,
            icon = { Icon(Icons.Default.Add, contentDescription = null) },
            text = { Text(if (viewModel.quotes) "New sales quote" else "New invoice") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        )
    }
}

class DocumentViewModel(private val api: BrokerApi, val id: String) : ViewModel() {
    private val _state = MutableStateFlow<Load<Versioned<BillingDocument>>>(Load.Loading)
    val state = _state.asStateFlow()
    var credit by mutableStateOf("0")
        private set
    var mpesa by mutableStateOf(false)
        private set

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try {
            val doc = api.billingDocument(id)
            credit = runCatching { api.account(doc.value.client.id).credit }.getOrDefault("0")
            mpesa = runCatching { api.mpesaConnection()?.status == "active" }.getOrDefault(false)
            Load.Ready(doc)
        } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    private suspend fun refresh() { load().join() }

    suspend fun issue() { api.issue(id); refresh() }
    suspend fun send(email: String?, message: String): DocumentSent = api.sendDocument(id, SendDocument(email?.trim()?.ifBlank { null }, message)).also { refresh() }
    suspend fun void(reason: String) { api.voidDocument(id, reason); refresh() }
    suspend fun creditNote(reason: String): String = api.creditNote(CreditNoteCreate(id, reason), newIdempotencyKey()).id
    suspend fun convert(): String = api.convertSalesQuote(id).id
    suspend fun applyCredit() { api.applyCredit(id); refresh() }
    suspend fun etims(cu: String, url: String?) { api.recordEtims(id, EtimsIn(cu, url)); refresh() }
    suspend fun pay(doc: BillingDocument, amount: String, method: String, reference: String?, on: LocalDate) {
        api.recordPayment(PaymentCreate(doc.client.id, amount, on.toString(), method, reference, listOf(AllocationTo(id, amount))), newIdempotencyKey())
        refresh()
    }
    suspend fun prompt(phone: String?): Prompt = api.mpesaPrompt(id, phone)
    suspend fun promptStatus(promptId: String): Prompt = api.prompt(promptId)
    suspend fun pdf(): ByteArray = api.bytes("/billing-documents/$id/pdf")
}

@Composable
fun DocumentScreen(viewModel: DocumentViewModel, canIssue: Boolean, canPay: Boolean, onEdit: () -> Unit, onOpenDocument: (String) -> Unit, onOpenClient: (String) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    var dialog by remember { mutableStateOf<String?>(null) }
    var sent by remember { mutableStateOf<DocumentSent?>(null) }
    fun act(done: String, block: suspend () -> Unit) = scope.launch { try { block(); toast(done) } catch (e: AppException) { toast(e.message ?: "Try again.") } }

    Loaded(state, onRetry = { viewModel.load() }) { versioned ->
        val d = versioned.value
        val title = Labels.of(d.kind) + (d.number?.let { " $it" } ?: " (draft)")
        FormColumn {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Text(listOfNotNull(Labels.of(d.status), d.issueDate?.let { Dates.date(it) }, d.dueDate?.let { "due ${Dates.date(it)}" }).joinToString(" · "), color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick = { onOpenClient(d.client.id) }) { Text(d.client.displayName) }
            d.responseStatus?.let { Text("Client ${Labels.of(it).lowercase()} this quote.", color = MaterialTheme.colorScheme.primary) }
            d.voidReason?.let { Text("Void: $it", color = MaterialTheme.colorScheme.error) }
            d.lines.groupBy { it.section }.forEach { (section, lines) ->
                section?.let { SectionTitle(it) }
                lines.forEach { l ->
                    ListItem(
                        headlineContent = { Text(l.description + if (l.optional) " (optional)" else "") },
                        supportingContent = { Text("${l.quantity} × ${money(l.unitPrice, d.currency, decimals = true)}" + (l.discountRate.toBigDecimalOrNull()?.takeIf { it.signum() > 0 }?.let { " less ${it.movePointRight(2).stripTrailingZeros().toPlainString()}%" } ?: "")) },
                        trailingContent = { Text(money(l.total, d.currency, decimals = true)) },
                    )
                }
            }
            Card {
                Column(Modifier.padding(14.dp)) {
                    Detail("Subtotal", money(d.subtotal, d.currency, decimals = true))
                    d.taxes.forEach { Detail(it.name, money(it.tax, d.currency, decimals = true)) }
                    Detail("Total", money(d.total, d.currency, decimals = true))
                    if (positive(d.optionalTotal)) Detail("Optional extras", money(d.optionalTotal, d.currency, decimals = true))
                    if (d.isInvoice && d.issued) {
                        Detail("Paid", money(d.paid, d.currency, decimals = true))
                        Detail("Balance", money(d.balance, d.currency, decimals = true))
                    }
                    Detail("Payment reference", d.paymentReference)
                }
            }
            d.etimsCuInvoiceNumber?.let { Detail("KRA eTIMS CU number", it) }
            // Actions, by state.
            if (d.status == "draft" && canIssue) {
                OutlinedButton(onClick = onEdit, modifier = Modifier.fillMaxWidth()) { Text("Edit") }
                if (!d.isQuote) Button(onClick = { act("${Labels.of(d.kind)} issued") { viewModel.issue() } }, modifier = Modifier.fillMaxWidth()) { Text("Issue") }
            }
            if (canIssue && (d.isQuote && d.status in listOf("draft", "sent") || !d.isQuote && d.issued)) {
                Button(onClick = { dialog = "send" }, modifier = Modifier.fillMaxWidth()) { Text(if (d.isQuote && d.status == "draft") "Send to client" else "Send") }
            }
            if (d.isQuote && canIssue && d.status in listOf("sent", "accepted", "expired") && d.convertedDocumentId == null) {
                Button(onClick = { scope.launch { try { onOpenDocument(viewModel.convert()) } catch (e: AppException) { toast(e.message ?: "Try again.") } } }, modifier = Modifier.fillMaxWidth()) { Text("Create invoice") }
            }
            d.convertedDocumentId?.let { id -> TextButton(onClick = { onOpenDocument(id) }) { Text("Open the invoice") } }
            if (d.isInvoice && d.issued && canPay && positive(d.balance)) {
                if (viewModel.mpesa) Button(onClick = { dialog = "mpesa" }, modifier = Modifier.fillMaxWidth()) { Text("Ask for M-Pesa payment") }
                Button(onClick = { dialog = "pay" }, modifier = Modifier.fillMaxWidth()) { Text("Record payment") }
                if (positive(viewModel.credit)) OutlinedButton(onClick = { act("Credit applied") { viewModel.applyCredit() } }, modifier = Modifier.fillMaxWidth()) {
                    Text("Use ${money(viewModel.credit, d.currency, decimals = true)} credit")
                }
            }
            OutlinedButton(onClick = {
                scope.launch {
                    try {
                        val bytes = viewModel.pdf()
                        if (!withContext(Dispatchers.IO) { Files.openPdf(context, bytes, d.number ?: "draft") }) toast("Install a PDF viewer to open documents.")
                    } catch (e: AppException) { toast(e.message ?: "Try again.") }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Open PDF") }
            if (canIssue && d.issued && (d.isInvoice || d.kind == "credit_note")) {
                OutlinedButton(onClick = { dialog = "etims" }, modifier = Modifier.fillMaxWidth()) { Text(if (d.etimsCuInvoiceNumber == null) "Add KRA eTIMS details" else "Change eTIMS details") }
            }
            if (canIssue && d.issued && d.status != "void") {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (d.isInvoice) TextButton(onClick = { dialog = "credit" }) { Text("Issue a credit note") }
                    TextButton(onClick = { dialog = "void" }) { Text("Void", color = MaterialTheme.colorScheme.error) }
                }
            }
            if (canIssue && d.status == "draft") TextButton(onClick = { dialog = "void" }) { Text("Delete draft", color = MaterialTheme.colorScheme.error) }
            if (d.allocations.isNotEmpty()) {
                SectionTitle("Payments and credits")
                d.allocations.forEach { a ->
                    ListItem(headlineContent = { Text(money(a.amount, d.currency, decimals = true)) }, supportingContent = { Text(listOfNotNull(Labels.of(a.source), a.sourceNumber, Dates.date(a.createdAt)).joinToString(" · ")) })
                }
            }
            d.notes?.let { Detail("Notes", it) }
        }

        when (dialog) {
            "send" -> SendDialog(d.client.email, onDismiss = { dialog = null }) { email, message -> sent = viewModel.send(email, message); dialog = null }
            "pay" -> PayDialog(d.balance, onDismiss = { dialog = null }) { amount, method, ref, on -> viewModel.pay(d, amount, method, ref, on); dialog = null; toast("Payment recorded") }
            "mpesa" -> MpesaDialog(viewModel, d.client.phone, d.balance, onDismiss = { dialog = null; viewModel.load() })
            "void" -> ReasonDialog(if (d.status == "draft") "Delete draft" else "Void ${Labels.of(d.kind).lowercase()}", onDismiss = { dialog = null }) { reason ->
                viewModel.void(reason); dialog = null; toast(if (d.status == "draft") "Draft deleted" else "Voided")
            }
            "credit" -> ReasonDialog("Issue a credit note for the whole invoice", onDismiss = { dialog = null }) { reason ->
                val noteId = viewModel.creditNote(reason); dialog = null; toast("Credit note created"); onOpenDocument(noteId)
            }
            "etims" -> EtimsDialog(d.etimsCuInvoiceNumber, d.etimsVerificationUrl, onDismiss = { dialog = null }) { cu, url -> viewModel.etims(cu, url); dialog = null; toast("eTIMS details saved") }
        }
        sent?.let { s ->
            AlertDialog(
                onDismissRequest = { sent = null },
                title = { Text("Sent") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        s.emailedTo?.let { Text("Emailed to $it.") }
                        Text(s.url, style = MaterialTheme.typography.bodySmall)
                        s.whatsappUrl?.let { Button(onClick = { context.open(it) }, modifier = Modifier.fillMaxWidth()) { Text("Share on WhatsApp") } }
                        OutlinedButton(onClick = { clipboard.setText(AnnotatedString(s.url)); toast("Link copied") }, modifier = Modifier.fillMaxWidth()) { Text("Copy link") }
                        OutlinedButton(onClick = { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, s.url), "Share")) }, modifier = Modifier.fillMaxWidth()) { Text("Share another way") }
                    }
                },
                confirmButton = { TextButton(onClick = { sent = null }) { Text("Done") } },
            )
        }
    }
}

@Composable
private fun SendDialog(clientEmail: String?, onDismiss: () -> Unit, onSend: suspend (String?, String) -> Unit) {
    var email by remember { mutableStateOf(clientEmail ?: "") }
    var message by remember { mutableStateOf("") }
    BusyDialog("Send to client", "Send", onDismiss, onSend = { onSend(email, message) }) {
        Text("You get a link to share on WhatsApp. Add an email to send it there too.")
        Field("Client's email", email, { email = it }, keyboard = KeyboardType.Email, hint = "Optional")
        Field("Message", message, { message = it }, singleLine = false, minLines = 2, hint = "Optional")
    }
}

@Composable
private fun PayDialog(balance: String, onDismiss: () -> Unit, onSave: suspend (String, String, String?, LocalDate) -> Unit) {
    var amount by remember { mutableStateOf(balance.toBigDecimalOrNull()?.stripTrailingZeros()?.toPlainString() ?: "") }
    var method by remember { mutableStateOf("mpesa") }
    var reference by remember { mutableStateOf("") }
    var on by remember { mutableStateOf<LocalDate?>(LocalDate.now()) }
    BusyDialog("Record payment", "Record payment", onDismiss, enabled = amount.isNotBlank() && on != null, onSend = { onSave(amount, method, reference.trim().ifBlank { null }, on!!) }) {
        Field("Amount (KES)", amount, { amount = amountOf(it) }, keyboard = KeyboardType.Decimal, hint = "More than the balance is kept as the client's credit")
        Choices("Paid by", METHODS, method, { method = it ?: "mpesa" })
        Field("Reference", reference, { reference = it.uppercase() }, hint = "e.g. M-Pesa code")
        DateField("Received on", on, { on = it })
    }
}

@Composable
private fun ReasonDialog(title: String, onDismiss: () -> Unit, onConfirm: suspend (String) -> Unit) {
    var reason by remember { mutableStateOf("") }
    BusyDialog(title, "Confirm", onDismiss, enabled = reason.isNotBlank(), onSend = { onConfirm(reason.trim()) }) {
        Field("Reason", reason, { reason = it }, hint = "Kept with the record for your books")
    }
}

@Composable
private fun EtimsDialog(cu: String?, url: String?, onDismiss: () -> Unit, onSave: suspend (String, String?) -> Unit) {
    var number by remember { mutableStateOf(cu ?: "") }
    var link by remember { mutableStateOf(url ?: "") }
    BusyDialog("KRA eTIMS details", "Save eTIMS details", onDismiss, enabled = number.isNotBlank(), onSend = { onSave(number.trim(), link.trim().ifBlank { null }) }) {
        Text("From your own eTIMS tool. They are printed on the document and the client's page.")
        Field("CU invoice number", number, { number = it.uppercase() })
        Field("Verification link", link, { link = it }, keyboard = KeyboardType.Uri, hint = "Optional, the itax.kra.go.ke link")
    }
}

/** A dialog whose confirm button runs a suspend action, showing errors in place. */
@Composable
fun BusyDialog(title: String, confirm: String, onDismiss: () -> Unit, enabled: Boolean = true, onSend: suspend () -> Unit, content: @Composable () -> Unit) {
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(title) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { content(); FormError(error) } },
        confirmButton = {
            SubmitButton(confirm, busy, enabled) {
                busy = true
                scope.launch { try { onSend() } catch (e: AppException) { error = e.message } finally { busy = false } }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } },
    )
}

/** Sends an M-Pesa prompt to the client's phone and follows it until it is paid or ends. */
@Composable
private fun MpesaDialog(viewModel: DocumentViewModel, clientPhone: String?, balance: String, onDismiss: () -> Unit) {
    var phone by remember { mutableStateOf(clientPhone?.let(Phone::display) ?: "") }
    var prompt by remember { mutableStateOf<Prompt?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val done = prompt?.status in listOf("paid", "cancelled", "failed", "expired")
    LaunchedEffect(prompt?.id, done) {
        val p = prompt ?: return@LaunchedEffect
        while (!done) {
            delay(3000)
            runCatching { viewModel.promptStatus(p.id) }.getOrNull()?.let { prompt = it; if (it.status != "pending") return@LaunchedEffect }
        }
    }
    val whole = (balance.toBigDecimalOrNull() ?: BigDecimal.ZERO).setScale(0, java.math.RoundingMode.CEILING).toPlainString()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("M-Pesa payment prompt") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("The client gets a prompt for ${money(whole, "KES")} (M-Pesa takes whole shillings) and enters their PIN. The money goes to your Paybill or Till.")
                val p = prompt
                if (p == null) {
                    Field("Client's M-Pesa number", phone, { phone = it }, keyboard = KeyboardType.Phone)
                } else {
                    Text(
                        when (p.status) {
                            "pending" -> "Waiting for the client to enter their M-Pesa PIN…"
                            "paid" -> "Paid. The payment is recorded on the invoice." + (p.receipt?.let { " Receipt $it." } ?: "")
                            "cancelled" -> "The client cancelled the prompt."
                            "expired" -> "The prompt timed out. Try again."
                            else -> p.resultDesc ?: "The payment did not go through."
                        },
                        color = if (p.status == "paid") MaterialTheme.colorScheme.primary else if (done) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
                    )
                }
                FormError(error)
            }
        },
        confirmButton = {
            if (prompt?.status == "paid") {
                TextButton(onClick = onDismiss) { Text("Done") }
            } else if (prompt == null || done) {
                SubmitButton(if (prompt == null) "Send prompt" else "Send again", busy, phone.isNotBlank()) {
                    busy = true
                    scope.launch { try { prompt = viewModel.prompt(phone); error = null } catch (e: AppException) { error = e.message } finally { busy = false } }
                }
            } else {
                TextButton(onClick = onDismiss) { Text("Close (it keeps going)") }
            }
        },
    )
}
