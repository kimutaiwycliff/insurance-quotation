package app.brokeros.android

import app.brokeros.android.core.Jwt
import app.brokeros.android.core.Phone
import app.brokeros.android.ui.home.money
import app.brokeros.android.update.AppConfig
import app.brokeros.android.update.UpdateNeed
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.util.Base64

fun fakeJwt(exp: Long): String {
    val enc = { s: String -> Base64.getUrlEncoder().withoutPadding().encodeToString(s.toByteArray()) }
    return "${enc("{\"alg\":\"EdDSA\"}")}.${enc("{\"sub\":\"u1\",\"exp\":$exp}")}.signature"
}

class HelpersTest {
    @Test fun `reads the expiry of an API token`() {
        assertEquals(1_900_000_000L, Jwt.expiresAt(fakeJwt(1_900_000_000)))
        assertNull(Jwt.expiresAt("not-a-token"))
    }

    @Test fun `phone links and the way Kenyans write numbers`() {
        assertEquals("0712 345 678", Phone.display("+254712345678"))
        assertEquals("+44 20 7946 0000", Phone.display("+44 20 7946 0000"))
        assertEquals("tel:+254712345678", Phone.dialUri("+254712345678"))
        assertEquals("https://wa.me/254712345678?text=Hello%20Wanjiru%2C%20this%20is%20Achieng.", Phone.whatsAppUrl("+254712345678", "Hello Wanjiru, this is Achieng."))
        assertEquals("https://wa.me/254712345678", Phone.whatsAppUrl("+254712345678"))
    }

    @Test fun `update rules from the server`() {
        val config = AppConfig(android = AppConfig.Android(minVersionCode = 5, latestVersionCode = 8))
        assertEquals(UpdateNeed.Required, UpdateNeed.of(4, config))
        assertEquals(UpdateNeed.Available, UpdateNeed.of(5, config))
        assertEquals(UpdateNeed.None, UpdateNeed.of(8, config))
    }

    @Test fun `money is shown from decimal strings, never floats`() {
        assertEquals("KES 70,355", money("70355.00", "KES"))
        assertEquals("KES 0", money("not a number", "KES"))
        assertEquals("UGX 1,850,000", money("1850000", "UGX"))
    }
}

class UpdateTest {
    @Test fun `a direct download installs only with the published checksum`() {
        val sha = "a".repeat(64)
        assertEquals(true, app.brokeros.android.update.Checksum.matches(" ${sha.uppercase()} ", sha))
        assertEquals(false, app.brokeros.android.update.Checksum.matches("", sha)) // nothing published: refuse
        assertEquals(false, app.brokeros.android.update.Checksum.matches("b".repeat(64), sha))
    }

    @Test fun `the app reads the APK link and checksum from the server`() {
        val config = app.brokeros.android.data.ApiJson.decodeFromString(
            AppConfig.serializer(),
            """{"android":{"min_version_code":2,"latest_version_code":5,"store_url":"","apk_url":"/downloads/brokeros-0.5.0.apk","apk_sha256":"ab"},"notice":null,"features":[]}""",
        )
        assertEquals("/downloads/brokeros-0.5.0.apk", config.android.apkUrl)
        assertEquals(UpdateNeed.Available, UpdateNeed.of(3, config))
    }
}
