package app.brokeros.android.core

/** Phone links for a client's number (stored as E.164, e.g. +254712345678). */
object Phone {
    fun digits(e164: String): String = e164.filter(Char::isDigit)

    fun dialUri(e164: String): String = "tel:${e164.filter { it.isDigit() || it == '+' }}"

    fun whatsAppUrl(e164: String, message: String? = null): String {
        val base = "https://wa.me/${digits(e164)}"
        return if (message.isNullOrBlank()) base else "$base?text=${java.net.URLEncoder.encode(message, "UTF-8").replace("+", "%20")}"
    }

    /** +254712345678 → 0712 345 678 (how Kenyans write it); other numbers are left as they are. */
    fun display(e164: String): String {
        val d = digits(e164)
        return if (e164.startsWith("+254") && d.length == 12) {
            "0${d.substring(3, 6)} ${d.substring(6, 9)} ${d.substring(9)}"
        } else {
            e164
        }
    }
}
