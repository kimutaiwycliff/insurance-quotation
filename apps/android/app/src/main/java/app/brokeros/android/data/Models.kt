package app.brokeros.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Only the fields the app shows; the JSON reader ignores the rest, so new API fields never break the app.

@Serializable
data class Agency(val id: String, val name: String, val slug: String? = null)

@Serializable
data class TenantSummary(val id: String, val name: String)

@Serializable
data class Me(
    @SerialName("user_id") val userId: String,
    val email: String,
    val name: String,
    val tenant: TenantSummary,
    val role: String,
    val permissions: List<String> = emptyList(),
    val plan: String = "",
    val features: List<String> = emptyList(),
    @SerialName("read_only") val readOnly: Boolean = false,
) {
    val firstName: String get() = name.trim().split(" ").firstOrNull()?.takeIf { it.isNotBlank() } ?: email
    fun can(permission: String): Boolean = permission in permissions
}

@Serializable
data class TaskCounts(val overdue: Int = 0, val today: Int = 0, val upcoming: Int = 0)

@Serializable
data class BookStats(
    val currency: String = "KES",
    @SerialName("written_premium") val writtenPremium: String = "0",
    @SerialName("written_count") val writtenCount: Int = 0,
    @SerialName("outstanding_premium") val outstandingPremium: String = "0",
)

@Serializable
data class Dashboard(
    val clients: Int = 0,
    @SerialName("new_clients_30d") val newClients30d: Int = 0,
    val tasks: TaskCounts? = null,
    @SerialName("policies_active") val policiesActive: Int = 0,
    @SerialName("renewals_due_30d") val renewalsDue30d: Int = 0,
    @SerialName("premiums_to_remit") val premiumsToRemit: Int = 0,
    @SerialName("documents_expiring_30d") val documentsExpiring30d: Int = 0,
    val book: BookStats = BookStats(),
)

@Serializable
data class ClientSummary(
    val id: String,
    @SerialName("display_name") val displayName: String,
    val kind: String = "individual",
    val phone: String? = null,
    val email: String? = null,
    val status: String = "active",
    val tags: List<String> = emptyList(),
)

@Serializable
data class ClientPage(val items: List<ClientSummary>, @SerialName("next_cursor") val nextCursor: String? = null)

@Serializable
data class Client(
    val id: String,
    @SerialName("display_name") val displayName: String,
    val kind: String = "individual",
    val phone: String? = null,
    @SerialName("alt_phone") val altPhone: String? = null,
    val email: String? = null,
    @SerialName("kra_pin") val kraPin: String? = null,
    val occupation: String? = null,
    val status: String = "active",
    val tags: List<String> = emptyList(),
    val notes: String? = null,
    @SerialName("preferred_channel") val preferredChannel: String? = null,
)

/** RFC 9457 problem from the API. */
@Serializable
data class Problem(val title: String = "", val detail: String? = null, val code: String = "")

/** Better Auth error body. */
@Serializable
data class AuthError(val message: String = "", val code: String = "")
