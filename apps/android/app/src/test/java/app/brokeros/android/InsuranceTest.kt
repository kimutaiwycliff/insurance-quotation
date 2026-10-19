package app.brokeros.android

import app.brokeros.android.core.Endpoints
import app.brokeros.android.data.AllocationIn
import app.brokeros.android.data.ApiJson
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.CompareRequest
import app.brokeros.android.data.Policy
import app.brokeros.android.data.Quote
import app.brokeros.android.data.ReceiptCreate
import app.brokeros.android.data.compare
import app.brokeros.android.data.httpClient
import app.brokeros.android.data.recordCommission
import app.brokeros.android.data.renewals
import app.brokeros.android.ui.home.money
import app.brokeros.android.ui.insurance.amountOf
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private val json = headersOf(HttpHeaders.ContentType, "application/json")
private val endpoints = Endpoints("https://app.test", "https://api.test", "https://app.test")
private fun HttpRequestData.text() = (body as? OutgoingContent.ByteArrayContent)?.bytes()?.let(::String).orEmpty()

class InsuranceTest {
    @Test fun `a comparison quote reads options, acceptance and commission when shown`() {
        val q = ApiJson.decodeFromString(
            Quote.serializer(),
            """{"id":"q1","title":"Motor private quotation","number":"QT-2026-00001","status":"accepted","client":{"id":"c1","display_name":"Otieno Ochieng"},
               "currency":"KES","accepted_position":1,"response":{"name":"Otieno Ochieng","option":1},"future_field":{"x":1},
               "option_list":[{"position":1,"insurer_name":"Rift Assurance","product_name":"Motor","product_id":"p1","client_total":"70355.0000","recommended":true,"commission":{"gross":"7000.0000"},"breakdown":{}},
                              {"position":2,"insurer_name":"Savanna General","product_name":"Motor","product_id":"p2","client_total":"80355.0000","commission":null,"breakdown":{}}]}""",
        )
        assertEquals(1, q.acceptedPosition)
        assertEquals("Otieno Ochieng", q.response?.get("name")?.jsonPrimitive?.content)
        assertEquals("7000.0000", q.optionList[0].commission?.get("gross")?.jsonPrimitive?.content)
        assertNull("hidden from roles without commission access", q.optionList[1].commission)
    }

    @Test fun `new statuses from a newer server do not break older apps`() {
        val p = ApiJson.decodeFromString(
            Policy.serializer(),
            """{"id":"p1","description":"KCB 789C Honda Fit","client":{"id":"c1","display_name":"Achieng"},"insurer_name":"Jubilee","status":"suspended","renewal_stage":"negotiating"}""",
        )
        assertEquals("suspended", p.status)
        assertEquals("negotiating", p.renewalStage)
    }

    @Test fun `the calculator sends only what was typed`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r -> seen += r; respond("""{"results":[{"product":{"id":"p1","name":"Motor","insurer_name":"Rift"},"client_total":"70355.0000"}]}""", HttpStatusCode.OK, json) }), endpoints) { "t" }
        val result = api.compare(CompareRequest(listOf("p1", "p2"), sumInsured = "2000000"))
        assertEquals("Rift", result.results.single().product.insurerName)
        val body = seen.single().text()
        assertTrue(body.contains("\"sum_insured\":\"2000000\""))
        assertFalse(body.contains("manual_amount"))
    }

    @Test fun `recording commission sends the policies and a retry-safe key`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r -> seen += r; respond("""{"id":"r1","insurer_name":"Savanna","net":"5400.0000"}""", HttpStatusCode.Created, json) }), endpoints) { "t" }
        api.recordCommission(ReceiptCreate("Savanna", "2026-10-19", listOf(AllocationIn("pol1", "3500"), AllocationIn("pol2", "2500")), whtCertificate = "KRAWHT0099"), "k1")
        val body = seen.single().text()
        assertTrue(body.contains("\"wht_certificate\":\"KRAWHT0099\""))
        assertTrue(body.contains("\"policy_id\":\"pol2\""))
        assertEquals("k1", seen.single().headers["Idempotency-Key"])
    }

    @Test fun `the renewal board groups policies by stage`() = runTest {
        val api = BrokerApi(httpClient(MockEngine {
            respond(
                """{"columns":[{"stage":"due","count":1,"premium":"38500.0000"}],"currency":"KES","window_days":60,
                    "items":[{"id":"p1","description":"KCB 789C","client":{"id":"c1","display_name":"Achieng"},"insurer_name":"Jubilee","renewal_stage":"due","days_to_expiry":10,"whatsapp_url":"https://wa.me/254700000000"}]}""",
                HttpStatusCode.OK,
                json,
            )
        }), endpoints) { "t" }
        val board = api.renewals()
        assertEquals(1, board.columns.single().count)
        assertEquals("https://wa.me/254700000000", board.items.single().whatsappUrl)
    }

    @Test fun `money shows two decimals where the currency has them`() {
        assertEquals("KES 70,355.00", money("70355.0000", "KES", decimals = true))
        assertEquals("UGX 1,850,000", money("1850000", "UGX", decimals = true))
        assertEquals("2000000", amountOf("2,000,000"))
    }
}
