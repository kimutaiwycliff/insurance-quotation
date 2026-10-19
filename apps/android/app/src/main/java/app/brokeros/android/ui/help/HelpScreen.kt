package app.brokeros.android.ui.help

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import app.brokeros.android.core.HELP_AREAS
import app.brokeros.android.core.HELP_TOPICS
import app.brokeros.android.core.Help
import app.brokeros.android.core.HelpTopic
import app.brokeros.android.core.appRoute
import app.brokeros.android.data.Me
import app.brokeros.android.ui.components.Empty

/** The in-app guide: search everything the app does, by area, with a way straight there. */
@Composable
fun HelpScreen(me: Me, onGo: (String) -> Unit, onOpenWeb: (String) -> Unit) {
    val visible = remember(me) { HELP_TOPICS.filter { Help.canSee(it, me.permissions, me.features) } }
    var query by rememberSaveable { mutableStateOf("") }
    var area by rememberSaveable { mutableStateOf<String?>(null) }
    var open by remember { mutableStateOf(setOf<String>()) }
    val results = Help.search(visible, query).filter { area == null || it.area == area }
    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Help & guide", style = MaterialTheme.typography.headlineMedium)
                Text("Everything the app can do for your agency, and how.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedTextField(
                    value = query, onValueChange = { query = it }, singleLine = true,
                    placeholder = { Text("e.g. send a quote on WhatsApp") },
                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = area == null, onClick = { area = null }, label = { Text("All") })
                    HELP_AREAS.filter { a -> visible.any { it.area == a.key } }.forEach { a ->
                        FilterChip(selected = area == a.key, onClick = { area = if (area == a.key) null else a.key }, label = { Text(a.title) })
                    }
                }
                Text(
                    if (query.isBlank()) "${results.size} topics" else "${results.size} ${if (results.size == 1) "topic matches" else "topics match"} “${query.trim()}”",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        if (results.isEmpty()) item { Empty("Nothing matches yet. Try fewer words, like “M-Pesa” or “renewals”.") }
        items(results, key = { it.id }) { topic ->
            TopicCard(topic, expanded = topic.id in open, onToggle = { open = if (topic.id in open) open - topic.id else open + topic.id }, onGo = onGo, onOpenWeb = onOpenWeb)
        }
    }
}

@Composable
private fun TopicCard(topic: HelpTopic, expanded: Boolean, onToggle: () -> Unit, onGo: (String) -> Unit, onOpenWeb: (String) -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp).animateContentSize()) {
        Column(Modifier.clickable(onClick = onToggle).padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(topic.title, style = MaterialTheme.typography.titleMedium)
            Text(topic.summary, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (expanded) {
                topic.steps.forEachIndexed { i, step -> Text("${i + 1}. $step") }
                topic.tip?.let { Text("Tip: $it", color = MaterialTheme.colorScheme.primary) }
                topic.href?.let { href ->
                    val route = appRoute(href)
                    TextButton(onClick = { if (route != null) onGo(route) else onOpenWeb(href) }) {
                        Text(if (route != null) topic.linkLabel ?: "Take me there" else "${topic.linkLabel ?: "Open"} on the web")
                    }
                }
            }
        }
    }
}
