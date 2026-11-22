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
import coil.ImageLoader
import coil.compose.AsyncImage
import coil.decode.GifDecoder
import coil.decode.ImageDecoderDecoder
import coil.request.ImageRequest
import androidx.compose.ui.platform.LocalContext
import android.os.Build
import com.freehands.console.data.LogRow
import com.freehands.console.data.SelfTest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val clock = SimpleDateFormat("HH:mm:ss", Locale.US)

@Composable
private fun TestCard(result: SelfTest, onDismiss: () -> Unit) {
    Card(
        Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = PanelAlt),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (result.ok) "Self-test passed" else "${result.passed}/${result.total} passed",
                    color = if (result.ok) Good else Danger,
                    fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onDismiss) {
                    Text("close", color = Muted, fontSize = 11.sp)
                }
            }
            result.checks.forEach { c ->
                Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                    Text(
                        if (c.ok) "OK" else "FAIL",
                        color = if (c.ok) Good else Danger,
                        fontSize = 10.sp, fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.width(38.dp),
                    )
                    Text(c.name, color = Color.White, fontSize = 11.sp,
                        modifier = Modifier.width(78.dp))
                    Text(c.detail, color = Muted, fontSize = 10.sp,
                        modifier = Modifier.weight(1f), maxLines = 2,
                        overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

/**
 * One loader for the whole feed, with animated-image support.
 *
 * Coil only animates GIF/WebP when a decoder is registered. Building the loader
 * once (not per row) also keeps the bitmap cache shared across the list.
 */
@Composable
private fun rememberImageLoader(): ImageLoader {
    val context = LocalContext.current
    return remember(context) {
        ImageLoader.Builder(context)
            .components {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    add(ImageDecoderDecoder.Factory())
                } else {
                    add(GifDecoder.Factory())
                }
            }
            .build()
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

        // -- start / stop ---------------------------------------------------
        Card(
            Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Panel),
        ) {
            Row(
                Modifier.fillMaxWidth().padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        if (running) "Bot is running" else "Bot is stopped",
                        color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        if (running) "${counts["message"] ?: 0} messages  " +
                            "${counts["delete"] ?: 0} deletes" else "Tap start to bring it online",
                        color = Muted, fontSize = 11.sp,
                    )
                }
                StatusPill(running, live)
                Spacer(Modifier.width(10.dp))
                Button(
                    onClick = onTogglePower,
                    enabled = !busy,
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (running) Danger else Good,
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
                Spacer(Modifier.width(8.dp))
                OutlinedButton(
                    onClick = onTest,
                    enabled = running && !testing,
                    shape = RoundedCornerShape(12.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                ) {
                    if (testing) {
                        CircularProgressIndicator(
                            Modifier.size(14.dp), color = Brand, strokeWidth = 2.dp,
                        )
                    } else {
                        Text("Test", color = Brand, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        test?.let { result ->
            Spacer(Modifier.height(12.dp))
            TestCard(result, onDismissTest)
        }

        Spacer(Modifier.height(14.dp))
        SectionTitle("Live activity", "${rows.size} events")

        if (rows.isEmpty()) {
            EmptyState(
                if (running) "Nothing yet" else "Bot offline",
                if (running) "Messages, deletes and media will appear here."
                else "Start the bot to begin watching the server.",
            )
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                items(rows.reversed()) { row ->
                    RowCard(row) { url -> uri.openUri(url) }
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }
}

@Composable
private fun RowCard(row: LogRow, onOpen: (String) -> Unit) {
    val accent = when (row.type) {
        "delete" -> Danger
        "edit" -> Color(0xFFE0A33E)
        "presence" -> Color(0xFF9B8CFF)
        else -> Brand
    }
    Card(
        Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
    ) {
        Row(Modifier.fillMaxWidth()) {
            Box(Modifier.width(3.dp).height(72.dp).background(accent))
            Column(Modifier.padding(11.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        row.authorName.ifBlank { "unknown" },
                        color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(Modifier.width(7.dp))
                    Text(
                        when (row.type) {
                            "delete" -> "deleted a message"
                            "edit" -> "edited"
                            "presence" -> "came online"
                            else -> "said"
                        },
                        color = accent, fontSize = 10.sp, fontWeight = FontWeight.Medium,
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        clock.format(Date(row.at * 1000)),
                        color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace,
                    )
                }

                if (row.text.isNotBlank()) {
                    Spacer(Modifier.height(5.dp))
                    Text(
                        row.text, color = Color(0xFFDCE3EC), fontSize = 13.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                if (row.before.isNotBlank() && row.before != row.text) {
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "was: ${row.before}", color = Muted, fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }

                if (row.platforms.isNotEmpty()) {
                    Spacer(Modifier.height(5.dp))
                    Text(
                        "online from ${row.platforms.joinToString(", ")}",
                        color = Color(0xFF9B8CFF), fontSize = 10.sp,
                    )
                }

                row.media.forEach { m ->
                    Spacer(Modifier.height(6.dp))
                    MediaChip(m.kind, m.url, m.name) { onOpen(m.url) }
                }
            }
        }
    }
}

@Composable
private fun MediaChip(kind: String, url: String, name: String, onOpen: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(9.dp))
            .background(PanelAlt)
            .clickable { onOpen() }
            .padding(7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Everything Discord sends as a picture, including custom emoji.
        // Stickers and emoji are small, so they get a smaller tile than a photo.
        if (kind in setOf("image", "gif", "sticker", "emoji")) {
            val side = if (kind == "emoji") 30.dp else 44.dp
            AsyncImage(
                model = ImageRequest.Builder(LocalContext.current).data(url).build(),
                imageLoader = rememberImageLoader(),
                contentDescription = kind,
                modifier = Modifier.size(side).clip(RoundedCornerShape(7.dp)),
            )
            Spacer(Modifier.width(9.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(
                "${kind.uppercase()}${if (name.isNotBlank()) "  $name" else ""}",
                color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Medium,
                maxLines = 1,
            )
            Text(
                url, color = Muted, fontSize = 9.sp, fontFamily = FontFamily.Monospace,
                maxLines = 1,
            )
        }
        Text("open", color = Brand, fontSize = 10.sp, fontWeight = FontWeight.Bold)
    }
}
