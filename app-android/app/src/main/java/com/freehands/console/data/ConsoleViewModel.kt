package com.freehands.console.data

import android.app.Application
import android.os.Build
import com.freehands.console.BuildConfig
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

const val CREATOR_LOGIN = "Lynxifyy"
const val REPO_URL = "https://github.com/Lynxifyy/Freehands-Discord-Bot"

data class UiState(
    val configured: Boolean = false,
    val pairing: Boolean = false,
    val pairError: String? = null,
    val running: Boolean = false,
    val botName: String = "",
    val settings: Map<String, Any> = emptyMap(),
    val counts: Map<String, Int> = emptyMap(),
    val rows: List<LogRow> = emptyList(),
    val commands: List<CommandInfo> = emptyList(),
    val creator: Creator? = null,
    val error: String? = null,
    val busy: Boolean = false,
    val live: Boolean = true,
    val test: SelfTest? = null,
    val testing: Boolean = false,
    val update: UpdateInfo? = null,
    val updateDismissed: Boolean = false,
    val people: List<Person> = emptyList(),
    val loops: List<LoopInfo> = emptyList(),
    val powers: List<Power>? = null,
    /** Transient line shown after a loop or power action. */
    val notice: String? = null,
)

/**
 * Compares dotted versions numerically.
 *
 * String comparison would call 1.10.0 older than 1.9.0, which would either
 * hide a real update or nag forever about an old one.
 */
internal fun isNewer(remote: String, local: String): Boolean {
    val a = remote.trim().removePrefix("v").split(".").map { it.toIntOrNull() ?: 0 }
    val b = local.trim().removePrefix("v").split(".").map { it.toIntOrNull() ?: 0 }
    for (i in 0 until maxOf(a.size, b.size)) {
        val x = a.getOrElse(i) { 0 }
        val y = b.getOrElse(i) { 0 }
        if (x != y) return x > y
    }
    return false
}

class ConsoleViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = app.getSharedPreferences("freehands", 0)
    private val api = ApiClient(
        // The address ships with the app; only a self-hosted build overrides it.
        prefs.getString("base", "")?.ifBlank { null } ?: Endpoint.DEFAULT_BASE,
        prefs.getString("token", "") ?: "",
    )

    private val _state = MutableStateFlow(UiState(configured = api.token.isNotBlank()))
    val state: StateFlow<UiState> = _state.asStateFlow()
    private var polling = false

    init {
        checkForUpdate()
        if (_state.value.configured) {
            refreshCreator()
            poll()
        }
    }


    // -- loops -------------------------------------------------------------
    /**
     * Loads the people a loop can target, plus the loops already running.
     * Called when the panel opens rather than on the poll, because the member
     * list is a heavier call than the status refresh.
     */
    fun loadLoops() {
        viewModelScope.launch {
            val people = runCatching { api.people() }.getOrDefault(emptyList())
            val loops = runCatching { api.loops() }.getOrDefault(emptyList())
            _state.value = _state.value.copy(people = people, loops = loops)
        }
    }

    fun armLoop(
        kind: String,
        target: String,
        passes: Int,
        intervalSeconds: Int,
        reason: String,
        notify: Boolean,
    ) {
        viewModelScope.launch {
            runCatching {
                api.armLoop(kind, target, passes, intervalSeconds, reason, notify)
            }
                .onSuccess { loop ->
                    _state.value = _state.value.copy(
                        notice = "${loop.id} armed: $kind every ${loop.interval.toInt()}s " +
                            "for ${loop.passes} passes",
                        loops = runCatching { api.loops() }.getOrDefault(_state.value.loops),
                    )
                }
                .onFailure { e ->
                    _state.value = _state.value.copy(notice = e.message ?: "could not arm the loop")
                }
        }
    }

    fun stopLoop(id: String) {
        viewModelScope.launch {
            runCatching { api.stopLoop(id) }
                .onSuccess {
                    _state.value = _state.value.copy(
                        notice = "stopped $id",
                        loops = runCatching { api.loops() }.getOrDefault(_state.value.loops),
                    )
                }
                .onFailure { e ->
                    _state.value = _state.value.copy(notice = e.message ?: "could not stop $id")
                }
        }
    }

    // -- owner powers ------------------------------------------------------
    fun loadPowers() {
        viewModelScope.launch {
            val powers = api.ownerPanel()
            _state.value = _state.value.copy(
                powers = powers,
                notice = if (powers == null) "Owner powers are Lynx only." else null,
            )
        }
    }

    fun setPower(key: String, on: Boolean, confirm: String = "") {
        viewModelScope.launch {
            val detail = api.setPower(key, on, confirm)
            _state.value = _state.value.copy(
                powers = api.ownerPanel() ?: _state.value.powers,
                notice = detail ?: "$key ${if (on) "on" else "off"}",
            )
        }
    }

    fun clearNotice() {
        _state.value = _state.value.copy(notice = null)
    }

    /**
     * Asks the host for the newest release. Silent on failure: a phone that is
     * offline or a host that cannot reach GitHub must not show an error banner
     * for a check the operator never asked for.
     */
    fun checkForUpdate() {
        viewModelScope.launch {
            val latest = api.latestVersion() ?: return@launch
            if (!latest.known || latest.version.isBlank()) return@launch
            if (isNewer(latest.version, BuildConfig.VERSION_NAME)) {
                _state.value = _state.value.copy(update = latest)
            }
        }
    }

    /** Runs the same checks as `+test`, so the phone and Discord agree. */
    fun runTest() {
        if (_state.value.testing) return
        viewModelScope.launch {
            _state.value = _state.value.copy(testing = true, error = null)
            val result = runCatching { api.selfTest() }.getOrNull()
            _state.value = _state.value.copy(
                testing = false,
                test = result,
                error = if (result == null) "self-test could not run" else _state.value.error,
            )
        }
    }

    fun clearTest() {
        _state.value = _state.value.copy(test = null)
    }

    fun dismissUpdate() {
        _state.value = _state.value.copy(updateDismissed = true)
    }

    /**
     * Turns a code from Discord into this device's credential.
     *
     * Nothing is typed except the six characters the operator already has on
     * screen in Discord, and the resulting token is stored on the device only.
     */
    fun pair(code: String) {
        val cleaned = code.filter { it.isLetterOrDigit() }.uppercase()
        if (cleaned.length != 6) {
            _state.value = _state.value.copy(pairError = "Enter the six-character code from Discord.")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(pairing = true, pairError = null)
            runCatching { api.pair(cleaned, deviceName(), Build.MODEL) }
                .onSuccess { token ->
                    prefs.edit()
                        .putString("base", api.baseUrl)
                        .putString("token", token)
                        .apply()
                    api.token = token
                    _state.value = _state.value.copy(
                        configured = true, pairing = false, pairError = null, error = null,
                    )
                    refreshCreator()
                    poll()
                }
                .onFailure { e ->
                    _state.value = _state.value.copy(
                        pairing = false,
                        pairError = e.message ?: "Could not pair. Check the code and try again.",
                    )
                }
        }
    }

    /** The phone's own model name, so `+devices` shows something recognisable. */
    private fun deviceName(): String =
        "${Build.MANUFACTURER} ${Build.MODEL}".replaceFirstChar { it.uppercase() }.trim()

    /** Forgets this device locally. The server-side device stays until +revoke. */
    fun forgetDevice() {
        prefs.edit().remove("token").apply()
        api.token = ""
        _state.value = UiState(configured = false)
    }

    private fun refreshCreator() {
        viewModelScope.launch {
            val c = api.creator(CREATOR_LOGIN)
            if (c != null) _state.value = _state.value.copy(creator = c)
        }
    }

    fun poll() {
        // Guarded: two loops would double the request rate against the bot.
        if (polling) return
        polling = true
        viewModelScope.launch {
            while (true) {
                try {
                    val running = api.powerState()
                    if (running) {
                        val st = api.status()
                        val rows = api.log()
                        val cmds = if (_state.value.commands.isEmpty()) api.commands() else _state.value.commands
                        _state.value = _state.value.copy(
                            running = true, botName = st.botName, settings = st.settings,
                            counts = st.counts, rows = rows, commands = cmds,
                            error = null, live = true,
                        )
                    } else {
                        _state.value = _state.value.copy(running = false, live = false)
                    }
                } catch (e: Exception) {
                    _state.value = _state.value.copy(
                        running = false, live = false,
                        error = e.message ?: "connection failed",
                    )
                }
                delay(if (_state.value.live) 4000L else 8000L)
            }
        }
    }

    fun togglePower() {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            val action = if (_state.value.running) "stop" else "start"
            api.power(action)
            delay(2500)
            _state.value = _state.value.copy(busy = false)
        }
    }

    fun forceRestart() {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            api.power("restart")
            delay(4000)
            _state.value = _state.value.copy(busy = false)
        }
    }

    fun setSetting(key: String, value: Any) {
        viewModelScope.launch {
            api.patchSettings(mapOf(key to value))
            val st = runCatching { api.status() }.getOrNull() ?: return@launch
            _state.value = _state.value.copy(settings = st.settings)
        }
    }
}
