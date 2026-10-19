package app.brokeros.android.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.util.Base64

/** Reads a JWT's expiry (seconds since epoch) without verifying it: the API verifies; we only plan refreshes. */
object Jwt {
    fun expiresAt(token: String): Long? = runCatching {
        val payload = token.split(".")[1]
        val json = String(Base64.getUrlDecoder().decode(payload.padEnd((payload.length + 3) / 4 * 4, '=')))
        Json.parseToJsonElement(json).jsonObject["exp"]?.jsonPrimitive?.longOrNull
    }.getOrNull()
}
