package com.freehands.console.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class Media(val kind: String, val url: String, val name: String)

data class LogRow(
    val seq: Int,
    val type: String,
    val at: Long,
    val channel: String,
    val authorId: String,
    val authorName: String,
    val text: String,
    val before: String,
    val media: List<Media>,
    val platforms: List<String>,
    val messageId: String,
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

data class Creator(
    val login: String,
    val name: String,
    val avatarUrl: String,
    val bio: String,
)

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
            val mediaArr = r.optJSONArray("media") ?: JSONArray()
            val platArr = r.optJSONArray("platforms") ?: JSONArray()
            LogRow(
                seq = r.optInt("seq"),
                type = r.optString("type"),
                at = r.optLong("at"),
                channel = r.optString("channel"),
                authorId = a.optString("id"),
                authorName = a.optString("name"),
                text = r.optString("text"),
                before = r.optString("before"),
                media = (0 until mediaArr.length()).map { m ->
                    val mo = mediaArr.getJSONObject(m)
                    Media(mo.optString("kind"), mo.optString("url"), mo.optString("name"))
                },
                platforms = (0 until platArr.length()).map { platArr.getString(it) },
                messageId = r.optString("message_id"),
            )
        }
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
}
