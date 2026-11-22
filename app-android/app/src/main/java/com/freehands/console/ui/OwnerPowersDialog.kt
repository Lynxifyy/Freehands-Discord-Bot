package com.freehands.console.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
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
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.freehands.console.data.Power

// The panel is light on a dark app on purpose: it is the one screen that is
// about the owner rather than the server, and the contrast makes it read as a
// separate, deliberate place.
private val SheetLight = Color(0xFFEFF1F5)
private val SheetLightAlt = Color(0xFFE2E6ED)
private val SheetInk = Color(0xFF15181F)
private val SheetMuted = Color(0xFF5F6775)
private val SheetLine = Color(0xFFCFD5DF)

/**
 * The Owner Powers panel.
 *
 * Only Lynx can open it. The gate is on the server, so this composable only
 * has to be honest about the result: a refused load shows why rather than an
 * empty list.
 *
 * Each power expands in place to show its blurb and its switch, so the panel
 * is a short list of names until you open the one you want. That keeps the
 * destructive ones from being a single stray tap away.
 */
@Composable
fun OwnerPowersDialog(
    powers: List<Power>?,
    notice: String?,
    onLoad: () -> Unit,
    onSet: (key: String, on: Boolean, confirm: String) -> Unit,
    onDismiss: () -> Unit,
) {
    var open by remember { mutableStateOf<String?>(null) }
    var confirmFor by remember { mutableStateOf<Power?>(null) }

    Dialog(onDismissRequest = onDismiss) {
        val shape = RoundedCornerShape(26.dp)
        Column(
            Modifier
                .fillMaxWidth()
                // Auto-sizing: the panel takes the height its content needs,
                // up to the screen. A fixed height would leave a short list
                // floating in empty space.
                .heightIn(min = 120.dp, max = 640.dp)
                .clip(shape)
                .background(Brush.verticalGradient(listOf(SheetLight, SheetLightAlt)))
                .border(1.dp, SheetLine, shape)
                .padding(20.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(34.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(SheetInk),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("\u26A1", fontSize = 15.sp)
                }
                Spacer(Modifier.width(11.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        "Owner Powers",
                        color = SheetInk,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "Lynx only \u00B7 changes take effect at once",
                        color = SheetMuted,
                        fontSize = 10.sp,
                    )
                }
                Text(
                    "\u00D7",
                    color = SheetMuted,
                    fontSize = 20.sp,
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .clickable(onClick = onDismiss)
                        .padding(horizontal = 8.dp, vertical = 2.dp),
                )
            }

            Spacer(Modifier.height(14.dp))

            if (notice != null) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(Color(0xFFFFF3D6))
                        .border(1.dp, Color(0xFFE8CE93), RoundedCornerShape(10.dp))
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                ) {
                    Text(notice, color = Color(0xFF6B4E12), fontSize = 10.sp)
                }
                Spacer(Modifier.height(10.dp))
            }

            when {
                powers == null -> RefusedPanel(onLoad)
                powers.isEmpty() -> Text(
                    "No powers on this server build.",
                    color = SheetMuted,
                    fontSize = 12.sp,
                )
                else -> Column(
                    Modifier
                        .weight(1f, fill = false)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    powers.forEach { power ->
                        PowerRow(
                            power = power,
                            expanded = open == power.key,
                            onToggleOpen = {
                                open = if (open == power.key) null else power.key
                            },
                            onFlip = { want ->
                                if (want && power.confirm) confirmFor = power
                                else onSet(power.key, want, "")
                            },
                        )
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Destructive switches stay on until you turn them off. " +
                            "Two of them ask you to type the name first.",
                        color = SheetMuted,
                        fontSize = 9.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }

    val target = confirmFor
    if (target != null) {
        ConfirmDialog(
            power = target,
            onCancel = { confirmFor = null },
            onConfirm = {
                onSet(target.key, true, target.key)
                confirmFor = null
            },
        )
    }
}

@Composable
private fun RefusedPanel(onLoad: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().padding(vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("\u26BF", fontSize = 26.sp)
        Spacer(Modifier.height(8.dp))
        Text(
            "This panel is for Lynx.",
            color = SheetInk,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            "The server refused the request, so nothing here is reachable " +
                "from this device.",
            color = SheetMuted,
            fontSize = 10.sp,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(12.dp))
        Box(
            Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(SheetInk)
                .clickable(onClick = onLoad)
                .padding(horizontal = 16.dp, vertical = 8.dp),
        ) {
            Text("Try again", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

/**
 * One power: a name and its state, opening to show what it does.
 *
 * The switch is inside the expanded area, not on the row, so a scroll cannot
 * flip a destructive switch by accident.
 */
@Composable
private fun PowerRow(
    power: Power,
    expanded: Boolean,
    onToggleOpen: () -> Unit,
    onFlip: (Boolean) -> Unit,
) {
    val shape = RoundedCornerShape(13.dp)
    val accent = kindColor(power.kind)
    val arrow by animateFloatAsState(
        targetValue = if (expanded) 180f else 0f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
        label = "powerArrow",
    )
    val scale by animateFloatAsState(
        targetValue = if (power.on) 1f else 0.94f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
        label = "powerScale",
    )

    Column(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(if (power.on) accent.copy(alpha = 0.10f) else Color.White.copy(alpha = 0.55f))
            .border(
                1.dp,
                if (power.on) accent.copy(alpha = 0.45f) else SheetLine,
                shape,
            )
            .clickable(onClick = onToggleOpen),
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier
                    .size(7.dp)
                    .scale(scale)
                    .clip(RoundedCornerShape(4.dp))
                    .background(if (power.on) accent else SheetLine),
            )
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    power.name,
                    color = SheetInk,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    kindLabel(power.kind) + if (power.on) " \u00B7 on" else "",
                    color = if (power.on) accent else SheetMuted,
                    fontSize = 9.sp,
                    maxLines = 1,
                )
            }
            Text("\u25BC", color = SheetMuted, fontSize = 9.sp, modifier = Modifier.rotate(arrow))
        }

        AnimatedVisibility(
            visible = expanded,
            enter = expandVertically(tween(190)) + fadeIn(tween(150)),
            exit = shrinkVertically(tween(150)) + fadeOut(tween(120)),
        ) {
            Column(Modifier.padding(start = 12.dp, end = 12.dp, bottom = 12.dp)) {
                Text(power.blurb, color = SheetMuted, fontSize = 10.sp)
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        if (power.on) "Armed" else "Off",
                        color = if (power.on) accent else SheetMuted,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.weight(1f),
                    )
                    if (power.confirm && !power.on) {
                        Text(
                            "needs confirm",
                            color = accent,
                            fontSize = 8.sp,
                            modifier = Modifier.padding(end = 8.dp),
                        )
                    }
                    Switch(
                        checked = power.on,
                        onCheckedChange = onFlip,
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = Color.White,
                            checkedTrackColor = accent,
                            uncheckedThumbColor = Color.White,
                            uncheckedTrackColor = SheetLine,
                        ),
                    )
                }
            }
        }
    }
}

