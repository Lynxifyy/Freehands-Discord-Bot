package com.freehands.console.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
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
import androidx.compose.ui.window.Dialog
import com.freehands.console.data.CommandInfo

@Composable
fun CommandsTab(commands: List<CommandInfo>) {
    var open by remember { mutableStateOf<CommandInfo?>(null) }
    val grouped = commands.groupBy { it.tier }

    Column(Modifier.fillMaxSize().padding(horizontal = 14.dp)) {
        SectionTitle("Commands", "${commands.size} total")
        if (commands.isEmpty()) {
            EmptyState("No commands loaded", "Start the bot so the app can read its command list.")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("owner", "mod", "user").forEach { tier ->
                    val list = grouped[tier] ?: return@forEach
                    item(key = "h-$tier") {
                        Row(
                            Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(
                                Modifier
                                    .width(3.dp).height(12.dp)
                                    .clip(RoundedCornerShape(2.dp))
                                    .background(
                                        when (tier) {
                                            "owner" -> Danger
                                            "mod" -> Warn
                                            else -> Brand
                                        }
                                    )
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                when (tier) {
                                    "owner" -> "Owner only"
                                    "mod" -> "Moderators"
                                    else -> "Everyone"
                                },
                                color = Color(0xFFB9C4D2), fontSize = 10.sp,
                                fontWeight = FontWeight.Bold, letterSpacing = 1.4.sp,
                            )
                            Spacer(Modifier.weight(1f))
                            Text(
                                "${list.size}", color = MutedDim, fontSize = 10.sp,
                                fontFamily = FontFamily.Monospace,
                            )
                        }
                    }
                    items(list, key = { it.name }) { cmd ->
                        CommandRow(cmd) { open = cmd }
                    }
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }

    open?.let { CommandDetailDialog(it) { open = null } }
}

@Composable
private fun CommandRow(cmd: CommandInfo, onClick: () -> Unit) {
    val accent = when (cmd.tier) {
        "owner" -> Danger
        "mod" -> Warn
        else -> Brand
    }
    SurfaceCard(Modifier.clickable { onClick() }, accent = accent) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    cmd.usage.ifBlank { "+${cmd.name}" },
                    color = Color.White, fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    cmd.summary, color = Muted, fontSize = 11.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.width(8.dp))
            Text("\u203A", color = accent.copy(alpha = 0.7f), fontSize = 18.sp)
        }
    }
}

@Composable
private fun CommandDetailDialog(cmd: CommandInfo, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Panel),
        ) {
            Column(Modifier.padding(20.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        cmd.usage.ifBlank { "+${cmd.name}" },
                        color = Color.White, fontSize = 15.sp,
                        fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, "close", tint = Muted)
                    }
                }
                TierChip(cmd.tier)
                Spacer(Modifier.height(14.dp))
                Text(
                    cmd.detail.ifBlank { cmd.summary },
                    color = Color(0xFFDCE3EC), fontSize = 13.sp, lineHeight = 20.sp,
                )
                if (cmd.aliases.isNotEmpty()) {
                    Spacer(Modifier.height(14.dp))
                    Text(
                        "Also written as " + cmd.aliases.joinToString(", ") { "+$it" },
                        color = Muted, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
    }
}

@Composable
private fun TierChip(tier: String) {
    val color = when (tier) {
        "owner" -> Danger
        "mod" -> Color(0xFFE0A33E)
        else -> Good
    }
    Row(Modifier.padding(top = 8.dp)) {
        Card(
            shape = RoundedCornerShape(6.dp),
            colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.16f)),
        ) {
            Text(
                when (tier) {
                    "owner" -> "OWNER ONLY"
                    "mod" -> "MODERATORS"
                    else -> "EVERYONE"
                },
                color = color, fontSize = 9.sp, fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            )
        }
        Spacer(Modifier.width(6.dp))
        Card(
            shape = RoundedCornerShape(6.dp),
            colors = CardDefaults.cardColors(containerColor = PanelAlt),
        ) {
            Text(
                "prefix +", color = Muted, fontSize = 9.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            )
        }
    }
}
