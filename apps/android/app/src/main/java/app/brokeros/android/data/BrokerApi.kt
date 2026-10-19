package app.brokeros.android.data

import app.brokeros.android.core.Endpoints
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess

/** The API (/api/v1) with the short-lived token; retries once with a fresh token after a 401. */
class BrokerApi(
    private val http: HttpClient,
    private val endpoints: Endpoints,
    private val token: suspend (forceRefresh: Boolean) -> String,
) {
    private fun url(path: String) = "${endpoints.apiUrl}/api/v1$path"

    suspend fun me(): Me = get("/me").body()

    suspend fun dashboard(): Dashboard = get("/dashboard").body()

    suspend fun clients(query: String, cursor: String? = null): ClientPage = get("/clients") {
        if (query.isNotBlank()) parameter("q", query.trim())
        cursor?.let { parameter("cursor", it) }
        parameter("limit", 30)
    }.body()

    suspend fun client(id: String): Client = get("/clients/$id").body()

    private suspend fun get(
        path: String,
        block: io.ktor.client.request.HttpRequestBuilder.() -> Unit = {},
    ): HttpResponse {
        var response = send(path, token(false), block)
        if (response.status.value == 401) response = send(path, token(true), block)
        if (response.status.isSuccess()) return response
        val problem = runCatching { response.body<Problem>() }.getOrNull()
        throw AppException(
            problem?.detail ?: problem?.title?.takeIf { it.isNotBlank() } ?: "Something went wrong. Try again.",
            response.status.value,
            problem?.code,
        )
    }

    private suspend fun send(
        path: String,
        token: String,
        block: io.ktor.client.request.HttpRequestBuilder.() -> Unit,
    ): HttpResponse = try {
        http.get(url(path)) {
            bearerAuth(token)
            block()
        }
    } catch (e: Exception) {
        throw AppException(OFFLINE_MESSAGE)
    }
}
