package app.brokeros.android.core

import java.text.Normalizer

/** Search and visibility for the help guide: the same rules as the web's (components/help/topics.ts). */
object Help {
    fun canSee(topic: HelpTopic, permissions: List<String>, features: List<String>): Boolean {
        val featureOk = topic.feature == null || topic.feature in features || "*" in features
        val roleOk = topic.anyOf.isEmpty() || topic.anyOf.any { it in permissions }
        return featureOk && roleOk
    }

    /** Words that mean the same thing to our users. */
    private val synonyms = mapOf(
        "bill" to listOf("invoice"), "receipt" to listOf("payment"), "pay" to listOf("payment", "mpesa"),
        "customer" to listOf("client"), "quotation" to listOf("quote"), "staff" to listOf("team", "invite"),
        "user" to listOf("team", "invite"), "logo" to listOf("brand"), "renew" to listOf("renewal"),
        "expiry" to listOf("renewal"), "tax" to listOf("etims", "vat"), "excel" to listOf("import"),
    )

    /** Lower case, accents removed, and "M-Pesa" / "m pesa" / "mpesa" made the same. */
    fun normalise(text: String): String = Normalizer.normalize(text.lowercase(), Normalizer.Form.NFKD)
        .replace(Regex("\\p{M}+"), "")
        .replace(Regex("m[\\s-]?pesa"), "mpesa")
        .replace(Regex("[^a-z0-9%]+"), " ")
        .trim()

    fun terms(query: String): List<String> = normalise(query).split(" ").filter { it.length > 1 || it.any(Char::isDigit) }

    private fun score(term: String, t: HelpTopic): Double {
        fun hit(s: String) = normalise(s).split(" ").any { it.startsWith(term) }
        return when {
            hit(t.title) -> 5.0
            t.keywords.any(::hit) -> 4.0
            hit(t.summary) -> 2.0
            t.steps.any(::hit) || (t.tip?.let(::hit) ?: false) -> 1.0
            else -> 0.0
        }
    }

    /** Every term (or one of its synonyms) must match; better matches rank higher. Blank query: no ranking. */
    fun search(topics: List<HelpTopic>, query: String): List<HelpTopic> {
        val terms = terms(query)
        if (terms.isEmpty()) return topics
        return topics.mapNotNull { topic ->
            var total = 0.0
            for (term in terms) {
                val best = maxOf(score(term, topic), synonyms[term].orEmpty().maxOfOrNull { score(it, topic) - 0.5 } ?: 0.0)
                if (best <= 0) return@mapNotNull null
                total += best
            }
            topic to total
        }.sortedByDescending { it.second }.map { it.first }
    }
}

/**
 * The app screen for a web link (from help topics and notifications), or null to open it on the web.
 * "/quotes/123" → "quote/123".
 */
fun appRoute(href: String?): String? {
    val path = href?.substringBefore('?')?.substringBefore('#')?.trimEnd('/') ?: return null
    val parts = path.trimStart('/').split('/')
    val lists = mapOf(
        "clients" to "clients", "leads" to "leads", "tasks" to "tasks", "calculator" to "calculator",
        "quotes" to "quotes", "policies" to "policies", "renewals" to "renewals", "commission" to "commission",
        "invoices" to "invoices", "sales-quotes" to "sales-quotes", "payments" to "payments", "help" to "help",
        "" to "home",
    )
    return when {
        parts.size == 1 -> lists[parts[0]]
        parts == listOf("settings", "plan") -> "plan"
        parts == listOf("settings", "organization") -> "profile"
        parts == listOf("settings", "members") -> "team"
        parts == listOf("settings", "security") -> "security"
        parts == listOf("settings", "payments") -> "mpesa-setup"
        parts.size == 2 && parts[1] == "new" -> when (parts[0]) {
            "clients" -> "client/new"
            "leads" -> "lead/new"
            "quotes" -> "quote/new?clientId=&clientName="
            "policies" -> "policy/new?clientId=&clientName=&quoteId="
            else -> null
        }
        parts.size == 2 -> when (parts[0]) {
            "clients" -> "client/${parts[1]}"
            "leads" -> "lead/${parts[1]}"
            "quotes" -> "quote/${parts[1]}"
            "policies" -> "policy/${parts[1]}"
            "invoices", "sales-quotes", "credit-notes" -> "document/${parts[1]}"
            else -> null
        }
        else -> null
    }
}
