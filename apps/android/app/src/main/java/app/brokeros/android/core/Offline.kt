package app.brokeros.android.core

import app.brokeros.android.data.ApiJson
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonElement
import java.io.File
import java.security.MessageDigest

/**
 * The last good answer to every read, kept in the app's private storage so screens still show something with
 * no signal (cleared on sign-out). Bounded: the oldest answers are dropped first.
 */
class ResponseCache(private val dir: File, private val maxEntries: Int = 400) {
    init { dir.mkdirs() }

    fun key(path: String, params: Map<String, Any?>): String {
        val text = path + "?" + params.filterValues { it != null }.toSortedMap().entries.joinToString("&") { "${it.key}=${it.value}" }
        return MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }.take(40)
    }

    fun put(key: String, text: String) {
        runCatching {
            File(dir, "$key.json").writeText(text)
            val files = dir.listFiles().orEmpty()
            if (files.size > maxEntries) files.sortedBy { it.lastModified() }.take(files.size - maxEntries).forEach { it.delete() }
        }
    }

    /** The saved text and when it was saved (epoch millis). */
    fun get(key: String): Pair<String, Long>? = File(dir, "$key.json").takeIf { it.exists() }?.let { it.readText() to it.lastModified() }

    fun clear() { dir.listFiles()?.forEach { it.delete() } }
}

/** A write made while offline, sent later in order. */
@Serializable
data class PendingWrite(
    val id: String,
    val method: String,
    val path: String,
    val body: JsonElement,
    val label: String,
    val idempotencyKey: String? = null,
    val ifMatch: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
)

/** Writes waiting for the connection to come back, persisted so they survive the app closing. */
class Outbox(private val file: File) {
    private val lock = Mutex()
    private val _pending = MutableStateFlow(load())
    val pending: StateFlow<List<PendingWrite>> = _pending.asStateFlow()
    private val _failed = MutableStateFlow<List<String>>(emptyList())

    /** Changes the server refused when they were finally sent (e.g. the record changed meanwhile). */
    val failed: StateFlow<List<String>> = _failed.asStateFlow()

    private fun load(): List<PendingWrite> = runCatching {
        ApiJson.decodeFromString(ListSerializer(PendingWrite.serializer()), file.readText())
    }.getOrDefault(emptyList())

    private fun save(list: List<PendingWrite>) {
        _pending.value = list
        runCatching { file.writeText(ApiJson.encodeToString(ListSerializer(PendingWrite.serializer()), list)) }
    }

    suspend fun add(write: PendingWrite) = lock.withLock { save(_pending.value + write) }

    /**
     * Send what is waiting, oldest first. [send] returns normally on success, throws [Offline] when still offline
     * (stop and try later), or throws anything else when the server refused (dropped and reported).
     */
    suspend fun flush(send: suspend (PendingWrite) -> Unit) = lock.withLock {
        var queue = _pending.value
        while (queue.isNotEmpty()) {
            val next = queue.first()
            try {
                send(next)
            } catch (e: Offline) {
                break
            } catch (e: Exception) {
                _failed.value = _failed.value + "${next.label}: ${e.message ?: "refused"}"
            }
            queue = queue.drop(1)
            save(queue)
        }
    }

    fun dismissFailures() { _failed.value = emptyList() }

    suspend fun clear() = lock.withLock { save(emptyList()); _failed.value = emptyList() }

    /** Thrown by a send that could not reach the server. */
    class Offline : Exception()
}
