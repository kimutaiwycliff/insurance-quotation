package app.brokeros.android.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.brokeros.android.AppContainer
import app.brokeros.android.data.AppException
import app.brokeros.android.data.Me
import app.brokeros.android.data.SessionState
import app.brokeros.android.ui.account.AccountScreen
import android.net.Uri
import androidx.navigation.NavType
import androidx.navigation.navArgument
import app.brokeros.android.data.ClientRef
import app.brokeros.android.ui.clients.ClientFormScreen
import app.brokeros.android.ui.clients.ClientLinks
import app.brokeros.android.ui.insurance.CalculatorScreen
import app.brokeros.android.ui.money.DocumentEditor
import app.brokeros.android.ui.money.DocumentScreen
import app.brokeros.android.ui.money.DocumentViewModel
import app.brokeros.android.ui.money.DocumentsScreen
import app.brokeros.android.ui.money.DocumentsViewModel
import app.brokeros.android.ui.money.PaymentsScreen
import app.brokeros.android.ui.money.PaymentsViewModel
import app.brokeros.android.ui.insurance.CommissionScreen
import app.brokeros.android.ui.insurance.CommissionViewModel
import app.brokeros.android.ui.insurance.NewPolicyScreen
import app.brokeros.android.ui.insurance.NewQuoteScreen
import app.brokeros.android.ui.insurance.PoliciesScreen
import app.brokeros.android.ui.insurance.PoliciesViewModel
import app.brokeros.android.ui.insurance.PolicyScreen
import app.brokeros.android.ui.insurance.PolicyViewModel
import app.brokeros.android.ui.insurance.QuoteScreen
import app.brokeros.android.ui.insurance.QuoteViewModel
import app.brokeros.android.ui.insurance.QuotesScreen
import app.brokeros.android.ui.insurance.QuotesViewModel
import app.brokeros.android.ui.insurance.RenewalsScreen
import app.brokeros.android.ui.insurance.RenewalsViewModel
import app.brokeros.android.ui.clients.ClientScreen
import app.brokeros.android.ui.clients.ClientViewModel
import app.brokeros.android.ui.clients.ClientsScreen
import app.brokeros.android.ui.clients.ClientsViewModel
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.leads.LeadFormScreen
import app.brokeros.android.ui.leads.LeadScreen
import app.brokeros.android.ui.leads.LeadViewModel
import app.brokeros.android.ui.leads.LeadsScreen
import app.brokeros.android.ui.leads.LeadsViewModel
import app.brokeros.android.ui.tasks.TasksScreen
import app.brokeros.android.ui.tasks.TasksViewModel
import app.brokeros.android.ui.components.Banner
import app.brokeros.android.ui.components.ErrorMessage
import app.brokeros.android.ui.components.Loading
import app.brokeros.android.ui.components.open
import app.brokeros.android.ui.home.HomeScreen
import app.brokeros.android.ui.home.HomeViewModel
import app.brokeros.android.ui.signin.AgencyScreen
import app.brokeros.android.ui.signin.CodeScreen
import app.brokeros.android.ui.signin.ForceUpdateScreen
import app.brokeros.android.ui.signin.NoAgencyScreen
import app.brokeros.android.ui.signin.SignInScreen
import app.brokeros.android.update.AppConfig
import app.brokeros.android.update.PlayUpdates
import app.brokeros.android.update.UpdateNeed
import kotlinx.coroutines.launch

