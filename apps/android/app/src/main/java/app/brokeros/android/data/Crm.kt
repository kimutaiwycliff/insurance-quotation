package app.brokeros.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---------------------------------------------------------------- clients

/** Create or update a client. Unset fields are left out of the JSON (explicitNulls = false). */
@Serializable
data class ClientInput(
    val kind: String? = null,
    @SerialName("first_name") val firstName: String? = null,
    @SerialName("last_name") val lastName: String? = null,
    @SerialName("other_names") val otherNames: String? = null,
    @SerialName("company_name") val companyName: String? = null,
    val phone: String? = null,
    @SerialName("alt_phone") val altPhone: String? = null,
    val email: String? = null,
    @SerialName("kra_pin") val kraPin: String? = null,
    @SerialName("id_type") val idType: String? = null,
    @SerialName("id_number") val idNumber: String? = null,
    @SerialName("date_of_birth") val dateOfBirth: String? = null,
    val gender: String? = null,
    val occupation: String? = null,
    val notes: String? = null,
    val source: String? = null,
    @SerialName("preferred_channel") val preferredChannel: String? = null,
    @SerialName("marketing_consent") val marketingConsent: Boolean? = null,
    val address: Address? = null,
    val tags: List<String>? = null,
    @SerialName("allow_duplicate") val allowDuplicate: Boolean? = null,
    val archived: Boolean? = null,
)

@Serializable
data class DuplicateCheck(
    val phone: String? = null,
    val email: String? = null,
    @SerialName("kra_pin") val kraPin: String? = null,
    @SerialName("id_number") val idNumber: String? = null,
    @SerialName("exclude_id") val excludeId: String? = null,
)

@Serializable
data class DuplicateMatch(val client: ClientSummary, @SerialName("matched_on") val matchedOn: List<String> = emptyList())

@Serializable
data class DuplicateResult(val matches: List<DuplicateMatch> = emptyList(), val hidden: Int = 0)

@Serializable
data class TimelineItem(
    val at: String,
    val kind: String,
    val title: String,
    val detail: String? = null,
    val actor: String? = null,
)

@Serializable
data class ActivityInput(val kind: String, val body: String, @SerialName("occurred_at") val occurredAt: String? = null)

@Serializable
data class ActivityOut(val id: String, val kind: String, val body: String)

suspend fun BrokerApi.clients(query: String, cursor: String? = null): ClientPage =
    get("/clients", mapOf("q" to query.trim().ifBlank { null }, "cursor" to cursor, "limit" to 30))

suspend fun BrokerApi.client(id: String): Versioned<Client> = getVersioned("/clients/$id")

suspend fun BrokerApi.createClient(input: ClientInput, key: String): Client = post("/clients", input, key)

suspend fun BrokerApi.updateClient(id: String, input: ClientInput, etag: String?): Versioned<Client> =
    patch("/clients/$id", input, etag)

suspend fun BrokerApi.checkDuplicates(check: DuplicateCheck): DuplicateResult = post("/clients/duplicates", check)

suspend fun BrokerApi.timeline(clientId: String): List<TimelineItem> = get("/clients/$clientId/timeline")

suspend fun BrokerApi.logActivity(clientId: String, input: ActivityInput): ActivityOut =
    post("/clients/$clientId/activities", input)

// ---------------------------------------------------------------- tasks

@Serializable
data class Task(
    val id: String,
    val title: String,
    val status: String = "open",
    val priority: String = "normal",
    @SerialName("due_at") val dueAt: String? = null,
    val notes: String? = null,
    @SerialName("entity_type") val entityType: String? = null,
    @SerialName("entity_id") val entityId: String? = null,
    @SerialName("completed_at") val completedAt: String? = null,
    val version: Int = 1,
)

@Serializable
data class TaskInput(
    val title: String? = null,
    @SerialName("due_at") val dueAt: String? = null,
    val priority: String? = null,
    val notes: String? = null,
    @SerialName("entity_type") val entityType: String? = null,
    @SerialName("entity_id") val entityId: String? = null,
    val done: Boolean? = null,
)

/** due: overdue | today | upcoming | none | all; status: open | done | all. */
suspend fun BrokerApi.tasks(
    due: String = "all",
    status: String = "open",
    entityType: String? = null,
    entityId: String? = null,
): List<Task> = get("/tasks", mapOf("due" to due, "status" to status, "entity_type" to entityType, "entity_id" to entityId))

suspend fun BrokerApi.createTask(input: TaskInput, key: String): Task = post("/tasks", input, key)

/** Tasks carry their version in the body, so If-Match comes from it. */
suspend fun BrokerApi.updateTask(task: Task, input: TaskInput): Task =
    patch<TaskInput, Task>("/tasks/${task.id}", input, "\"${task.version}\"").value

