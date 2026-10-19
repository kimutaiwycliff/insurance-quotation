package app.brokeros.android

import app.brokeros.android.core.Endpoints
import app.brokeros.android.core.MemoryTokenStore
import app.brokeros.android.data.AppException
import app.brokeros.android.data.AuthApi
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Me
import app.brokeros.android.data.SessionRepository
import app.brokeros.android.data.SessionState
import app.brokeros.android.data.SignInStep
import app.brokeros.android.data.TenantSummary
import app.brokeros.android.data.httpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

private val endpoints = Endpoints("https://app.test", "https://api.test", "https://app.test")
private val json = headersOf(HttpHeaders.ContentType, "application/json")

/** A fake auth service and API: routes by path, records requests. */
private class FakeServer {
    val requests = mutableListOf<HttpRequestData>()
    var routes: MutableMap<String, suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData> = mutableMapOf()
    val engine = MockEngine { request ->
        requests += request
        val handler = routes[request.url.encodedPath] ?: return@MockEngine respond("{}", HttpStatusCode.NotFound, json)
        handler(request)
    }
    val http = httpClient(engine)
}

private fun MockRequestHandleScope.ok(body: String, vararg headers: Pair<String, String>) =
    respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType to listOf("application/json"), *headers.map { it.first to listOf(it.second) }.toTypedArray()))

private val me = Me("u1", "achieng@example.com", "Achieng Otieno", TenantSummary("t1", "Otieno Agency"), "owner")

class AuthApiTest {
    @Test fun `password sign-in returns the session token and sends the trusted origin`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/sign-in/email"] = { ok("""{"token":"s1"}""", "set-auth-token" to "s1") }
        val step = AuthApi(server.http, endpoints).signIn(" achieng@example.com ", "pw")
        assertEquals(SignInStep.Done("s1"), step)
        assertEquals("https://app.test", server.requests.single().headers[HttpHeaders.Origin])
    }

    @Test fun `two-factor keeps the sign-in cookies for the code step`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/sign-in/email"] = {
            respond(
                """{"twoFactorRedirect":true}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType to listOf("application/json"), HttpHeaders.SetCookie to listOf("better-auth.two_factor=abc; Path=/; HttpOnly", "other=1; Path=/")),
            )
        }
        server.routes["/api/auth/two-factor/verify-totp"] = { request ->
            assertEquals("better-auth.two_factor=abc; other=1", request.headers[HttpHeaders.Cookie])
            ok("{}", "set-auth-token" to "s2")
        }
        val auth = AuthApi(server.http, endpoints)
        val step = auth.signIn("a@b.c", "pw") as SignInStep.NeedsCode
        assertEquals("s2", auth.verifyCode(step.cookies, "123 456"))
    }

    @Test fun `wrong password and no internet read plainly`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/sign-in/email"] = {
            respond("""{"code":"INVALID_EMAIL_OR_PASSWORD","message":"Invalid email or password"}""", HttpStatusCode.Unauthorized, json)
        }
        try {
            AuthApi(server.http, endpoints).signIn("a@b.c", "nope")
            fail("expected an error")
        } catch (e: AppException) {
            assertEquals("That email and password don't match. Check them and try again.", e.message)
        }
        val offline = AuthApi(httpClient(MockEngine { throw IOException("no route") }), endpoints)
        try {
            offline.signIn("a@b.c", "pw")
            fail("expected an error")
        } catch (e: AppException) {
            assertTrue(e.message!!.startsWith("Can't reach the server"))
        }
    }
}

class SessionTest {
    private fun session(server: FakeServer, store: MemoryTokenStore, now: () -> Long = { 1_000L }) =
        SessionRepository(AuthApi(server.http, endpoints), store, loadMe = { me }, now = now)

    @Test fun `no saved session means the sign-in screen`() = runTest {
        val repo = session(FakeServer(), MemoryTokenStore())
        repo.restore()
        assertEquals(SessionState.SignedOut, repo.state.value)
    }

