package com.freehands.console

import android.content.Intent
import android.net.Uri
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.Terminal
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material.icons.rounded.WarningAmber
import androidx.compose.material3.Icon
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.freehands.console.data.ConsoleViewModel
import com.freehands.console.data.UpdateInfo
import com.freehands.console.ui.Brand
import com.freehands.console.ui.CommandsTab
import com.freehands.console.ui.Danger
import com.freehands.console.ui.Ink
import com.freehands.console.ui.LogTab
import com.freehands.console.ui.Muted
import com.freehands.console.ui.MutedDim
import com.freehands.console.ui.Panel
import com.freehands.console.ui.PanelAlt
import com.freehands.console.ui.BrandBright
import com.freehands.console.ui.BrandMark
import com.freehands.console.ui.Hairline
import com.freehands.console.ui.SettingsTab
import com.freehands.console.ui.SplashScreen
import com.freehands.console.ui.StatusPill

private val scheme = darkColorScheme(
    primary = Brand,
    background = Ink,
    surface = Panel,
    onPrimary = Color.White,
    onBackground = Color.White,
    onSurface = Color.White,
)

@Composable
private fun UpdateDialog(
    latest: UpdateInfo,
    onInstall: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Panel,
        title = {
            Text(
                "Update available",
                color = Color.White, fontWeight = FontWeight.Bold, fontSize = 17.sp,
            )
        },
        text = {
            Column {
                Text(
                    "Version ${latest.version} is ready. You are on ${BuildConfig.VERSION_NAME}.",
                    color = Color.White, fontSize = 13.sp,
                )
                if (latest.notes.isNotBlank()) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        latest.notes.trim().take(400),
                        color = Muted, fontSize = 11.sp,
                        maxLines = 8,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = onInstall,
                colors = ButtonDefaults.buttonColors(containerColor = Brand),
            ) { Text("Download", color = Color.White, fontSize = 13.sp) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Later", color = Muted, fontSize = 13.sp)
            }
        },
    )
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = scheme) {
                Box(Modifier.fillMaxSize().background(Ink)) {
                    var splashDone by rememberSaveable { mutableStateOf(false) }
                    Crossfade(
                        targetState = splashDone,
                        animationSpec = tween(650),
                        label = "splash",
                    ) { done ->
                        if (done) App() else SplashScreen { splashDone = true }
                    }
                }
            }
        }
    }
}

