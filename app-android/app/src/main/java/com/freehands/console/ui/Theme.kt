package com.freehands.console.ui

import androidx.compose.foundation.background
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
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

val Brand = Color(0xFF5865F2)
val Ink = Color(0xFF0E1116)
val Panel = Color(0xFF161B22)
val PanelAlt = Color(0xFF1C232D)
val Muted = Color(0xFF8B98A9)
val Danger = Color(0xFFE5484D)
val Good = Color(0xFF2FBF71)

@Composable
fun CreatorCard(creator: Creator?, modifier: Modifier = Modifier) {
    val uri = LocalUriHandler.current
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Panel),
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(Brand.copy(alpha = 0.22f), Panel)))
                .padding(18.dp)
        ) {
            Column {
                Text(
                    "CREATOR OF FREEHANDS",
                    color = Muted, fontSize = 10.sp, letterSpacing = 1.6.sp,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(14.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier
                            .size(74.dp)
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
                                color = Brand, strokeWidth = 2.dp,
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
                            color = Muted, fontSize = 13.sp, fontFamily = FontFamily.Monospace,
                        )
                        if (!creator?.bio.isNullOrBlank()) {
                            Spacer(Modifier.height(4.dp))
                            Text(creator!!.bio, color = Muted, fontSize = 12.sp, maxLines = 2)
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
                        modifier = Modifier.size(20.dp),
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

@Composable
fun SectionTitle(text: String, trailing: String? = null) {
    Row(
        Modifier.fillMaxWidth().padding(bottom = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text.uppercase(), color = Muted, fontSize = 10.sp,
            letterSpacing = 1.4.sp, fontWeight = FontWeight.Bold,
        )
        if (trailing != null) {
            Text(trailing, color = Muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun StatusPill(running: Boolean, live: Boolean) {
    val color = when {
        !running -> Danger
        !live -> Color(0xFFE0A33E)
        else -> Good
    }
    val label = when {
        !running -> "STOPPED"
        !live -> "DEGRADED"
        else -> "LIVE"
    }
    Surface(color = color.copy(alpha = 0.16f), shape = RoundedCornerShape(20.dp)) {
        Row(
            Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(6.dp))
            Text(label, color = color, fontSize = 10.sp, fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp)
        }
    }
}

@Composable
fun EmptyState(title: String, body: String, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            imageVector = Icons.Default.Refresh,
            contentDescription = null,
            tint = Muted, modifier = Modifier.size(30.dp),
        )
        Spacer(Modifier.height(12.dp))
        Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text(body, color = Muted, fontSize = 12.sp)
    }
}
