package com.freehands.console.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `/api/status` reports the verified account, and the account screen renders
 * it. A regression here is what produced the black account page before: the
 * app never read `identity` at all, so the screen had nothing to show.
 */
class AccountTest {

    private fun json(vararg pairs: Pair<String, Any>): JSONObject {
        val o = JSONObject()
        pairs.forEach { (k, v) -> o.put(k, v) }
        return o
    }

    @Test
    fun `parses the identity the bot reports`() {
        val a = Account.from(
            json(
                "id" to "1310733783653154816",
                "username" to "lynxifyy",
                "display_name" to "Lynxifyy",
                "avatar" to "abc123",
                "tier" to "owner",
            )
        )
        assertEquals("1310733783653154816", a?.id)
        assertEquals("lynxifyy", a?.username)
        assertEquals("Lynxifyy", a?.displayName)
        assertEquals("owner", a?.tier)
        assertTrue(a!!.isOwner)
    }

    @Test
    fun `a missing identity is null, not an empty account`() {
        assertNull(Account.from(null))
        assertNull(Account.from(JSONObject()))
        // An id is the one field that cannot be faked into existence.
        assertNull(Account.from(json("username" to "someone")))
    }

    @Test
    fun `label falls back from display name to username to id`() {
        assertEquals("Lynxifyy", Account(id = "1", username = "u", displayName = "Lynxifyy").label)
        assertEquals("u", Account(id = "1", username = "u").label)
        assertEquals("1", Account(id = "1").label)
    }

    @Test
    fun `a blank tier is treated as a normal user`() {
        val a = Account.from(json("id" to "1", "tier" to ""))
        assertEquals("user", a?.tier)
        assertFalse(a!!.isOwner)
    }

    @Test
    fun `animated avatars use the gif endpoint`() {
        val a = Account(id = "42", avatar = "a_abc")
        assertEquals(
            "https://cdn.discordapp.com/avatars/42/a_abc.gif?size=128",
            a.avatarUrl,
        )
    }

    @Test
    fun `static avatars use the png endpoint`() {
        val a = Account(id = "42", avatar = "abc")
        assertEquals(
            "https://cdn.discordapp.com/avatars/42/abc.png?size=128",
            a.avatarUrl,
        )
    }

    @Test
    fun `no avatar yields no url so the initial is drawn instead`() {
        assertEquals("", Account(id = "42").avatarUrl)
    }

    @Test
    fun `an absolute avatar url is left untouched`() {
        val url = "https://example.test/a.png"
        assertEquals(url, Account(id = "42", avatar = url).avatarUrl)
    }

    @Test
    fun `status carries the account through`() {
        // The parser reads `identity`; the old one dropped it on the floor.
        val status = JSONObject(
            """
            {
              "running": true,
              "bot": {"name": "Freehands", "id": "1568005572769480704"},
              "identity": {"id": "7", "username": "ops", "tier": "owner"},
              "settings": {},
              "stats": {"events": {}}
            }
            """.trimIndent()
        )
        val account = Account.from(status.optJSONObject("identity"))
        assertEquals("ops", account?.username)
        assertEquals("7", account?.id)
    }
}
