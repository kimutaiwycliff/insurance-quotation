package app.brokeros.android.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
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
import app.brokeros.android.ui.clients.ClientScreen
import app.brokeros.android.ui.clients.ClientViewModel
import app.brokeros.android.ui.clients.ClientsScreen
import app.brokeros.android.ui.clients.ClientsViewModel
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

private val TABS = listOf(
    Triple("home", "Home", Icons.Default.Home),
    Triple("clients", "Clients", Icons.Default.Person),
    Triple("account", "Account", Icons.Default.AccountCircle),
)

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
    var agencies by remember { mutableIntStateOf(1) }
    LaunchedEffect(me.tenant.id) { agencies = runCatching { container.session.agencyCount() }.getOrDefault(1) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (route == "client/{id}") "Client" else TABS.firstOrNull { it.first == route }?.second ?: "") },
                navigationIcon = {
                    if (route == "client/{id}") {
                        IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                TABS.forEach { (key, label, icon) ->
                    NavigationBarItem(
                        selected = route == key || (key == "clients" && route == "client/{id}"),
                        onClick = { nav.goTo(key) },
                        icon = { Icon(icon, contentDescription = null) },
                        label = { Text(label) },
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
                    HomeScreen(me, viewModel(factory = viewModelFactory { initializer { HomeViewModel(container.api) } }))
                }
                composable("clients") {
                    ClientsScreen(viewModel(factory = viewModelFactory { initializer { ClientsViewModel(container.api) } })) { id ->
                        nav.navigate("client/$id")
                    }
                }
                composable("client/{id}") { back ->
                    val id = back.arguments?.getString("id").orEmpty()
                    ClientScreen(
                        viewModel(key = id, factory = viewModelFactory { initializer { ClientViewModel(container.api, id) } }),
                        siteUrl = container.endpoints.siteUrl,
                        agentName = me.firstName,
                    )
                }
                composable("account") {
                    AccountScreen(
                        me = me,
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

private fun NavHostController.goTo(route: String) = navigate(route) {
    popUpTo(graph.startDestinationId) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
