package app.brokeros.android.update

import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.net.toUri
import com.google.android.play.core.appupdate.AppUpdateManagerFactory
import com.google.android.play.core.appupdate.AppUpdateOptions
import com.google.android.play.core.install.InstallStateUpdatedListener
import com.google.android.play.core.install.model.AppUpdateType
import com.google.android.play.core.install.model.InstallStatus
import com.google.android.play.core.install.model.UpdateAvailability
import com.google.android.play.core.ktx.requestAppUpdateInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Google Play in-app updates (ADR-0026): immediate when this version is no longer supported, flexible (download in
 * the background, then restart) otherwise. Outside Play (debug builds, side-loading) it opens the store listing.
 * Must be created in the activity's onCreate (it registers an activity result).
 */
class PlayUpdates(private val activity: ComponentActivity) : Updater {
    private val manager = AppUpdateManagerFactory.create(activity)
    private val launcher = activity.registerForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) {}
    private val _readyToInstall = MutableStateFlow(false)

    /** A flexible update finished downloading: offer to restart. */
    override val readyToInstall: StateFlow<Boolean> = _readyToInstall.asStateFlow()
    override val progress: StateFlow<Float?> = MutableStateFlow(null)

    private val listener = InstallStateUpdatedListener { state ->
        if (state.installStatus() == InstallStatus.DOWNLOADED) _readyToInstall.value = true
    }

    override suspend fun start(required: Boolean, config: AppConfig) {
        val storeUrl = config.android.storeUrl
        val type = if (required) AppUpdateType.IMMEDIATE else AppUpdateType.FLEXIBLE
        val info = runCatching { manager.requestAppUpdateInfo() }.getOrNull()
        val playCanDoIt = info != null &&
            info.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE &&
            info.isUpdateTypeAllowed(type)
        if (playCanDoIt) {
            if (!required) manager.registerListener(listener)
            manager.startUpdateFlowForResult(info, launcher, AppUpdateOptions.newBuilder(type).build())
        } else if (storeUrl.isNotBlank()) {
            runCatching { activity.startActivity(Intent(Intent.ACTION_VIEW, storeUrl.toUri())) }
        }
    }

    /** An immediate update that was interrupted (the app was left) must carry on when the app comes back. */
    override suspend fun resume() {
        val info = runCatching { manager.requestAppUpdateInfo() }.getOrNull() ?: return
        if (info.updateAvailability() == UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS) {
            manager.startUpdateFlowForResult(info, launcher, AppUpdateOptions.newBuilder(AppUpdateType.IMMEDIATE).build())
        }
        if (info.installStatus() == InstallStatus.DOWNLOADED) _readyToInstall.value = true
    }

    override fun install() {
        manager.completeUpdate()
    }

    override fun close() = manager.unregisterListener(listener)
}

/** The play flavor's updater (MainActivity calls this; the direct flavor has its own). */
fun createUpdater(activity: ComponentActivity): Updater = PlayUpdates(activity)
