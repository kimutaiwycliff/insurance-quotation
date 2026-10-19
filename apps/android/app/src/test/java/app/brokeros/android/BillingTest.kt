package app.brokeros.android

import app.brokeros.android.core.Endpoints
import app.brokeros.android.data.AllocationTo
import app.brokeros.android.data.ApiJson
import app.brokeros.android.data.BillingDocument
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.InvoiceCreate
import app.brokeros.android.data.PaymentCreate
import app.brokeros.android.data.createSalesQuote
import app.brokeros.android.data.httpClient
import app.brokeros.android.data.prompt
import app.brokeros.android.data.recordPayment
import app.brokeros.android.ui.money.LineDraft
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

private val json = headersOf(HttpHeaders.ContentType, "application/json")
private val endpoints = Endpoints("https://app.test", "https://api.test", "https://app.test")
private fun HttpRequestData.text() = (body as? OutgoingContent.ByteArrayContent)?.bytes()?.let(::String).orEmpty()

class BillingTest {
    @Test fun `a 10 percent discount is sent as the fraction 0_1`() {
        val line = LineDraft(description = "Monthly bookkeeping", quantity = "3", unitPrice = "1500", discountPercent = "10", taxCode = "vat_standard")
        val input = line.toInput()
        assertEquals("0.1", input.discountRate)
        assertEquals(0, BigDecimal("4050").compareTo(line.estimate())) // 3 × 1,500 less 10%, before tax
        assertEquals("0", LineDraft(description = "x", unitPrice = "1").toInput().discountRate)
    }

    @Test fun `an issued invoice reads its totals and payments`() {
        val d = ApiJson.decodeFromString(
            BillingDocument.serializer(),
            """{"id":"i1","kind":"invoice","number":"INV-2026-00001","status":"part_paid","client":{"id":"c1","display_name":"Wanjiru Kamau"},
               "lines":[{"position":1,"description":"Monthly bookkeeping","quantity":"3","unit_price":"1500.0000","discount_rate":"0.1","tax_code":"vat_standard","tax_rate":"0.16","total":"4698.0000","net":"4050","tax":"648"}],
               "subtotal":"4050.0000","tax":"648.0000","taxes":[{"name":"VAT 16%","rate":"0.16","tax":"648.0000","code":"vat_standard","taxable":"4050"}],
               "total":"4698.0000","paid":"2000.0000","balance":"2698.0000","allocations":[{"amount":"2000.0000","source":"payment","source_number":"RCT-1","created_at":"2026-10-19T10:00:00Z","id":"a1","invoice_id":"i1","source_id":"p1"}],
               "something_new":true}""",
        )
        assertTrue(d.isInvoice && d.issued)
        assertEquals("2698.0000", d.balance)
        assertEquals("VAT 16%", d.taxes.single().name)
        assertEquals("RCT-1", d.allocations.single().sourceNumber)
    }

    @Test fun `a payment is applied to the invoice it was recorded on`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r -> seen += r; respond("""{"id":"p1","amount":"2000","client":{"id":"c1","display_name":"W"}}""", HttpStatusCode.Created, json) }), endpoints) { "t" }
        api.recordPayment(PaymentCreate("c1", "2000", "2026-10-19", "mpesa", "SJK12AB34C", listOf(AllocationTo("i1", "2000"))), "k")
        val body = seen.single().text()
        assertTrue(body.contains("\"allocations\":[{\"invoice_id\":\"i1\",\"amount\":\"2000\"}]"))
        assertTrue(body.contains("\"reference\":\"SJK12AB34C\""))
    }

    @Test fun `a sales quote sends optional extras and its validity, not a due date`() = runTest {
        val seen = mutableListOf<HttpRequestData>()
        val api = BrokerApi(httpClient(MockEngine { r -> seen += r; respond("""{"id":"q1","kind":"sales_quote","client":{"id":"c1","display_name":"O"}}""", HttpStatusCode.Created, json) }), endpoints) { "t" }
        api.createSalesQuote(
            InvoiceCreate("c1", listOf(LineDraft(description = "Hosting", unitPrice = "5000", taxCode = "vat_standard", optional = true).toInput()), validDays = 30),
            "k",
        )
        val body = seen.single().text()
        assertTrue(body.contains("\"optional\":true"))
        assertTrue(body.contains("\"valid_days\":30"))
        assertFalse(body.contains("due_in_days"))
    }

    @Test fun `an M-Pesa prompt reports its outcome`() = runTest {
        val api = BrokerApi(httpClient(MockEngine { respond("""{"id":"m1","status":"paid","amount":"2698","phone":"+254712345678","receipt":"SIM123"}""", HttpStatusCode.OK, json) }), endpoints) { "t" }
        val p = api.prompt("m1")
        assertEquals("paid", p.status)
        assertEquals("SIM123", p.receipt)
    }
}
