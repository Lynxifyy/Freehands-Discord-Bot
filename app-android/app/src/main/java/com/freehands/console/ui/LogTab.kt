package com.freehands.console.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.TextButton
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.freehands.console.data.LogRow
import com.freehands.console.data.SelfTest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
private fun TestCard(result: SelfTest, onDismiss: () -> Unit) {
    SurfaceCard(accent = if (result.ok) Good else Danger) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Pill(
                    if (result.ok) "PASSED" else "FAILED",
                    if (result.ok) Good else Danger,
                )
                Spacer(Modifier.width(9.dp))
                Text(
                    "${result.passed} of ${result.total} checks",
                    color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onDismiss) {
                    Text("dismiss", color = Muted, fontSize = 11.sp)
                }
            }
            Spacer(Modifier.height(8.dp))
            result.checks.forEach { c ->
                Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
                    Text(
                        if (c.ok) "OK" else "FAIL",
                        color = if (c.ok) Good else Danger,
                        fontSize = 9.sp, fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.width(34.dp),
                    )
                    Text(
                        c.name, color = Color.White, fontSize = 11.sp,
                        modifier = Modifier.width(74.dp),
                    )
                    Text(
                        c.detail, color = Muted, fontSize = 10.sp,
                        modifier = Modifier.weight(1f), maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
fun LogTab(
    rows: List<LogRow>,
    running: Boolean,
    live: Boolean,
    busy: Boolean,
    counts: Map<String, Int>,
    onTogglePower: () -> Unit,
    onTest: () -> Unit = {},
    testing: Boolean = false,
    test: SelfTest? = null,
    onDismissTest: () -> Unit = {},
) {
    val uri = LocalUriHandler.current
    Column(Modifier.fillMaxSize().padding(horizontal = 14.dp)) {

        // -- power ----------------------------------------------------------
        SurfaceCard(accent = if (running) Good else Danger) {
            Column(Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // A live pulse next to the state word: the cheapest way to
                    // make "running" feel like a fact rather than a label.
                    Box(
                        Modifier
                            .size(38.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(
                                (if (running) Good else Danger).copy(alpha = 0.14f)
                            ),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            if (running) "\u25B6" else "\u25A0",
                            color = if (running) Good else Danger, fontSize = 15.sp,
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            if (running) "Bot is online" else "Bot is offline",
                            color = Color.White, fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Spacer(Modifier.height(3.dp))
                        Text(
                            if (running) {
                                "${counts["message"] ?: 0} messages  ·  " +
                                    "${counts["delete"] ?: 0} deletes  ·  " +
                                    "${counts["edit"] ?: 0} edits"
                            } else {
                                "Tap start to bring the console online"
                            },
                            color = Muted, fontSize = 10.sp,
                        )
                    }
                    StatusPill(running, live)
                }
                Spacer(Modifier.height(14.dp))
                Row(Modifier.fillMaxWidth()) {
                    Button(
                        onClick = onTogglePower,
                        enabled = !busy,
                        modifier = Modifier.weight(1f).height(44.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (running) Danger else Brand,
                        ),
                    ) {
                        if (busy) {
                            CircularProgressIndicator(
                                Modifier.size(16.dp), color = Color.White, strokeWidth = 2.dp,
                            )
                        } else {
                            Text(
                                if (running) "Stop" else "Start",
                                color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp,
                            )
                        }
                    }
                    Spacer(Modifier.width(10.dp))
                    OutlinedButton(
                        onClick = onTest,
                        enabled = running && !testing,
                        modifier = Modifier.height(44.dp),
                        shape = RoundedCornerShape(12.dp),
                        border = androidx.compose.foundation.BorderStroke(
                            1.dp, Brand.copy(alpha = 0.55f)
                        ),
                        contentPadding = PaddingValues(horizontal = 18.dp),
                    ) {
                        if (testing) {
                            CircularProgressIndicator(
                                Modifier.size(14.dp), color = BrandBright, strokeWidth = 2.dp,
                            )
                        } else {
                            Text(
                                "Self-test", color = BrandBright, fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
            }
        }

        test?.let { result ->
            Spacer(Modifier.height(12.dp))
            TestCard(result, onDismissTest)
        }

        Spacer(Modifier.height(16.dp))
        SectionTitle("Live activity", "${rows.size} events")

        if (rows.isEmpty()) {
            EmptyState(
                if (running) "Nothing yet" else "Bot offline",
                if (running) "Messages, deletions and attachments will stream in here."
                else "Start the bot to begin watching the server.",
                glyph = "\u25CE",
            )
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                items(rows.reversed(), key = { it.seq }) { row ->
                    SurfaceCard {
                        LogRowCard(row) { url -> uri.openUri(url) }
                    }
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }
}
