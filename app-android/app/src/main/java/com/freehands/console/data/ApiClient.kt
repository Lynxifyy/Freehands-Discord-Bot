package com.freehands.console.data

import com.freehands.console.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class Media(
    val kind: String,
    val url: String,
    val name: String,
    /** Attachment size in bytes, 0 when Discord did not report one. */
    val size: Long = 0L,
)

data class LogRow(
    val seq: Int,
    val type: String,
    val at: Long,
    val channel: String,
    val authorId: String,
    val authorName: String,
    /**
     * Who performed the action when it is not the author: the person who
     * deleted a message, or the bot when automod removed it. Empty for a plain
     * message, where the author is the only actor.
     */
    val actorId: String,
    val actorName: String,
    val text: String,
    val before: String,
    val media: List<Media>,
    val platforms: List<String>,
    val messageId: String,
)

/** Someone who can reach the bot, labelled by the power they hold. */
data class Person(
    val id: String,
    val name: String,
    val display: String,
    val tier: String,
    /** Human tier label, e.g. "Owner of Freehands". */
    val label: String,
    val avatar: String,
    /** Lynx owns Freehands, so destructive actions cannot target him. */
    val protected: Boolean,
    val reason: String,
)

/** An armed loop: a ban or kick that repeats on a timer. */
data class LoopInfo(
    val id: String,
    val kind: String,
    val target: String,
    val reason: String,
    val interval: Double,
    val passes: Int,
    val fired: Int,
    val running: Boolean,
    val stopped: String,
    val lastError: String,
)

/** One owner-power switch. */
data class Power(
    val key: String,
    val name: String,
    val blurb: String,
    val kind: String,
    val confirm: Boolean,
    val on: Boolean,
)

data class CommandInfo(
    val name: String,
    val usage: String,
    val summary: String,
    val detail: String,
    val tier: String,
    val aliases: List<String>,
)

data class BotStatus(
    val running: Boolean,
    val botName: String,
    val botId: String,
    val settings: Map<String, Any>,
    val counts: Map<String, Int>,
)

data class UpdateInfo(
    val known: Boolean,
    val version: String,
    val url: String,
    val notes: String,
)

data class SelfTest(
    val passed: Int,
    val total: Int,
    val checks: List<SelfTestCheck>,
) {
    val ok: Boolean get() = total > 0 && passed == total
}

data class SelfTestCheck(val name: String, val ok: Boolean, val detail: String)

data class Creator(
    val login: String,
    val name: String,
    val avatarUrl: String,
    val bio: String,
)

/**
 * The console address ships with the app, so nobody has to type one.
 *
 * This is the operator host. Override at build time with
 * `-PfreehandsBaseUrl=https://...` for a self-hosted deployment.
 */
object Endpoint {
    val DEFAULT_BASE: String = BuildConfig.BASE_URL
}

class ApiClient(var baseUrl: String, var token: String) {

