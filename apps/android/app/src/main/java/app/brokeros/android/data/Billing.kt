package app.brokeros.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---------------------------------------------------------------- invoices, sales quotes, credit notes

@Serializable
data class BillingSummaryRow(
    val id: String,
    val kind: String = "invoice",
    val number: String? = null,
    val status: String = "draft",
    val client: ClientRef,
    val total: String = "0",
    val paid: String = "0",
    val balance: String = "0",
    val currency: String = "KES",
    @SerialName("issue_date") val issueDate: String? = null,
    @SerialName("due_date") val dueDate: String? = null,
    @SerialName("valid_until") val validUntil: String? = null,
    @SerialName("etims_cu_invoice_number") val etimsCuInvoiceNumber: String? = null,
)

@Serializable
data class BillingLine(
    val position: Int = 0,
    val description: String,
    val quantity: String = "1",
    @SerialName("unit_price") val unitPrice: String = "0",
    @SerialName("discount_rate") val discountRate: String = "0",
    @SerialName("tax_code") val taxCode: String = "",
    @SerialName("tax_rate") val taxRate: String = "0",
    val total: String = "0",
    val section: String? = null,
    val optional: Boolean = false,
    @SerialName("item_id") val itemId: String? = null,
)

@Serializable
data class TaxLine(val name: String, val rate: String = "0", val tax: String = "0")

