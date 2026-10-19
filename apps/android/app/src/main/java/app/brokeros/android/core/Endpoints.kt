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
) {
    companion object {
        val fromBuild = Endpoints(BuildConfig.SITE_URL, BuildConfig.API_URL, BuildConfig.AUTH_ORIGIN)
    }
}
