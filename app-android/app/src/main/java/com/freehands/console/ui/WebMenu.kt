package com.freehands.console.ui

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView

/**
 * An in-app browser for pages the bot serves.
 *
 * Pairing used to mean typing a six-character code into a text field, which is
 * fine but leaves the phone doing the work. Serving the page instead means the
 * bot controls the whole exchange: it mints the code, shows it, and knows the
 * moment it is approved. The user never leaves the app.
 *
 * Only same-origin navigation is allowed. An embedded browser that will follow
 * any link is a phishing surface, and there is nothing outside the bot's own
 * pages that this screen needs to reach.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun WebMenu(
    url: String,
    title: String,
    onClose: () -> Unit,
    onPaired: (String, String?) -> Unit,
    onNavigate: ((String) -> Unit)? = null,
) {
    var progress by remember { mutableStateOf(true) }
    val origin = remember(url) { runCatching { java.net.URI(url).host }.getOrNull() }

    // Runs on the UI thread, so the callback can touch Compose state.
    fun adopt(payload: String) {
        runCatching {
            val o = org.json.JSONObject(payload)
            val token = o.optString("token")
            val who = o.optJSONObject("identity")?.optString("label").orEmpty()
            if (token.isNotBlank()) onPaired(token, who.ifBlank { null })
        }
    }

    Column(Modifier.fillMaxSize().background(Ink).statusBarsPadding()) {
        Row(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    title, color = Color.White, fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                if (progress) {
                    Text("Loading", color = Muted, fontSize = 10.sp)
                }
            }
            TextButton(onClick = onClose) {
                Text("Close", color = Brand, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.height(6.dp))

        Box(Modifier.fillMaxWidth().weight(1f)) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { context ->
                    WebView(context).apply {
                        val self = this
                        setBackgroundColor(android.graphics.Color.TRANSPARENT)
                        settings.javaScriptEnabled = true
                        // The page pushes the token here once approval lands.
                        // It cannot be read on `onPageFinished`: that fires
                        // before the operator has approved anything, and the
                        // page never navigates afterwards.
                        addJavascriptInterface(
                            object {
                                @android.webkit.JavascriptInterface
                                fun onPaired(payload: String) {
                                    self.post { adopt(payload) }
                                }
                            },
                            "FreehandsAndroid",
                        )
                        // The pairing page talks to the same origin it was
                        // served from, so no file or cross-origin access is
                        // needed.
                        settings.domStorageEnabled = true
                        settings.allowFileAccess = false
                        settings.allowContentAccess = false
                        settings.setSupportMultipleWindows(false)
                        webViewClient = object : WebViewClient() {
                            override fun shouldOverrideUrlLoading(
                                view: WebView,
                                request: WebResourceRequest,
                            ): Boolean {
                                val target = request.url
                                if (origin != null && target.host != origin) {
                                    // Off-origin: hand it to the system browser
                                    // rather than loading it in a view that
                                    // could read the bot's pages.
                                    onNavigate?.invoke(target.toString())
                                    return true
                                }
                                return false
                            }

                            override fun onPageStarted(v: WebView?, u: String?, f: Bitmap?) {
                                progress = true
                            }

                            override fun onPageFinished(v: WebView?, u: String?) {
                                progress = false
                                // The page publishes the token once approval
                                // lands, so the app can take it without the
                                // user copying anything.
                                v?.evaluateJavascript(
                                    "(function(){var p=window.FreehandsPairing;" +
                                        "return p?JSON.stringify(p):'';})()",
                                ) { raw ->
                                    val text = raw?.trim()?.trim('"') ?: ""
                                    if (text.isNotEmpty() && text != "null") adopt(text)
                                }
                            }
                        }
                        loadUrl(url)
                    }
                },
                update = { view ->
                    if (view.url != url) view.loadUrl(url)
                },
            )
        }
    }
}
