package app.brokeros.android.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import app.brokeros.android.core.Phone
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientRef
import app.brokeros.android.data.clients
import kotlinx.coroutines.delay

/** Choose the client a quote, policy or invoice is for: type to search, tap to pick. */
@Composable
fun ClientPicker(api: BrokerApi, selected: ClientRef?, onSelect: (ClientRef?) -> Unit) {
    if (selected != null) {
        Column {
            Text("Client", style = MaterialTheme.typography.labelLarge)
            Text(selected.displayName, style = MaterialTheme.typography.titleMedium)
            OutlinedButton(onClick = { onSelect(null) }) { Text("Change client") }
        }
        return
    }
    var query by rememberSaveable { mutableStateOf("") }
    var results by remember { mutableStateOf<List<ClientRef>>(emptyList()) }
    LaunchedEffect(query) {
        delay(300)
        results = runCatching {
            api.clients(query).items.take(8).map { ClientRef(it.id, it.displayName, it.phone, it.email) }
        }.getOrDefault(emptyList())
    }
    Column {
        Field("Client", query, { query = it }, hint = "Type a name or phone")
        results.forEach { c ->
            ListItem(
                headlineContent = { Text(c.displayName) },
                supportingContent = { Text(c.phone?.let(Phone::display) ?: c.email ?: "") },
                modifier = Modifier.clickable { onSelect(c) },
            )
        }
    }
}
