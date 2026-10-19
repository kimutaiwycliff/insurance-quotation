package app.brokeros.android.ui.insurance

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PrimaryScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.RenewalBoard
import app.brokeros.android.data.RenewalItem
import app.brokeros.android.data.RenewalUpdate
import app.brokeros.android.data.renewalStage
import app.brokeros.android.data.renewals
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private val STAGES = listOf("due" to "To contact", "contacted" to "Contacted", "quoted" to "Quoted", "renewed" to "Renewed", "lost" to "Lost")

class RenewalsViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow<Load<RenewalBoard>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.renewals()) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun move(item: RenewalItem, stage: String, reason: String? = null) {
        api.renewalStage(item.id, RenewalUpdate(stage, reason))
        load()
    }
}

@Composable
fun RenewalsScreen(viewModel: RenewalsViewModel, onOpenPolicy: (String) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var stage by rememberSaveable { mutableStateOf("due") }
    var losing by remember { mutableStateOf<RenewalItem?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    fun act(done: String, block: suspend () -> Unit) = scope.launch { try { block(); toast(done) } catch (e: AppException) { toast(e.message ?: "Try again.") } }

    Loaded(state, onRetry = { viewModel.load() }) { board ->
        Column(Modifier.fillMaxSize()) {
            PrimaryScrollableTabRow(selectedTabIndex = STAGES.indexOfFirst { it.first == stage }, edgePadding = 8.dp) {
                STAGES.forEach { (key, label) ->
                    val col = board.columns.firstOrNull { it.stage == key }
                    Tab(selected = stage == key, onClick = { stage = key }, text = { Text("$label ${col?.count ?: 0}") })
                }
            }
            board.columns.firstOrNull { it.stage == stage }?.let {
                Text(
                    "${money(it.premium, board.currency)} in premium · next ${board.windowDays} days",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                )
            }
            PullToRefreshBox(isRefreshing = false, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
                val items = board.items.filter { it.renewalStage == stage }
                if (items.isEmpty()) Empty(if (stage == "due") "No renewals to chase right now." else "Nothing here.")
                LazyColumn(Modifier.fillMaxSize()) {
                    items(items, key = { it.id }) { r ->
                        Column(Modifier.clickable { onOpenPolicy(r.id) }.padding(horizontal = 16.dp, vertical = 10.dp)) {
                            Text(r.description, style = MaterialTheme.typography.titleMedium)
                            Text(
                                listOfNotNull(r.client.displayName, r.insurerName, money(r.totalPremium, r.currency)).joinToString(" · "),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                            Text(
                                "Ends ${Dates.date(r.endDate)} (${Dates.relative(r.endDate)})" + (r.lostReason?.let { " · $it" } ?: "") +
                                    (r.renewalQuoteStatus?.let { " · quote ${Labels.of(it)}" } ?: ""),
                                style = MaterialTheme.typography.bodySmall,
                                color = if (r.daysToExpiry <= 7 && stage == "due") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                r.whatsappUrl?.let { url -> TextButton(onClick = { context.open(url) }) { Text("WhatsApp") } }
                                if (stage == "due") TextButton(onClick = { act("Marked as contacted") { viewModel.move(r, "contacted") } }) { Text("Contacted") }
                                if (stage in listOf("due", "contacted", "quoted")) {
                                    TextButton(onClick = { onOpenPolicy(r.id) }) { Text(if (r.renewalQuoteId == null) "Quote renewal" else "Open") }
                                    TextButton(onClick = { losing = r }) { Text("Lost") }
                                }
                                if (stage == "lost") TextButton(onClick = { act("Reopened") { viewModel.move(r, "due") } }) { Text("Reopen") }
                            }
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
    losing?.let { r ->
        var reason by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { losing = null },
            title = { Text("Renewal lost") },
            text = { Field("Reason", reason, { reason = it }, hint = "e.g. sold the car") },
            confirmButton = { TextButton(enabled = reason.isNotBlank(), onClick = { losing = null; act("Marked as lost") { viewModel.move(r, "lost", reason.trim()) } }) { Text("Mark as lost") } },
            dismissButton = { TextButton(onClick = { losing = null }) { Text("Cancel") } },
        )
    }
}
