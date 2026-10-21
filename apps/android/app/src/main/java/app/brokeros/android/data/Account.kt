package app.brokeros.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---------------------------------------------------------------- plan and billing (our own subscription)

@Serializable
data class Usage(val clients: Int = 0, @SerialName("documents_this_month") val documentsThisMonth: Int = 0, @SerialName("seats_used") val seatsUsed: Int = 1)

@Serializable
data class Subscription(
    val plan: String,
    @SerialName("plan_name") val planName: String = "",
    @SerialName("paid_plan") val paidPlan: String = "trial",
    val status: String = "trialing",
    @SerialName("trial_ends_at") val trialEndsAt: String? = null,
    @SerialName("period_end") val periodEnd: String? = null,
    @SerialName("founding_member") val foundingMember: Boolean = false,
    @SerialName("founding_places_left") val foundingPlacesLeft: Int = 0,
    @SerialName("discount_percent") val discountPercent: Int = 0,
    val limits: Map<String, Int> = emptyMap(),
    val seats: Int = 1,
    val usage: Usage = Usage(),
)

@Serializable
data class PlanPrice(val cycle: String, @SerialName("list_price") val listPrice: String, val price: String, @SerialName("discount_percent") val discountPercent: Int = 0)

@Serializable
data class Plan(
    val code: String,
    val name: String,
    val tagline: String = "",
    val features: List<String> = emptyList(),
    val limits: Map<String, Int> = emptyMap(),
    @SerialName("included_seats") val includedSeats: Int = 1,
    @SerialName("extra_seat_monthly") val extraSeatMonthly: String? = null,
    val prices: List<PlanPrice> = emptyList(),
)

@Serializable
data class Checkout(val plan: String, val cycle: String = "monthly", val phone: String, @SerialName("extra_seats") val extraSeats: Int = 0)

@Serializable
data class SubscriptionPayment(
    val id: String,
    val status: String = "pending",
    val amount: String = "0",
    val plan: String = "",
    val receipt: String? = null,
    @SerialName("result_desc") val resultDesc: String? = null,
    @SerialName("period_end") val periodEnd: String? = null,
)

suspend fun BrokerApi.subscription(): Subscription = get("/subscription")

suspend fun BrokerApi.plans(): List<Plan> = get("/subscription/plans")

suspend fun BrokerApi.checkout(input: Checkout): SubscriptionPayment = post("/subscription/checkout", input)

suspend fun BrokerApi.subscriptionPayment(id: String): SubscriptionPayment = get("/subscription/payments/$id")

// ---------------------------------------------------------------- notifications

@Serializable
data class Notification(
    val id: String,
    val title: String,
    val body: String = "",
    val kind: String = "",
    val link: String? = null,
    @SerialName("read_at") val readAt: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class NotificationPage(val items: List<Notification> = emptyList(), @SerialName("next_cursor") val nextCursor: String? = null)

@Serializable
data class UnreadCount(val unread: Int = 0)

suspend fun BrokerApi.notifications(): NotificationPage = get("/notifications", mapOf("limit" to 50))

suspend fun BrokerApi.unreadCount(): Int = get<UnreadCount>("/notifications/unread-count").unread

suspend fun BrokerApi.markRead(id: String) { send(io.ktor.http.HttpMethod.Post, "/notifications/$id/read") {} }

suspend fun BrokerApi.markAllRead() { send(io.ktor.http.HttpMethod.Post, "/notifications/read-all") {} }

// ---------------------------------------------------------------- agency profile

@Serializable
data class Organization(
    val name: String,
    @SerialName("legal_name") val legalName: String? = null,
    @SerialName("tax_pin") val taxPin: String? = null,
    @SerialName("licence_number") val licenceNumber: String? = null,
    @SerialName("licence_expiry") val licenceExpiry: String? = null,
    @SerialName("registration_number") val registrationNumber: String? = null,
    val email: String? = null,
    val phone: String? = null,
    @SerialName("etims_enabled") val etimsEnabled: Boolean = false,
    @SerialName("renewal_client_emails") val renewalClientEmails: Boolean = false,
    @SerialName("billing_reminders") val billingReminders: Boolean = false,
    val version: Int = 1,
)

@Serializable
data class OrganizationUpdate(
    val name: String? = null,
    @SerialName("legal_name") val legalName: String? = null,
    @SerialName("tax_pin") val taxPin: String? = null,
    @SerialName("licence_number") val licenceNumber: String? = null,
    @SerialName("licence_expiry") val licenceExpiry: String? = null,
    val email: String? = null,
    val phone: String? = null,
    @SerialName("renewal_client_emails") val renewalClientEmails: Boolean? = null,
    @SerialName("billing_reminders") val billingReminders: Boolean? = null,
    @SerialName("etims_enabled") val etimsEnabled: Boolean? = null,
)

suspend fun BrokerApi.organization(): Versioned<Organization> = getVersioned("/organization")

suspend fun BrokerApi.updateOrganization(input: OrganizationUpdate, etag: String?): Versioned<Organization> = patch("/organization", input, etag)

@Serializable
data class Role(val key: String, val description: String = "")

suspend fun BrokerApi.roles(): List<Role> = get("/roles")
