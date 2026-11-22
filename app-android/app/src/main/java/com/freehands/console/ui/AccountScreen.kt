package com.freehands.console.ui

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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.freehands.console.data.Account

/**
 * Who this phone is signed in as.
 *
 * This is a native screen on purpose. It used to open a webview pointing at
 * `/authorize` — the pairing page — which on an already-paired device showed
 * nothing but an empty dark page, and the user reported it as a black screen.
 * The data was already arriving in `/api/status`; rendering it here removes a
 * round trip, works offline once cached, and cannot go blank.
 */
@Composable
fun AccountScreen(
    account: Account?,
    botName: String,
    onClose: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(Ink)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState()),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "Account", color = Color.White, fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onClose) {
                Text("Close", color = Brand, fontSize = 13.sp)
            }
        }

        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
            Spacer(Modifier.height(6.dp))
            IdentityCard(account)
            Spacer(Modifier.height(16.dp))
            SectionTitle("Session")
            SurfaceCard {
                Column(Modifier.padding(16.dp)) {
                    DetailRow("Server", botName.ifBlank { "Eternal" })
                    Spacer(Modifier.height(10.dp))
                    DetailRow(
                        "Tier",
                        account?.tier?.replaceFirstChar { it.uppercase() } ?: "Unknown",
                    )
                    if (account != null && account.id.isNotBlank()) {
                        Spacer(Modifier.height(10.dp))
                        DetailRow("Discord ID", account.id, mono = true)
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            SectionTitle("Access")
            SurfaceCard {
                Column(Modifier.padding(16.dp)) {
                    Text(
                        if (account == null) {
                            "The bot has not reported an account for this device yet. " +
                                "That usually means it is not running, or this phone was " +
                                "revoked with +revoke and needs pairing again."
                        } else {
                            "Commands run as this account. Anything it can do, this " +
                                "phone can do, so keep it paired only to a device you " +
                                "control."
                        },
                        color = Muted, fontSize = 11.sp, lineHeight = 16.sp,
                    )
                }
            }
            Spacer(Modifier.height(28.dp))
        }
    }
}

@Composable
private fun IdentityCard(account: Account?) {
    SurfaceCard(accent = if (account != null) Brand else Danger) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Avatar(account)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    account?.label?.takeIf { it.isNotBlank() } ?: "Not signed in",
                    color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    when {
                        account == null -> "No verified account"
                        account.username.isNotBlank() -> "@${account.username}"
                        else -> "Verified by the bot"
                    },
                    color = Muted, fontSize = 11.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (account != null) {
                Pill(if (account.isOwner) "Owner" else "Paired", Good)
            }
        }
    }
}

@Composable
private fun Avatar(account: Account?) {
    val url = account?.avatarUrl.orEmpty()
    val shape = CircleShape
    Box(
        Modifier
            .size(52.dp)
            .clip(shape)
            .background(
                Brush.linearGradient(listOf(BrandDeep, BrandBright))
            )
            .border(1.dp, Color.White.copy(alpha = 0.12f), shape),
        contentAlignment = Alignment.Center,
    ) {
        if (url.isNotBlank()) {
            AsyncImage(
                model = url,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            // Initial as a fallback, so a missing avatar still reads as a person.
            Text(
                account?.label?.firstOrNull()?.uppercase() ?: "?",
                color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String, mono: Boolean = false) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = Muted, fontSize = 11.sp)
        Text(
            value,
            color = Color.White,
            fontSize = 11.sp,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(start = 12.dp),
        )
    }
}
