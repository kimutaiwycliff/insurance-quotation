package app.brokeros.android.update

import android.content.Intent
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.core.content.FileProvider
import androidx.core.net.toUri
import app.brokeros.android.core.Endpoints
import app.brokeros.android.data.httpClient
import io.ktor.client.HttpClient
import io.ktor.client.request.prepareGet
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.contentLength
import io.ktor.http.isSuccess
import io.ktor.utils.io.readAvailable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import java.io.File
import java.security.MessageDigest

/**
 * Updates for the APK people download from our site (no Google Play): fetch the new APK named by the server's
 * app config, refuse it unless its SHA-256 matches, then hand it to Android's installer. Android itself also
 * refuses an update not signed with the same key as the installed app.
 */
class DirectUpdates(
    private val activity: ComponentActivity,
    private val http: HttpClient = httpClient(),
    private val endpoints: Endpoints = Endpoints.fromBuild,
) : Updater {
    private val _ready = MutableStateFlow(false)
    override val readyToInstall: StateFlow<Boolean> = _ready.asStateFlow()
    private val _progress = MutableStateFlow<Float?>(null)
    override val progress: StateFlow<Float?> = _progress.asStateFlow()
    private var downloaded: File? = null
    private var installWhenAllowed = false

    override suspend fun start(required: Boolean, config: AppConfig) {
        val android = config.android
        if (android.apkUrl.isBlank()) {
            // No APK published: send them to the download page instead.
            runCatching { activity.startActivity(Intent(Intent.ACTION_VIEW, "${endpoints.siteUrl}/download".toUri())) }
            return
        }
        val file = downloaded ?: download(endpoints.reachable(absolute(android.apkUrl)), android.latestVersionCode, android.apkSha256) ?: return
        downloaded = file
        _ready.value = true
        if (required) install()
    }

    override suspend fun resume() {
        if (installWhenAllowed && canInstall()) {
            installWhenAllowed = false
            install()
        }
    }

    override fun install() {
        val file = downloaded ?: return
        if (!canInstall()) {
            // Android asks once: "Allow installs from this app". Come back and we carry on.
            installWhenAllowed = true
            runCatching {
                activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, "package:${activity.packageName}".toUri()))
            }
            return
        }
        val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.files", file)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { activity.startActivity(intent) }
    }

    override fun close() = Unit

    private fun canInstall() = activity.packageManager.canRequestPackageInstalls()

    private fun absolute(url: String) = if (url.startsWith("http")) url else endpoints.siteUrl + url

    /** Stream the APK to the cache while hashing it; null (and nothing kept) if anything is off. */
    private suspend fun download(url: String, versionCode: Int, sha256: String): File? = withContext(Dispatchers.IO) {
        val dir = File(activity.cacheDir, "updates").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
        val file = File(dir, "update-$versionCode.apk")
        val digest = MessageDigest.getInstance("SHA-256")
        val ok = runCatching {
            http.prepareGet(url).execute { response ->
                if (!response.status.isSuccess()) return@execute false
                val total = response.contentLength()
                val channel = response.bodyAsChannel()
                val buffer = ByteArray(64 * 1024)
                var read = 0L
                file.outputStream().use { out ->
                    while (true) {
                        val n = channel.readAvailable(buffer)
                        if (n < 0) break
                        if (n == 0) continue
                        out.write(buffer, 0, n)
                        digest.update(buffer, 0, n)
                        read += n
                        if (total != null && total > 0) _progress.value = read.toFloat() / total
                    }
                }
                true
            }
        }.getOrDefault(false)
        _progress.value = null
        val actual = digest.digest().joinToString("") { "%02x".format(it) }
        if (!ok || !Checksum.matches(sha256, actual)) {
            file.delete()
            null
        } else {
            file
        }
    }
}

/** The direct flavor's updater (MainActivity calls this; the play flavor has its own). */
fun createUpdater(activity: ComponentActivity): Updater = DirectUpdates(activity)
