package app.brokeros.android.ui.account

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.AuthApi
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Checkout
import app.brokeros.android.data.Notification
import app.brokeros.android.data.Organization
import app.brokeros.android.data.OrganizationUpdate
import app.brokeros.android.data.Plan
import app.brokeros.android.data.Role
import app.brokeros.android.data.SessionRepository
import app.brokeros.android.data.Subscription
import app.brokeros.android.data.SubscriptionPayment
import app.brokeros.android.data.Team
import app.brokeros.android.data.Versioned
import app.brokeros.android.data.checkout
import app.brokeros.android.data.markAllRead
import app.brokeros.android.data.markRead
import app.brokeros.android.data.notifications
import app.brokeros.android.data.organization
import app.brokeros.android.data.plans
import app.brokeros.android.data.roles
import app.brokeros.android.data.subscription
import app.brokeros.android.data.subscriptionPayment
import app.brokeros.android.data.updateOrganization
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
import app.brokeros.android.ui.money.BusyDialog
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

// ---------------------------------------------------------------- plan and billing

class PlanViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow<Load<Pair<Subscription, List<Plan>>>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.subscription() to api.plans()) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun checkout(plan: String, cycle: String, phone: String) = api.checkout(Checkout(plan, cycle, phone))
    suspend fun payment(id: String) = api.subscriptionPayment(id)
}

private val FEATURE_NAMES = mapOf(
    "insurance" to "Quotes, policies and renewals", "comparison_quotes" to "Compare insurers on one quote",
    "commission" to "Commission tracking", "book_import" to "Import your book from Excel",
    "client_reminders" to "Reminders emailed to clients", "branding" to "Your logo and colours on documents",
    "etims" to "KRA eTIMS details on invoices", "team" to "Team members and roles",
)

@Composable
fun PlanScreen(viewModel: PlanViewModel, canPay: Boolean, onPaid: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var cycle by rememberSaveable { mutableStateOf("monthly") }
    var paying by remember { mutableStateOf<Plan?>(null) }
    Loaded(state, onRetry = { viewModel.load() }) { (sub, plans) ->
        FormColumn {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(sub.planName.ifBlank { sub.plan }, style = MaterialTheme.typography.headlineSmall)
                    Text(when (sub.status) {
                        "trialing" -> "Free trial: every Agency feature until ${Dates.date(sub.trialEndsAt)} (${Dates.relative(sub.trialEndsAt)})."
                        "active" -> "Paid until ${Dates.date(sub.periodEnd)}. Nothing renews by itself: pay again before then."
                        "past_due" -> "Your plan ended on ${Dates.date(sub.periodEnd)}. Pay now to avoid read-only mode."
                        "read_only" -> "Your plan has lapsed. You can see everything but not change anything until you pay."
                        else -> "The Free plan has no time limit. Upgrade when you need more."
                    })
                    if (sub.foundingMember) Text("Founding member: ${sub.discountPercent}% off", fontWeight = FontWeight.SemiBold)
                }
            }
            Detail("Clients", "${sub.usage.clients}" + (sub.limits["clients"]?.let { " of $it" } ?: ""))
            Detail("Documents issued this month", "${sub.usage.documentsThisMonth}" + (sub.limits["documents_per_month"]?.let { " of $it" } ?: ""))
            Detail("Team seats", "${sub.usage.seatsUsed} of ${sub.seats}")
            SectionTitle("Plans")
            if (sub.foundingPlacesLeft > 0 && !sub.foundingMember) Text("Founding offer: half price for your first 12 months. ${sub.foundingPlacesLeft} of the first 100 places are left.")
            Choices(null, listOf("monthly", "yearly"), cycle, { cycle = it ?: "monthly" })
            val current = if (sub.status == "trialing") sub.paidPlan.takeIf { it != "free" } else sub.plan
            plans.forEach { plan ->
                val price = plan.prices.firstOrNull { it.cycle == cycle }
                val free = price == null || (price.listPrice.toBigDecimalOrNull()?.signum() ?: 0) == 0
                Card(colors = CardDefaults.cardColors(containerColor = if (plan.code == current) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(plan.name + if (plan.code == current) " · your plan" else "", style = MaterialTheme.typography.titleLarge)
                        Text(plan.tagline, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (free) Text("KES 0", style = MaterialTheme.typography.headlineSmall) else {
                            Text("${money(price!!.price, "KES")} / ${if (cycle == "yearly") "year" else "month"}", style = MaterialTheme.typography.headlineSmall)
                            if (price.price != price.listPrice) Text(money(price.listPrice, "KES"), textDecoration = TextDecoration.LineThrough, style = MaterialTheme.typography.bodySmall)
                            if (plan.includedSeats > 1) Text("${plan.includedSeats} users" + (plan.extraSeatMonthly?.let { ", then ${money(it, "KES")} per extra user a month" } ?: ""), style = MaterialTheme.typography.bodySmall)
                        }
                        plan.features.forEach { Text("✓ ${FEATURE_NAMES[it] ?: Labels.of(it)}", style = MaterialTheme.typography.bodyMedium) }
                        plan.limits["clients"]?.let { Text("Up to $it clients", style = MaterialTheme.typography.bodySmall) }
                        plan.limits["documents_per_month"]?.let { Text("Up to $it documents a month", style = MaterialTheme.typography.bodySmall) }
                        if (!free && canPay) Button(onClick = { paying = plan }, modifier = Modifier.fillMaxWidth()) { Text(if (plan.code == current) "Pay for this plan" else "Choose ${plan.name}") }
                    }
                }
            }
            if (!canPay) Text("Only the owner or an admin can pay for the plan.", style = MaterialTheme.typography.bodySmall)
        }
    }
    paying?.let { plan -> CheckoutDialog(viewModel, plan, cycle, onDismiss = { paying = null }, onPaid = { paying = null; viewModel.load(); onPaid() }) }
}

