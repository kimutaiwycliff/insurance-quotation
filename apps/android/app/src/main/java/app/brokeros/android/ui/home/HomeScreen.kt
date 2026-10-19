package app.brokeros.android.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Dashboard
import app.brokeros.android.data.Me
import app.brokeros.android.ui.components.ErrorMessage
import app.brokeros.android.ui.components.Loading
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.text.NumberFormat
import java.util.Locale

data class HomeState(val board: Dashboard? = null, val error: String? = null, val refreshing: Boolean = false)

class HomeViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow(HomeState())
    val state = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(refreshing = true, error = null)
        viewModelScope.launch {
            _state.value = try {
                HomeState(board = api.dashboard())
            } catch (e: AppException) {
                _state.value.copy(error = e.message, refreshing = false)
            }
        }
    }
}

/** "KES 70,355" from a decimal string (money is never a float, even for display: BigDecimal). */
fun money(amount: String, currency: String): String {
    val value = amount.toBigDecimalOrNull() ?: BigDecimal.ZERO
    val format = NumberFormat.getNumberInstance(Locale.US).apply { maximumFractionDigits = 0 }
    return "$currency ${format.format(value)}"
}

@Composable
private fun Tile(value: String, label: String, modifier: Modifier = Modifier, urgent: Boolean = false) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall,
                color = if (urgent) MaterialTheme.colorScheme.error else Color.Unspecified,
            )
            Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(me: Me, viewModel: HomeViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val board = state.board
    when {
        board == null && state.error != null -> ErrorMessage(state.error!!, viewModel::refresh)
        board == null -> Loading()
        else -> PullToRefreshBox(isRefreshing = state.refreshing, onRefresh = viewModel::refresh, modifier = Modifier.fillMaxSize()) {
            LazyVerticalGrid(
                columns = GridCells.Adaptive(160.dp),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Column(Modifier.padding(bottom = 8.dp)) {
                        Text("Welcome, ${me.firstName}", style = MaterialTheme.typography.headlineMedium)
                        Text(me.tenant.name, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                board.tasks?.let { tasks ->
                    item { Tile("${tasks.overdue}", "Tasks overdue", urgent = tasks.overdue > 0) }
                    item { Tile("${tasks.today}", "Tasks due today") }
                }
                item { Tile("${board.renewalsDue30d}", "Renewals due in 30 days", urgent = board.renewalsDue30d > 0) }
                item { Tile("${board.clients}", "Clients (+${board.newClients30d} in 30 days)") }
                item { Tile("${board.policiesActive}", "Active policies") }
                item { Tile("${board.premiumsToRemit}", "Premiums to pass on to insurers") }
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Tile(
                        money(board.book.writtenPremium, board.book.currency),
                        "Premium written this year (${board.book.writtenCount} policies)",
                    )
                }
            }
        }
    }
}
