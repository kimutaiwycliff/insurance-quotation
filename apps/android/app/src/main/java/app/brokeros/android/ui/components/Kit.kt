package app.brokeros.android.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import java.time.LocalDate

/** Show a short message at the bottom of the screen (success or failure). */
val LocalToast = compositionLocalOf<(String) -> Unit> { {} }

/** Something being loaded, that loaded, or that failed with a readable message. */
sealed interface Load<out T> {
    data object Loading : Load<Nothing>
    data class Failed(val message: String) : Load<Nothing>
    data class Ready<T>(val value: T) : Load<T>
}

@Composable
fun <T> Loaded(state: Load<T>, onRetry: () -> Unit, content: @Composable (T) -> Unit) {
    when (state) {
        Load.Loading -> Loading()
        is Load.Failed -> ErrorMessage(state.message, onRetry)
        is Load.Ready -> content(state.value)
    }
}

@Composable
fun Empty(message: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(message, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = modifier.padding(top = 16.dp, bottom = 6.dp))
}

@Composable
fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    keyboard: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    minLines: Int = 1,
    hint: String? = null,
    error: String? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = singleLine,
        minLines = minLines,
        isError = error != null,
        supportingText = (error ?: hint)?.let { { Text(it) } },
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        modifier = modifier.fillMaxWidth(),
    )
}

/** One choice from a few codes, shown with their plain names. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Choices(label: String?, options: List<String>, selected: String?, onSelect: (String?) -> Unit, allowNone: Boolean = false) {
    Column {
        label?.let { Text(it, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 4.dp)) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            options.forEach { option ->
                FilterChip(
                    selected = option == selected,
                    onClick = { onSelect(if (option == selected && allowNone) null else option) },
                    label = { Text(Labels.of(option)) },
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MultiChoices(label: String?, options: List<String>, selected: List<String>, onChange: (List<String>) -> Unit) {
    Column {
        label?.let { Text(it, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(bottom = 4.dp)) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            options.forEach { option ->
                FilterChip(
                    selected = option in selected,
                    onClick = { onChange(if (option in selected) selected - option else selected + option) },
                    label = { Text(Labels.of(option)) },
                )
            }
        }
    }
}

/** A calendar day, picked from a date picker. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateField(label: String, value: LocalDate?, onChange: (LocalDate?) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value?.let { Dates.date(it.toString()) } ?: "",
        onValueChange = {},
        readOnly = true,
        label = { Text(label) },
        trailingIcon = { IconButton(onClick = { open = true }) { Icon(Icons.Default.DateRange, contentDescription = "Pick a date") } },
        modifier = modifier.fillMaxWidth(),
    )
    if (open) {
        val state = rememberDatePickerState(initialSelectedDateMillis = value?.let(Dates::toPicker))
        DatePickerDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton(onClick = { onChange(state.selectedDateMillis?.let(Dates::fromPicker)); open = false }) { Text("Done") }
            },
            dismissButton = {
                TextButton(onClick = { onChange(null); open = false }) { Text("Clear") }
            },
        ) { DatePicker(state) }
    }
}

@Composable
fun FormError(message: String?) {
    if (message != null) {
        Text(
            message,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
    }
}

@Composable
fun SubmitButton(label: String, busy: Boolean, enabled: Boolean = true, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = Modifier.fillMaxWidth().height(52.dp)) {
        if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp) else Text(label)
    }
}

/** A label above a value, for detail pages. Hidden when empty. */
@Composable
fun Detail(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Column(Modifier.padding(vertical = 6.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}

/** A scrolling form column with standard spacing. */
@Composable
fun FormColumn(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) { content() }
}

@Composable
fun Row2(content: @Composable () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) { content() }
}