@Serializable
data class Allocation(
    val amount: String,
    val source: String = "payment",
    @SerialName("source_number") val sourceNumber: String? = null,
    @SerialName("invoice_number") val invoiceNumber: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class BillingDocument(
    val id: String,
    val kind: String = "invoice",
    val number: String? = null,
    val status: String = "draft",
    val client: ClientRef,
    val currency: String = "KES",
    val lines: List<BillingLine> = emptyList(),
    val subtotal: String = "0",
    val discount: String = "0",
    val tax: String = "0",
    val taxes: List<TaxLine> = emptyList(),
    val total: String = "0",
    @SerialName("optional_total") val optionalTotal: String = "0",
    val paid: String = "0",
    val balance: String = "0",
    @SerialName("issue_date") val issueDate: String? = null,
    @SerialName("due_date") val dueDate: String? = null,
    @SerialName("valid_until") val validUntil: String? = null,
    val reference: String? = null,
    @SerialName("payment_reference") val paymentReference: String? = null,
    val notes: String? = null,
    val terms: String? = null,
    val allocations: List<Allocation> = emptyList(),
    @SerialName("void_reason") val voidReason: String? = null,
    @SerialName("response_status") val responseStatus: String? = null,
    @SerialName("converted_document_id") val convertedDocumentId: String? = null,
    @SerialName("credits_document_id") val creditsDocumentId: String? = null,
    @SerialName("etims_cu_invoice_number") val etimsCuInvoiceNumber: String? = null,
    @SerialName("etims_verification_url") val etimsVerificationUrl: String? = null,
    val version: Int = 1,
) {
    val isQuote get() = kind == "sales_quote"
    val isInvoice get() = kind == "invoice"
    val issued get() = status !in listOf("draft", "void")
}

@Serializable
data class LineInput(
    val description: String? = null,
    val quantity: String = "1",
    @SerialName("unit_price") val unitPrice: String? = null,
    @SerialName("discount_rate") val discountRate: String = "0",
    @SerialName("item_id") val itemId: String? = null,
    @SerialName("tax_code") val taxCode: String? = null,
    val section: String? = null,
    val optional: Boolean = false,
)

@Serializable
data class InvoiceCreate(
    @SerialName("client_id") val clientId: String,
    val lines: List<LineInput>,
    @SerialName("due_in_days") val dueInDays: Int? = null,
    @SerialName("valid_days") val validDays: Int? = null,
    val reference: String? = null,
    val notes: String? = null,
    val terms: String? = null,
    @SerialName("prices_include_tax") val pricesIncludeTax: Boolean = false,
)

@Serializable
data class InvoiceUpdate(
    val lines: List<LineInput>? = null,
    @SerialName("due_in_days") val dueInDays: Int? = null,
    @SerialName("valid_days") val validDays: Int? = null,
    val reference: String? = null,
    val notes: String? = null,
    val terms: String? = null,
)

@Serializable
data class Issue(@SerialName("issue_date") val issueDate: String? = null)

@Serializable
data class SendDocument(val email: String? = null, val message: String = "")

@Serializable
data class DocumentSent(val url: String, @SerialName("whatsapp_url") val whatsappUrl: String? = null, @SerialName("emailed_to") val emailedTo: String? = null, val document: BillingDocument)

@Serializable
data class VoidIn(val reason: String)

@Serializable
data class CreditNoteCreate(@SerialName("invoice_id") val invoiceId: String, val reason: String, val lines: List<LineInput>? = null)

@Serializable
data class EtimsIn(@SerialName("cu_invoice_number") val cuInvoiceNumber: String, @SerialName("verification_url") val verificationUrl: String? = null)

suspend fun BrokerApi.invoices(clientId: String? = null, status: String? = null): List<BillingSummaryRow> =
    get("/invoices", mapOf("client_id" to clientId, "status" to status, "limit" to 200))

suspend fun BrokerApi.salesQuotes(clientId: String? = null, status: String? = null): List<BillingSummaryRow> =
    get("/sales-quotes", mapOf("client_id" to clientId, "status" to status, "limit" to 200))

suspend fun BrokerApi.billingDocument(id: String): Versioned<BillingDocument> = getVersioned("/billing-documents/$id")

suspend fun BrokerApi.createInvoice(input: InvoiceCreate, key: String): BillingDocument = post("/invoices", input, key)

suspend fun BrokerApi.createSalesQuote(input: InvoiceCreate, key: String): BillingDocument = post("/sales-quotes", input, key)

suspend fun BrokerApi.updateDraft(id: String, input: InvoiceUpdate, etag: String?): Versioned<BillingDocument> =
    patch("/billing-documents/$id", input, etag)

suspend fun BrokerApi.issue(id: String): BillingDocument = post("/billing-documents/$id/issue", Issue())

suspend fun BrokerApi.sendDocument(id: String, input: SendDocument): DocumentSent = post("/billing-documents/$id/send", input)

suspend fun BrokerApi.voidDocument(id: String, reason: String): BillingDocument = post("/billing-documents/$id/void", VoidIn(reason))

suspend fun BrokerApi.creditNote(input: CreditNoteCreate, key: String): BillingDocument = post("/credit-notes", input, key)

suspend fun BrokerApi.convertSalesQuote(id: String): BillingDocument = action("/sales-quotes/$id/convert")

suspend fun BrokerApi.applyCredit(invoiceId: String): BillingDocument = action("/invoices/$invoiceId/apply-credit")

suspend fun BrokerApi.recordEtims(id: String, input: EtimsIn): BillingDocument = put("/billing-documents/$id/etims", input)

// ---------------------------------------------------------------- payments, accounts, items, summary

@Serializable
data class ReceivedPayment(
    val id: String,
    val number: String = "",
    val amount: String,
    val currency: String = "KES",
    val method: String = "",
    val client: ClientRef,
    @SerialName("received_on") val receivedOn: String = "",
    val reference: String? = null,
    val unallocated: String = "0",
    val allocations: List<Allocation> = emptyList(),
    @SerialName("voided_at") val voidedAt: String? = null,
)

@Serializable
data class AllocationTo(@SerialName("invoice_id") val invoiceId: String, val amount: String)

@Serializable
data class PaymentCreate(
    @SerialName("client_id") val clientId: String,
    val amount: String,
    @SerialName("received_on") val receivedOn: String,
    val method: String = "mpesa",
    val reference: String? = null,
    val allocations: List<AllocationTo>? = null,
    val notes: String? = null,
)

@Serializable
data class ClientAccount(
    val credit: String = "0",
    val owed: String = "0",
    val currency: String = "KES",
    @SerialName("open_invoices") val openInvoices: List<BillingSummaryRow> = emptyList(),
)

@Serializable
data class Item(
    val id: String,
    val name: String,
    @SerialName("unit_price") val unitPrice: String = "0",
    @SerialName("tax_code") val taxCode: String = "",
    val currency: String = "KES",
    val active: Boolean = true,
)

@Serializable
data class AgeingBucket(val label: String, val count: Int = 0, val amount: String = "0")

@Serializable
data class BillingSummary(
    val currency: String = "KES",
    val outstanding: String = "0",
    val overdue: String = "0",
    @SerialName("overdue_count") val overdueCount: Int = 0,
    @SerialName("invoiced_this_month") val invoicedThisMonth: String = "0",
    @SerialName("collected_this_month") val collectedThisMonth: String = "0",
    @SerialName("quotes_awaiting") val quotesAwaiting: Int = 0,
    @SerialName("quotes_awaiting_total") val quotesAwaitingTotal: String = "0",
    @SerialName("etims_pending") val etimsPending: Int = 0,
    val ageing: List<AgeingBucket> = emptyList(),
)

suspend fun BrokerApi.payments(clientId: String? = null): List<ReceivedPayment> = get("/payments", mapOf("client_id" to clientId, "limit" to 200))

suspend fun BrokerApi.recordPayment(input: PaymentCreate, key: String): ReceivedPayment = post("/payments", input, key)

suspend fun BrokerApi.voidPayment(id: String, reason: String): ReceivedPayment = post("/payments/$id/void", VoidIn(reason))

suspend fun BrokerApi.account(clientId: String): ClientAccount = get("/clients/$clientId/account")

suspend fun BrokerApi.items(): List<Item> = get("/items")

suspend fun BrokerApi.billingSummary(): BillingSummary = get("/billing/summary")

// ---------------------------------------------------------------- M-Pesa

@Serializable
data class MpesaConnection(val status: String = "", val environment: String = "", @SerialName("business_shortcode") val shortcode: String = "")

@Serializable
data class PromptIn(val phone: String? = null)

@Serializable
data class Prompt(
    val id: String,
    val status: String = "pending",
    val amount: String = "0",
    val phone: String = "",
    val receipt: String? = null,
    @SerialName("result_desc") val resultDesc: String? = null,
)

@Serializable
data class MpesaTransaction(
    val id: String,
    val receipt: String,
    val amount: String,
    val payer: String? = null,
    @SerialName("bill_reference") val billReference: String? = null,
    @SerialName("paid_at") val paidAt: String? = null,
    val status: String = "unmatched",
    val note: String? = null,
)

@Serializable
data class MatchIn(@SerialName("client_id") val clientId: String, @SerialName("invoice_id") val invoiceId: String? = null)

@Serializable
data class IgnoreIn(val reason: String)

suspend fun BrokerApi.mpesaConnection(): MpesaConnection? = get("/mpesa/connection")

suspend fun BrokerApi.mpesaPrompt(invoiceId: String, phone: String?): Prompt = post("/invoices/$invoiceId/mpesa-prompt", PromptIn(phone))

suspend fun BrokerApi.prompt(id: String): Prompt = get("/mpesa/prompts/$id")

suspend fun BrokerApi.unmatched(): List<MpesaTransaction> = get("/mpesa/transactions", mapOf("status" to "unmatched", "limit" to 100))

suspend fun BrokerApi.matchTransaction(id: String, input: MatchIn): MpesaTransaction = post("/mpesa/transactions/$id/match", input)

suspend fun BrokerApi.ignoreTransaction(id: String, reason: String): MpesaTransaction = post("/mpesa/transactions/$id/ignore", IgnoreIn(reason))
