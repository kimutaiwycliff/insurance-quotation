package app.brokeros.android.data

import app.brokeros.android.core.Endpoints
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.put
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import java.util.UUID

/** A response with its version tag (ETag), needed to update the record safely later (If-Match). */
data class Versioned<T>(val value: T, val etag: String?)

/** A fresh key for one create action; reuse it when retrying the same action so nothing is created twice. */
fun newIdempotencyKey(): String = UUID.randomUUID().toString()

/**
 * The API (/api/v1) with the short-lived token. Retries once with a fresh token after a 401, sends If-Match on
 * updates and Idempotency-Key on creates, and turns problem responses into [AppException]s with the server's words.
 * Feature calls are small typed functions in the other data/ files.
 */
class BrokerApi(
    @PublishedApi internal val http: HttpClient,
    @PublishedApi internal val endpoints: Endpoints,
    private val token: suspend (forceRefresh: Boolean) -> String,
) {
    suspend fun me(): Me = get("/me")

    suspend fun dashboard(): Dashboard = get("/dashboard")

    suspend inline fun <reified T> get(path: String, params: Map<String, Any?> = emptyMap()): T =
        send(HttpMethod.Get, path) { params.forEach { (k, v) -> if (v != null) parameter(k, v) } }.body()

    suspend inline fun <reified T> getVersioned(path: String): Versioned<T> {
        val response = send(HttpMethod.Get, path) {}
        return Versioned(response.body(), response.headers[HttpHeaders.ETag])
    }

    suspend inline fun <reified B : Any, reified T> post(path: String, body: B, idempotencyKey: String? = null): T =
        send(HttpMethod.Post, path) {
            contentType(ContentType.Application.Json)
            idempotencyKey?.let { header("Idempotency-Key", it) }
            setBody(body)
        }.body()

    /** POST without a body (actions such as issue, withdraw, read-all). */
    suspend inline fun <reified T> action(path: String): T =
        send(HttpMethod.Post, path) {}.body()

    suspend inline fun <reified B : Any, reified T> patch(path: String, body: B, ifMatch: String?): Versioned<T> {
        val response = send(HttpMethod.Patch, path) {
            contentType(ContentType.Application.Json)
            ifMatch?.let { header(HttpHeaders.IfMatch, it) }
            setBody(body)
        }
        return Versioned(response.body(), response.headers[HttpHeaders.ETag])
    }

    suspend inline fun <reified B : Any, reified T> put(path: String, body: B, ifMatch: String? = null): T =
        send(HttpMethod.Put, path) {
            contentType(ContentType.Application.Json)
            ifMatch?.let { header(HttpHeaders.IfMatch, it) }
            setBody(body)
        }.body()

    /** Raw bytes (PDFs) from an authenticated endpoint. */
    suspend fun bytes(path: String): ByteArray = send(HttpMethod.Get, path) {}.body()

    suspend fun delete(path: String) {
        send(HttpMethod.Delete, path) {}
    }

    /** Upload bytes to a presigned storage URL (no API token: the URL itself is the permission). */
    suspend fun upload(url: String, headers: Map<String, String>, bytes: ByteArray, contentType: String) {
        val response = try {
            http.put(endpoints.reachable(url)) {
                headers.forEach { (k, v) -> header(k, v) }
                if (headers.keys.none { it.equals(HttpHeaders.ContentType, ignoreCase = true) }) {
                    header(HttpHeaders.ContentType, contentType)
                }
                setBody(bytes)
            }
        } catch (e: Exception) {
            throw AppException(OFFLINE_MESSAGE)
        }
        if (!response.status.isSuccess()) throw AppException("The upload did not finish. Try again.", response.status.value)
    }

    @PublishedApi
    internal suspend fun send(method: HttpMethod, path: String, block: HttpRequestBuilder.() -> Unit): HttpResponse {
        var response = attempt(method, path, token(false), block)
        if (response.status.value == 401) response = attempt(method, path, token(true), block)
        if (response.status.isSuccess()) return response
        val problem = runCatching { response.body<Problem>() }.getOrNull()
        throw AppException(problemMessage(response.status.value, problem), response.status.value, problem?.code)
    }

    private suspend fun attempt(
        method: HttpMethod,
        path: String,
        token: String,
        block: HttpRequestBuilder.() -> Unit,
    ): HttpResponse = try {
        http.request("${endpoints.apiUrl}/api/v1$path") {
            this.method = method
            bearerAuth(token)
            block()
        }
    } catch (e: AppException) {
        throw e
    } catch (e: Exception) {
        throw AppException(OFFLINE_MESSAGE)
    }

    companion object {
        fun problemMessage(status: Int, problem: Problem?): String {
            val fieldErrors = problem?.errors.orEmpty().mapNotNull { it.message.takeIf(String::isNotBlank) }
            return when {
                fieldErrors.isNotEmpty() -> fieldErrors.joinToString("\n")
                !problem?.detail.isNullOrBlank() -> problem!!.detail!!
                status == 412 -> "Someone else changed this just now. Reload and try again."
                !problem?.title.isNullOrBlank() -> problem!!.title
                else -> "Something went wrong. Try again."
            }
        }
    }
}
