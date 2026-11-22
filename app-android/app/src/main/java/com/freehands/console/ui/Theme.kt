package com.freehands.console.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.freehands.console.R
import com.freehands.console.data.Creator
import com.freehands.console.data.REPO_URL

// -- palette ---------------------------------------------------------------
// Discord blurple as the brand, on a near-black navy rather than neutral grey:
// the blue cast makes the white text sit warmer and stops the whole app reading
// as a default Material dark theme.
val Brand = Color(0xFF5865F2)
val BrandBright = Color(0xFF7C86FF)
val BrandDeep = Color(0xFF3A44C4)
val Ink = Color(0xFF080A0F)
val InkRaised = Color(0xFF0D1017)
val Panel = Color(0xFF141821)
val PanelAlt = Color(0xFF1B2029)
val Hairline = Color(0xFF232936)
val Muted = Color(0xFF8B98A9)
val MutedDim = Color(0xFF5E6A7A)
val Danger = Color(0xFFE5484D)
val Good = Color(0xFF2FBF71)
val Warn = Color(0xFFE0A33E)
val Violet = Color(0xFF9B8CFF)

// -- reusable surfaces -----------------------------------------------------

/**
 * The standard content card: a faint vertical wash so it has depth, a hairline
 * border so it separates from the background without a heavy shadow, and
 * generous corners. Used everywhere instead of raw `Card` so the app has one
 * idea of what a surface looks like.
 */
@Composable
fun SurfaceCard(
    modifier: Modifier = Modifier,
    accent: Color? = null,
    content: @Composable () -> Unit,
) {
    val shape = RoundedCornerShape(18.dp)
    Box(
        modifier
            .fillMaxWidth()
            .clip(shape)
            .background(
                Brush.verticalGradient(
                    listOf(accent?.copy(alpha = 0.10f) ?: PanelAlt, Panel)
                )
            )
            .border(1.dp, accent?.copy(alpha = 0.22f) ?: Hairline, shape)
    ) {
        content()
    }
}

/** A small pill with a dot: the status vocabulary of the whole app. */
@Composable
fun Pill(label: String, color: Color, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        color = color.copy(alpha = 0.14f),
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(1.dp, color.copy(alpha = 0.30f)),
    ) {
        Row(
            Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(6.dp))
            Text(
                label, color = color, fontSize = 10.sp, fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp,
            )
        }
    }
}

@Composable
fun StatusPill(running: Boolean, live: Boolean) {
    val (color, label) = when {
        !running -> Danger to "STOPPED"
        !live -> Warn to "DEGRADED"
        else -> Good to "LIVE"
    }
    Pill(label, color)
}

/** Section heading: an accent tick, a label, and an optional right-hand count. */
@Composable
fun SectionTitle(text: String, trailing: String? = null) {
    Row(
        Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .width(3.dp)
                    .height(13.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(Brush.verticalGradient(listOf(BrandBright, BrandDeep)))
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text.uppercase(), color = Color(0xFFB9C4D2), fontSize = 10.sp,
                letterSpacing = 1.6.sp, fontWeight = FontWeight.Bold,
            )
        }
        if (trailing != null) {
            Text(trailing, color = MutedDim, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

/**
 * The Freehands mark: three slanted bars that read as forward motion.
 *
 * Drawn rather than shipped as a glyph because the previous version used a
 * raised-hand emoji, which renders differently on every device, cannot be
 * tinted, and is not the brand. The same geometry is the launcher icon.
 */
@Composable
fun BrandMark(size: Int = 30, modifier: Modifier = Modifier) {
    Box(
        modifier
            .size(size.dp)
            .clip(RoundedCornerShape((size * 0.28f).dp))
            .background(
                Brush.linearGradient(
                    listOf(BrandBright, BrandDeep),
                    start = Offset(0f, 0f),
                    end = Offset(size.toFloat(), size.toFloat()),
                )
            ),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.fillMaxSize()) {
            // Proportions match res/drawable/ic_launcher_foreground.xml, which
            // uses a 108-unit viewport.
            val u = this.size.minDimension / 108f
            val bars = listOf(
                listOf(28f, 38f, 52f, 38f, 49f, 46f, 25f, 46f),
                listOf(34f, 51f, 66f, 51f, 63f, 59f, 31f, 59f),
                listOf(40f, 64f, 78f, 64f, 75f, 72f, 37f, 72f),
            )
            for (b in bars) {
                val path = Path().apply {
                    moveTo(b[0] * u, b[1] * u)
                    lineTo(b[2] * u, b[3] * u)
                    lineTo(b[4] * u, b[5] * u)
                    lineTo(b[6] * u, b[7] * u)
                    close()
                }
                drawPath(path, Color.White)
            }
        }
    }
}

@Composable
fun EmptyState(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    glyph: String = "\u25CC",
) {
    Column(
        modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier
                .size(58.dp)
                .clip(RoundedCornerShape(18.dp))
                .background(Brand.copy(alpha = 0.10f))
                .border(1.dp, Brand.copy(alpha = 0.22f), RoundedCornerShape(18.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text(glyph, color = BrandBright, fontSize = 22.sp)
        }
        Spacer(Modifier.height(14.dp))
        Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text(body, color = Muted, fontSize = 12.sp, lineHeight = 18.sp)
    }
}

/** Key/value row used by the settings and status panels. */
@Composable
fun StatRow(label: String, value: String, tint: Color = Color.White) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 5.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = Muted, fontSize = 11.sp)
        Text(
            value, color = tint, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
fun CreatorCard(creator: Creator?, modifier: Modifier = Modifier) {
    val uri = LocalUriHandler.current
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
        border = BorderStroke(1.dp, Hairline),
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .background(
                    Brush.linearGradient(
                        listOf(Brand.copy(alpha = 0.26f), Brand.copy(alpha = 0.02f), Panel)
                    )
                )
                .padding(18.dp)
        ) {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    BrandMark(20)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "CREATOR OF FREEHANDS",
                        color = Muted, fontSize = 9.sp, letterSpacing = 1.6.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Spacer(Modifier.height(14.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier
                            .size(74.dp)
                            .clip(CircleShape)
                            .background(Brush.linearGradient(listOf(Brand, BrandDeep)))
                            .padding(2.dp)
                            .clip(CircleShape)
                            .background(PanelAlt),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (creator != null) {
                            AsyncImage(
                                model = creator.avatarUrl,
                                contentDescription = "GitHub avatar",
                                modifier = Modifier.fillMaxSize().clip(CircleShape),
                            )
                        } else {
                            CircularProgressIndicator(
                                modifier = Modifier.size(22.dp),
                                color = BrandBright, strokeWidth = 2.dp,
                            )
                        }
                    }
                    Spacer(Modifier.width(16.dp))
                    Column {
                        Text(
                            creator?.name ?: "Lynx",
                            color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "@${creator?.login ?: "Lynxifyy"}",
                            color = BrandBright, fontSize = 12.sp,
                            fontFamily = FontFamily.Monospace,
                        )
                        if (!creator?.bio.isNullOrBlank()) {
                            Spacer(Modifier.height(4.dp))
                            Text(
                                creator!!.bio, color = Muted, fontSize = 11.sp,
                                maxLines = 2, lineHeight = 16.sp,
                            )
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = { uri.openUri(REPO_URL) },
                    modifier = Modifier.fillMaxWidth().height(46.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF24292F)),
                ) {
                    Icon(
                        painter = painterResource(id = R.drawable.ic_github),
                        contentDescription = "GitHub",
                        modifier = Modifier.size(19.dp),
                        tint = Color.White,
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(
                        "Freehands-Discord-Bot",
                        color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}