@Composable
private fun CheckoutDialog(viewModel: PlanViewModel, plan: Plan, cycle: String, onDismiss: () -> Unit, onPaid: () -> Unit) {
    var phone by remember { mutableStateOf("") }
    var payment by remember { mutableStateOf<SubscriptionPayment?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    val done = payment?.status in listOf("paid", "cancelled", "failed", "expired")
    LaunchedEffect(payment?.id) {
        val id = payment?.id ?: return@LaunchedEffect
        while (true) {
            delay(3000)
            val next = runCatching { viewModel.payment(id) }.getOrNull() ?: continue
            payment = next
            if (next.status == "paid") { toast("Payment received. Your plan is active."); return@LaunchedEffect }
            if (next.status != "pending") return@LaunchedEffect
        }
    }
    val price = plan.prices.firstOrNull { it.cycle == cycle }?.price ?: "0"
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Pay for ${plan.name} by M-Pesa") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("We send a payment prompt to your phone for ${money(price, "KES")}. Card payments are coming soon.")
                val p = payment
                if (p == null) Field("Your M-Pesa number", phone, { phone = it }, keyboard = KeyboardType.Phone)
                else Text(when (p.status) {
                    "pending" -> "Check your phone and enter your M-Pesa PIN…"
                    "paid" -> "Paid. Thank you! Your plan is active." + (p.receipt?.let { " Receipt $it." } ?: "")
                    "cancelled" -> "The prompt was cancelled."
                    "expired" -> "The prompt timed out. Try again."
                    else -> p.resultDesc ?: "The payment did not go through."
                })
                FormError(error)
            }
        },
        confirmButton = {
            when {
                payment?.status == "paid" -> TextButton(onClick = onPaid) { Text("Done") }
                payment == null || done -> SubmitButton(if (payment == null) "Send prompt" else "Send again", busy, phone.trim().length >= 9) {
                    busy = true
                    scope.launch { try { payment = viewModel.checkout(plan.code, cycle, phone.trim()); error = null } catch (e: AppException) { error = e.message } finally { busy = false } }
                }
                else -> TextButton(onClick = onDismiss) { Text("Close (it keeps going)") }
            }
        },
    )
}

// ---------------------------------------------------------------- notifications

class NotificationsViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow<Load<List<Notification>>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.notifications().items) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun read(n: Notification) { if (n.readAt == null) runCatching { api.markRead(n.id) } }
    suspend fun readAll() { api.markAllRead(); load() }
}

