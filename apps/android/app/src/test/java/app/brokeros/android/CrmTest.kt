package app.brokeros.android

import app.brokeros.android.core.Dates
import app.brokeros.android.core.Endpoints
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientInput
import app.brokeros.android.data.DocumentStart
import app.brokeros.android.data.EntityRef
import app.brokeros.android.data.Problem
import app.brokeros.android.data.Task
import app.brokeros.android.data.TaskInput
import app.brokeros.android.data.createClient
import app.brokeros.android.data.httpClient
import app.brokeros.android.data.updateTask
import app.brokeros.android.data.uploadDocument
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.time.LocalDate

private val json = headersOf(HttpHeaders.ContentType, "application/json")

private fun HttpRequestData.text(): String = when (val b = body) {
    is OutgoingContent.ByteArrayContent -> String(b.bytes())
    else -> ""
}

class CrmTest {
    private val endpoints = Endpoints("https://app.test", "http://api.test", "https://app.test", localhostAlias = "10.0.2.2")

    @Test fun `a new client sends only what was filled in, with a retry-safe key`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r -> seen += r; respond("""{"id":"c1","display_name":"Wanjiru Kamau"}""", HttpStatusCode.Created, json) }), endpoints) { "t" }
        val client = api.createClient(ClientInput(kind = "individual", firstName = "Wanjiru", lastName = "Kamau", phone = "0712345678"), "key-1")
        assertEquals("c1", client.id)
        val body = seen.single().text()
        assertTrue(body.contains("\"first_name\":\"Wanjiru\""))
        assertFalse("nulls are left out", body.contains("null"))
        assertEquals("key-1", seen.single().headers["Idempotency-Key"])
    }

    @Test fun `editing a task sends its version so conflicting edits are refused`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r -> seen += r; respond("""{"id":"t1","title":"Call","status":"done","version":4}""", HttpStatusCode.OK, json) }), endpoints) { "t" }
        val updated = api.updateTask(Task(id = "t1", title = "Call", version = 3), TaskInput(done = true))
        assertEquals("done", updated.status)
        assertEquals(HttpMethod.Patch, seen.single().method)
        assertEquals("\"3\"", seen.single().headers[HttpHeaders.IfMatch])
    }

    @Test fun `documents upload in three steps, straight to storage`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val engine = MockEngine { r ->
            seen += r
            when {
                r.url.encodedPath == "/api/v1/documents" -> respond(
                    """{"document":{"id":"d1","title":"ID","category":"kyc_id"},"upload":{"url":"http://localhost:9000/documents/x?sig=1","headers":{"Content-Type":"image/jpeg"}},"version_no":1}""",
                    HttpStatusCode.Created,
                    json,
                )
                r.url.host == "10.0.2.2" -> respond("", HttpStatusCode.OK)
                r.url.encodedPath.endsWith("/complete") -> respond("""{"id":"d1","title":"ID","category":"kyc_id","status":"active"}""", HttpStatusCode.OK, json)
                else -> respond("{}", HttpStatusCode.NotFound, json)
            }
        }
        val api = BrokerApi(httpClient(engine), endpoints) { "t" }
        val doc = api.uploadDocument(DocumentStart("id.jpg", 3, "kyc_id", links = listOf(EntityRef("client", "c1"))), byteArrayOf(1, 2, 3), "image/jpeg")
        assertEquals("active", doc.status)
        assertEquals(listOf(HttpMethod.Post, HttpMethod.Put, HttpMethod.Post), seen.map { it.method })
        assertEquals("the emulator reaches the computer's storage", "10.0.2.2", seen[1].url.host)
        assertEquals(null, seen[1].headers[HttpHeaders.Authorization])
    }

    @Test fun `validation problems show each field's message`() {
        val problem = Problem(title = "Invalid", errors = listOf(Problem.FieldError("phone", "Enter a Kenyan phone number"), Problem.FieldError("email", "Enter a valid email")))
        assertEquals("Enter a Kenyan phone number\nEnter a valid email", BrokerApi.problemMessage(422, problem))
        assertEquals("Someone else changed this just now. Reload and try again.", BrokerApi.problemMessage(412, Problem()))
    }

    @Test fun `server errors arrive as readable exceptions`() = runTest {
        val api = BrokerApi(httpClient(MockEngine { respond("""{"title":"Conflict","detail":"This client may already exist","code":"possible_duplicate"}""", HttpStatusCode.Conflict, json) }), endpoints) { "t" }
        try {
            api.createClient(ClientInput(firstName = "A", lastName = "B"), "k")
            fail("expected an error")
        } catch (e: AppException) {
            assertEquals("possible_duplicate", e.code)
            assertEquals("This client may already exist", e.message)
        }
    }

    @Test fun `dates read the way agents say them`() {
        val today = LocalDate.of(2026, 10, 19)
        assertEquals("today", Dates.relative("2026-10-19", today))
        assertEquals("tomorrow", Dates.relative("2026-10-20", today))
        assertEquals("in 10 days", Dates.relative("2026-10-29", today))
        assertEquals("3 days ago", Dates.relative("2026-10-16", today))
        assertEquals("19 Oct 2026", Dates.date("2026-10-19"))
        assertEquals(LocalDate.of(2026, 10, 19), Dates.fromPicker(Dates.toPicker(LocalDate.of(2026, 10, 19))))
    }

    @Test fun `codes have plain names`() {
        assertEquals("ID or passport copy", Labels.of("kyc_id"))
        assertEquals("WhatsApp", Labels.of("whatsapp"))
        assertEquals("Something new", Labels.of("something_new"))
    }

    @Test fun `storage links on the computer are rewritten for the emulator only`() {
        assertEquals("http://10.0.2.2:9000/a", endpoints.reachable("http://localhost:9000/a"))
        assertEquals("https://files.example/a", Endpoints("", "", "").reachable("https://files.example/a"))
    }
}
