package app.brokeros.android.ui.money

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BillingSummaryRow
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientRef
import app.brokeros.android.data.MatchIn
import app.brokeros.android.data.MpesaTransaction
import app.brokeros.android.data.ReceivedPayment
import app.brokeros.android.data.account
import app.brokeros.android.data.ignoreTransaction
import app.brokeros.android.data.matchTransaction
import app.brokeros.android.data.payments
import app.brokeros.android.data.unmatched
import app.brokeros.android.ui.components.ClientPicker
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PaymentsState(val payments: List<ReceivedPayment>, val unmatched: List<MpesaTransaction>)

class PaymentsViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow<Load<PaymentsState>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try {
            Load.Ready(PaymentsState(api.payments(), runCatching { api.unmatched() }.getOrDefault(emptyList())))
        } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun openInvoices(clientId: String): List<BillingSummaryRow> = api.account(clientId).openInvoices
    suspend fun match(t: MpesaTransaction, clientId: String, invoiceId: String?) { api.matchTransaction(t.id, MatchIn(clientId, invoiceId)); load() }
    suspend fun ignore(t: MpesaTransaction, reason: String) { api.ignoreTransaction(t.id, reason); load() }
}

@Composable
fun PaymentsScreen(viewModel: PaymentsViewModel, api: BrokerApi) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var matching by remember { mutableStateOf<MpesaTransaction?>(null) }
    var ignoring by remember { mutableStateOf<MpesaTransaction?>(null) }
    val toast = LocalToast.current
    PullToRefreshBox(isRefreshing = state is Load.Loading, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
        Loaded(state, onRetry = { viewModel.load() }) { s ->
            LazyColumn(Modifier.fillMaxSize()) {
                if (s.unmatched.isNotEmpty()) {
                    item { SectionTitle("M-Pesa payments to match", Modifier.padding(horizontal = 16.dp)) }
                    items(s.unmatched, key = { "t" + it.id }) { t ->
                        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                            Text("${money(t.amount, "KES", decimals = true)} from ${t.payer ?: "unknown"}", style = MaterialTheme.typography.titleMedium)
                            Text(listOfNotNull(t.receipt, t.billReference?.let { "account $it" }, t.paidAt?.let { Dates.dateTime(it) }).joinToString(" · "), style = MaterialTheme.typography.bodySmall)
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                TextButton(onClick = { matching = t }) { Text("Assign to a client") }
                                TextButton(onClick = { ignoring = t }) { Text("Set aside") }
                            }
                        }
                        HorizontalDivider()
                    }
                }
                item { SectionTitle("Payments received", Modifier.padding(horizontal = 16.dp)) }
                if (s.payments.isEmpty()) item { Empty("No payments yet.") }
                items(s.payments, key = { it.id }) { p ->
                    ListItem(
                        headlineContent = { Text("${money(p.amount, p.currency, decimals = true)} · ${p.client.displayName}" + if (p.voidedAt != null) " (voided)" else "") },
                        supportingContent = {
                            Text(listOfNotNull(p.number, Labels.of(p.method), p.reference, Dates.date(p.receivedOn),
                                p.unallocated.toBigDecimalOrNull()?.takeIf { it.signum() > 0 }?.let { "${money(p.unallocated, p.currency)} kept as credit" }).joinToString(" · "))
                        },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
    matching?.let { t ->
        var client by remember { mutableStateOf<ClientRef?>(null) }
        var invoices by remember { mutableStateOf<List<BillingSummaryRow>>(emptyList()) }
        var invoice by remember { mutableStateOf<String?>(null) }
        LaunchedEffect(client) { invoices = client?.let { runCatching { viewModel.openInvoices(it.id) }.getOrDefault(emptyList()) } ?: emptyList() }
        BusyDialog("Assign ${money(t.amount, "KES")}", "Assign", onDismiss = { matching = null }, enabled = client != null, onSend = {
            viewModel.match(t, client!!.id, invoice); matching = null; toast("Payment assigned")
        }) {
            ClientPicker(api, client) { client = it; invoice = null }
            if (invoices.isNotEmpty()) {
                Text("Pay this invoice (or leave none to keep it as credit)", style = MaterialTheme.typography.labelLarge)
                invoices.forEach { inv ->
                    androidx.compose.material3.FilterChip(
                        selected = invoice == inv.id,
                        onClick = { invoice = if (invoice == inv.id) null else inv.id },
                        label = { Text("${inv.number ?: "Draft"} · owes ${money(inv.balance, inv.currency)}") },
                    )
                }
            }
        }
    }
    ignoring?.let { t ->
        var reason by remember { mutableStateOf("") }
        BusyDialog("Set aside ${t.receipt}", "Set aside", onDismiss = { ignoring = null }, enabled = reason.isNotBlank(), onSend = {
            viewModel.ignore(t, reason.trim()); ignoring = null; toast("Set aside")
        }) {
            Field("Reason", reason, { reason = it }, hint = "e.g. not for us, refunded")
        }
    }
}