/** What the app shows, from the session state and the server's update rules. */
@Composable
fun BrokerRoot(container: AppContainer, updates: PlayUpdates, versionCode: Int, versionName: String) {
    val session = container.session
    val state by session.state.collectAsStateWithLifecycle()
    val readyToInstall by updates.readyToInstall.collectAsStateWithLifecycle()
    var config by remember { mutableStateOf<AppConfig?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        config = container.appConfig.fetch()
        updates.resumeRequired()
        session.restore()
    }
    val need = config?.let { UpdateNeed.of(versionCode, it) } ?: UpdateNeed.None
    val storeUrl = config?.android?.storeUrl.orEmpty()
    if (need == UpdateNeed.Required) {
        ForceUpdateScreen { scope.launch { updates.start(required = true, storeUrl = storeUrl) } }
        return
    }

    when (val s = state) {
        SessionState.Starting -> Loading()
        SessionState.SignedOut -> SignInScreen(container.endpoints.siteUrl) { email, password -> session.signIn(email, password) }
        is SessionState.NeedsCode -> CodeScreen(onVerify = { session.verifyCode(it) }, onCancel = session::cancelCode)
        is SessionState.ChooseAgency -> AgencyScreen(s.agencies) { session.chooseAgency(it) }
        SessionState.NoAgency -> NoAgencyScreen(container.endpoints.siteUrl) { scope.launch { session.signOut() } }
        is SessionState.Offline -> ErrorMessage(s.message, onRetry = { scope.launch { session.restore() } })
        is SessionState.Ready -> SignedIn(
            me = s.me,
            container = container,
            versionName = versionName,
            notice = config?.notice,
            update = when {
                readyToInstall -> "The update is ready." to ("Restart" to { updates.install() })
                need == UpdateNeed.Available -> "A new version is available." to ("Update" to { scope.launch { updates.start(false, storeUrl) }; Unit })
                else -> null
            },
            onCheckUpdates = { scope.launch { updates.start(false, storeUrl) } },
        )
    }
}

private data class Tab(val route: String, val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector)

private val TABS = listOf(
    Tab("home", "Home", Icons.Default.Home),
    Tab("clients", "Clients", Icons.Default.Person),
    Tab("leads", "Leads", Icons.Default.Star),
    Tab("tasks", "Tasks", Icons.Default.CheckCircle),
    Tab("more", "More", Icons.Default.Menu),
)

/** Titles for pages that are not tabs (they get a back arrow). */
private val TITLES = mapOf(
    "client/{id}" to "Client",
    "client/new" to "New client",
    "client/{id}/edit" to "Edit client",
    "lead/{id}" to "Lead",
    "lead/new" to "New lead",
    "lead/{id}/edit" to "Edit lead",
    "calculator" to "Premium calculator",
    "quotes" to "Quotes",
    "quote/{id}" to "Quote",
    "quote/new?clientId={clientId}&clientName={clientName}" to "New quote",
    "policies" to "Policies",
    "policy/{id}" to "Policy",
    "policy/new?clientId={clientId}&clientName={clientName}&quoteId={quoteId}" to "Add policy",
    "renewals" to "Renewals",
    "commission" to "Commission",
    "invoices" to "Invoices",
    "sales-quotes" to "Sales quotes",
    "payments" to "Payments",
    "document/{id}" to "Document",
    "document/{id}/edit" to "Edit draft",
    "document/new/{kind}?clientId={clientId}&clientName={clientName}" to "New document",
)

private fun newDocumentRoute(kind: String, client: ClientRef? = null) =
    "document/new/$kind?clientId=${client?.id.orEmpty()}&clientName=${Uri.encode(client?.displayName.orEmpty())}"

private fun newQuoteRoute(client: ClientRef? = null) =
    "quote/new?clientId=${client?.id.orEmpty()}&clientName=${Uri.encode(client?.displayName.orEmpty())}"

private fun newPolicyRoute(client: ClientRef? = null, quoteId: String? = null) =
    "policy/new?clientId=${client?.id.orEmpty()}&clientName=${Uri.encode(client?.displayName.orEmpty())}&quoteId=${quoteId.orEmpty()}"

/** Optional text arguments of a route ("" when absent). */
private fun androidx.navigation.NavBackStackEntry.arg(name: String) = arguments?.getString(name).orEmpty()

private val optional = { name: String -> navArgument(name) { type = NavType.StringType; defaultValue = "" } }