@Composable
fun NotificationsScreen(viewModel: NotificationsViewModel, onOpenLink: (String) -> Unit, onChanged: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    Loaded(state, onRetry = { viewModel.load() }) { list ->
        LazyColumn(Modifier.fillMaxSize()) {
            item {
                if (list.any { it.readAt == null }) TextButton(onClick = { scope.launch { viewModel.readAll(); onChanged() } }, modifier = Modifier.padding(8.dp)) { Text("Mark all as read") }
            }
            if (list.isEmpty()) item { Empty("Nothing new. You will see here when clients open or accept what you share.") }
            items(list, key = { it.id }) { n ->
                ListItem(
                    headlineContent = { Text(n.title, fontWeight = if (n.readAt == null) FontWeight.Bold else FontWeight.Normal) },
                    supportingContent = { Text(n.body + " · " + Dates.relative(n.createdAt)) },
                    modifier = Modifier.clickable {
                        scope.launch { viewModel.read(n); onChanged(); n.link?.let(onOpenLink) }
                    },
                )
                HorizontalDivider()
            }
        }
    }
}

// ---------------------------------------------------------------- team

class TeamViewModel(private val api: BrokerApi, private val auth: AuthApi, private val session: SessionRepository) : ViewModel() {
    private val _state = MutableStateFlow<Load<Team>>(Load.Loading)
    val state = _state.asStateFlow()
    var roles by mutableStateOf<List<Role>>(emptyList())
        private set

    init { load() }

    fun load() = viewModelScope.launch {
        if (roles.isEmpty()) roles = runCatching { api.roles() }.getOrDefault(emptyList())
        _state.value = try { Load.Ready(session.withSession { auth.team(it) }) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun invite(email: String, role: String) { session.withSession { auth.invite(it, email, role) }; load() }
    suspend fun changeRole(memberId: String, role: String) { session.withSession { auth.changeRole(it, memberId, role) }; load() }
    suspend fun remove(memberId: String) { session.withSession { auth.removeMember(it, memberId) }; load() }
    suspend fun cancel(invitationId: String) { session.withSession { auth.cancelInvitation(it, invitationId) }; load() }
}

@Composable
fun TeamScreen(viewModel: TeamViewModel, myUserId: String, canManage: Boolean) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var inviting by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<app.brokeros.android.data.TeamMember?>(null) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    val roleKeys = viewModel.roles.map { it.key }.filter { it != "owner" }.ifEmpty { listOf("admin", "agent", "accounts", "assistant", "viewer") }
    Loaded(state, onRetry = { viewModel.load() }) { team ->
        LazyColumn(Modifier.fillMaxSize()) {
            if (canManage) item { Button(onClick = { inviting = true }, modifier = Modifier.fillMaxWidth().padding(16.dp)) { Text("Invite a colleague") } }
            item { SectionTitle("Members", Modifier.padding(horizontal = 16.dp)) }
            items(team.members, key = { it.id }) { m ->
                ListItem(
                    headlineContent = { Text(m.user.name.ifBlank { m.user.email } + if (m.user.id == myUserId) " (you)" else "") },
                    supportingContent = { Text("${m.user.email} · ${Labels.of(m.role)}") },
                    trailingContent = { if (canManage && m.role != "owner" && m.user.id != myUserId) TextButton(onClick = { editing = m }) { Text("Change") } },
                )
                HorizontalDivider()
            }
            val pending = team.invitations.filter { it.status == "pending" }
            if (pending.isNotEmpty()) item { SectionTitle("Invitations waiting", Modifier.padding(horizontal = 16.dp)) }
            items(pending, key = { it.id }) { inv ->
                ListItem(
                    headlineContent = { Text(inv.email) },
                    supportingContent = { Text(Labels.of(inv.role)) },
                    trailingContent = { if (canManage) TextButton(onClick = { scope.launch { try { viewModel.cancel(inv.id); toast("Invitation cancelled") } catch (e: AppException) { toast(e.message ?: "Try again.") } } }) { Text("Cancel") } },
                )
            }
            item {
                Text(
                    "Agents see only their own clients and commission. Assistants handle clients, documents and tasks, without money.",
                    style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(16.dp),
                )
            }
        }
    }
    if (inviting) {
        var email by remember { mutableStateOf("") }
        var role by remember { mutableStateOf("agent") }
        BusyDialog("Invite a colleague", "Send invitation", onDismiss = { inviting = false }, enabled = email.contains('@'), onSend = {
            viewModel.invite(email, role); inviting = false; toast("Invitation sent to $email")
        }) {
            Field("Email", email, { email = it }, keyboard = KeyboardType.Email)
            Choices("Role", roleKeys, role, { role = it ?: "agent" })
            viewModel.roles.firstOrNull { it.key == role }?.let { Text(it.description, style = MaterialTheme.typography.bodySmall) }
        }
    }
    editing?.let { m ->
        var role by remember { mutableStateOf(m.role) }
        AlertDialog(
            onDismissRequest = { editing = null },
            title = { Text(m.user.name.ifBlank { m.user.email }) },
            text = { Choices("Role", roleKeys, role, { role = it ?: m.role }) },
            confirmButton = {
                TextButton(onClick = { editing = null; scope.launch { try { viewModel.changeRole(m.id, role); toast("Role changed") } catch (e: AppException) { toast(e.message ?: "Try again.") } } }) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = { editing = null; scope.launch { try { viewModel.remove(m.id); toast("Removed from the agency") } catch (e: AppException) { toast(e.message ?: "Try again.") } } }) {
                    Text("Remove", color = MaterialTheme.colorScheme.error)
                }
            },
        )
    }
}

