package app.brokeros.android.ui.account

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import app.brokeros.android.BuildConfig
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.AuthApi
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ConnectionIn
import app.brokeros.android.data.Me
import app.brokeros.android.data.MpesaConnection
import app.brokeros.android.data.SessionRepository
import app.brokeros.android.data.TwoFactorSetup
import app.brokeros.android.data.disableMpesa
import app.brokeros.android.data.mpesaConnection
import app.brokeros.android.data.registerC2b
import app.brokeros.android.data.saveMpesa
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.Detail
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.Loading
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.components.SubmitButton
import kotlinx.coroutines.launch

// ---------------------------------------------------------------- security: two-factor sign-in

@Composable
fun SecurityScreen(me: Me, auth: AuthApi, session: SessionRepository) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    var password by remember { mutableStateOf("") }
    var setup by remember { mutableStateOf<TwoFactorSetup?>(null) }
    var code by remember { mutableStateOf("") }
    var enabled by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    fun run(block: suspend () -> Unit) {
        busy = true
        error = null
        scope.launch { try { block() } catch (e: AppException) { error = e.message } finally { busy = false } }
    }
    val secret = setup?.totpURI?.toUri()?.getQueryParameter("secret")

    FormColumn {
        Text("Two-factor sign-in", style = MaterialTheme.typography.headlineSmall)
        Text("Adds a code from an authenticator app (Google Authenticator, Authy, Microsoft Authenticator) when you sign in, so a stolen password is not enough.")
        when {
            enabled -> {
                Text("Two-factor is on. Keep these backup codes somewhere safe; each works once if you lose your phone.", color = MaterialTheme.colorScheme.primary)
                setup?.backupCodes?.let { codes ->
                    Card { Text(codes.joinToString("\n"), fontFamily = FontFamily.Monospace, modifier = Modifier.padding(14.dp)) }
                    OutlinedButton(onClick = { clipboard.setText(AnnotatedString(codes.joinToString("\n"))); toast("Backup codes copied") }, modifier = Modifier.fillMaxWidth()) { Text("Copy backup codes") }
                }
            }
            me.mfaEnrolled -> {
                Text("Two-factor is on for your account.")
                SectionTitle("Turn it off")
                Field("Your password", password, { password = it }, keyboard = KeyboardType.Password)
                FormError(error)
                SubmitButton("Turn off two-factor", busy, password.isNotBlank()) {
                    run { session.withSession { auth.disableTwoFactor(it, password) }; password = ""; toast("Two-factor is off"); session.restore() }
                }
            }
            setup == null -> {
                androidx.compose.material3.OutlinedTextField(
                    value = password, onValueChange = { password = it }, label = { Text("Your password") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
                )
                FormError(error)
                SubmitButton("Turn on two-factor", busy, password.isNotBlank()) {
                    run { setup = session.withSession { auth.enableTwoFactor(it, password) }; password = "" }
                }
            }
            else -> {
                Text("1. Add this account to your authenticator app.")
                Button(onClick = {
                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, setup!!.totpURI.toUri())) }
                        .onFailure { toast("No authenticator app found. Install one, or type the key below.") }
                }, modifier = Modifier.fillMaxWidth()) { Text("Open in authenticator app") }
                secret?.let {
                    Text("Or type this key:", style = MaterialTheme.typography.bodySmall)
                    Text(it.chunked(4).joinToString(" "), fontFamily = FontFamily.Monospace)
                    TextButton(onClick = { clipboard.setText(AnnotatedString(it)); toast("Key copied") }) { Text("Copy key") }
                }
                Text("2. Enter the 6-digit code it shows.")
                Field("6-digit code", code, { code = it.filter(Char::isDigit).take(6) }, keyboard = KeyboardType.NumberPassword)
                FormError(error)
                SubmitButton("Confirm and turn on", busy, code.length == 6) {
                    run { session.withSession { auth.confirmTwoFactor(it, code) }; enabled = true; toast("Two-factor is on") }
                }
            }
        }
    }
}

// ---------------------------------------------------------------- M-Pesa: connect the agency's own Paybill or Till

