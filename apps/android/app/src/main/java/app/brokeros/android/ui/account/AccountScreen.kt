package app.brokeros.android.ui.account

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.brokeros.android.data.Me

@Composable
fun AccountScreen(
    me: Me,
    versionName: String,
    canSwitchAgency: Boolean,
    onSwitchAgency: () -> Unit,
    onCheckUpdates: () -> Unit,
    onOpenWeb: () -> Unit,
    onSignOut: () -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(me.name.ifBlank { me.email }, style = MaterialTheme.typography.titleLarge)
                Text(me.email, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("${me.tenant.name} · ${me.role.replaceFirstChar { it.uppercase() }}", style = MaterialTheme.typography.bodyMedium)
                if (me.plan.isNotBlank()) Text("Plan: ${me.plan.replaceFirstChar { it.uppercase() }}", style = MaterialTheme.typography.bodyMedium)
                if (me.readOnly) {
                    Text(
                        "Your plan has lapsed, so the account is read-only. Pay on the web to keep working.",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }
        if (canSwitchAgency) OutlinedButton(onClick = onSwitchAgency, modifier = Modifier.fillMaxWidth()) { Text("Switch agency") }
        OutlinedButton(onClick = onOpenWeb, modifier = Modifier.fillMaxWidth()) { Text("Open the full app on the web") }
        OutlinedButton(onClick = onCheckUpdates, modifier = Modifier.fillMaxWidth()) { Text("Check for updates") }
        TextButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) {
            Text("Sign out", color = MaterialTheme.colorScheme.error)
        }
        Text("Version $versionName", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
