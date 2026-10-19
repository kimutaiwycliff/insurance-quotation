package app.brokeros.android.ui.signin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import app.brokeros.android.data.Agency
import app.brokeros.android.data.AppException
import app.brokeros.android.ui.components.open
import kotlinx.coroutines.launch

/** Runs [block], turning failures into a message for the screen. */
@Composable
private fun rememberSubmit(): Pair<Submit, Boolean> {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    return Submit { onError, block ->
        if (busy) return@Submit
        busy = true
        scope.launch {
            try {
                block()
            } catch (e: AppException) {
                onError(e.message ?: "Something went wrong. Try again.")
            } finally {
                busy = false
            }
        }
    } to busy
}

private fun interface Submit {
    operator fun invoke(onError: (String) -> Unit, block: suspend () -> Unit)
}

@Composable
private fun AuthFrame(title: String, subtitle: String, content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().imePadding(), contentAlignment = Alignment.Center) {
        Column(
            Modifier.widthIn(max = 440.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primary, modifier = Modifier.size(56.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Surface(shape = CircleShape, color = MaterialTheme.colorScheme.secondary, modifier = Modifier.size(18.dp)) {}
                }
            }
            Text(title, style = MaterialTheme.typography.headlineMedium)
            Text(subtitle, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            content()
        }
    }
}

@Composable
private fun ErrorText(error: String?) {
    if (error != null) {
        Text(
            error,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
    }
}

@Composable
private fun BusyButton(label: String, busy: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = Modifier.fillMaxWidth().height(52.dp)) {
        if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp) else Text(label)
    }
}

@Composable
fun SignInScreen(siteUrl: String, onSignIn: suspend (String, String) -> Unit) {
    val context = LocalContext.current
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val (submit, busy) = rememberSubmit()
    val go = { submit({ error = it }) { error = null; onSignIn(email, password) } }

    AuthFrame("Welcome back", "Sign in to your agency.") {
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { go() }),
            modifier = Modifier.fillMaxWidth(),
        )
        ErrorText(error)
        BusyButton("Sign in", busy, email.isNotBlank() && password.isNotBlank()) { go() }
        TextButton(onClick = { context.open("$siteUrl/forgot-password") }) { Text("Forgot your password?") }
        Spacer(Modifier.height(8.dp))
        Text("New here?", style = MaterialTheme.typography.bodyMedium)
        TextButton(onClick = { context.open("$siteUrl/sign-up") }) { Text("Create an account on the web") }
    }
}

@Composable
fun CodeScreen(onVerify: suspend (String) -> Unit, onCancel: () -> Unit) {
    var code by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val (submit, busy) = rememberSubmit()
    val go = { submit({ error = it }) { error = null; onVerify(code) } }
    AuthFrame("Enter your code", "Open your authenticator app and type the 6-digit code for this account.") {
        OutlinedTextField(
            value = code,
            onValueChange = { code = it.filter(Char::isDigit).take(6) },
            label = { Text("6-digit code") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { go() }),
            modifier = Modifier.fillMaxWidth(),
        )
        ErrorText(error)
        BusyButton("Verify", busy, code.length == 6) { go() }
        TextButton(onClick = onCancel) { Text("Back to sign in") }
    }
}

@Composable
fun AgencyScreen(agencies: List<Agency>, onChoose: suspend (String) -> Unit) {
    var error by remember { mutableStateOf<String?>(null) }
    val (submit, busy) = rememberSubmit()
    AuthFrame("Choose an agency", "You belong to ${agencies.size} agencies. You can switch later from Account.") {
        ErrorText(error)
        agencies.forEach { agency ->
            Card(
                onClick = { submit({ error = it }) { onChoose(agency.id) } },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(agency.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(18.dp))
            }
        }
    }
}

@Composable
fun NoAgencyScreen(siteUrl: String, onSignOut: () -> Unit) {
    val context = LocalContext.current
    AuthFrame("Set up your agency first", "Your account has no agency yet. Create it on the web, then come back here.") {
        Button(onClick = { context.open("$siteUrl/onboarding") }, modifier = Modifier.fillMaxWidth()) { Text("Set up on the web") }
        TextButton(onClick = onSignOut) { Text("Sign out") }
    }
}

@Composable
fun ForceUpdateScreen(progress: Float? = null, onUpdate: () -> Unit) {
    AuthFrame("Update to continue", "This version of the app is no longer supported. The update takes a minute and keeps everything as it was.") {
        if (progress != null) {
            androidx.compose.material3.LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
            Text("Downloading… ${(progress * 100).toInt()}%")
        } else {
            Button(onClick = onUpdate, modifier = Modifier.fillMaxWidth().height(52.dp)) { Text("Update now") }
        }
        Text(
            if (app.brokeros.android.BuildConfig.DISTRIBUTION == "play") "Updates come from Google Play." else "The update downloads from our website and Android asks you to confirm.",
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
