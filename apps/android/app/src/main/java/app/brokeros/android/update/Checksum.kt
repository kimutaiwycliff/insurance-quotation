package app.brokeros.android.update

/** Compares the server's published SHA-256 with what was downloaded. No published checksum, no install. */
object Checksum {
    fun matches(expected: String, actual: String): Boolean {
        val want = expected.trim().lowercase()
        return want.length == 64 && want == actual.lowercase()
    }
}
