package app.brokeros.android.data

import app.brokeros.android.core.Jwt
import app.brokeros.android.core.TokenStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Where the person is in signing in. The UI shows one screen per state. */
sealed interface SessionState {
    data object Starting : SessionState
    data object SignedOut : SessionState
    data class NeedsCode(val cookies: String) : SessionState
    data class ChooseAgency(val agencies: List<Agency>) : SessionState
    data object NoAgency : SessionState
    data class Ready(val me: Me) : SessionState

    /** Could not check the session (usually no internet); the saved session is kept. */
    data class Offline(val message: String) : SessionState
}

/**
 * Owns the session token and hands out short-lived API tokens (ADR-0026). The API token is cached until a
 * minute before it expires and refreshed after a 401 (for example after switching agency).
 */
class SessionRepository(
    private val auth: AuthApi,
    private val store: TokenStore,
    private val loadMe: suspend () -> Me,
    private val now: () -> Long = { System.currentTimeMillis() / 1000 },
    private val onSignedOut: suspend () -> Unit = {},
) {
    private val _state = MutableStateFlow<SessionState>(SessionState.Starting)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    private val lock = Mutex()
    private var apiToken: String? = null

    /** On app start: resume the saved session, if any. */
    suspend fun restore() {
        val token = store.read()
        if (token == null) {
            _state.value = SessionState.SignedOut
            return
        }
        try {
            enter(token)
        } catch (e: AppException) {
            _state.value = SessionState.Offline(e.message ?: OFFLINE_MESSAGE)
        }
    }

    suspend fun signIn(email: String, password: String) {
        when (val step = auth.signIn(email, password)) {
            is SignInStep.Done -> start(step.sessionToken)
            is SignInStep.NeedsCode -> _state.value = SessionState.NeedsCode(step.cookies)
        }
    }

    suspend fun verifyCode(code: String) {
        val pending = _state.value as? SessionState.NeedsCode ?: return
        start(auth.verifyCode(pending.cookies, code))
    }

    /** Leave the code step and start again. */
    fun cancelCode() {
        if (_state.value is SessionState.NeedsCode) _state.value = SessionState.SignedOut
    }

    suspend fun chooseAgency(agencyId: String) {
        val token = store.read() ?: return signedOut()
        auth.chooseAgency(token, agencyId)
        forgetApiToken()
        _state.value = SessionState.Ready(loadMe())
    }

    /** From the account page: back to the agency list. */
    suspend fun switchAgency() {
        val token = store.read() ?: return signedOut()
        _state.value = SessionState.ChooseAgency(auth.agencies(token))
    }

    suspend fun agencyCount(): Int = store.read()?.let { auth.agencies(it).size } ?: 0

    suspend fun signOut() {
        store.read()?.let { auth.signOut(it) }
        signedOut()
    }

    /** Run an auth-service call that needs the session token (team management). */
    suspend fun <T> withSession(block: suspend (sessionToken: String) -> T): T =
        block(store.read() ?: throw AppException("Signed out", 401))

    /** A valid API token, minted when needed. Throws [AppException] when signed out. */
    suspend fun apiToken(forceRefresh: Boolean = false): String = lock.withLock {
        val cached = apiToken
        if (!forceRefresh && cached != null && (Jwt.expiresAt(cached) ?: 0) - now() > 60) return cached
        val session = store.read() ?: throw AppException("Signed out", 401)
        val fresh = try {
            auth.apiToken(session)
        } catch (e: AppException) {
            if (e.status == 401) signedOut()
            throw e
        }
        apiToken = fresh
        fresh
    }

    private suspend fun start(sessionToken: String) {
        store.write(sessionToken)
        enter(sessionToken)
    }

    private suspend fun enter(sessionToken: String) {
        val session = auth.session(sessionToken) ?: return signedOut()
        if (session.session.activeOrganizationId == null) {
            val agencies = auth.agencies(sessionToken)
            when (agencies.size) {
                0 -> { _state.value = SessionState.NoAgency; return }
                1 -> auth.chooseAgency(sessionToken, agencies.single().id)
                else -> { _state.value = SessionState.ChooseAgency(agencies); return }
            }
        }
        forgetApiToken()
        _state.value = SessionState.Ready(loadMe())
    }

    private suspend fun forgetApiToken() = lock.withLock { apiToken = null }

    private suspend fun signedOut() {
        onSignedOut()
        store.write(null)
        forgetApiToken()
        _state.value = SessionState.SignedOut
    }
}