@Composable
fun MpesaSetupScreen(api: BrokerApi, canEdit: Boolean) {
    var connection by remember { mutableStateOf<MpesaConnection?>(null) }
    var loaded by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    LaunchedEffect(Unit) { connection = runCatching { api.mpesaConnection() }.getOrNull(); loaded = true }
    if (!loaded) { Loading(); return }
    val c = connection
    FormColumn {
        Text("Get paid by M-Pesa", style = MaterialTheme.typography.headlineSmall)
        Text("Connect your own Paybill or Till. Money goes straight to your account; the app only records it.")
        if (c != null && !editing) {
            Card {
                Column(Modifier.padding(14.dp)) {
                    Detail("Status", Labels.of(c.status).ifBlank { c.status })
                    Detail(if (c.shortcodeType == "till") "Till" else "Paybill", c.partyB.ifBlank { c.shortcode })
                    Detail("Account", Labels.of(c.environment))
                    Detail("Consumer key", c.consumerKeyHint)
                    Detail("Paybill payments registered", c.c2bRegisteredAt?.let { Dates.dateTime(it) })
                    c.lastError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                }
            }
            if (canEdit) {
                if (c.shortcodeType == "paybill") OutlinedButton(onClick = {
                    scope.launch { try { connection = api.registerC2b(); toast("Paybill payments registered") } catch (e: AppException) { toast(e.message ?: "Try again.") } }
                }, modifier = Modifier.fillMaxWidth()) { Text("Register Paybill payments") }
                OutlinedButton(onClick = { editing = true }, modifier = Modifier.fillMaxWidth()) { Text("Change keys") }
                TextButton(onClick = {
                    scope.launch { try { connection = api.disableMpesa(); toast("M-Pesa turned off") } catch (e: AppException) { toast(e.message ?: "Try again.") } }
                }) { Text("Turn off", color = MaterialTheme.colorScheme.error) }
            }
        } else if (canEdit) {
            ConnectForm(api, existing = c) { saved -> connection = saved; editing = false }
        } else {
            Text("Not connected. Ask the owner or an admin to connect M-Pesa.")
        }
    }
}

@Composable
private fun ConnectForm(api: BrokerApi, existing: MpesaConnection?, onSaved: (MpesaConnection) -> Unit) {
    val environments = if (BuildConfig.DEBUG) listOf("production", "sandbox", "simulator") else listOf("production", "sandbox")
    var environment by remember { mutableStateOf(existing?.environment?.takeIf { it in environments } ?: "production") }
    var type by remember { mutableStateOf(existing?.shortcodeType ?: "paybill") }
    var shortcode by remember { mutableStateOf(existing?.shortcode ?: "") }
    var till by remember { mutableStateOf("") }
    var key by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var passkey by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("The keys come from Safaricom's Daraja portal (Go Live). They are checked with Safaricom and stored encrypted.", style = MaterialTheme.typography.bodySmall)
        Choices("Account", environments, environment, { environment = it ?: "production" })
        Choices("Type", listOf("paybill", "till"), type, { type = it ?: "paybill" })
        Field(if (type == "till") "Store number" else "Paybill number", shortcode, { shortcode = it.filter(Char::isDigit) }, keyboard = KeyboardType.Number)
        if (type == "till") Field("Till number", till, { till = it.filter(Char::isDigit) }, keyboard = KeyboardType.Number)
        Field("Consumer key", key, { key = it.trim() })
        Field("Consumer secret", secret, { secret = it.trim() })
        Field("Passkey", passkey, { passkey = it.trim() })
        FormError(error)
        SubmitButton("Connect M-Pesa", busy, shortcode.length >= 5 && key.length >= 8 && secret.length >= 8 && passkey.length >= 10 && (type == "paybill" || till.length >= 5)) {
            busy = true
            scope.launch {
                try {
                    onSaved(api.saveMpesa(ConnectionIn(environment, type, shortcode, till.ifBlank { null }, key, secret, passkey)))
                    toast("M-Pesa connected")
                } catch (e: AppException) { error = e.message } finally { busy = false }
            }
        }
    }
}
