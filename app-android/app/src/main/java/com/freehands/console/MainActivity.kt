package com.freehands.console

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
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
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.Loop
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
import com.freehands.console.ui.LoopsTab
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
import com.freehands.console.ui.AccountScreen
import com.freehands.console.ui.WebMenu

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
        goFullScreen()
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

    /**
     * Hides the status and navigation bars, and keeps them hidden.
     *
     * `enableEdgeToEdge` only lets the app draw *behind* the bars; it does not
     * remove them, which is why the app still showed system buttons. Swiping
     * also brings them back temporarily, so the hide is repeated on every
     * window-focus gain — without that, leaving the app and coming back leaves
     * the bars on screen for good.
     */
    private fun goFullScreen() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        // Keeps the screen awake while the console is open: the log is meant to
        // be watched, and a screen that sleeps mid-command looks like a freeze.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) goFullScreen()
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

    // The in-app browser exists only to finish pairing, which has to happen
    // inside the bot's own page. The account page used to reuse it and pointed
    // at `/authorize`, which shows nothing on an already-paired device.
    var web by rememberSaveable { mutableStateOf<String?>(null) }
    var accountOpen by rememberSaveable { mutableStateOf(false) }

    if (!state.configured) {
        if (web != null) {
            WebMenu(
                url = web!!,
                title = "Authorize this phone",
                onClose = { web = null; vm.cancelPairing() },
                onPaired = { token, who ->
                    web = null
                    vm.adoptPairing(token, who)
                },
            )
            return
        }
        PairScreen(
            pairing = state.pairing,
            error = state.pairError,
            onConnect = { web = vm.authorizeUrl() },
        )
        return
    }

    if (accountOpen) {
        AccountScreen(
            account = state.account,
            botName = state.botName,
            onClose = { accountOpen = false },
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
                        Triple("Loops", Icons.Rounded.Loop, 2),
                        Triple("Settings", Icons.Rounded.Tune, 3),
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
                        2 -> LoopsTab(
                            people = state.people,
                            loops = state.loops,
                            notice = state.notice,
                            onRefresh = vm::loadLoops,
                            onArm = { kind, target, passes, interval, reason, notify ->
                                vm.armLoop(kind, target, passes, interval, reason, notify)
                            },
                            onStop = vm::stopLoop,
                            onDismissNotice = vm::clearNotice,
                        )
                        else -> SettingsTab(
                            settings = state.settings,
                            creator = state.creator,
                            busy = state.busy,
                            onToggle = { k, v -> vm.setSetting(k, v) },
                            onSelect = { k, v -> vm.setSetting(k, v) },
                            onForceRestart = vm::forceRestart,
                            powers = state.powers,
                            powerNotice = state.notice,
                            onOpenPowers = vm::loadPowers,
                            onSetPower = { k, on, c -> vm.setPower(k, on, c) },
                            identity = state.identity,
                            onOpenAccount = { accountOpen = true },
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
private fun PairScreen(
    pairing: Boolean,
    error: String?,
    onConnect: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp)
            .statusBarsPadding(),
        verticalArrangement = Arrangement.Center,
    ) {
        BrandMark(size = 44)
        Spacer(Modifier.height(18.dp))
        Text(
            "FREEHANDS", color = Color.White, fontSize = 26.sp,
            fontWeight = FontWeight.Bold, letterSpacing = 3.sp,
        )
        Text("Operator console", color = Muted, fontSize = 12.sp)
        Spacer(Modifier.height(32.dp))

        Text("CONNECT THIS PHONE", color = Muted, fontSize = 10.sp, letterSpacing = 1.2.sp)
        Spacer(Modifier.height(10.dp))
        Text(
            "The console acts as your Discord account, so the bot has to see " +
                "the approval come from you. Press Connect and the code appears " +
                "on the next screen.",
            color = Color.White, fontSize = 13.sp, lineHeight = 19.sp,
        )

        if (error != null) {
            Spacer(Modifier.height(10.dp))
            Text(error, color = Danger, fontSize = 11.sp, lineHeight = 16.sp)
        }

        Spacer(Modifier.height(18.dp))
        Button(
            onClick = onConnect,
            enabled = !pairing,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Brand),
        ) {
            Text(
                if (pairing) "Opening..." else "Connect to Discord",
                color = Color.White, fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.height(14.dp))
        Text(
            "Approval happens inside Discord, where the bot already knows who " +
                "you are. This phone gets its own token, and +revoke cuts it off.",
            color = Muted, fontSize = 10.sp, lineHeight = 15.sp,
        )
    }
}
