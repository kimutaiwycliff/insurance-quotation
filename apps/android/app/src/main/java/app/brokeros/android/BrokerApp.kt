package app.brokeros.android

import android.app.Application
import android.content.Context
import app.brokeros.android.core.Endpoints
import app.brokeros.android.core.KeystoreTokenStore
import app.brokeros.android.data.AuthApi
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.SessionRepository
import app.brokeros.android.data.httpClient
import app.brokeros.android.update.AppConfigApi

/** Everything the screens need, created once (manual dependency injection, ADR-0026). */
class AppContainer(context: Context) {
    val endpoints = Endpoints.fromBuild
    private val http = httpClient()
    private val auth = AuthApi(http, endpoints)
    val appConfig = AppConfigApi(http, endpoints)
    val session: SessionRepository by lazy {
        SessionRepository(auth, KeystoreTokenStore(context), loadMe = { api.me() })
    }
    val api: BrokerApi by lazy { BrokerApi(http, endpoints) { force -> session.apiToken(force) } }
}

class BrokerApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