    private fun conn(path: String, method: String, body: String?): HttpURLConnection {
        val url = URL(baseUrl.trimEnd('/') + path)
        val c = url.openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 8000
        c.readTimeout = 12000
        c.setRequestProperty("Authorization", "Bearer $token")
        if (body != null) {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(body.toByteArray()) }
        }
        return c
    }

    private fun read(c: HttpURLConnection): String {
        val code = c.responseCode
        val stream = if (code in 200..299) c.inputStream else c.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
        if (code !in 200..299) throw IOException("HTTP $code: ${text.take(200)}")
        return text
    }

    /**
     * The newest published release. Public, so it works before pairing.
     *
     * A failure here is not an error worth showing: the phone may be offline,
     * or GitHub may be rate-limiting. The caller treats "unknown" as "say
     * nothing" rather than nagging about a check that never happened.
     */
    suspend fun latestVersion(): UpdateInfo? = withContext(Dispatchers.IO) {
        runCatching {
            val url = URL(baseUrl.trimEnd('/') + "/api/version")
            val c = url.openConnection() as HttpURLConnection
            c.connectTimeout = 5000
            c.readTimeout = 8000
            val text = c.inputStream.bufferedReader().use { it.readText() }
            val o = JSONObject(text)
            UpdateInfo(
                known = o.optBoolean("known", false),
                version = o.optString("version"),
                url = o.optString("url"),
                notes = o.optString("notes"),
            )
        }.getOrNull()
    }

    suspend fun status(): BotStatus = withContext(Dispatchers.IO) {
        val o = JSONObject(read(conn("/api/status", "GET", null)))
        val settings = mutableMapOf<String, Any>()
        o.optJSONObject("settings")?.let { s ->
            s.keys().forEach { k -> settings[k] = s.get(k) }
        }
        val counts = mutableMapOf<String, Int>()
        o.optJSONObject("stats")?.optJSONObject("events")?.let { e ->
            e.keys().forEach { k -> counts[k] = e.optInt(k) }
        }
        BotStatus(
            running = o.optBoolean("running", false),
            botName = o.optJSONObject("bot")?.optString("name") ?: "",
            botId = o.optJSONObject("bot")?.optString("id") ?: "",
            settings = settings,
            counts = counts,
        )
    }

    suspend fun log(after: Int = 0, limit: Int = 200): List<LogRow> = withContext(Dispatchers.IO) {
        val o = JSONObject(read(conn("/api/log?after=$after&limit=$limit", "GET", null)))
        val arr = o.optJSONArray("rows") ?: JSONArray()
        (0 until arr.length()).map { i ->
            val r = arr.getJSONObject(i)
            val a = r.optJSONObject("author") ?: JSONObject()
            val act = r.optJSONObject("actor") ?: JSONObject()
            val mediaArr = r.optJSONArray("media") ?: JSONArray()
            val platArr = r.optJSONArray("platforms") ?: JSONArray()
            LogRow(
                seq = r.optInt("seq"),
                type = r.optString("type"),
                at = r.optLong("at"),
                channel = r.optString("channel"),
                authorId = a.optString("id"),
                authorName = a.optString("name"),
                actorId = act.optString("id"),
                actorName = act.optString("name"),
                text = r.optString("text"),
                before = r.optString("before"),
                media = (0 until mediaArr.length()).map { m ->
                    val mo = mediaArr.getJSONObject(m)
                    Media(
                        kind = mo.optString("kind"),
                        url = mo.optString("url"),
                        name = mo.optString("name"),
                        size = mo.optString("size").toLongOrNull() ?: 0L,
                    )
                },
                platforms = (0 until platArr.length()).map { platArr.getString(it) },
                messageId = r.optString("message_id"),
            )
        }
    }

    suspend fun selfTest(): SelfTest = withContext(Dispatchers.IO) {
        val o = JSONObject(read(conn("/api/selftest", "GET", null)))
        val arr = o.optJSONArray("checks") ?: JSONArray()
        SelfTest(
            passed = o.optInt("passed"),
            total = o.optInt("total"),
            checks = (0 until arr.length()).map { i ->
                val c = arr.getJSONObject(i)
                SelfTestCheck(
                    name = c.optString("name"),
                    ok = c.optBoolean("ok"),
                    detail = c.optString("detail"),
                )
            },
        )
    }

    suspend fun commands(): List<CommandInfo> = withContext(Dispatchers.IO) {
        val o = JSONObject(read(conn("/api/commands", "GET", null)))
        val arr = o.optJSONArray("commands") ?: JSONArray()
        (0 until arr.length()).map { i ->
            val c = arr.getJSONObject(i)
            val al = c.optJSONArray("aliases") ?: JSONArray()
            CommandInfo(
                name = c.optString("name"),
                usage = c.optString("usage"),
                summary = c.optString("summary"),
                detail = c.optString("detail"),
                tier = c.optString("tier"),
                aliases = (0 until al.length()).map { al.getString(it) },
            )
        }
    }

    /**
     * Trades a six-character code from Discord for a device token.
     *
     * This is the only unauthenticated call: the code is the credential, and
     * it can only have come from an operator running `+pair` in the server.
     */
    suspend fun pair(code: String, deviceName: String, model: String = ""): String =
        withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("action", "claim")
            .put("code", code)
            .put("name", deviceName)
            // Build.MODEL is stable per hardware model; the display name is not.
            .put("model", model)
            .toString()
        val c = URL(baseUrl.trimEnd('/') + "/api/pair").openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.connectTimeout = 8000
        c.readTimeout = 12000
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.outputStream.use { it.write(body.toByteArray()) }
        val o = JSONObject(read(c))
        o.optString("token").ifBlank { throw IOException("pairing returned no token") }
    }

    suspend fun power(action: String): Boolean = withContext(Dispatchers.IO) {
        val body = JSONObject().put("action", action).toString()
        runCatching { read(conn("/api/power", "POST", body)) }.isSuccess
    }

    suspend fun powerState(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val o = JSONObject(read(conn("/api/power", "GET", null)))
            o.optBoolean("running", false)
        }.getOrDefault(false)
    }

    suspend fun patchSettings(patch: Map<String, Any>): Boolean = withContext(Dispatchers.IO) {
        val body = JSONObject()
        patch.forEach { (k, v) -> body.put(k, v) }
        runCatching { read(conn("/api/settings", "PATCH", body.toString())) }.isSuccess
    }

    /** GitHub profile, fetched straight from the public API so it stays live. */
    suspend fun creator(login: String): Creator? = withContext(Dispatchers.IO) {
        runCatching {
            val c = URL("https://api.github.com/users/$login").openConnection() as HttpURLConnection
            c.connectTimeout = 8000
            c.readTimeout = 10000
            c.setRequestProperty("Accept", "application/vnd.github+json")
            val o = JSONObject(read(c))
            Creator(
                login = o.optString("login"),
                name = o.optString("name").ifBlank { o.optString("login") },
                avatarUrl = o.optString("avatar_url"),
                bio = o.optString("bio"),
            )
        }.getOrNull()
    }

    suspend fun people(): List<Person> = withContext(Dispatchers.IO) {
        val o = JSONObject(read(conn("/api/people", "GET", null)))
        val arr = o.optJSONArray("people") ?: JSONArray()
        (0 until arr.length()).map { i ->
            val p = arr.getJSONObject(i)
            Person(
                id = p.optString("id"),
                name = p.optString("name"),
                display = p.optString("display"),
                tier = p.optString("tier"),
                label = p.optString("label"),
                avatar = p.optString("avatar"),
                protected = p.optBoolean("protected", false),
                reason = p.optString("reason"),
            )
        }
    }

    suspend fun loops(): List<LoopInfo> = withContext(Dispatchers.IO) {
        val o = JSONObject(read(conn("/api/loops", "GET", null)))
        val arr = o.optJSONArray("loops") ?: JSONArray()
        (0 until arr.length()).map { i ->
            val l = arr.getJSONObject(i)
            LoopInfo(
                id = l.optString("id"),
                kind = l.optString("kind"),
                target = l.optString("target"),
                reason = l.optString("reason"),
                interval = l.optDouble("interval", 60.0),
                passes = l.optInt("passes", 1),
                fired = l.optInt("fired", 0),
                running = l.optBoolean("running", false),
                stopped = l.optString("stopped"),
                lastError = l.optString("last_error"),
            )
        }
    }

    /** Arms a loop. Returns the new loop, or throws with the server's reason. */
    suspend fun armLoop(
        kind: String,
        target: String,
        passes: Int,
        intervalSeconds: Int,
        reason: String,
        notify: Boolean,
    ): LoopInfo = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("kind", kind)
            .put("target", target)
            .put("passes", passes)
            .put("interval", intervalSeconds)
            .put("reason", reason)
            .put("notify", notify)
            .toString()
        val l = JSONObject(read(conn("/api/loops", "POST", body))).optJSONObject("loop")
            ?: throw IOException("loop was not armed")
        LoopInfo(
            id = l.optString("id"),
            kind = l.optString("kind"),
            target = l.optString("target"),
            reason = l.optString("reason"),
            interval = l.optDouble("interval", 60.0),
            passes = l.optInt("passes", 1),
            fired = l.optInt("fired", 0),
            running = l.optBoolean("running", false),
            stopped = l.optString("stopped"),
            lastError = l.optString("last_error"),
        )
    }

    suspend fun stopLoop(id: String): Boolean = withContext(Dispatchers.IO) {
        val body = JSONObject().put("id", id).toString()
        JSONObject(read(conn("/api/loops/stop", "POST", body))).optBoolean("ok", false)
    }

    /** The owner panel, or null when this account is not Lynx. */
    suspend fun ownerPanel(): List<Power>? = withContext(Dispatchers.IO) {
        runCatching {
            val o = JSONObject(read(conn("/api/owner", "GET", null)))
            if (!o.optBoolean("ok", false)) return@runCatching null
            val arr = o.optJSONArray("powers") ?: JSONArray()
            (0 until arr.length()).map { i ->
                val p = arr.getJSONObject(i)
                Power(
                    key = p.optString("key"),
                    name = p.optString("name"),
                    blurb = p.optString("blurb"),
                    kind = p.optString("kind"),
                    confirm = p.optBoolean("confirm", false),
                    on = p.optBoolean("on", false),
                )
            }
        }.getOrNull()
    }

    suspend fun setPower(
        key: String,
        on: Boolean,
        confirm: String = "",
    ): String? = withContext(Dispatchers.IO) {
        runCatching {
            val body = JSONObject()
                .put("key", key)
                .put("on", on)
                .put("confirm", confirm)
                .toString()
            val o = JSONObject(read(conn("/api/owner", "POST", body)))
            if (o.optBoolean("ok", false)) o.optString("detail").ifBlank { null }
            else o.optString("error").ifBlank { "refused" }
        }.getOrNull()
    }

}
