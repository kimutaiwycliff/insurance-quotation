package app.brokeros.android

import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import app.brokeros.android.core.Endpoints
import app.brokeros.android.core.KeystoreTokenStore
import app.brokeros.android.core.Outbox
import app.brokeros.android.core.ResponseCache
import app.brokeros.android.data.AuthApi
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.SessionRepository
import app.brokeros.android.data.httpClient
import app.brokeros.android.update.AppConfigApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.io.File

/** Everything the screens need, created once (manual dependency injection, ADR-0026). */
class AppContainer(private val context: Context) {
    val endpoints = Endpoints.fromBuild
    private val http = httpClient()
    val auth = AuthApi(http, endpoints)
    val appConfig = AppConfigApi(http, endpoints)
    private val cache = ResponseCache(File(context.filesDir, "api-cache"))
    val outbox = Outbox(File(context.filesDir, "outbox.json"))
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val session: SessionRepository by lazy {
        SessionRepository(auth, KeystoreTokenStore(context), loadMe = { api.me() }, onSignedOut = {
            // Nothing about clients stays on the phone after signing out.
            cache.clear()
            outbox.clear()
            app.brokeros.android.work.Background.stop(context)
        })
    }
    val api: BrokerApi by lazy { BrokerApi(http, endpoints, cache) { force -> session.apiToken(force) } }

    /** Send waiting offline changes. */
    fun flush() {
        scope.launch { runCatching { outbox.flush { api.replay(it) } } }
    }

    init {
        // When the phone gets a connection back, send what was saved offline.
        runCatching {
            context.getSystemService(ConnectivityManager::class.java).registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) = flush()
            })
        }
    }
}

class BrokerApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
