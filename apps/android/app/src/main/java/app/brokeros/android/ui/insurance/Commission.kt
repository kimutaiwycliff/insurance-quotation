package app.brokeros.android.ui.insurance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Dates
import app.brokeros.android.data.AllocationIn
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.CommissionSummary
import app.brokeros.android.data.ReceiptCreate
import app.brokeros.android.data.StatementRow
import app.brokeros.android.data.commissionSummary
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.recordCommission
import app.brokeros.android.data.statement
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
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.time.LocalDate

class CommissionViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow<Load<CommissionSummary>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.commissionSummary()) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }
}

@Composable
fun CommissionScreen(viewModel: CommissionViewModel, api: BrokerApi) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var recording by remember { mutableStateOf(false) }
    Loaded(state, onRetry = { viewModel.load() }) { s ->
        FormColumn {
            Text("Commission ${s.year}", style = MaterialTheme.typography.headlineSmall)
            Card {
                Column(Modifier.padding(14.dp)) {
                    Detail("Insurers owe you (after 10% WHT)", money(s.outstandingNet, s.currency, decimals = true))
                    Detail("Received this year", money(s.receivedNet, s.currency, decimals = true))
                    Detail("Expected this year", money(s.expectedNet, s.currency, decimals = true))
                    Detail("WHT withheld", money(s.wht, s.currency, decimals = true))
                }
            }
            Button(onClick = { recording = true }, modifier = Modifier.fillMaxWidth()) { Text("Record commission") }
            if ((s.outstandingNet.toBigDecimalOrNull() ?: BigDecimal.ZERO).signum() == 0) Text("Insurers have paid everything they owe you.")
            if (s.insurers.isNotEmpty()) SectionTitle("By insurer")
            s.insurers.forEach { i ->
                ListItem(
                    headlineContent = { Text(i.insurerName) },
                    supportingContent = { Text("Received ${money(i.receivedNet, s.currency)} · owed ${money(i.outstandingNet, s.currency)}") },
                )
            }
            if (s.whtCertificates.isNotEmpty()) SectionTitle("WHT certificates")
            s.whtCertificates.forEach { c ->
                ListItem(
                    headlineContent = { Text(c.certificate ?: "No certificate number yet") },
                    supportingContent = { Text("${c.insurerName} · ${Dates.date(c.receivedOn)} · ${money(c.wht, s.currency, decimals = true)}") },
                )
            }
        }
    }
    if (recording) RecordCommissionSheet(api, onDismiss = { recording = false }) { recording = false; viewModel.load() }
}

/** Copy the figures from an insurer's commission statement: pick the insurer, tick the policies paid. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RecordCommissionSheet(api: BrokerApi, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var rows by remember { mutableStateOf<List<StatementRow>?>(null) }
    var insurer by remember { mutableStateOf<String?>(null) }
    val gross = remember { mutableStateMapOf<String, String>() }
    val chosen = remember { mutableStateMapOf<String, Boolean>() }
    var receivedOn by remember { mutableStateOf<LocalDate?>(LocalDate.now()) }
    var reference by remember { mutableStateOf("") }
    var certificate by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    LaunchedEffect(Unit) {
        try {
            val all = api.statement(outstanding = true).rows
            rows = all
            insurer = all.map { it.insurerName }.distinct().firstOrNull()
        } catch (e: AppException) { error = e.message }
    }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.padding(horizontal = 16.dp).padding(bottom = 24.dp).navigationBarsPadding().verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Record commission received", style = MaterialTheme.typography.titleLarge)
            Text("Copy the figures from the insurer's statement. WHT is worked out at 10% unless you enter the insurer's figure.", style = MaterialTheme.typography.bodySmall)
            val all = rows
            if (all == null) { FormError(error); return@Column }
            val insurers = all.map { it.insurerName }.distinct()
            if (insurers.isEmpty()) { Empty("Nothing outstanding from any insurer."); return@Column }
            Choices("Insurer", insurers, insurer, { insurer = it })
            val mine = all.filter { it.insurerName == insurer }
            mine.forEach { r ->
                val on = chosen[r.policyId] ?: true
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = on, onCheckedChange = { chosen[r.policyId] = it })
                    Column(Modifier.weight(1f)) {
                        Text("${r.clientName}: ${r.description}", style = MaterialTheme.typography.bodyMedium)
                        Text("Owed ${money(r.outstanding.gross, r.currency, decimals = true)} gross", style = MaterialTheme.typography.bodySmall)
                    }
                    Box(Modifier.weight(0.7f)) {
                        Field("Gross", gross[r.policyId] ?: r.outstanding.gross, { gross[r.policyId] = amountOf(it) }, keyboard = KeyboardType.Decimal)
                    }
                }
            }
            DateField("Received on", receivedOn, { receivedOn = it })
            Field("Payment reference", reference, { reference = it }, hint = "Optional")
            Field("WHT certificate number", certificate, { certificate = it.uppercase() }, hint = "Optional")
            val lines = mine.filter { chosen[it.policyId] ?: true }.map { AllocationIn(it.policyId, gross[it.policyId] ?: it.outstanding.gross) }
            val total = lines.sumOf { it.gross.toBigDecimalOrNull() ?: BigDecimal.ZERO }
            Text("Gross ${money(total.toPlainString(), mine.firstOrNull()?.currency ?: "KES", decimals = true)} for ${lines.size} policies")
            FormError(error)
            SubmitButton("Record commission", busy, lines.isNotEmpty() && receivedOn != null && insurer != null) {
                busy = true
                scope.launch {
                    try {
                        api.recordCommission(ReceiptCreate(insurer!!, receivedOn.toString(), lines, reference.trim().ifBlank { null }, certificate.trim().ifBlank { null }), key)
                        toast("Commission recorded")
                        onSaved()
                    } catch (e: AppException) { error = e.message } finally { busy = false }
                }
            }
        }
    }
}
