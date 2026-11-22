package com.freehands.console.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import coil.compose.AsyncImage
import com.freehands.console.data.LoopInfo
import com.freehands.console.data.Person

/**
 * Loop ban / loop kick.
 *
 * The flow is: pick a person from the dropdown, then the action opens a
 * full-height sheet with the fields a loop needs. The sheet shows who was
 * picked, why they cannot be picked, and what the loop will do, so arming one
 * is a decision rather than a tap.
 */
@Composable
fun LoopsTab(
    people: List<Person>,
    loops: List<LoopInfo>,
    notice: String?,
    onRefresh: () -> Unit,
    onArm: (kind: String, target: String, passes: Int, interval: Int,
             reason: String, notify: Boolean) -> Unit,
    onStop: (String) -> Unit,
    onDismissNotice: () -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Person?>(null) }
    var sheetFor by remember { mutableStateOf<String?>(null) }

    Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp)) {
        SectionTitle("Loop ban / kick", "${loops.count { it.running }} running")

        if (notice != null) {
            NoticeCard(notice, onDismissNotice)
            Spacer(Modifier.height(10.dp))
        }

        // -- the picker ----------------------------------------------------
        SurfaceCard {
            Column(Modifier.padding(14.dp)) {
                Text(
                    "Who is it aimed at?",
                    color = Color.White,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    "Only people who can already reach Freehands are listed, " +
                        "labelled by the power they hold.",
                    color = Muted,
                    fontSize = 11.sp,
                )
                Spacer(Modifier.height(10.dp))

                PickerRow(
                    person = selected,
                    expanded = expanded,
                    onToggle = {
                        expanded = !expanded
                        if (expanded && people.isEmpty()) onRefresh()
                    },
                )

                AnimatedVisibility(
                    visible = expanded,
                    enter = expandVertically(tween(180)) + fadeIn(tween(150)),
                    exit = shrinkVertically(tween(150)) + fadeOut(tween(120)),
                ) {
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .heightIn(max = 300.dp)
                            .padding(top = 8.dp)
                            .verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        if (people.isEmpty()) {
                            Text(
                                "No one loaded. Pull to refresh.",
                                color = MutedDim,
                                fontSize = 12.sp,
                                modifier = Modifier.padding(10.dp),
                            )
                        }
                        people.forEach { person ->
                            PersonRow(
                                person = person,
                                chosen = person.id == selected?.id,
                                onPick = {
                                    selected = person
                                    expanded = false
                                },
                            )
                        }
                    }
                }

                // -- the two actions --------------------------------------
                Spacer(Modifier.height(12.dp))
                val ready = selected != null && selected?.protected != true
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LoopButton(
                        label = "Loop ban",
                        tint = Danger,
                        enabled = ready,
                        modifier = Modifier.weight(1f),
                    ) { sheetFor = "ban" }
                    LoopButton(
                        label = "Loop kick",
                        tint = Warn,
                        enabled = ready,
                        modifier = Modifier.weight(1f),
                    ) { sheetFor = "kick" }
                }
                if (selected?.protected == true) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "${selected?.display} owns Freehands, so no loop can target them.",
                        color = Danger,
                        fontSize = 11.sp,
                    )
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        SectionTitle("Armed", if (loops.isEmpty()) "none" else "${loops.size} total")

        if (loops.isEmpty()) {
            EmptyState(
                "Nothing is looping",
                "A loop bans or kicks the same person on a timer until it runs " +
                    "out of passes.",
            )
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                loops.forEach { loop ->
                    LoopRow(loop, onStop = { onStop(loop.id) })
                }
            }
        }
        Spacer(Modifier.height(20.dp))
    }

    val person = selected
    val kind = sheetFor
    if (person != null && kind != null) {
        LoopSheet(
            person = person,
            kind = kind,
            onDismiss = { sheetFor = null },
            onArm = { passes, interval, reason, notify ->
                onArm(kind, person.id, passes, interval, reason, notify)
                sheetFor = null
            },
        )
    }
}

/** The collapsed picker: avatar, name, tier. */
@Composable
private fun PickerRow(person: Person?, expanded: Boolean, onToggle: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    val arrow by animateFloatAsState(if (expanded) 180f else 0f, tween(180), label = "arrow")
    Row(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Panel)
            .border(1.dp, if (expanded) Brand.copy(alpha = 0.5f) else Hairline, shape)
            .clickable(onClick = onToggle)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (person == null) {
            Box(
                Modifier.size(32.dp).clip(CircleShape).background(PanelAlt),
                contentAlignment = Alignment.Center,
            ) {
                Text("?", color = MutedDim, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(10.dp))
            Text("Choose a person", color = Muted, fontSize = 13.sp, modifier = Modifier.weight(1f))
        } else {
            Avatar(person.avatar, 32)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    person.display,
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(person.label, color = Muted, fontSize = 10.sp, maxLines = 1)
            }
        }
        Text(
            "\u25BC",
            color = Muted,
            fontSize = 10.sp,
            modifier = Modifier.rotate(arrow),
        )
    }
}

