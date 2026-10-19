package app.brokeros.android.ui.account

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.brokeros.android.data.Me
import app.brokeros.android.ui.components.SectionTitle

/** An item in the More menu: shown only when the plan and role allow it. */
data class MenuItem(val route: String, val label: String, val hint: String)

/** Every area of the app that does not have its own tab, grouped like the web's menu. */
fun menu(me: Me): List<Pair<String, List<MenuItem>>> {
    val has = { feature: String -> feature in me.features || "*" in me.features }
    val insurance = buildList {
        if (has("insurance")) {
            add(MenuItem("calculator", "Premium calculator", "Compare insurers in seconds"))
            add(MenuItem("quotes", "Quotes", "Send, follow up and accept"))
            add(MenuItem("policies", "Policies", "Your book, payments and renewals"))
            add(MenuItem("renewals", "Renewals", "Who to call before cover ends"))
        }
        if (has("commission") && (me.can("commission:read:all") || me.can("commission:read:own"))) {
            add(MenuItem("commission", "Commission", "What insurers owe you"))
        }
    }
    val money = buildList {
        if (me.can("invoice:write") || me.can("invoice:issue") || me.can("client:read:all")) {
            add(MenuItem("invoices", "Invoices", "Bill clients and track what they owe"))
            add(MenuItem("sales-quotes", "Sales quotes", "Quote a job, then invoice it"))
        }
        if (me.can("payment:write") || me.can("invoice:issue")) add(MenuItem("payments", "Payments", "Received payments and M-Pesa to match"))
    }
    return listOf("Insurance" to insurance, "Money" to money).filter { it.second.isNotEmpty() }
}

@Composable
fun AccountScreen(
    me: Me,
    versionName: String,
    canSwitchAgency: Boolean,
    onOpen: (String) -> Unit,
    onSwitchAgency: () -> Unit,
    onCheckUpdates: () -> Unit,
    onOpenWeb: () -> Unit,
    onSignOut: () -> Unit,
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        menu(me).forEach { (group, items) ->
            SectionTitle(group)
            Card(Modifier.fillMaxWidth()) {
                items.forEachIndexed { i, item ->
                    ListItem(
                        headlineContent = { Text(item.label) },
                        supportingContent = { Text(item.hint) },
                        trailingContent = { Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null) },
                        modifier = Modifier.clickable { onOpen(item.route) },
                    )
                    if (i < items.lastIndex) HorizontalDivider()
                }
            }
        }
        SectionTitle("Account")
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(me.name.ifBlank { me.email }, style = MaterialTheme.typography.titleLarge)
                Text(me.email, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("${me.tenant.name} · ${me.role.replaceFirstChar { it.uppercase() }}", style = MaterialTheme.typography.bodyMedium)
                if (me.plan.isNotBlank()) Text("Plan: ${me.plan.replaceFirstChar { it.uppercase() }}", style = MaterialTheme.typography.bodyMedium)
                if (me.readOnly) {
                    Text("Your plan has lapsed, so the account is read-only. Pay on the web to keep working.", color = MaterialTheme.colorScheme.error)
                }
            }
        }
        if (canSwitchAgency) OutlinedButton(onClick = onSwitchAgency, modifier = Modifier.fillMaxWidth()) { Text("Switch agency") }
        OutlinedButton(onClick = onOpenWeb, modifier = Modifier.fillMaxWidth()) { Text("Open the full app on the web") }
        OutlinedButton(onClick = onCheckUpdates, modifier = Modifier.fillMaxWidth()) { Text("Check for updates") }
        TextButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) { Text("Sign out", color = MaterialTheme.colorScheme.error) }
        Text("Version $versionName", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
