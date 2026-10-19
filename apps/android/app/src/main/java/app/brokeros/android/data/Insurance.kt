package app.brokeros.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// ---------------------------------------------------------------- insurers, products, premium engine

@Serializable
data class Insurer(val id: String, val name: String, @SerialName("is_active") val isActive: Boolean = true)

@Serializable
data class Product(
    val id: String,
    @SerialName("insurer_id") val insurerId: String,
    val name: String,
    @SerialName("class_code") val classCode: String,
    @SerialName("rating_basis") val ratingBasis: String = "rate",
    val rate: String? = null,
    @SerialName("min_premium") val minPremium: String = "0",
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class InsuranceClass(val code: String, val name: String, @SerialName("rating_hint") val ratingHint: String = "")

@Serializable
data class TaxCode(val code: String, val name: String, val rate: String = "0", val kind: String = "")

@Serializable
data class Pack(
    val title: String = "",
    val signed: Boolean = true,
    @SerialName("sign_off_note") val signOffNote: String = "",
    val classes: List<InsuranceClass> = emptyList(),
    @SerialName("tax_codes") val taxCodes: List<TaxCode> = emptyList(),
)

/** What is being priced. Money values are decimal strings. */
@Serializable
data class Risk(
    @SerialName("sum_insured") val sumInsured: String? = null,
    @SerialName("manual_amount") val manualAmount: String? = null,
    val renewal: Boolean = false,
)

@Serializable
data class CompareRequest(
    @SerialName("product_ids") val productIds: List<String>,
    @SerialName("sum_insured") val sumInsured: String? = null,
    @SerialName("manual_amount") val manualAmount: String? = null,
    val renewal: Boolean = false,
)

@Serializable
data class ProductRef(val id: String, val name: String, @SerialName("insurer_name") val insurerName: String, @SerialName("excess_text") val excessText: String? = null)

@Serializable
data class Line(val label: String, val amount: String, val kind: String = "", @SerialName("charged_to") val chargedTo: String = "client")

@Serializable
data class Commission(val gross: String = "0", val net: String = "0", val rate: String = "0", val wht: String = "0")

@Serializable
data class Calculation(
    val product: ProductRef,
    val currency: String = "KES",
    @SerialName("basic_premium") val basicPremium: String = "0",
    @SerialName("client_total") val clientTotal: String = "0",
    val lines: List<Line> = emptyList(),
    val commission: Commission? = null,
    @SerialName("needs_input") val needsInput: List<String> = emptyList(),
    val notes: List<String> = emptyList(),
)

@Serializable
data class Comparison(val results: List<Calculation> = emptyList())

suspend fun BrokerApi.insurers(): List<Insurer> = get("/insurers")

suspend fun BrokerApi.products(classCode: String? = null): List<Product> = get("/products", mapOf("class_code" to classCode))

suspend fun BrokerApi.pack(): Pack = get("/jurisdiction-pack")

suspend fun BrokerApi.compare(request: CompareRequest): Comparison = post("/premium/compare", request)

// ---------------------------------------------------------------- quotes

@Serializable
data class ClientRef(
    val id: String,
    @SerialName("display_name") val displayName: String,
    val phone: String? = null,
    val email: String? = null,
)

@Serializable
data class Detail(val label: String, val value: String)

@Serializable
data class QuoteSummary(
    val id: String,
    val title: String,
    val number: String? = null,
    val status: String = "draft",
    val client: ClientRef,
    val currency: String = "KES",
    @SerialName("lowest_total") val lowestTotal: String? = null,
    val options: Int = 0,
    @SerialName("valid_until") val validUntil: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class QuoteOption(
    val position: Int,
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("product_name") val productName: String,
    @SerialName("product_id") val productId: String,
    @SerialName("client_total") val clientTotal: String,
    val recommended: Boolean = false,
    @SerialName("excess_text") val excessText: String? = null,
    /** Present only for people allowed to see commission. */
    val commission: JsonObject? = null,
    val breakdown: JsonObject? = null,
)

@Serializable
data class Quote(
    val id: String,
    val title: String,
    val number: String? = null,
    val status: String = "draft",
    val client: ClientRef,
    val currency: String = "KES",
    @SerialName("class_code") val classCode: String = "",
    @SerialName("option_list") val optionList: List<QuoteOption> = emptyList(),
    val details: List<Detail> = emptyList(),
    val notes: String? = null,
    @SerialName("valid_until") val validUntil: String? = null,
    @SerialName("sent_at") val sentAt: String? = null,
    @SerialName("accepted_position") val acceptedPosition: Int? = null,
    @SerialName("responded_at") val respondedAt: String? = null,
    val response: JsonObject? = null,
)

@Serializable
data class QuoteCreate(
    @SerialName("client_id") val clientId: String,
    @SerialName("product_ids") val productIds: List<String>,
    val risk: Risk,
    val title: String? = null,
    val details: List<Detail> = emptyList(),
    val notes: String? = null,
    @SerialName("recommended_product_id") val recommendedProductId: String? = null,
)

@Serializable
data class SendQuote(val email: String? = null, val message: String = "")

@Serializable
data class QuoteSent(val url: String, @SerialName("whatsapp_url") val whatsappUrl: String? = null, @SerialName("emailed_to") val emailedTo: String? = null, val quote: Quote)

suspend fun BrokerApi.quotes(clientId: String? = null, status: String? = null): List<QuoteSummary> =
    get("/quotes", mapOf("client_id" to clientId, "status" to status, "limit" to 100))

suspend fun BrokerApi.quote(id: String): Quote = get("/quotes/$id")

suspend fun BrokerApi.createQuote(input: QuoteCreate, key: String): Quote = post("/quotes", input, key)

suspend fun BrokerApi.sendQuote(id: String, input: SendQuote): QuoteSent = post("/quotes/$id/send", input)

suspend fun BrokerApi.withdrawQuote(id: String): Quote = action("/quotes/$id/withdraw")

// ---------------------------------------------------------------- policies and renewals

@Serializable
data class PolicySummary(
    val id: String,
    val description: String,
    @SerialName("policy_number") val policyNumber: String? = null,
    val client: ClientRef,
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("product_name") val productName: String = "",
    val status: String = "active",
    @SerialName("start_date") val startDate: String = "",
    @SerialName("end_date") val endDate: String = "",
    @SerialName("days_to_expiry") val daysToExpiry: Int = 0,
    @SerialName("total_premium") val totalPremium: String = "0",
    val balance: String = "0",
    val currency: String = "KES",
    @SerialName("renewal_stage") val renewalStage: String = "due",
)

@Serializable
data class PolicyPayment(
    val id: String,
    val amount: String,
    val currency: String = "KES",
    val method: String = "",
    @SerialName("paid_on") val paidOn: String = "",
    @SerialName("paid_to") val paidTo: String = "",
    val reference: String? = null,
    @SerialName("voided_at") val voidedAt: String? = null,
)

@Serializable
data class Policy(
    val id: String,
    val description: String,
    @SerialName("policy_number") val policyNumber: String? = null,
    val client: ClientRef,
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("product_name") val productName: String = "",
    @SerialName("class_code") val classCode: String = "",
    val status: String = "active",
    @SerialName("start_date") val startDate: String = "",
    @SerialName("end_date") val endDate: String = "",
    @SerialName("days_to_expiry") val daysToExpiry: Int = 0,
    @SerialName("total_premium") val totalPremium: String = "0",
    val paid: String = "0",
    val balance: String = "0",
    val unremitted: String = "0",
    val currency: String = "KES",
    @SerialName("collection_mode") val collectionMode: String = "insurer_direct",
    @SerialName("sum_insured") val sumInsured: String? = null,
    val details: List<Detail> = emptyList(),
    val payments: List<PolicyPayment> = emptyList(),
    val notes: String? = null,
    @SerialName("renewal_stage") val renewalStage: String = "due",
    @SerialName("renewal_quote_id") val renewalQuoteId: String? = null,
    @SerialName("lost_reason") val lostReason: String? = null,
    @SerialName("quote_id") val quoteId: String? = null,
    val commission: JsonObject? = null,
    val version: Int = 1,
)

@Serializable
data class PaymentIn(
    val amount: String,
    @SerialName("paid_on") val paidOn: String,
    val method: String = "mpesa",
    @SerialName("paid_to") val paidTo: String? = null,
    val reference: String? = null,
)

@Serializable
data class PolicyCreate(
    @SerialName("client_id") val clientId: String,
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String? = null,
    @SerialName("total_premium") val totalPremium: String,
    @SerialName("insurer_name") val insurerName: String? = null,
    @SerialName("product_id") val productId: String? = null,
    @SerialName("product_name") val productName: String? = null,
    @SerialName("class_code") val classCode: String? = null,
    val description: String? = null,
    @SerialName("policy_number") val policyNumber: String? = null,
    @SerialName("collection_mode") val collectionMode: String = "insurer_direct",
    @SerialName("insurer_confirmed") val insurerConfirmed: Boolean = false,
    val payment: PaymentIn? = null,
    @SerialName("sum_insured") val sumInsured: String? = null,
    @SerialName("renewed_from_id") val renewedFromId: String? = null,
    val notes: String? = null,
)

@Serializable
data class FromQuote(
    @SerialName("quote_id") val quoteId: String,
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String? = null,
    val option: Int? = null,
    @SerialName("policy_number") val policyNumber: String? = null,
    @SerialName("collection_mode") val collectionMode: String = "insurer_direct",
    @SerialName("insurer_confirmed") val insurerConfirmed: Boolean = false,
    val payment: PaymentIn? = null,
)

@Serializable
data class Activate(@SerialName("insurer_confirmed") val insurerConfirmed: Boolean = true, val basis: String = "paid", val note: String = "")

@Serializable
data class RenewalUpdate(val stage: String, @SerialName("lost_reason") val lostReason: String? = null, val note: String? = null)

@Serializable
data class Remind(val channel: String, val message: String? = null)

@Serializable
data class Reminded(@SerialName("whatsapp_url") val whatsappUrl: String? = null, @SerialName("emailed_to") val emailedTo: String? = null)

@Serializable
data class RenewalQuote(
    @SerialName("product_ids") val productIds: List<String>,
    val risk: Risk,
    val notes: String? = null,
)

@Serializable
data class RenewalColumn(val stage: String, val count: Int, val premium: String)

@Serializable
data class RenewalItem(
    val id: String,
    val description: String,
    val client: ClientRef,
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("end_date") val endDate: String = "",
    @SerialName("days_to_expiry") val daysToExpiry: Int = 0,
    @SerialName("total_premium") val totalPremium: String = "0",
    val currency: String = "KES",
    @SerialName("renewal_stage") val renewalStage: String = "due",
    @SerialName("renewal_quote_id") val renewalQuoteId: String? = null,
    @SerialName("renewal_quote_status") val renewalQuoteStatus: String? = null,
    @SerialName("lost_reason") val lostReason: String? = null,
    @SerialName("last_contacted_at") val lastContactedAt: String? = null,
    @SerialName("whatsapp_url") val whatsappUrl: String? = null,
)

@Serializable
data class RenewalBoard(
    val columns: List<RenewalColumn> = emptyList(),
    val items: List<RenewalItem> = emptyList(),
    val currency: String = "KES",
    @SerialName("window_days") val windowDays: Int = 60,
)

suspend fun BrokerApi.policies(clientId: String? = null, status: String? = null, query: String = ""): List<PolicySummary> =
    get("/policies", mapOf("client_id" to clientId, "status" to status, "q" to query.trim().ifBlank { null }, "limit" to 200))

suspend fun BrokerApi.policy(id: String): Policy = get("/policies/$id")

suspend fun BrokerApi.createPolicy(input: PolicyCreate, key: String): Policy = post("/policies", input, key)

suspend fun BrokerApi.policyFromQuote(input: FromQuote, key: String): Policy = post("/policies/from-quote", input, key)

suspend fun BrokerApi.recordPolicyPayment(id: String, input: PaymentIn): Policy = post("/policies/$id/payments", input)

suspend fun BrokerApi.activatePolicy(id: String, input: Activate): Policy = post("/policies/$id/activate", input)

suspend fun BrokerApi.renewalStage(id: String, input: RenewalUpdate): Policy = post("/policies/$id/renewal", input)

suspend fun BrokerApi.remind(id: String, input: Remind): Reminded = post("/policies/$id/remind", input)

suspend fun BrokerApi.renewalQuote(id: String, input: RenewalQuote): Quote = post("/policies/$id/renewal-quote", input)

suspend fun BrokerApi.renewals(windowDays: Int = 60): RenewalBoard = get("/renewals", mapOf("window_days" to windowDays))

// ---------------------------------------------------------------- commission

@Serializable
data class Amounts(val gross: String = "0", val net: String = "0", val wht: String = "0")

@Serializable
data class InsurerCommission(
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("expected_net") val expectedNet: String = "0",
    @SerialName("received_net") val receivedNet: String = "0",
    @SerialName("outstanding_net") val outstandingNet: String = "0",
    val wht: String = "0",
)

@Serializable
data class WhtCertificate(
    val certificate: String? = null,
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("received_on") val receivedOn: String = "",
    val wht: String = "0",
)

@Serializable
data class CommissionSummary(
    val year: Int,
    val currency: String = "KES",
    @SerialName("expected_net") val expectedNet: String = "0",
    @SerialName("received_net") val receivedNet: String = "0",
    @SerialName("outstanding_net") val outstandingNet: String = "0",
    val wht: String = "0",
    val insurers: List<InsurerCommission> = emptyList(),
    @SerialName("wht_certificates") val whtCertificates: List<WhtCertificate> = emptyList(),
)

@Serializable
data class StatementRow(
    @SerialName("policy_id") val policyId: String,
    @SerialName("client_name") val clientName: String,
    val description: String,
    @SerialName("policy_number") val policyNumber: String? = null,
    @SerialName("insurer_name") val insurerName: String,
    val currency: String = "KES",
    val expected: Amounts = Amounts(),
    val received: Amounts = Amounts(),
    val outstanding: Amounts = Amounts(),
)

@Serializable
data class Statement(val rows: List<StatementRow> = emptyList(), val currency: String = "KES")

@Serializable
data class AllocationIn(@SerialName("policy_id") val policyId: String, val gross: String, val wht: String? = null)

@Serializable
data class ReceiptCreate(
    @SerialName("insurer_name") val insurerName: String,
    @SerialName("received_on") val receivedOn: String,
    val lines: List<AllocationIn>,
    val reference: String? = null,
    @SerialName("wht_certificate") val whtCertificate: String? = null,
    val notes: String? = null,
)

@Serializable
data class Receipt(val id: String, @SerialName("insurer_name") val insurerName: String, val net: String = "0", val currency: String = "KES")

suspend fun BrokerApi.commissionSummary(year: Int? = null): CommissionSummary = get("/commissions/summary", mapOf("year" to year))

suspend fun BrokerApi.statement(insurer: String? = null, outstanding: Boolean = true): Statement =
    get("/commissions/statement", mapOf("insurer" to insurer, "outstanding" to outstanding))

suspend fun BrokerApi.recordCommission(input: ReceiptCreate, key: String): Receipt = post("/commission-receipts", input, key)
