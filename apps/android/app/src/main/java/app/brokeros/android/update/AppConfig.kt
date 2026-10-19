package app.brokeros.android.update

import app.brokeros.android.core.Endpoints
import app.brokeros.android.data.ApiJson
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AppConfig(
    val android: Android = Android(),
    val notice: String? = null,
    val features: List<String> = emptyList(),
) {
    @Serializable
    data class Android(
        @SerialName("min_version_code") val minVersionCode: Int = 1,
        @SerialName("latest_version_code") val latestVersionCode: Int = 1,
        @SerialName("store_url") val storeUrl: String = "",
        @SerialName("apk_url") val apkUrl: String = "",
        @SerialName("apk_sha256") val apkSha256: String = "",
    )
}

/** What to do about updates, from the installed version and the server's rules. */
sealed interface UpdateNeed {
    data object None : UpdateNeed
    data object Available : UpdateNeed

    /** This version is no longer supported: update before using the app. */
    data object Required : UpdateNeed

    companion object {
        fun of(installed: Int, config: AppConfig): UpdateNeed = when {
            installed < config.android.minVersionCode -> Required
            installed < config.android.latestVersionCode -> Available
            else -> None
        }
    }
}

/** GET /api/v1/public/app-config: remote switches and update rules (ADR-0026). Null when unreachable. */
class AppConfigApi(private val http: HttpClient, private val endpoints: Endpoints) {
    suspend fun fetch(): AppConfig? = runCatching {
        val response = http.get("${endpoints.apiUrl}/api/v1/public/app-config")
        if (!response.status.isSuccess()) return null
        ApiJson.decodeFromString(AppConfig.serializer(), response.bodyAsText())
    }.getOrNull()
}