@Composable
private fun App(vm: ConsoleViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current

    // Shown above both screens: an update matters even before pairing.
    state.update?.let { latest ->
        if (!state.updateDismissed) {
            UpdateDialog(
                latest = latest,
                onInstall = {
                    runCatching {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(latest.url)))
                    }
                    vm.dismissUpdate()
                },
                onDismiss = vm::dismissUpdate,
            )
        }
    }

    if (!state.configured) {
        PairScreen(
            pairing = state.pairing,
            error = state.pairError,
            onPair = vm::pair,
        )
        return
    }

    var tab by rememberSaveable { mutableStateOf(0) }

    Scaffold(
        containerColor = Ink,
        bottomBar = {
            // A custom bar rather than NavigationBar: the default draws a flat
            // strip with equal-weight items, which is most of why the app read
            // as plain. This one floats, highlights the active tab with a
            // gradient pill, and uses real icons.
            Box(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp)) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(18.dp))
                        .background(Panel)
                        .border(1.dp, Hairline, RoundedCornerShape(18.dp))
                        .padding(6.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    val items = listOf(
                        Triple("Live", Icons.Rounded.Bolt, 0),
                        Triple("Commands", Icons.Rounded.Terminal, 1),
                        Triple("Settings", Icons.Rounded.Tune, 2),
                    )
                    items.forEach { (label, icon, i) ->
                        val active = tab == i
                        Row(
                            Modifier
                                .weight(1f)
                                .clip(RoundedCornerShape(13.dp))
                                .then(
                                    if (active) Modifier.background(
                                        Brush.verticalGradient(
                                            listOf(
                                                Brand.copy(alpha = 0.30f),
                                                Brand.copy(alpha = 0.12f),
                                            )
                                        )
                                    ) else Modifier
                                )
                                .clickable { tab = i }
                                .padding(vertical = 9.dp),
                            horizontalArrangement = Arrangement.Center,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                imageVector = icon,
                                contentDescription = label,
                                tint = if (active) BrandBright else MutedDim,
                                modifier = Modifier.size(17.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                label,
                                color = if (active) Color.White else Muted,
                                fontSize = 11.sp,
                                fontWeight = if (active) FontWeight.Bold else FontWeight.Medium,
                            )
                        }
                    }
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
                // Crossfade between tabs so switching does not snap.
                Crossfade(targetState = tab, animationSpec = tween(180), label = "tab") { t ->
                    when (t) {
                        0 -> LogTab(
                            rows = state.rows,
                            running = state.running,
                            live = state.live,
                            busy = state.busy,
                            counts = state.counts,
                            onTogglePower = vm::togglePower,
                            onTest = vm::runTest,
                            testing = state.testing,
                            test = state.test,
                            onDismissTest = vm::clearTest,
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
}

@Composable
private fun Header(running: Boolean, live: Boolean, botName: String, error: String?) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BrandMark(34)
        Spacer(Modifier.width(11.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "FREEHANDS", color = Color.White, fontSize = 16.sp,
                fontWeight = FontWeight.Bold, letterSpacing = 2.4.sp,
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (botName.isNotBlank()) "Eternal" else "Eternal console",
                    color = MutedDim, fontSize = 9.sp, letterSpacing = 1.sp,
                )
                if (botName.isNotBlank()) {
                    Text("  ·  ", color = MutedDim, fontSize = 9.sp)
                    Text(
                        botName, color = BrandBright, fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
        StatusPill(running, live)
    }
    if (error != null) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(Danger.copy(alpha = 0.10f))
                .padding(horizontal = 10.dp, vertical = 7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Rounded.WarningAmber, contentDescription = null,
                tint = Danger, modifier = Modifier.size(13.dp),
            )
            Spacer(Modifier.width(7.dp))
            Text(
                error, color = Danger, fontSize = 10.sp,
                fontFamily = FontFamily.Monospace, maxLines = 2,
            )
        }
    }
}

@Composable
private fun PairScreen(pairing: Boolean, error: String?, onPair: (String) -> Unit) {
    var code by remember { mutableStateOf("") }

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
        Spacer(Modifier.height(32.dp))

        Text("PAIR THIS PHONE", color = Muted, fontSize = 10.sp, letterSpacing = 1.2.sp)
        Spacer(Modifier.height(10.dp))
        Text(
            "In Discord, run +pair to get a code. Then type it here.",
            color = Color.White, fontSize = 13.sp, lineHeight = 19.sp,
        )
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = code,
            onValueChange = { raw ->
                // Accept a pasted code with spaces or dashes; the server
                // normalises too, this just keeps the field tidy.
                code = raw.filter { it.isLetterOrDigit() }.uppercase().take(6)
            },
            singleLine = true,
            isError = error != null,
            placeholder = { Text("ABC123", color = Muted, fontSize = 18.sp) },
            textStyle = androidx.compose.ui.text.TextStyle(
                color = Color.White,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 6.sp,
                fontFamily = FontFamily.Monospace,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            ),
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Brand, unfocusedBorderColor = PanelAlt,
                focusedTextColor = Color.White, unfocusedTextColor = Color.White,
            ),
        )

        if (error != null) {
            Spacer(Modifier.height(8.dp))
            Text(error, color = Danger, fontSize = 11.sp, lineHeight = 16.sp)
        }

        Spacer(Modifier.height(18.dp))
        Button(
            onClick = { onPair(code) },
            enabled = code.length == 6 && !pairing,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Brand),
        ) {
            Text(
                if (pairing) "Pairing..." else "Pair",
                color = Color.White, fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.height(14.dp))
        Text(
            "This phone gets its own access token. Nothing else needs typing, " +
                "and you can cut it off later with +revoke in Discord.",
            color = Muted, fontSize = 10.sp, lineHeight = 15.sp,
        )
    }
}
