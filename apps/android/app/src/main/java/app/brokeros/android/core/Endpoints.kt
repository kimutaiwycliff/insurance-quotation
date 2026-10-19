package app.brokeros.android.core

import app.brokeros.android.BuildConfig

/** Where the app talks to, fixed at build time (debug: the local stack; release: Gradle properties). */
data class Endpoints(
    /** The web app: sign-in goes through its /api/auth proxy, and links open here. */
    val siteUrl: String,
    /** The API (routes under /api/v1). */
    val apiUrl: String,
    /** Sent as Origin on sign-in requests: the auth service trusts the web app's origin (ADR-0026). */
    val authOrigin: String,
    /** Debug only: the emulator's name for the computer, replacing "localhost" in storage links. */
    val localhostAlias: String = "",
) {
    /** Presigned storage links name the server as the computer sees it; the emulator needs [localhostAlias]. */
    fun reachable(url: String): String =
        if (localhostAlias.isBlank()) url else url.replace("://localhost:", "://$localhostAlias:").replace("://127.0.0.1:", "://$localhostAlias:")

    companion object {
        val fromBuild = Endpoints(BuildConfig.SITE_URL, BuildConfig.API_URL, BuildConfig.AUTH_ORIGIN, BuildConfig.LOCALHOST_ALIAS)
    }
}
