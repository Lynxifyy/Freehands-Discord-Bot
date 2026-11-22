package com.freehands.console.data

import android.app.Application
import android.os.Build
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
)

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
        if (_state.value.configured) {
            refreshCreator()
            poll()
        }
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
            runCatching { api.pair(cleaned, deviceName()) }
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
