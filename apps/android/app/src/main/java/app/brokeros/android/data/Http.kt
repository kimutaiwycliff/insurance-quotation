package app.brokeros.android.data

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

val ApiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
}

/** One HTTP client for the app. Timeouts suit slow mobile data without hanging forever. */
fun httpClient(engine: HttpClientEngine = OkHttp.create()): HttpClient = HttpClient(engine) {
    expectSuccess = false
    install(ContentNegotiation) { json(ApiJson) }
    install(HttpTimeout) {
        connectTimeoutMillis = 15_000
        requestTimeoutMillis = 30_000
        socketTimeoutMillis = 30_000
    }
}

/** Something the person can read and act on. */
class AppException(message: String, val status: Int? = null, val code: String? = null) : Exception(message)

const val OFFLINE_MESSAGE = "Can't reach the server. Check your internet connection and try again."