// ---------------------------------------------------------------- leads

@Serializable
data class Lead(
    val id: String,
    val name: String,
    val phone: String? = null,
    val email: String? = null,
    val stage: String = "new",
    val source: String = "other",
    val interests: List<String> = emptyList(),
    @SerialName("estimated_premium") val estimatedPremium: Money? = null,
    @SerialName("next_follow_up_at") val nextFollowUpAt: String? = null,
    @SerialName("lost_reason") val lostReason: String? = null,
    val notes: String? = null,
    @SerialName("client_id") val clientId: String? = null,
    val version: Int = 1,
)

@Serializable
data class LeadInput(
    val name: String? = null,
    val phone: String? = null,
    val email: String? = null,
    val stage: String? = null,
    val source: String? = null,
    val interests: List<String>? = null,
    @SerialName("estimated_premium") val estimatedPremium: Money? = null,
    @SerialName("next_follow_up_at") val nextFollowUpAt: String? = null,
    @SerialName("lost_reason") val lostReason: String? = null,
    val notes: String? = null,
)

@Serializable
data class StageSummary(val stage: String, val count: Int, @SerialName("estimated_premium") val estimatedPremium: Money)

@Serializable
data class LeadPipeline(val stages: List<StageSummary> = emptyList(), @SerialName("follow_ups_due") val followUpsDue: Int = 0)

@Serializable
data class ConvertLead(
    val kind: String = "individual",
    @SerialName("first_name") val firstName: String? = null,
    @SerialName("last_name") val lastName: String? = null,
    @SerialName("company_name") val companyName: String? = null,
    @SerialName("allow_duplicate") val allowDuplicate: Boolean = false,
)

@Serializable
data class Converted(@SerialName("client_id") val clientId: String, val lead: Lead)

suspend fun BrokerApi.leads(stage: String? = null, query: String = "", followUpDue: Boolean = false): List<Lead> =
    get("/leads", mapOf("stage" to stage, "q" to query.trim().ifBlank { null }, "follow_up_due" to followUpDue.takeIf { it }))

suspend fun BrokerApi.pipeline(): LeadPipeline = get("/leads/pipeline")

suspend fun BrokerApi.lead(id: String): Lead = get("/leads/$id")

suspend fun BrokerApi.createLead(input: LeadInput, key: String): Lead = post("/leads", input, key)

suspend fun BrokerApi.updateLead(lead: Lead, input: LeadInput): Lead =
    patch<LeadInput, Lead>("/leads/${lead.id}", input, "\"${lead.version}\"").value

suspend fun BrokerApi.convertLead(id: String, input: ConvertLead): Converted = post("/leads/$id/convert", input)

// ---------------------------------------------------------------- documents

@Serializable
data class Document(
    val id: String,
    val title: String,
    val category: String,
    val status: String = "active",
    @SerialName("expires_on") val expiresOn: String? = null,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("current_version_no") val currentVersionNo: Int? = null,
)

@Serializable
data class DocumentPage(val items: List<Document>, @SerialName("next_cursor") val nextCursor: String? = null)

@Serializable
data class EntityRef(@SerialName("entity_type") val entityType: String, @SerialName("entity_id") val entityId: String)

@Serializable
data class DocumentStart(
    val filename: String,
    @SerialName("size_bytes") val sizeBytes: Long,
    val category: String,
    val title: String? = null,
    @SerialName("expires_on") val expiresOn: String? = null,
    val links: List<EntityRef> = emptyList(),
)

@Serializable
data class UploadTicket(val url: String, val method: String = "PUT", val headers: Map<String, String> = emptyMap())

@Serializable
data class UploadStarted(val document: Document, val upload: UploadTicket, @SerialName("version_no") val versionNo: Int)

@Serializable
data class DownloadUrl(val url: String)

suspend fun BrokerApi.documents(entityType: String, entityId: String): DocumentPage =
    get("/documents", mapOf("entity_type" to entityType, "entity_id" to entityId, "limit" to 100))

/** Presigned upload (ADR-0023): register, send the bytes straight to storage, then let the API verify them. */
suspend fun BrokerApi.uploadDocument(start: DocumentStart, bytes: ByteArray, contentType: String): Document {
    val started: UploadStarted = post("/documents", start, newIdempotencyKey())
    upload(started.upload.url, started.upload.headers, bytes, contentType)
    return action("/documents/${started.document.id}/versions/${started.versionNo}/complete")
}

suspend fun BrokerApi.downloadUrl(documentId: String): String =
    endpoints.reachable(get<DownloadUrl>("/documents/$documentId/download", mapOf("inline" to true)).url)
