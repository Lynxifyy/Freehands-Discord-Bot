package com.freehands.console.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The power card used to read a single boolean, so "I cannot reach the server"
 * and "the bot is stopped" both rendered as "Bot is offline" — and the only
 * button on offer was Start, which could not work because nothing was listening
 * to receive it. These pin the four states apart.
 */
class PowerStatusTest {

    private fun json(vararg pairs: Pair<String, Any>): JSONObject {
        val o = JSONObject()
        pairs.forEach { (k, v) -> o.put(k, v) }
        return o
    }

    @Test
    fun `a healthy bot is online`() {
        assertEquals(PowerStatus.Online, parsePowerStatus(json("running" to true, "healthy" to true)))
    }

    @Test
    fun `an alive but silent bot needs a restart`() {
        // The gateway reads its socket with no timeout, so this is a real
        // state: the process is there but no longer answering.
        assertEquals(PowerStatus.Unresponsive, parsePowerStatus(json("running" to true, "healthy" to false)))
    }

    @Test
    fun `a supervisor that says not running is stopped`() {
        assertEquals(PowerStatus.Stopped, parsePowerStatus(json("running" to false, "healthy" to false)))
    }

    @Test
    fun `running without a health field is treated as unresponsive`() {
        // Older servers do not send `healthy`. Alive-but-unverified must not be
        // reported as online, or Start would never be offered for a wedged bot.
        assertEquals(PowerStatus.Unresponsive, parsePowerStatus(json("running" to true)))
    }

    @Test
    fun `an empty payload is stopped`() {
        assertEquals(PowerStatus.Stopped, parsePowerStatus(JSONObject()))
    }

    @Test
    fun `a refused token is its own state, not an unreachable host`() {
        // The server is healthy; this phone just needs to pair again. Calling
        // it "unreachable" would send the user to fix the wrong thing.
        val e = java.io.IOException("HTTP 401: {\"error\": \"unauthorized\"}")
        assertEquals(PowerStatus.Unauthorized, classifyPowerFailure(e))
    }

    @Test
    fun `a timeout stays unreachable`() {
        val e = java.io.IOException("connect timed out")
        assertEquals(PowerStatus.Unreachable, classifyPowerFailure(e))
    }
}