/** The typed confirmation for the two switches that ask for one. */
@Composable
private fun ConfirmDialog(power: Power, onCancel: () -> Unit, onConfirm: () -> Unit) {
    Dialog(onDismissRequest = onCancel) {
        val shape = RoundedCornerShape(20.dp)
        Column(
            Modifier
                .fillMaxWidth()
                .clip(shape)
                .background(Brush.verticalGradient(listOf(SheetLight, SheetLightAlt)))
                .border(1.dp, SheetLine, shape)
                .padding(20.dp),
        ) {
            Text(
                power.name,
                color = SheetInk,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(6.dp))
            Text(power.blurb, color = SheetMuted, fontSize = 11.sp)
            Spacer(Modifier.height(12.dp))
            Text(
                "This one is not reversible with a second tap. Confirm only if " +
                    "you mean it.",
                color = Color(0xFF8A5A00),
                fontSize = 10.sp,
            )
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(40.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(Color.White.copy(alpha = 0.7f))
                        .border(1.dp, SheetLine, RoundedCornerShape(11.dp))
                        .clickable(onClick = onCancel),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Cancel", color = SheetMuted, fontSize = 11.sp)
                }
                Box(
                    Modifier
                        .weight(1f)
                        .height(40.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(kindColor(power.kind))
                        .clickable(onClick = onConfirm),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "Confirm",
                        color = Color.White,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

private fun kindColor(kind: String): Color = when (kind) {
    "destructive" -> Color(0xFFC8323A)
    "disruptive" -> Color(0xFFB4751A)
    else -> Color(0xFF5B4BC4)
}

private fun kindLabel(kind: String): String = when (kind) {
    "destructive" -> "Destructive"
    "disruptive" -> "Disruptive"
    else -> "Troll"
}
