package app.brokeros.android.update

import kotlinx.coroutines.flow.StateFlow

/** How the app updates itself: Google Play (play flavor) or our own signed APK (direct flavor). ADR-0026. */
interface Updater {
    /** A newer version is downloaded and ready: offer to install or restart. */
    val readyToInstall: StateFlow<Boolean>

    /** Download progress 0..1 while an update downloads, else null. */
    val progress: StateFlow<Float?>

    /** Start updating. [required]: this version is no longer supported. */
    suspend fun start(required: Boolean, config: AppConfig)

    /** On app start: carry on an interrupted required update; notice a finished download. */
    suspend fun resume()

    fun install()

    fun close()
}
