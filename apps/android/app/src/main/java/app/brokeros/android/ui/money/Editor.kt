package app.brokeros.android.ui.money

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BillingDocument
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.ClientRef
import app.brokeros.android.data.InvoiceCreate
import app.brokeros.android.data.InvoiceUpdate
import app.brokeros.android.data.Item
import app.brokeros.android.data.LineInput
import app.brokeros.android.data.TaxCode
import app.brokeros.android.data.Versioned
import app.brokeros.android.data.createInvoice
import app.brokeros.android.data.createSalesQuote
import app.brokeros.android.data.items
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.pack
import app.brokeros.android.data.updateDraft
import app.brokeros.android.ui.components.ClientPicker
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.home.money
import app.brokeros.android.ui.insurance.amountOf
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.math.RoundingMode

/** One line being edited. Discount is typed as a percent and sent as a fraction (10 → 0.1). */
data class LineDraft(
    val itemId: String? = null,
    val description: String = "",
    val quantity: String = "1",
    val unitPrice: String = "",
    val discountPercent: String = "",
    val taxCode: String = "",
    val section: String = "",
    val optional: Boolean = false,
) {
    fun toInput() = LineInput(
        description = description.trim().ifBlank { null },
        quantity = quantity.ifBlank { "1" },
        unitPrice = unitPrice.ifBlank { null },
        discountRate = (discountPercent.toBigDecimalOrNull() ?: BigDecimal.ZERO).divide(BigDecimal(100), 4, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString(),
        itemId = itemId,
        taxCode = taxCode.ifBlank { null },
        section = section.trim().ifBlank { null },
        optional = optional,
    )

    /** Display-only estimate before tax (the API computes the real totals). */
    fun estimate(): BigDecimal {
        val q = quantity.toBigDecimalOrNull() ?: BigDecimal.ONE
        val p = unitPrice.toBigDecimalOrNull() ?: BigDecimal.ZERO
        val d = (discountPercent.toBigDecimalOrNull() ?: BigDecimal.ZERO).divide(BigDecimal(100))
        return q * p * (BigDecimal.ONE - d)
    }
}

/** A new invoice or sales quote ([quote]), or an edit of a draft ([existing]). */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun DocumentEditor(api: BrokerApi, quote: Boolean, client: ClientRef?, existing: Versioned<BillingDocument>?, onSaved: (String) -> Unit) {
    val doc = existing?.value
    var who by remember { mutableStateOf(client ?: doc?.client) }
    val lines = remember {
        mutableStateListOf<LineDraft>().apply {
            if (doc == null) add(LineDraft()) else addAll(doc.lines.map {
                LineDraft(it.itemId, it.description, it.quantity, it.unitPrice,
                    (it.discountRate.toBigDecimalOrNull() ?: BigDecimal.ZERO).multiply(BigDecimal(100)).stripTrailingZeros().toPlainString().let { d -> if (d == "0") "" else d },
                    it.taxCode, it.section.orEmpty(), it.optional)
            })
        }
    }
    var items by remember { mutableStateOf<List<Item>>(emptyList()) }
    var taxCodes by remember { mutableStateOf<List<TaxCode>>(emptyList()) }
    var days by rememberSaveable { mutableStateOf(if (quote) "30" else "14") }
    var reference by rememberSaveable { mutableStateOf(doc?.reference ?: "") }
    var notes by rememberSaveable { mutableStateOf(doc?.notes ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current
    LaunchedEffect(Unit) {
        items = runCatching { api.items().filter { it.active } }.getOrDefault(emptyList())
        taxCodes = runCatching { api.pack().taxCodes }.getOrDefault(emptyList())
    }
    val defaultTax = taxCodes.firstOrNull { it.kind == "vat" }?.code ?: taxCodes.firstOrNull()?.code ?: ""

    FormColumn {
        if (doc == null) ClientPicker(api, who) { who = it } else Text(doc.client.displayName, style = MaterialTheme.typography.titleMedium)
        SectionTitle("Lines")
        lines.forEachIndexed { i, line ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Line ${i + 1}", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                        if (lines.size > 1) IconButton(onClick = { lines.removeAt(i) }) { Icon(Icons.Default.Delete, contentDescription = "Remove line ${i + 1}") }
                    }
                    if (items.isNotEmpty()) {
                        Text("From your items", style = MaterialTheme.typography.labelMedium)
                        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            items.forEach { item ->
                                androidx.compose.material3.FilterChip(
                                    selected = line.itemId == item.id,
                                    onClick = {
                                        lines[i] = if (line.itemId == item.id) line.copy(itemId = null) else line.copy(
                                            itemId = item.id, description = item.name, unitPrice = item.unitPrice.substringBefore(".0000"), taxCode = item.taxCode,
                                        )
                                    },
                                    label = { Text("${item.name} · ${money(item.unitPrice, item.currency)}") },
                                )
                            }
                        }
                    }
                    if (quote) Field("Heading", line.section, { lines[i] = line.copy(section = it) }, hint = "Optional, groups lines")
                    Field("Description", line.description, { lines[i] = line.copy(description = it) })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Field("Qty", line.quantity, { lines[i] = line.copy(quantity = amountOf(it)) }, Modifier.weight(0.6f), keyboard = KeyboardType.Decimal)
                        Field("Price", line.unitPrice, { lines[i] = line.copy(unitPrice = amountOf(it)) }, Modifier.weight(1f), keyboard = KeyboardType.Decimal)
                        Field("Disc. %", line.discountPercent, { lines[i] = line.copy(discountPercent = amountOf(it)) }, Modifier.weight(0.7f), keyboard = KeyboardType.Decimal)
                    }
                    if (taxCodes.isNotEmpty()) {
                        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            taxCodes.forEach { t ->
                                androidx.compose.material3.FilterChip(
                                    selected = (line.taxCode.ifBlank { defaultTax }) == t.code,
                                    onClick = { lines[i] = line.copy(taxCode = t.code) },
                                    label = { Text(t.name) },
                                )
                            }
                        }
                    }
                    if (quote) {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { lines[i] = line.copy(optional = !line.optional) }) {
                            Checkbox(checked = line.optional, onCheckedChange = { lines[i] = line.copy(optional = it) })
                            Text("Optional extra (the client chooses; not in the total)")
                        }
                    }
                    Text("≈ ${money(line.estimate().toPlainString(), "KES", decimals = true)} before tax", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        TextButton(onClick = { lines.add(LineDraft()) }) {
            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.padding(end = 6.dp)); Text("Add line")
        }
        if (doc == null) Field(if (quote) "Valid for (days)" else "Due in (days)", days, { days = it.filter(Char::isDigit) }, keyboard = KeyboardType.Number)
        Field("Your reference", reference, { reference = it }, hint = "Optional, e.g. an LPO number")
        Field("Notes", notes, { notes = it }, singleLine = false, minLines = 2, hint = "Optional, printed on the document")
        FormError(error)
        val ready = who != null && lines.all { it.itemId != null || (it.description.isNotBlank() && it.unitPrice.isNotBlank()) }
        SubmitButton(if (doc != null) "Save draft" else if (quote) "Save draft quote" else "Save draft invoice", busy, ready) {
            busy = true
            scope.launch {
                try {
                    val input = lines.map { it.copy(taxCode = it.taxCode.ifBlank { if (it.itemId == null) defaultTax else "" }).toInput() }
                    val saved = if (doc != null) {
                        api.updateDraft(doc.id, InvoiceUpdate(lines = input, reference = reference.trim().ifBlank { null }, notes = notes.trim().ifBlank { null }), existing.etag).value
                    } else {
                        val create = InvoiceCreate(
                            clientId = who!!.id, lines = input,
                            dueInDays = if (quote) null else days.toIntOrNull(),
                            validDays = if (quote) days.toIntOrNull() else null,
                            reference = reference.trim().ifBlank { null }, notes = notes.trim().ifBlank { null },
                        )
                        if (quote) api.createSalesQuote(create, key) else api.createInvoice(create, key)
                    }
                    toast("Draft saved")
                    onSaved(saved.id)
                } catch (e: AppException) { error = e.message } finally { busy = false }
            }
        }
    }
}