// ---------------------------------------------------------------- agency profile

class ProfileViewModel(private val api: BrokerApi) : ViewModel() {
    private val _state = MutableStateFlow<Load<Versioned<Organization>>>(Load.Loading)
    val state = _state.asStateFlow()

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = try { Load.Ready(api.organization()) } catch (e: AppException) { Load.Failed(e.message ?: "Try again.") }
    }

    suspend fun save(current: Versioned<Organization>, update: OrganizationUpdate) {
        _state.value = Load.Ready(api.updateOrganization(update, current.etag))
    }
}

@Composable
fun ProfileScreen(viewModel: ProfileViewModel, canEdit: Boolean) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    Loaded(state, onRetry = { viewModel.load() }) { versioned ->
        val o = versioned.value
        var name by remember(versioned) { mutableStateOf(o.name) }
        var legal by remember(versioned) { mutableStateOf(o.legalName ?: "") }
        var pin by remember(versioned) { mutableStateOf(o.taxPin ?: "") }
        var licence by remember(versioned) { mutableStateOf(o.licenceNumber ?: "") }
        var expiry by remember(versioned) { mutableStateOf(Dates.parseDate(o.licenceExpiry)) }
        var email by remember(versioned) { mutableStateOf(o.email ?: "") }
        var phone by remember(versioned) { mutableStateOf(o.phone ?: "") }
        var renewalEmails by remember(versioned) { mutableStateOf(o.renewalClientEmails) }
        var invoiceReminders by remember(versioned) { mutableStateOf(o.billingReminders) }
        var etims by remember(versioned) { mutableStateOf(o.etimsEnabled) }
        var busy by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf<String?>(null) }
        val scope = rememberCoroutineScope()
        val toast = LocalToast.current
        FormColumn {
            Field("Trading name", name, { name = it })
            Field("Registered name", legal, { legal = it })
            Field("KRA PIN", pin, { pin = it.uppercase() })
            Field("IRA licence number", licence, { licence = it })
            DateField("Licence expiry", expiry, { expiry = it })
            Field("Office email", email, { email = it }, keyboard = KeyboardType.Email)
            Field("Office phone", phone, { phone = it }, keyboard = KeyboardType.Phone)
            SectionTitle("Reminders and tax")
            Toggle("Email renewal reminders to clients", renewalEmails) { renewalEmails = it }
            Toggle("Email invoice reminders to clients", invoiceReminders) { invoiceReminders = it }
            Toggle("Record KRA eTIMS on invoices", etims) { etims = it }
            FormError(error)
            if (canEdit) SubmitButton("Save", busy, name.isNotBlank()) {
                busy = true
                scope.launch {
                    try {
                        viewModel.save(versioned, OrganizationUpdate(
                            name = name.trim(), legalName = legal.trim().ifBlank { null }, taxPin = pin.trim().ifBlank { null },
                            licenceNumber = licence.trim().ifBlank { null }, licenceExpiry = expiry?.toString(),
                            email = email.trim().ifBlank { null }, phone = phone.trim().ifBlank { null },
                            renewalClientEmails = renewalEmails, billingReminders = invoiceReminders, etimsEnabled = etims,
                        ))
                        toast("Saved")
                    } catch (e: AppException) { error = e.message } finally { busy = false }
                }
            }
        }
    }
}

@Composable
private fun Toggle(label: String, value: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Text(label, modifier = Modifier.weight(1f))
        Switch(checked = value, onCheckedChange = onChange)
    }
}
