package com.freehands.console.ui

import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
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
import com.freehands.console.data.LogRow
import com.freehands.console.data.Media
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val clock = SimpleDateFormat("HH:mm:ss", Locale.US)

/** Colour of the row's spine and its verb. */
private fun accentFor(type: String): Color = when (type) {
    "delete" -> Danger
    "edit" -> Color(0xFFE0A33E)
    "presence" -> Color(0xFF9B8CFF)
    else -> Brand
}

/**
 * One loader for the whole feed, with animated-image support.
 *
 * Coil only animates GIF/WebP when a decoder is registered. Building the loader
 * once (not per row) also keeps the bitmap cache shared across the list.
 */
@Composable
fun rememberImageLoader(): ImageLoader {
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

/** "1.4 MB" — a size a person can judge, not a raw byte count. */
private fun humanSize(bytes: Long): String {
    if (bytes <= 0L) return ""
    val units = listOf("B", "KB", "MB", "GB")
    var value = bytes.toDouble()
    var unit = 0
    while (value >= 1024 && unit < units.lastIndex) {
        value /= 1024
        unit++
    }
    return if (unit == 0) "${bytes} B" else String.format(Locale.US, "%.1f %s", value, units[unit])
}

/** Discord marks animated emoji with an `a:` prefix; the CDN path tells us too. */
private fun Media.isAnimated(): Boolean = kind == "gif" || url.endsWith(".gif", true)

@Composable
fun LogRowCard(row: LogRow, onOpen: (String) -> Unit) {
    val accent = accentFor(row.type)
    // A delete names two people. Showing only the author is what produced
    // "unknown deleted a message", so the headline is built from the actor.
    val headline = when (row.type) {
        "delete" -> when {
            row.actorName.isNotBlank() && row.authorName.isNotBlank() ->
                "${row.actorName} deleted ${row.authorName}'s message"
            row.actorName.isNotBlank() -> "${row.actorName} deleted a message"
            row.authorName.isNotBlank() -> "${row.authorName}'s message was deleted"
            else -> "Message deleted"
        }
        "edit" -> "${row.authorName.ifBlank { "unknown" }} edited a message"
        "presence" -> "${row.authorName.ifBlank { "unknown" }} came online"
        else -> null
    }

    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
        // Spine: a solid accent bar with a soft glow, so the row type is
        // readable from a glance at the edge of the screen.
        Box(
            Modifier
                .width(3.dp)
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(accent, accent.copy(alpha = 0.25f))
                    )
                )
        )
        Column(Modifier.weight(1f).padding(start = 11.dp, top = 10.dp, bottom = 10.dp, end = 4.dp)) {
            if (headline != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        headline,
                        color = accent,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    Spacer(Modifier.width(8.dp))
                    TimeStamp(row.at)
                }
                if (row.text.isNotBlank() || row.media.isNotEmpty()) {
                    Spacer(Modifier.height(7.dp))
                    QuotedBody(row)
                }
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        row.authorName.ifBlank { "unknown" },
                        color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    Spacer(Modifier.width(7.dp))
                    Text("said", color = accent, fontSize = 10.sp)
                    Spacer(Modifier.weight(1f))
                    TimeStamp(row.at)
                }
                if (row.text.isNotBlank()) {
                    Spacer(Modifier.height(5.dp))
                    Text(
                        row.text, color = Color(0xFFDCE3EC), fontSize = 13.sp,
                        lineHeight = 19.sp, fontFamily = FontFamily.Monospace,
                    )
                }
                BodyMedia(row, onOpen)
            }

            if (row.before.isNotBlank() && row.before != row.text) {
                Spacer(Modifier.height(5.dp))
                Text(
                    "was: ${row.before}", color = Muted, fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace, maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (row.platforms.isNotEmpty()) {
                Spacer(Modifier.height(5.dp))
                Text(
                    "online from ${row.platforms.joinToString(", ")}",
                    color = Color(0xFF9B8CFF), fontSize = 10.sp,
                )
            }
        }
    }
}

@Composable
private fun TimeStamp(at: Long) {
    Text(
        clock.format(Date(at * 1000)),
        color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace,
    )
}