/** Which tab a page belongs to, for the bottom bar highlight. */
private fun tabOf(route: String?): String? = when {
    route == null -> null
    route.startsWith("client") -> "clients"
    route.startsWith("lead") -> "leads"
    route.startsWith("quote") || route.startsWith("polic") || route.startsWith("document") ||
        route in listOf("calculator", "renewals", "commission", "invoices", "sales-quotes", "payments") -> "more"
    else -> TABS.firstOrNull { it.route == route }?.route
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SignedIn(
    me: Me,
    container: AppContainer,
    versionName: String,
    notice: String?,
    update: Pair<String, Pair<String, () -> Unit>>?,
    onCheckUpdates: () -> Unit,
) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    val api = container.api
    var agencies by remember { mutableIntStateOf(1) }
    LaunchedEffect(me.tenant.id) { agencies = runCatching { container.session.agencyCount() }.getOrDefault(1) }
    val toast: (String) -> Unit = { message -> scope.launch { snackbar.showSnackbar(message) } }
    val isTab = TABS.any { it.route == route }

    CompositionLocalProvider(LocalToast provides toast) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(TITLES[route] ?: TABS.firstOrNull { it.route == route }?.label ?: "") },
                    navigationIcon = {
                        if (!isTab && route != null) {
                            IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
                        }
                    },
                )
            },
            bottomBar = {
                NavigationBar {
                    TABS.forEach { tab ->
                        NavigationBarItem(
                            selected = tabOf(route) == tab.route,
                            onClick = { nav.goTo(tab.route) },
                            icon = { Icon(tab.icon, contentDescription = null) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            },
            snackbarHost = { SnackbarHost(snackbar) },
        ) { padding ->
            Column(Modifier.padding(padding).fillMaxSize()) {
                notice?.let { Banner(it) }
                update?.let { (text, action) -> Banner(text, action.first, action.second) }
                if (me.readOnly) Banner("Your plan has lapsed: you can look, but not change anything. Pay on the web to unlock.")
                NavHost(nav, startDestination = "home", modifier = Modifier.fillMaxSize()) {
                    composable("home") {
                        HomeScreen(me, viewModel(factory = viewModelFactory { initializer { HomeViewModel(api) } }), onNavigate = { nav.goTo(it) })
                    }
                    composable("clients") {
                        ClientsScreen(
                            viewModel(factory = viewModelFactory { initializer { ClientsViewModel(api) } }),
                            canAdd = me.can("client:write"),
                            onOpen = { nav.navigate("client/$it") },
                            onAdd = { nav.navigate("client/new") },
                        )
                    }
                    composable("client/new") {
                        ClientFormScreen(api, existing = null, onSaved = { id ->
                            nav.navigate("client/$id") { popUpTo("clients") }
                        }, onOpenClient = { nav.navigate("client/$it") })
                    }
                    composable("client/{id}") { back ->
                        val id = back.arguments?.getString("id").orEmpty()
                        ClientScreen(
                            viewModel(key = "client-$id", factory = viewModelFactory { initializer { ClientViewModel(api, id) } }),
                            api = api,
                            siteUrl = container.endpoints.siteUrl,
                            agentName = me.firstName,
                            canEdit = me.can("client:write"),
                            onEdit = { nav.navigate("client/$id/edit") },
                            links = ClientLinks(
                                insurance = "insurance" in me.features || "*" in me.features,
                                onOpenQuote = { nav.navigate("quote/$it") },
                                onNewQuote = { nav.navigate(newQuoteRoute(it)) },
                                onOpenPolicy = { nav.navigate("policy/$it") },
                                onNewPolicy = { nav.navigate(newPolicyRoute(it)) },
                                billing = me.can("invoice:write") || me.can("client:read:all"),
                                onOpenDocument = { nav.navigate("document/$it") },
                                onNewInvoice = { nav.navigate(newDocumentRoute("invoice", it)) },
                                onNewSalesQuote = { nav.navigate(newDocumentRoute("sales_quote", it)) },
                            ),
                        )
                    }
                    composable("client/{id}/edit") { back ->
                        val id = back.arguments?.getString("id").orEmpty()
                        val vm: ClientViewModel = viewModel(key = "client-edit-$id", factory = viewModelFactory { initializer { ClientViewModel(api, id) } })
                        val state by vm.client.collectAsStateWithLifecycle()
                        Loaded(state, onRetry = { vm.load() }) { versioned ->
                            ClientFormScreen(api, versioned, onSaved = {
                                nav.navigate("client/$id") { popUpTo("clients") }
                            }, onOpenClient = { nav.navigate("client/$it") })
                        }
                    }
                    composable("leads") {
                        LeadsScreen(
                            viewModel(factory = viewModelFactory { initializer { LeadsViewModel(api) } }),
                            onOpen = { nav.navigate("lead/$it") },
                            onAdd = { nav.navigate("lead/new") },
                        )
                    }
                    composable("lead/new") {
                        LeadFormScreen(api, existing = null) { id -> nav.navigate("lead/$id") { popUpTo("leads") } }
                    }
                    composable("lead/{id}") { back ->
                        val id = back.arguments?.getString("id").orEmpty()
                        LeadScreen(
                            viewModel(key = "lead-$id", factory = viewModelFactory { initializer { LeadViewModel(api, id) } }),
                            agentName = me.firstName,
                            onEdit = { nav.navigate("lead/$id/edit") },
                            onOpenClient = { nav.navigate("client/$it") },
                        )
                    }
                    composable("lead/{id}/edit") { back ->
                        val id = back.arguments?.getString("id").orEmpty()
                        val vm: LeadViewModel = viewModel(key = "lead-edit-$id", factory = viewModelFactory { initializer { LeadViewModel(api, id) } })
                        val state by vm.state.collectAsStateWithLifecycle()
                        Loaded(state, onRetry = { vm.load() }) { lead ->
                            LeadFormScreen(api, lead) { nav.navigate("lead/$id") { popUpTo("leads") } }
                        }
                    }
                    composable("tasks") {
                        TasksScreen(viewModel(factory = viewModelFactory { initializer { TasksViewModel(api) } }), api)
                    }
                    composable("calculator") {
                        CalculatorScreen(api, showCommission = me.can("commission:read:all") || me.can("commission:read:own"))
                    }
                    composable("quotes") {
                        QuotesScreen(viewModel(factory = viewModelFactory { initializer { QuotesViewModel(api) } }), onOpen = { nav.navigate("quote/$it") }, onNew = { nav.navigate(newQuoteRoute()) })
                    }
                    composable(
                        "quote/new?clientId={clientId}&clientName={clientName}",
                        arguments = listOf(optional("clientId"), optional("clientName")),
                    ) { back ->
                        val client = back.arg("clientId").takeIf { it.isNotBlank() }?.let { ClientRef(it, back.arg("clientName")) }
                        NewQuoteScreen(api, client) { id -> nav.navigate("quote/$id") { popUpTo("quote/new?clientId={clientId}&clientName={clientName}") { inclusive = true } } }
                    }
                    composable("quote/{id}") { back ->
                        val id = back.arg("id")
                        QuoteScreen(
                            viewModel(key = "quote-$id", factory = viewModelFactory { initializer { QuoteViewModel(api, id) } }),
                            showCommission = me.can("commission:read:all") || me.can("commission:read:own"),
                            canSend = me.can("client:write"),
                            onCreatePolicy = { q -> nav.navigate(newPolicyRoute(q.client, q.id)) },
                            onOpenClient = { nav.navigate("client/$it") },
                        )
                    }
                    composable("policies") {
                        PoliciesScreen(viewModel(factory = viewModelFactory { initializer { PoliciesViewModel(api) } }), onOpen = { nav.navigate("policy/$it") }, onNew = { nav.navigate(newPolicyRoute()) })
                    }
                    composable(
                        "policy/new?clientId={clientId}&clientName={clientName}&quoteId={quoteId}",
                        arguments = listOf(optional("clientId"), optional("clientName"), optional("quoteId")),
                    ) { back ->
                        val client = back.arg("clientId").takeIf { it.isNotBlank() }?.let { ClientRef(it, back.arg("clientName")) }
                        val quoteId = back.arg("quoteId")
                        val done: (String) -> Unit = { id -> nav.navigate("policy/$id") { popUpTo("policy/new?clientId={clientId}&clientName={clientName}&quoteId={quoteId}") { inclusive = true } } }
                        if (quoteId.isBlank()) {
                            NewPolicyScreen(api, client, quote = null, onCreated = done)
                        } else {
                            val vm: QuoteViewModel = viewModel(key = "policy-quote-$quoteId", factory = viewModelFactory { initializer { QuoteViewModel(api, quoteId) } })
                            val quote by vm.state.collectAsStateWithLifecycle()
                            Loaded(quote, onRetry = { vm.load() }) { q -> NewPolicyScreen(api, client, q, onCreated = done) }
                        }
                    }
                    composable("policy/{id}") { back ->
                        val id = back.arg("id")
                        PolicyScreen(
                            viewModel(key = "policy-$id", factory = viewModelFactory { initializer { PolicyViewModel(api, id) } }),
                            api = api,
                            canPay = me.can("premium:write"),
                            onOpenClient = { nav.navigate("client/$it") },
                            onOpenQuote = { nav.navigate("quote/$it") },
                        )
                    }
                    composable("renewals") {
                        RenewalsScreen(viewModel(factory = viewModelFactory { initializer { RenewalsViewModel(api) } })) { nav.navigate("policy/$it") }
                    }
                    composable("commission") {
                        CommissionScreen(viewModel(factory = viewModelFactory { initializer { CommissionViewModel(api) } }), api)
                    }
                    composable("invoices") {
                        DocumentsScreen(viewModel(key = "invoices", factory = viewModelFactory { initializer { DocumentsViewModel(api, false) } }), onOpen = { nav.navigate("document/$it") }, onNew = { nav.navigate(newDocumentRoute("invoice")) })
                    }
                    composable("sales-quotes") {
                        DocumentsScreen(viewModel(key = "sales-quotes", factory = viewModelFactory { initializer { DocumentsViewModel(api, true) } }), onOpen = { nav.navigate("document/$it") }, onNew = { nav.navigate(newDocumentRoute("sales_quote")) })
                    }
                    composable("payments") {
                        PaymentsScreen(viewModel(factory = viewModelFactory { initializer { PaymentsViewModel(api) } }), api)
                    }
                    composable(
                        "document/new/{kind}?clientId={clientId}&clientName={clientName}",
                        arguments = listOf(optional("clientId"), optional("clientName")),
                    ) { back ->
                        val client = back.arg("clientId").takeIf { it.isNotBlank() }?.let { ClientRef(it, back.arg("clientName")) }
                        DocumentEditor(api, quote = back.arg("kind") == "sales_quote", client = client, existing = null) { id ->
                            nav.navigate("document/$id") { popUpTo("document/new/{kind}?clientId={clientId}&clientName={clientName}") { inclusive = true } }
                        }
                    }
                    composable("document/{id}") { back ->
                        val id = back.arg("id")
                        DocumentScreen(
                            viewModel(key = "document-$id", factory = viewModelFactory { initializer { DocumentViewModel(api, id) } }),
                            canIssue = me.can("invoice:issue"),
                            canPay = me.can("payment:write"),
                            onEdit = { nav.navigate("document/$id/edit") },
                            onOpenDocument = { nav.navigate("document/$it") },
                            onOpenClient = { nav.navigate("client/$it") },
                        )
                    }
                    composable("document/{id}/edit") { back ->
                        val id = back.arg("id")
                        val vm: DocumentViewModel = viewModel(key = "document-edit-$id", factory = viewModelFactory { initializer { DocumentViewModel(api, id) } })
                        val state by vm.state.collectAsStateWithLifecycle()
                        Loaded(state, onRetry = { vm.load() }) { doc ->
                            DocumentEditor(api, quote = doc.value.isQuote, client = null, existing = doc) { nav.navigate("document/$id") { popUpTo("document/{id}") { inclusive = true } } }
                        }
                    }
                    composable("more") {
                        AccountScreen(
                            me = me,
                            onOpen = { nav.navigate(it) },
                            versionName = versionName,
                            canSwitchAgency = agencies > 1,
                            onSwitchAgency = {
                                scope.launch {
                                    try {
                                        container.session.switchAgency()
                                    } catch (e: AppException) {
                                        snackbar.showSnackbar(e.message ?: "Try again.")
                                    }
                                }
                            },
                            onCheckUpdates = onCheckUpdates,
                            onOpenWeb = { context.open(container.endpoints.siteUrl) },
                            onSignOut = { scope.launch { container.session.signOut() } },
                        )
                    }
                }
            }
        }
    }
}

private fun NavHostController.goTo(route: String) = navigate(route) {
    popUpTo(graph.startDestinationId) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
