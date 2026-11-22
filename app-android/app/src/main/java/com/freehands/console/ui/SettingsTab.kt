package com.freehands.console.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.freehands.console.data.Creator
import com.freehands.console.data.Power

private data class Toggle(
    val key: String,
    val label: String,
    val help: String,
)

private val TOGGLES = listOf(
    Toggle("moderation_enabled", "Moderation", "Master switch for strikes, mutes and automod"),
    Toggle("automod", "Auto moderation", "Delete spam, invites, slurs and mass mentions"),
    Toggle("codes_enabled", "Code sense", "Let codes such as code 8 raise an alert"),
    Toggle("watch_enabled", "Watch feature", "Allow the flagged-member watch to run"),
    Toggle("watch_armed", "Watch armed", "Copy every watched message to the ops channel"),
    Toggle("anti_ban", "Ban protection", "Hold bans for approval instead of banning at once"),
    Toggle("lockdown", "Lockdown", "Block ordinary members from every channel"),
    Toggle("presence_enabled", "Presence tracking", "Needs the privileged presence intent"),
)

private val DROPDOWNS = listOf(
    Triple("spam_limit", "Spam threshold", listOf("3", "4", "5", "6", "8", "10")),
    Triple("punish_strikes_to_lock", "Strikes to lockdown", listOf("1", "2", "3", "4", "5")),
    Triple("raid_joins", "Raid joins", listOf("4", "6", "8", "10", "12")),
    Triple("raid_window", "Raid window (s)", listOf("10", "20", "30", "60")),
)

@Composable
fun SettingsTab(
    settings: Map<String, Any>,
    creator: Creator?,
    busy: Boolean,
    onToggle: (String, Boolean) -> Unit,
    onSelect: (String, Any) -> Unit,
    onForceRestart: () -> Unit,
    powers: List<Power>? = null,
    powerNotice: String? = null,
    onOpenPowers: () -> Unit = {},
    onSetPower: (String, Boolean, String) -> Unit = { _, _, _ -> },
) {
    var confirmRestart by remember { mutableStateOf(false) }
    var powersOpen by remember { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 14.dp),
    ) {
        SectionTitle("Owner")
        SurfaceCard(accent = Danger) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable {
                        powersOpen = true
                        onOpenPowers()
                    }
                    .padding(horizontal = 16.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    Modifier
                        .size(34.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(Danger.copy(alpha = 0.16f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("\u26A1", fontSize = 15.sp)
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        "Owner Powers",
                        color = Color.White,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        "16 switches. Lynx only.",
                        color = Muted,
                        fontSize = 10.sp,
                    )
                }
                Text("\u203A", color = Muted, fontSize = 18.sp)
            }
        }

        Spacer(Modifier.height(16.dp))
        SectionTitle("Bot features")

        SurfaceCard {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                TOGGLES.forEachIndexed { i, t ->
                    val value = asBool(settings[t.key])
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 9.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                t.label, color = Color.White, fontSize = 13.sp,
                                fontWeight = FontWeight.Medium,
                            )
                            Text(t.help, color = Muted, fontSize = 10.sp)
                        }
                        Switch(
                            checked = value,
                            onCheckedChange = { onToggle(t.key, it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = Brand,
                            ),
                        )
                    }
                    if (i != TOGGLES.lastIndex) {
                        Spacer(
                            Modifier
                                .fillMaxWidth()
                                .height(1.dp)
                                .background(PanelAlt),
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        SectionTitle("Tuning")

        SurfaceCard {
            Column(Modifier.padding(16.dp)) {
                DROPDOWNS.forEach { (key, label, options) ->
                    DropdownRow(
                        label = label,
                        current = asInt(settings[key]).toString(),
                        options = options,
                    ) { picked ->
                        onSelect(key, picked.toIntOrNull() ?: 0)
                    }
                    Spacer(Modifier.height(12.dp))
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        SectionTitle("Process")

        SurfaceCard(accent = Danger) {
            Column(Modifier.padding(16.dp)) {
                Text(
                    "Force restart", color = Color.White, fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "Drops the gateway connection and brings the bot back up. " +
                        "Settings are kept.",
                    color = Muted, fontSize = 10.sp, lineHeight = 15.sp,
                )
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = { confirmRestart = true },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth().height(44.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Danger),
                ) {
                    Text(
                        if (busy) "Restarting..." else "Restart now",
                        color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp,
                    )
                }
            }
        }

        Spacer(Modifier.height(22.dp))
        CreatorCard(creator)
        Spacer(Modifier.height(24.dp))
    }

    if (confirmRestart) {
        AlertDialog(
            onDismissRequest = { confirmRestart = false },
            containerColor = Panel,
            title = { Text("Force restart?", color = Color.White) },
            text = {
                Text(
                    "The bot will drop its gateway connection and come back up. " +
                        "Commands sent in the next few seconds may be missed.",
                    color = Muted,
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmRestart = false
                    onForceRestart()
                }) { Text("Restart", color = Danger, fontWeight = FontWeight.Bold) }
            },
            dismissButton = {
                TextButton(onClick = { confirmRestart = false }) {
                    Text("Cancel", color = Muted)
                }
            },
        )
    }

    if (powersOpen) {
        OwnerPowersDialog(
            powers = powers,
            notice = powerNotice,
            onLoad = onOpenPowers,
            onSet = { key, on, confirm -> onSetPower(key, on, confirm) },
            onDismiss = { powersOpen = false },
        )
    }
}

@Composable
private fun DropdownRow(
    label: String,
    current: String,
    options: List<String>,
    onPick: (String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
        androidx.compose.foundation.layout.Box {
            Card(
                shape = RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = PanelAlt),
                modifier = Modifier.clickable { open = true },
            ) {
                Row(
                    Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        current, color = Color.White, fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                    Spacer(Modifier.width(6.dp))
                    Text("▾", color = Muted, fontSize = 10.sp)
                }
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { opt ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                opt,
                                color = if (opt == current) Brand else Color.White,
                                fontFamily = FontFamily.Monospace, fontSize = 12.sp,
                            )
                        },
                        onClick = {
                            open = false
                            onPick(opt)
                        },
                    )
                }
            }
        }
    }
}

private fun asBool(v: Any?): Boolean = when (v) {
    is Boolean -> v
    is Number -> v.toInt() != 0
    is String -> v.equals("true", ignoreCase = true)
    else -> false
}

private fun asInt(v: Any?): Int = when (v) {
    is Number -> v.toInt()
    is String -> v.toIntOrNull() ?: 0
    else -> 0
}