/** One row in the open dropdown. Protected people are visibly refused. */
@Composable
private fun PersonRow(person: Person, chosen: Boolean, onPick: () -> Unit) {
    val shape = RoundedCornerShape(10.dp)
    val tint = if (person.protected) Danger else tierColor(person.tier)
    Row(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(if (chosen) Brand.copy(alpha = 0.14f) else Color.Transparent)
            .border(1.dp, if (chosen) Brand.copy(alpha = 0.4f) else Hairline, shape)
            .clickable(enabled = !person.protected, onClick = onPick)
            .padding(horizontal = 8.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(person.avatar, 28)
        Spacer(Modifier.width(9.dp))
        Column(Modifier.weight(1f)) {
            Text(
                person.display,
                color = if (person.protected) Muted else Color.White,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                if (person.protected) "${person.label} — protected" else person.label,
                color = tint,
                fontSize = 9.sp,
                maxLines = 1,
            )
        }
        if (person.protected) {
            Text("locked", color = Danger, fontSize = 9.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun Avatar(url: String, size: Int) {
    if (url.isBlank()) {
        Box(
            Modifier.size(size.dp).clip(CircleShape).background(PanelAlt),
            contentAlignment = Alignment.Center,
        ) {
            Text("\u25CF", color = MutedDim, fontSize = (size / 3).sp)
        }
        return
    }
    AsyncImage(
        model = url,
        contentDescription = null,
        modifier = Modifier.size(size.dp).clip(CircleShape).background(PanelAlt),
    )
}

@Composable
private fun LoopButton(
    label: String,
    tint: Color,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(11.dp)
    Box(
        modifier
            .height(42.dp)
            .clip(shape)
            .background(
                if (enabled) Brush.horizontalGradient(listOf(tint.copy(alpha = 0.9f), tint))
                else Brush.horizontalGradient(listOf(PanelAlt, PanelAlt))
            )
            .border(1.dp, if (enabled) tint.copy(alpha = 0.7f) else Hairline, shape)
            .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (enabled) Color.White else MutedDim,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** A running or finished loop, with the numbers that matter. */
@Composable
private fun LoopRow(loop: LoopInfo, onStop: () -> Unit) {
    SurfaceCard(accent = if (loop.running) (if (loop.kind == "ban") Danger else Warn) else null) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Pill(
                    loop.kind.uppercase(),
                    if (loop.kind == "ban") Danger else Warn,
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    loop.id,
                    color = Color.White,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.weight(1f))
                if (loop.running) {
                    Text(
                        "${loop.fired}/${loop.passes}",
                        color = Color.White,
                        fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                } else {
                    Pill(loop.stopped.ifBlank { "finished" }, Muted)
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "target ${loop.target} · every ${loop.interval.toInt()}s · ${loop.reason}",
                color = Muted,
                fontSize = 10.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (loop.lastError.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(loop.lastError, color = Danger, fontSize = 10.sp, maxLines = 2)
            }
            if (loop.running) {
                Spacer(Modifier.height(8.dp))
                Text(
                    "STOP",
                    color = Danger,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .background(Danger.copy(alpha = 0.12f))
                        .clickable(onClick = onStop)
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun NoticeCard(text: String, onDismiss: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Brand.copy(alpha = 0.12f))
            .border(1.dp, Brand.copy(alpha = 0.3f), shape)
            .clickable(onClick = onDismiss)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, color = Color.White, fontSize = 11.sp, modifier = Modifier.weight(1f))
        Text("\u00D7", color = Muted, fontSize = 16.sp)
    }
}

fun tierColor(tier: String): Color = when (tier) {
    "owner" -> Danger
    "co-owner" -> Violet
    "admin" -> Warn
    "mod" -> BrandBright
    "helper" -> Good
    else -> Muted
}

/**
 * The arming sheet.
 *
 * Sized to its content and scrollable, so it works on a small phone and a
 * tablet without a second layout. Everything that decides how destructive the
 * loop is sits above the confirm button, and the confirm button repeats the
 * numbers back.
 */
@Composable
private fun LoopSheet(
    person: Person,
    kind: String,
    onDismiss: () -> Unit,
    onArm: (passes: Int, interval: Int, reason: String, notify: Boolean) -> Unit,
) {
    var passes by remember { mutableStateOf(5) }
    var interval by remember { mutableStateOf(60) }
    var reason by remember { mutableStateOf("") }
    var notify by remember { mutableStateOf(false) }

    Dialog(onDismissRequest = onDismiss) {
        val shape = RoundedCornerShape(22.dp)
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = 620.dp)
                .clip(shape)
                .background(
                    Brush.verticalGradient(listOf(PanelAlt, Panel))
                )
                .border(1.dp, Hairline, shape)
                .verticalScroll(rememberScrollState())
                .padding(18.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(person.avatar, 44)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        person.display,
                        color = Color.White,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(person.label, color = tierColor(person.tier), fontSize = 11.sp)
                }
            }

            Spacer(Modifier.height(14.dp))
            Pill("LOOP ${kind.uppercase()}", if (kind == "ban") Danger else Warn)
            Spacer(Modifier.height(10.dp))
            Text(
                if (kind == "ban")
                    "This person will be banned, and banned again on every pass."
                else
                    "This person will be kicked, and kicked again on every pass.",
                color = Muted,
                fontSize = 11.sp,
            )

            Spacer(Modifier.height(16.dp))
            Stepper(
                label = "Passes",
                value = passes,
                hint = "how many times it fires",
                onChange = { passes = it.coerceIn(1, 500) },
                step = 1,
                min = 1,
                max = 500,
            )
            Spacer(Modifier.height(10.dp))
            Stepper(
                label = "Every",
                value = interval,
                hint = "seconds between passes (min 5)",
                onChange = { interval = it.coerceIn(5, 21600) },
                step = 5,
                min = 5,
                max = 21600,
                suffix = "s",
            )

            Spacer(Modifier.height(14.dp))
            Text("Reason", color = Muted, fontSize = 10.sp)
            Spacer(Modifier.height(4.dp))
            androidx.compose.material3.OutlinedTextField(
                value = reason,
                onValueChange = { reason = it.take(120) },
                placeholder = { Text("what they did", color = MutedDim, fontSize = 12.sp) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(10.dp),
            )

            Spacer(Modifier.height(12.dp))
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Warn them first", color = Color.White, fontSize = 12.sp)
                    Text(
                        "Sends one DM before the first pass.",
                        color = Muted,
                        fontSize = 10.sp,
                    )
                }
                Switch(
                    checked = notify,
                    onCheckedChange = { notify = it },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = Color.White,
                        checkedTrackColor = Brand,
                    ),
                )
            }

            Spacer(Modifier.height(18.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(46.dp)
                    .clip(RoundedCornerShape(13.dp))
                    .background(
                        Brush.horizontalGradient(
                            listOf(
                                (if (kind == "ban") Danger else Warn).copy(alpha = 0.92f),
                                if (kind == "ban") Danger else Warn,
                            )
                        )
                    )
                    .clickable {
                        onArm(passes, interval, reason.ifBlank { "loop" }, notify)
                    },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "$kind ${person.display} $passes\u00D7 every ${interval}s",
                    color = Color.White,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 10.dp),
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(
                "Ends by itself after $passes passes. Stop it any time from Armed.",
                color = MutedDim,
                fontSize = 9.sp,
            )
        }
    }
}

/** A number with minus and plus, and a value that can be typed over. */
@Composable
private fun Stepper(
    label: String,
    value: Int,
    hint: String,
    onChange: (Int) -> Unit,
    step: Int,
    min: Int,
    max: Int,
    suffix: String = "",
) {
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, color = Muted, fontSize = 10.sp, modifier = Modifier.weight(1f))
            Text(hint, color = MutedDim, fontSize = 9.sp)
        }
        Spacer(Modifier.height(5.dp))
        Row(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(11.dp))
                .background(Panel)
                .border(1.dp, Hairline, RoundedCornerShape(11.dp)),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            StepKey("\u2212") { onChange((value - step).coerceAtLeast(min)) }
            Text(
                "$value$suffix",
                color = Color.White,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.weight(1f),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
            StepKey("+") { onChange((value + step).coerceAtMost(max)) }
        }
    }
}

@Composable
private fun StepKey(glyph: String, onClick: () -> Unit) {
    Box(
        Modifier
            .size(42.dp)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, color = BrandBright, fontSize = 17.sp, fontWeight = FontWeight.Bold)
    }
}
