package app.brokeros.android

import app.brokeros.android.core.HELP_AREAS
import app.brokeros.android.core.HELP_TOPICS
import app.brokeros.android.core.Help
import app.brokeros.android.core.appRoute
import app.brokeros.android.data.ApiJson
import app.brokeros.android.data.Subscription
import app.brokeros.android.data.Team
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HelpTest {
    private fun ids(q: String) = Help.search(HELP_TOPICS, q).map { it.id }

    @Test fun `the app's guide has the web's topics`() {
        assertEquals(36, HELP_TOPICS.size)
        assertEquals(HELP_TOPICS.size, HELP_TOPICS.map { it.id }.toSet().size)
        assertTrue(HELP_TOPICS.all { t -> HELP_AREAS.any { it.key == t.area } })
    }

    @Test fun `M-Pesa is found however it is spelled`() {
        assertEquals("mpesa", Help.normalise("M-Pesa"))
        listOf("mpesa", "M-Pesa", "m pesa").forEach { assertTrue(ids(it).contains("mpesa-prompt")) }
    }

    @Test fun `title matches rank first and every word must match`() {
        assertEquals("renewals", ids("renewal").first())
        assertTrue(ids("whatsapp quote").contains("send-quote"))
        assertEquals(emptyList<String>(), ids("whatsapp zebra"))
    }

    @Test fun `everyday words find the right topic`() {
        assertTrue(ids("bill").contains("invoice"))
        assertEquals("import", ids("excel").first())
        assertEquals("brand", ids("logo").first())
    }

    @Test fun `topics follow the plan and role`() {
        val perms = listOf("client:read:all", "client:write", "insurer:read", "commission:read:all", "invoice:write", "org:read", "member:read")
        val business = HELP_TOPICS.filter { Help.canSee(it, perms, listOf("branding", "team")) }.map { it.id }
        assertFalse(business.contains("send-quote"))
        assertTrue(business.contains("invoice"))
    }

    @Test fun `web links open the app's own screens where there is one`() {
        assertEquals("clients", appRoute("/clients"))
        assertEquals("quote/abc", appRoute("/quotes/abc"))
        assertEquals("document/inv1", appRoute("/invoices/inv1?tab=pay"))
        assertEquals("plan", appRoute("/settings/plan"))
        assertEquals("policy/new?clientId=&clientName=&quoteId=", appRoute("/policies/new"))
        assertNull(appRoute("/settings/branding"))
        assertNull(appRoute(null))
    }
}

class AgencyTest {
    @Test fun `the team comes from the auth service`() {
        val team = ApiJson.decodeFromString(
            Team.serializer(),
            """{"id":"o1","name":"Otieno Agency","members":[{"id":"m1","role":"owner","user":{"id":"u1","name":"Achieng","email":"a@example.com"},"createdAt":"x"}],
               "invitations":[{"id":"i1","email":"b@example.com","role":"agent","status":"pending","expiresAt":"y"}]}""",
        )
        assertEquals("owner", team.members.single().role)
        assertEquals("b@example.com", team.invitations.single().email)
    }

    @Test fun `the subscription reads the trial and usage`() {
        val s = ApiJson.decodeFromString(
            Subscription.serializer(),
            """{"plan":"agency","plan_name":"Agency","paid_plan":"trial","status":"trialing","trial_ends_at":"2026-11-02T00:00:00Z","limits":{},
               "seats":5,"usage":{"clients":3,"documents_this_month":1,"seats_used":1},"founding_places_left":97,"features":["insurance"],"billing_cycle":"monthly"}""",
        )
        assertEquals("trialing", s.status)
        assertEquals("trial", s.paidPlan)
        assertEquals(null, s.limits["clients"]) // no plan limits clients
        assertEquals(3, s.usage.clients)
    }
}
