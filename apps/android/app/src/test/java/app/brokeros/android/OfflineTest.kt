package app.brokeros.android

import app.brokeros.android.core.Endpoints
import app.brokeros.android.core.Outbox
import app.brokeros.android.core.ResponseCache
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Dashboard
import app.brokeros.android.data.TaskInput
import app.brokeros.android.data.httpClient
import app.brokeros.android.data.sendOrQueue
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.errors.IOException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files

private val json = headersOf(HttpHeaders.ContentType, "application/json")
private val endpoints = Endpoints("https://app.test", "https://api.test", "https://app.test")

class OfflineTest {
    private val dir = Files.createTempDirectory("offline").toFile()

    @Test fun `with no signal the last saved answer is shown and the app says so`() = runTest {
        var online = true
        val api = BrokerApi(httpClient(MockEngine {
            if (!online) throw IOException("no signal")
            respond("""{"clients":12,"policies_active":4}""", HttpStatusCode.OK, json)
        }), endpoints, ResponseCache(dir.resolve("cache"))) { "t" }
        assertEquals(12, api.dashboard().clients)
        assertNull(api.offlineSince.value)
        online = false
        assertEquals(12, api.get<Dashboard>("/dashboard").clients)
        assertNotNull("the banner knows when the data was saved", api.offlineSince.value)
        online = true
        api.dashboard()
        assertNull(api.offlineSince.value)
    }

    @Test fun `a change made offline waits, then goes in order with its original retry-safe key`() = runTest {
        var online = false
        val sent = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r ->
            if (!online) throw IOException("no signal")
            sent += r
            respond("""{"id":"t1","title":"Call Otieno"}""", HttpStatusCode.Created, json)
        }), endpoints) { "t" }
        val outbox = Outbox(dir.resolve("outbox.json"))
        assertFalse(api.sendOrQueue(outbox, "POST", "/tasks", TaskInput(title = "Call Otieno"), "Task: Call Otieno", idempotencyKey = "k1"))
        assertFalse(api.sendOrQueue(outbox, "PATCH", "/tasks/t9", TaskInput(done = true), "Task: Visit", ifMatch = "\"3\""))
        assertEquals(2, outbox.pending.value.size)
        assertEquals("survives the app closing", 2, Outbox(dir.resolve("outbox.json")).pending.value.size)

        outbox.flush { api.replay(it) } // still offline: nothing lost
        assertEquals(2, outbox.pending.value.size)

        online = true
        outbox.flush { api.replay(it) }
        assertTrue(outbox.pending.value.isEmpty())
        assertEquals(listOf("/api/v1/tasks", "/api/v1/tasks/t9"), sent.map { it.url.encodedPath })
        assertEquals("k1", sent[0].headers["Idempotency-Key"])
        assertEquals("\"3\"", sent[1].headers[HttpHeaders.IfMatch])
    }

    @Test fun `a change the server refuses later is reported, not lost silently`() = runTest {
        val api = BrokerApi(httpClient(MockEngine {
            respond("""{"title":"Precondition failed","code":"version_conflict"}""", HttpStatusCode.PreconditionFailed, json)
        }), endpoints) { "t" }
        val outbox = Outbox(dir.resolve("refused.json"))
        outbox.add(app.brokeros.android.core.PendingWrite("w1", "PATCH", "/tasks/t1", kotlinx.serialization.json.JsonObject(emptyMap()), "Task: Visit", ifMatch = "\"1\""))
        outbox.flush { api.replay(it) }
        assertTrue(outbox.pending.value.isEmpty())
        assertEquals(1, outbox.failed.value.size)
        assertTrue(outbox.failed.value.single().startsWith("Task: Visit:"))
    }

    @Test fun `signing out leaves nothing behind`() = runTest {
        val cache = ResponseCache(dir.resolve("c2"))
        cache.put(cache.key("/clients", emptyMap()), "[]")
        val outbox = Outbox(dir.resolve("o2.json"))
        outbox.add(app.brokeros.android.core.PendingWrite("w", "POST", "/tasks", kotlinx.serialization.json.JsonObject(emptyMap()), "x"))
        cache.clear(); outbox.clear()
        assertNull(cache.get(cache.key("/clients", emptyMap())))
        assertTrue(outbox.pending.value.isEmpty())
    }
}
