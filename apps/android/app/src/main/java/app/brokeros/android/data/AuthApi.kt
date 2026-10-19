package app.brokeros.android.data

import app.brokeros.android.core.Endpoints
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Outcome of the password step. */
sealed interface SignInStep {
    data class Done(val sessionToken: String) : SignInStep

    /** Two-factor is on: send the code with these cookies (kept in memory only). */
    data class NeedsCode(val cookies: String) : SignInStep
}

@Serializable
private data class Credentials(val email: String, val password: String, val rememberMe: Boolean = true)

@Serializable
private data class Code(val code: String, val trustDevice: Boolean = false)

@Serializable
private data class ActiveAgency(val organizationId: String)

@Serializable
private data class ApiToken(val token: String)

@Serializable
data class SessionInfo(val session: SessionPart) {
    @Serializable
    data class SessionPart(val activeOrganizationId: String? = null)
}

/**
 * The auth service (Better Auth) through the web app's /api/auth proxy (ADR-0026): the same flows the web uses,
 * with a bearer session token instead of a browser cookie.
 */
class AuthApi(private val http: HttpClient, private val endpoints: Endpoints) {
    private fun url(path: String) = "${endpoints.siteUrl}/api/auth$path"

    private fun HttpRequestBuilder.origin() = header(HttpHeaders.Origin, endpoints.authOrigin)

    suspend fun signIn(email: String, password: String): SignInStep {
        val response = call {
            http.post(url("/sign-in/email")) {
                origin()
                contentType(ContentType.Application.Json)
                setBody(Credentials(email.trim(), password))
            }
        }
        response.headers["set-auth-token"]?.let { return SignInStep.Done(it) }
        val body = runCatching { response.body<JsonObject>() }.getOrNull()
        if (body?.get("twoFactorRedirect")?.jsonPrimitive?.booleanOrNull == true) {
            val cookies = response.headers.getAll(HttpHeaders.SetCookie).orEmpty()
                .joinToString("; ") { it.substringBefore(";") }
            return SignInStep.NeedsCode(cookies)
        }
        throw AppException("Sign-in failed. Try again.")
    }

    suspend fun verifyCode(cookies: String, code: String): String {
        val response = call {
            http.post(url("/two-factor/verify-totp")) {
                origin()
                header(HttpHeaders.Cookie, cookies)
                contentType(ContentType.Application.Json)
                setBody(Code(code.filter(Char::isDigit)))
            }
        }
        return response.headers["set-auth-token"] ?: throw AppException("That code didn't work. Try the newest one.")
    }

    /** The session, or null when it has ended (signed out elsewhere, expired). */
    suspend fun session(token: String): SessionInfo? {
        val response = try {
            http.get(url("/get-session")) { bearerAuth(token) }
        } catch (e: Exception) {
            throw AppException(OFFLINE_MESSAGE)
        }
        if (!response.status.isSuccess()) return null
        val text = response.bodyAsText()
        if (text.isBlank() || text == "null") return null
        return ApiJson.decodeFromString(SessionInfo.serializer(), text)
    }

    suspend fun agencies(token: String): List<Agency> =
        call { http.get(url("/organization/list")) { bearerAuth(token) } }.body()

    suspend fun chooseAgency(token: String, agencyId: String) {
        call {
            http.post(url("/organization/set-active")) {
                origin()
                bearerAuth(token)
                contentType(ContentType.Application.Json)
                setBody(ActiveAgency(agencyId))
            }
        }
    }

    /** A 15-minute API token for the active agency. */
    suspend fun apiToken(token: String): String =
        call { http.get(url("/token")) { bearerAuth(token) } }.body<ApiToken>().token

    suspend fun signOut(token: String) {
        runCatching {
            http.post(url("/sign-out")) {
                origin()
                bearerAuth(token)
                contentType(ContentType.Application.Json)
                setBody(JsonObject(emptyMap()))
            }
        }
    }

    private suspend fun call(request: suspend () -> HttpResponse): HttpResponse {
        val response = try {
            request()
        } catch (e: Exception) {
            throw AppException(OFFLINE_MESSAGE)
        }
        if (response.status.isSuccess()) return response
        val error = runCatching { response.body<AuthError>() }.getOrNull()
        throw AppException(authMessage(error?.code, error?.message), response.status.value, error?.code)
    }

    companion object {
        fun authMessage(code: String?, fallback: String?): String = when (code) {
            "INVALID_EMAIL_OR_PASSWORD" -> "That email and password don't match. Check them and try again."
            "EMAIL_NOT_VERIFIED" -> "Confirm your email first: open the link we sent you."
            "INVALID_CODE", "INVALID_TWO_FACTOR_CODE", "INVALID_TOTP" -> "That code didn't work. Try the newest one."
            "TOO_MANY_ATTEMPTS", "TOO_MANY_REQUESTS" -> "Too many tries. Wait a minute and try again."
            else -> fallback?.takeIf { it.isNotBlank() } ?: "Something went wrong. Try again."
        }
    }
}
