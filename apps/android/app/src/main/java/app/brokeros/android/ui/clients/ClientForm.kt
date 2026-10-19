package app.brokeros.android.ui.clients

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.data.Address
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Client
import app.brokeros.android.data.ClientInput
import app.brokeros.android.data.DuplicateCheck
import app.brokeros.android.data.DuplicateMatch
import app.brokeros.android.data.Versioned
import app.brokeros.android.data.checkDuplicates
import app.brokeros.android.data.createClient
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.updateClient
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.DateField
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.components.SubmitButton
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private fun String.orNull() = trim().ifBlank { null }

/** Add a client, or edit one ([existing] with its version tag). */
@Composable
fun ClientFormScreen(api: BrokerApi, existing: Versioned<Client>?, onSaved: (String) -> Unit, onOpenClient: (String) -> Unit) {
    val c = existing?.value
    var kind by rememberSaveable { mutableStateOf(c?.kind ?: "individual") }
    var firstName by rememberSaveable { mutableStateOf(c?.firstName ?: "") }
    var lastName by rememberSaveable { mutableStateOf(c?.lastName ?: "") }
    var otherNames by rememberSaveable { mutableStateOf(c?.otherNames ?: "") }
    var companyName by rememberSaveable { mutableStateOf(c?.companyName ?: "") }
    var phone by rememberSaveable { mutableStateOf(c?.phone ?: "") }
    var altPhone by rememberSaveable { mutableStateOf(c?.altPhone ?: "") }
    var email by rememberSaveable { mutableStateOf(c?.email ?: "") }
    var kraPin by rememberSaveable { mutableStateOf(c?.kraPin ?: "") }
    var idType by rememberSaveable { mutableStateOf(c?.idType) }
    var idNumber by rememberSaveable { mutableStateOf("") }
    var dob by remember { mutableStateOf(Dates.parseDate(c?.dateOfBirth)) }
    var gender by rememberSaveable { mutableStateOf(c?.gender) }
    var occupation by rememberSaveable { mutableStateOf(c?.occupation ?: "") }
    var channel by rememberSaveable { mutableStateOf(c?.preferredChannel) }
    var source by rememberSaveable { mutableStateOf(c?.source) }
    var town by rememberSaveable { mutableStateOf(c?.address?.town ?: "") }
    var county by rememberSaveable { mutableStateOf(c?.address?.county ?: "") }
    var notes by rememberSaveable { mutableStateOf(c?.notes ?: "") }
    var consent by rememberSaveable { mutableStateOf(c?.marketingConsent ?: false) }
    var matches by remember { mutableStateOf<List<DuplicateMatch>>(emptyList()) }
    var different by rememberSaveable { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current

    // Catch duplicates while typing, before anything is saved.
    LaunchedEffect(phone, email, kraPin, idNumber) {
        delay(600)
        if (listOf(phone, email, kraPin, idNumber).all(String::isBlank)) {
            matches = emptyList()
            return@LaunchedEffect
        }
        matches = runCatching {
            api.checkDuplicates(DuplicateCheck(phone.orNull(), email.orNull(), kraPin.orNull(), idNumber.orNull(), excludeId = c?.id)).matches
        }.getOrDefault(matches)
    }

    val named = if (kind == "individual") firstName.isNotBlank() && lastName.isNotBlank() else companyName.isNotBlank()

    FormColumn {
        Choices("This client is", listOf("individual", "corporate"), kind, { kind = it ?: "individual" })
        if (kind == "individual") {
            Field("First name", firstName, { firstName = it })
            Field("Last name", lastName, { lastName = it })
            Field("Other names", otherNames, { otherNames = it }, hint = "Optional")
        } else {
            Field("Company name", companyName, { companyName = it })
        }
        Field("Phone", phone, { phone = it }, keyboard = KeyboardType.Phone, hint = "e.g. 0712 345 678")
        if (matches.isNotEmpty()) {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(14.dp)) {
                    Text("This client may already exist", style = MaterialTheme.typography.titleMedium)
                    matches.forEach { m ->
                        Text(
                            "${m.client.displayName} (same ${m.matchedOn.joinToString(", ") { it.replace('_', ' ') }})",
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(top = 6.dp).clickable { onOpenClient(m.client.id) },
                        )
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { different = !different }) {
                        Checkbox(checked = different, onCheckedChange = { different = it })
                        Text("This is a different person")
                    }
                }
            }
        }
        Field("Other phone", altPhone, { altPhone = it }, keyboard = KeyboardType.Phone, hint = "Optional")
        Field("Email", email, { email = it }, keyboard = KeyboardType.Email, hint = "Optional")
        Field("KRA PIN", kraPin, { kraPin = it.uppercase() }, hint = "Optional")
        SectionTitle("Identification")
        Choices(null, Labels.idTypes, idType, { idType = it }, allowNone = true)
        if (idType != null) {
            Field(
                if (c?.idNumberHint != null) "New ID number (now ${c.idNumberHint})" else "ID number",
                idNumber,
                { idNumber = it },
                hint = "Stored encrypted",
            )
        }
        if (kind == "individual") {
            DateField("Date of birth", dob, { dob = it })
            Choices("Gender", listOf("female", "male", "other"), gender, { gender = it }, allowNone = true)
            Field("Occupation", occupation, { occupation = it }, hint = "Optional")
        }
        SectionTitle("Contact and notes")
        Choices("Prefers", Labels.channels, channel, { channel = it }, allowNone = true)
        if (c == null) Choices("How they found you", Labels.clientSources, source, { source = it }, allowNone = true)
        Field("Town", town, { town = it })
        Field("County", county, { county = it })
        Field("Notes", notes, { notes = it }, singleLine = false, minLines = 3)
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("Agrees to receive news and offers", modifier = Modifier.weight(1f))
            Switch(checked = consent, onCheckedChange = { consent = it })
        }
        FormError(error)
        SubmitButton(if (c == null) "Save client" else "Save changes", busy, named) {
            busy = true
            error = null
            scope.launch {
                try {
                    val input = ClientInput(
                        kind = if (c == null) kind else null,
                        firstName = firstName.orNull().takeIf { kind == "individual" },
                        lastName = lastName.orNull().takeIf { kind == "individual" },
                        otherNames = otherNames.orNull().takeIf { kind == "individual" },
                        companyName = companyName.orNull().takeIf { kind == "corporate" },
                        phone = phone.orNull(),
                        altPhone = altPhone.orNull(),
                        email = email.orNull(),
                        kraPin = kraPin.orNull(),
                        idType = idType.takeIf { idNumber.isNotBlank() } ?: c?.idType,
                        idNumber = idNumber.orNull(),
                        dateOfBirth = dob?.let(Dates::isoDate),
                        gender = gender,
                        occupation = occupation.orNull(),
                        notes = notes.orNull(),
                        source = if (c == null) source else null,
                        preferredChannel = channel,
                        marketingConsent = consent,
                        address = Address(town = town.orNull(), county = county.orNull()).takeIf { town.isNotBlank() || county.isNotBlank() },
                        allowDuplicate = if (c == null) different else null,
                    )
                    val saved = if (c == null) api.createClient(input, key) else api.updateClient(c.id, input, existing.etag).value
                    toast(if (c == null) "Client added" else "Changes saved")
                    onSaved(saved.id)
                } catch (e: AppException) {
                    error = if (e.code == "possible_duplicate") "This client may already exist. Tick “This is a different person” to save anyway." else e.message
                } finally {
                    busy = false
                }
            }
        }
    }
}