/** The deleted/edited content, boxed so it reads as a quotation of something gone. */
@Composable
private fun QuotedBody(row: LogRow) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(Color.White.copy(alpha = 0.04f))
            .padding(9.dp)
    ) {
        if (row.text.isNotBlank()) {
            Text(
                row.text, color = Color(0xFFDCE3EC), fontSize = 12.sp,
                lineHeight = 17.sp, fontFamily = FontFamily.Monospace,
            )
        } else if (row.media.isEmpty()) {
            Text(
                "content not available", color = Muted, fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
        row.media.forEach { m ->
            Spacer(Modifier.height(6.dp))
            MediaBlock(m) { }
        }
    }
}

@Composable
private fun BodyMedia(row: LogRow, onOpen: (String) -> Unit) {
    if (row.media.isEmpty()) return
    Spacer(Modifier.height(8.dp))
    // Images and GIFs get a real preview; everything else gets a file row.
    // A 44dp chip was never enough to see what was actually posted.
    row.media.forEach { m ->
        MediaBlock(m, onOpen)
        Spacer(Modifier.height(6.dp))
    }
}

/**
 * A picture, a video still, or a file row.
 *
 * The branch is on what the viewer can actually see: an image renders inline,
 * a video shows its thumbnail with a play badge, and anything else - a PDF, a
 * zip, a log - becomes a labelled row with its size, because a broken image
 * placeholder is worse than no image at all.
 */
@Composable
private fun MediaBlock(m: Media, onOpen: (String) -> Unit) {
    val previewable = m.kind in setOf("image", "gif", "sticker", "emoji")
    when {
        m.kind == "emoji" -> {
            // Emoji are inline tokens: small, in a row, no chrome.
            Row(verticalAlignment = Alignment.CenterVertically) {
                AsyncImage(
                    model = ImageRequest.Builder(LocalContext.current).data(m.url).build(),
                    imageLoader = rememberImageLoader(),
                    contentDescription = m.name,
                    modifier = Modifier.size(26.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    m.name, color = Muted, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
                )
            }
        }
        previewable -> {
            Box(
                Modifier
                    .fillMaxWidth()
                    .heightIn(max = 260.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(PanelAlt)
                    .clickable { onOpen(m.url) }
            ) {
                AsyncImage(
                    model = ImageRequest.Builder(LocalContext.current)
                        .data(m.url)
                        .crossfade(true)
                        .build(),
                    imageLoader = rememberImageLoader(),
                    contentDescription = m.name.ifBlank { m.kind },
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().aspectRatio(1.6f),
                )
                // Badges sit on the image so the kind is clear without a caption.
                if (m.isAnimated()) Badge("GIF", Modifier.align(Alignment.TopEnd))
                if (m.kind == "sticker") Badge("STICKER", Modifier.align(Alignment.BottomStart))
            }
        }
        else -> FileRow(m, onOpen)
    }
}

@Composable
private fun Badge(text: String, modifier: Modifier = Modifier) {
    Box(
        modifier
            .padding(7.dp)
            .clip(RoundedCornerShape(5.dp))
            .background(Color.Black.copy(alpha = 0.62f))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(text, color = Color.White, fontSize = 8.sp, fontWeight = FontWeight.Bold,
            letterSpacing = 0.8.sp)
    }
}

/** A non-image attachment: icon, name, size, and a tap target to open it. */
@Composable
private fun FileRow(m: Media, onOpen: (String) -> Unit) {
    val glyph = when (m.kind) {
        "video" -> "▶"
        "audio" -> "♪"
        else -> "▣"
    }
    val tint = when (m.kind) {
        "video" -> Color(0xFFE0A33E)
        "audio" -> Color(0xFF9B8CFF)
        else -> Brand
    }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(9.dp))
            .background(PanelAlt)
            .clickable { onOpen(m.url) }
            .padding(horizontal = 10.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(tint.copy(alpha = 0.16f)),
            contentAlignment = Alignment.Center,
        ) {
            Text(glyph, color = tint, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                m.name.ifBlank { m.kind },
                color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Medium,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            val detail = listOf(m.kind.uppercase(), humanSize(m.size))
                .filter { it.isNotBlank() }
                .joinToString("  ·  ")
            Text(detail, color = Muted, fontSize = 10.sp)
        }
        Text("open", color = tint, fontSize = 10.sp, fontWeight = FontWeight.Bold)
    }
}
