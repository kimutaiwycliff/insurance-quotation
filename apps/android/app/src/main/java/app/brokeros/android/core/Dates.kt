package app.brokeros.android.core

import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

/** Dates as agents read them ("16 Oct 2026", "in 3 days"), in the phone's time zone (Nairobi for most). */
object Dates {
    private val day = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.ENGLISH)
    private val dayTime = DateTimeFormatter.ofPattern("d MMM yyyy, HH:mm", Locale.ENGLISH)

    fun zone(): ZoneId = ZoneId.systemDefault()

    /** "2026-10-16" or "2026-10-16T09:00:00Z" → a LocalDate (null if unreadable). */
    fun parseDate(value: String?): LocalDate? = value?.let {
        runCatching { LocalDate.parse(it.take(10)) }.getOrNull()
    }

    fun parseInstant(value: String?): Instant? = value?.let {
        runCatching { OffsetDateTime.parse(it).toInstant() }.getOrNull()
            ?: runCatching { Instant.parse(it) }.getOrNull()
    }

    fun date(value: String?): String = parseDate(value)?.format(day) ?: ""

    fun dateTime(value: String?): String = parseInstant(value)?.atZone(zone())?.format(dayTime) ?: date(value)

    /** "today", "tomorrow", "in 3 days", "2 days ago". */
    fun relative(value: String?, today: LocalDate = LocalDate.now(zone())): String {
        val date = parseInstant(value)?.atZone(zone())?.toLocalDate() ?: parseDate(value) ?: return ""
        return when (val days = ChronoUnit.DAYS.between(today, date)) {
            0L -> "today"
            1L -> "tomorrow"
            -1L -> "yesterday"
            in 2..Long.MAX_VALUE -> "in $days days"
            else -> "${-days} days ago"
        }
    }

    /** A due time on a chosen day: 09:00 local, sent as an ISO instant. */
    fun morningOf(date: LocalDate): String = date.atTime(LocalTime.of(9, 0)).atZone(zone()).toOffsetDateTime().toString()

    fun isoDate(date: LocalDate): String = date.toString()

    /** Date-picker millis (UTC midnight) → the calendar day picked. */
    fun fromPicker(millis: Long): LocalDate = Instant.ofEpochMilli(millis).atZone(ZoneId.of("UTC")).toLocalDate()

    fun toPicker(date: LocalDate): Long = date.atStartOfDay(ZoneId.of("UTC")).toInstant().toEpochMilli()
}

/** "kyc_id" → "Kyc id"; most labels have a proper name in [Labels]. */
fun humanize(value: String): String = value.replace('_', ' ').replaceFirstChar { it.uppercase() }
