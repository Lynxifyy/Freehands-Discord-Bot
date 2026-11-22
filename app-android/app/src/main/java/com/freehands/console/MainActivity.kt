package com.freehands.console

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.freehands.console.data.ConsoleViewModel
import com.freehands.console.ui.Brand
import com.freehands.console.ui.CommandsTab
import com.freehands.console.ui.Danger
import com.freehands.console.ui.Ink
import com.freehands.console.ui.LogTab
import com.freehands.console.ui.Muted
import com.freehands.console.ui.Panel
import com.freehands.console.ui.PanelAlt
import com.freehands.console.ui.SettingsTab
import com.freehands.console.ui.StatusPill

private val scheme = darkColorScheme(
    primary = Brand,
    background = Ink,
    surface = Panel,
    onPrimary = Color.White,
    onBackground = Color.White,
    onSurface = Color.White,
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = scheme) {
                Box(Modifier.fillMaxSize().background(Ink)) {
                    App()
                }
            }
        }
    }
}

@Composable
private fun App(vm: ConsoleViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()

    if (!state.configured) {
        SetupScreen { base, token -> vm.configure(base, token) }
        return
    }

    var tab by remember { mutableStateOf(0) }

    Scaffold(
        containerColor = Ink,
        bottomBar = {
            NavigationBar(containerColor = Panel, tonalElevation = 0.dp) {
                val items = listOf("Live", "Commands", "Settings")
                items.forEachIndexed { i, label ->
                    NavigationBarItem(
                        selected = tab == i,
                        onClick = { tab = i },
                        icon = {
                            Text(
                                when (i) {
                                    0 -> "▤"
                                    1 -> "❯"
                                    else -> "⚙"
                                },
                                fontSize = 15.sp,
                                color = if (tab == i) Brand else Muted,
                            )
                        },
                        label = {
                            Text(
                                label, fontSize = 10.sp,
                                color = if (tab == i) Brand else Muted,
                                fontWeight = if (tab == i) FontWeight.Bold else FontWeight.Normal,
                            )
                        },
                        colors = NavigationBarItemDefaults.colors(
                            indicatorColor = Brand.copy(alpha = 0.14f),
                        ),
                    )
                }
            }
        },
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).statusBarsPadding()) {
            Header(
                running = state.running,
                live = state.live,
                botName = state.botName,
                error = state.error,
            )
            Box(Modifier.fillMaxSize()) {
                when (tab) {
                    0 -> LogTab(
                        rows = state.rows,
                        running = state.running,
                        live = state.live,
                        busy = state.busy,
                        counts = state.counts,
                        onTogglePower = vm::togglePower,
                    )
                    1 -> CommandsTab(commands = state.commands)
                    else -> SettingsTab(
                        settings = state.settings,
                        creator = state.creator,
                        busy = state.busy,
                        onToggle = { k, v -> vm.setSetting(k, v) },
                        onSelect = { k, v -> vm.setSetting(k, v) },
                        onForceRestart = vm::forceRestart,
                    )
                }
            }
        }
    }
}

@Composable
private fun Header(running: Boolean, live: Boolean, botName: String, error: String?) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    "FREEHANDS", color = Color.White, fontSize = 17.sp,
                    fontWeight = FontWeight.Bold, letterSpacing = 2.sp,
                )
                Text(
                    if (botName.isNotBlank()) "Eternal  ·  $botName" else "Eternal console",
                    color = Muted, fontSize = 10.sp,
                )
            }
            StatusPill(running, live)
        }
        if (error != null) {
            Spacer(Modifier.height(6.dp))
            Text(
                error, color = Danger, fontSize = 10.sp,
                fontFamily = FontFamily.Monospace, maxLines = 2,
            )
        }
    }
}

@Composable
private fun SetupScreen(onSave: (String, String) -> Unit) {
    var base by remember { mutableStateOf("http://") }
    var token by remember { mutableStateOf("") }

    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp)
            .statusBarsPadding(),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            "FREEHANDS", color = Color.White, fontSize = 26.sp,
            fontWeight = FontWeight.Bold, letterSpacing = 3.sp,
        )
        Text("Operator console", color = Muted, fontSize = 12.sp)
        Spacer(Modifier.height(28.dp))

        Text("CONTROL API URL", color = Muted, fontSize = 10.sp, letterSpacing = 1.2.sp)
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = base,
            onValueChange = { base = it },
            singleLine = true,
            placeholder = { Text("https://your-host/", color = Muted, fontSize = 12.sp) },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Brand, unfocusedBorderColor = PanelAlt,
                focusedTextColor = Color.White, unfocusedTextColor = Color.White,
            ),
        )

        Spacer(Modifier.height(16.dp))
        Text("CONSOLE TOKEN", color = Muted, fontSize = 10.sp, letterSpacing = 1.2.sp)
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            singleLine = true,
            placeholder = { Text("FH_CONSOLE_TOKEN", color = Muted, fontSize = 12.sp) },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Brand, unfocusedBorderColor = PanelAlt,
                focusedTextColor = Color.White, unfocusedTextColor = Color.White,
            ),
        )

        Spacer(Modifier.height(22.dp))
        Button(
            onClick = { onSave(base, token) },
            enabled = base.isNotBlank() && token.isNotBlank(),
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Brand),
        ) {
            Text("Connect", color = Color.White, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(10.dp))
        Text(
            "The token is stored on this device only. The bot itself is never " +
                "exposed to the network; this app talks to the control API.",
            color = Muted, fontSize = 10.sp, lineHeight = 15.sp,
        )
    }
}
