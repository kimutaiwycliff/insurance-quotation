package app.brokeros.android.ui.insurance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.Calculation
import app.brokeros.android.data.CompareRequest
import app.brokeros.android.data.Insurer
import app.brokeros.android.data.Pack
import app.brokeros.android.data.Product
import app.brokeros.android.data.compare
import app.brokeros.android.data.insurers
import app.brokeros.android.data.pack
import app.brokeros.android.data.products
import app.brokeros.android.ui.components.Banner
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormColumn
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.SectionTitle
import app.brokeros.android.ui.components.SubmitButton
import app.brokeros.android.ui.home.money
import kotlinx.coroutines.launch

/** Digits only, for amounts typed with commas ("2,000,000" → "2000000"). */
fun amountOf(text: String): String = text.filter { it.isDigit() || it == '.' }

/** Products (with their insurer) to pick from, for the calculator and new quotes. */
class Catalogue(val pack: Pack, val insurers: List<Insurer>, val products: List<Product>) {
    fun insurerName(product: Product) = insurers.firstOrNull { it.id == product.insurerId }?.name ?: ""
    fun label(product: Product) = "${insurerName(product)}: ${product.name}"
    fun classes() = pack.classes.filter { c -> products.any { it.classCode == c.code } }
}

suspend fun BrokerApi.catalogue(): Catalogue = Catalogue(pack(), insurers(), products().filter { it.isActive })

/** Pick products of one class (several insurers to compare). */
@Composable
fun ProductPicker(catalogue: Catalogue, classCode: String?, onClass: (String?) -> Unit, selected: List<String>, onChange: (List<String>) -> Unit) {
    val classes = catalogue.classes()
    if (classes.isEmpty()) {
        Empty("No products yet. Add insurers and products on the web (Settings → Insurers & products).")
        return
    }
    Choices("Class of insurance", classes.map { it.code }, classCode, onClass)
    // Choices shows codes through Labels; class names come from the pack instead.
    classCode?.let { code -> Text(classes.firstOrNull { it.code == code }?.name ?: "", style = MaterialTheme.typography.bodySmall) }
    val inClass = catalogue.products.filter { it.classCode == classCode }
    if (classCode != null) {
        Text("Insurers to compare", style = MaterialTheme.typography.labelLarge)
        inClass.forEach { p ->
            Row(Modifier.fillMaxWidth()) {
                androidx.compose.material3.Checkbox(
                    checked = p.id in selected,
                    onCheckedChange = { on -> onChange(if (on) selected + p.id else selected - p.id) },
                )
                Text(catalogue.label(p), modifier = Modifier.padding(top = 12.dp))
            }
        }
    }
}

@Composable
fun CalculationCard(result: Calculation, showCommission: Boolean, cheapest: Boolean) {
    Card(colors = CardDefaults.cardColors(containerColor = if (cheapest) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(result.product.insurerName + if (cheapest) " · cheapest" else "", style = MaterialTheme.typography.titleMedium)
            Text(result.product.name, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(money(result.clientTotal, result.currency, decimals = true), style = MaterialTheme.typography.headlineSmall)
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            Line("Basic premium", money(result.basicPremium, result.currency, decimals = true))
            result.lines.filter { it.chargedTo == "client" && it.kind != "premium" }.forEach { Line(it.label, money(it.amount, result.currency, decimals = true)) }
            result.product.excessText?.let { Text("Excess: $it", style = MaterialTheme.typography.bodySmall) }
            if (result.needsInput.isNotEmpty()) Text("Needs: ${result.needsInput.joinToString(", ")}", color = MaterialTheme.colorScheme.error)
            if (showCommission) result.commission?.let {
                Text("Your commission: ${money(it.gross, result.currency, decimals = true)}", fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun Line(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun CalculatorScreen(api: BrokerApi, showCommission: Boolean) {
    var catalogue by remember { mutableStateOf<Catalogue?>(null) }
    var classCode by rememberSaveable { mutableStateOf<String?>(null) }
    var selected by rememberSaveable { mutableStateOf<List<String>>(emptyList()) }
    var sumInsured by rememberSaveable { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Calculation>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        try { catalogue = api.catalogue() } catch (e: AppException) { error = e.message }
    }
    FormColumn {
        val c = catalogue ?: run { FormError(error); if (error == null) app.brokeros.android.ui.components.Loading(); return@FormColumn }
        if (!c.pack.signed) Banner(c.pack.signOffNote.ifBlank { "Levy rates are awaiting adviser sign-off." })
        ProductPicker(c, classCode, { classCode = it; selected = c.products.filter { p -> p.classCode == it }.map { p -> p.id } }, selected, { selected = it })
        Field("Sum insured (KES)", sumInsured, { sumInsured = amountOf(it) }, keyboard = KeyboardType.Number, hint = "Value of the car, house or cover")
        FormError(error)
        SubmitButton("Compare ${selected.size} ${if (selected.size == 1) "quote" else "quotes"}", busy, selected.isNotEmpty()) {
            busy = true
            scope.launch {
                try {
                    results = api.compare(CompareRequest(selected, sumInsured = sumInsured.ifBlank { null })).results.sortedBy { it.clientTotal.toBigDecimalOrNull() }
                    error = null
                } catch (e: AppException) {
                    error = e.message
                } finally {
                    busy = false
                }
            }
        }
        if (results.isNotEmpty()) SectionTitle("Results, cheapest first")
        results.forEachIndexed { i, r -> CalculationCard(r, showCommission, cheapest = i == 0 && results.size > 1) }
    }
}