    @Test fun `one agency is chosen automatically`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/sign-in/email"] = { ok("{}", "set-auth-token" to "s1") }
        server.routes["/api/auth/get-session"] = { ok("""{"session":{"activeOrganizationId":null},"user":{}}""") }
        server.routes["/api/auth/organization/list"] = { ok("""[{"id":"o1","name":"Otieno Agency"}]""") }
        server.routes["/api/auth/organization/set-active"] = { ok("{}") }
        server.routes["/api/auth/token"] = { ok("""{"token":"${fakeJwt(5_000)}"}""") }
        val store = MemoryTokenStore()
        val repo = session(server, store)
        repo.signIn("a@b.c", "pw")
        assertEquals(SessionState.Ready(me), repo.state.value)
        assertEquals("s1", store.read())
        assertTrue(server.requests.any { it.url.encodedPath == "/api/auth/organization/set-active" })
    }

    @Test fun `several agencies ask which one`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/get-session"] = { ok("""{"session":{"activeOrganizationId":null}}""") }
        server.routes["/api/auth/organization/list"] = { ok("""[{"id":"o1","name":"A"},{"id":"o2","name":"B"}]""") }
        val repo = session(server, MemoryTokenStore("s1"))
        repo.restore()
        assertEquals(2, (repo.state.value as SessionState.ChooseAgency).agencies.size)
    }

    @Test fun `an ended session signs out and forgets the token`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/get-session"] = { ok("null") }
        val store = MemoryTokenStore("old")
        val repo = session(server, store)
        repo.restore()
        assertEquals(SessionState.SignedOut, repo.state.value)
        assertNull(store.read())
    }

    @Test fun `no internet at start keeps the saved session`() = runTest {
        val repo = SessionRepository(AuthApi(httpClient(MockEngine { throw IOException("offline") }), endpoints), MemoryTokenStore("s1"), loadMe = { me })
        repo.restore()
        assertTrue(repo.state.value is SessionState.Offline)
    }

    @Test fun `API tokens are cached until a minute before expiry`() = runTest {
        val server = FakeServer()
        var minted = 0
        server.routes["/api/auth/token"] = { minted++; ok("""{"token":"${fakeJwt(1_100)}"}""") }
        var clock = 1_000L
        val repo = session(server, MemoryTokenStore("s1")) { clock }
        repo.apiToken(); repo.apiToken()
        assertEquals(1, minted)
        clock = 1_050 // 50 s left: refresh
        repo.apiToken()
        assertEquals(2, minted)
    }

    @Test fun `the API retries once with a fresh token after a 401`() = runTest {
        val server = FakeServer()
        val seen = mutableListOf<String>()
        server.routes["/api/v1/me"] = { request ->
            seen += request.headers[HttpHeaders.Authorization].orEmpty()
            if (seen.size == 1) respond("""{"title":"Expired","code":"unauthenticated"}""", HttpStatusCode.Unauthorized, json)
            else ok("""{"user_id":"u1","email":"a@b.c","name":"A","tenant":{"id":"t1","name":"T"},"role":"owner","extra":"ignored"}""")
        }
        val tokens = ArrayDeque(listOf("t-old", "t-new"))
        val api = BrokerApi(server.http, endpoints) { tokens.removeFirst() }
        assertEquals("T", api.me().tenant.name)
        assertEquals(listOf("Bearer t-old", "Bearer t-new"), seen)
    }

    @Test fun `API problems carry the server's explanation`() = runTest {
        val server = FakeServer()
        server.routes["/api/v1/dashboard"] = {
            respond("""{"title":"Payment required","detail":"Your plan has lapsed.","code":"subscription_inactive"}""", HttpStatusCode.PaymentRequired, json)
        }
        try {
            BrokerApi(server.http, endpoints) { "t" }.dashboard()
            fail("expected an error")
        } catch (e: AppException) {
            assertEquals("Your plan has lapsed.", e.message)
            assertEquals("subscription_inactive", e.code)
        }
    }

    @Test fun `signing out revokes the session and forgets it`() = runTest {
        val server = FakeServer()
        server.routes["/api/auth/sign-out"] = { ok("{}") }
        val store = MemoryTokenStore("s1")
        val repo = session(server, store)
        repo.signOut()
        assertNull(store.read())
        assertEquals("Bearer s1", server.requests.single().headers[HttpHeaders.Authorization])
    }
}
