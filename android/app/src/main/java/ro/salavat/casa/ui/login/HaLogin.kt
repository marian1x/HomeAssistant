package ro.salavat.casa.ui.login

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import ro.salavat.casa.BuildConfig

/**
 * Home Assistant login (password + MFA) inside a locked-down WebView:
 * /casa/auth/login -> HA authorize page -> /casa/auth/callback -> 303 to /casa/.
 * When the flow lands on /casa/ we take the HttpOnly session cookie the server
 * just set, hand it to the native client and wipe the WebView's cookie store.
 * Only the Casa and HA-auth paths may load here; everything else opens outside.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun HaLogin(base: String, onSession: (String, String) -> Unit, onCancel: () -> Unit) {
    val origin = Uri.parse(base).let { "${it.scheme}://${it.authority}" }
    val casaPath = Uri.parse(base).path!!.trimEnd('/')          // "/casa"
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var webView by remember { mutableStateOf<WebView?>(null) }
    var done by remember { mutableStateOf(false) }

    fun allowed(uri: Uri): Boolean {
        if ("${uri.scheme}://${uri.authority}" != origin) return false
        val p = uri.path ?: ""
        return p.startsWith("$casaPath/auth/") || p.startsWith("/home-assistant/auth/")
    }

    fun landed(uri: Uri): Boolean =
        "${uri.scheme}://${uri.authority}" == origin && (uri.path == "$casaPath/" || uri.path == casaPath)

    fun harvest(): Boolean {
        val raw = CookieManager.getInstance().getCookie("$base/") ?: return false
        val pair = raw.split(';').map { it.trim() }.firstOrNull { it.substringBefore('=').endsWith("casa_session") } ?: return false
        done = true
        onSession(pair.substringBefore('='), pair.substringAfter('='))
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
        return true
    }

    BackHandler {
        val w = webView
        if (w != null && w.canGoBack()) w.goBack() else onCancel()
    }
    DisposableEffect(Unit) {
        onDispose {
            webView?.destroy()
            if (!done) CookieManager.getInstance().removeAllCookies(null)
        }
    }

    Column(Modifier.fillMaxSize().safeDrawingPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onCancel) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Înapoi") }
            Text("Conectare Home Assistant", style = MaterialTheme.typography.titleMedium)
        }
        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        Box(Modifier.weight(1f)) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { ctx ->
                    CookieManager.getInstance().apply {
                        setAcceptCookie(true)
                        removeAllCookies(null)
                    }
                    WebView(ctx).apply {
                        webView = this
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.allowFileAccess = false
                        settings.allowContentAccess = false
                        settings.setSupportMultipleWindows(false)
                        settings.setGeolocationEnabled(false)
                        settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
                        if (android.os.Build.VERSION.SDK_INT >= 26) settings.safeBrowsingEnabled = true
                        CookieManager.getInstance().setAcceptThirdPartyCookies(this, false)
                        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
                        webViewClient = object : WebViewClient() {
                            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                val uri = request.url
                                if (landed(uri)) {
                                    if (!harvest()) error = "Autentificarea nu a creat o sesiune. Reîncearcă."
                                    return true
                                }
                                if (allowed(uri)) return false
                                runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, uri)) }
                                return true
                            }

                            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                                loading = true
                                val uri = Uri.parse(url)
                                if (landed(uri) && !done) {
                                    view.stopLoading()
                                    if (!harvest()) error = "Autentificarea nu a creat o sesiune. Reîncearcă."
                                }
                            }

                            override fun onPageFinished(view: WebView, url: String) { loading = false }

                            override fun onReceivedError(view: WebView, request: WebResourceRequest, err: WebResourceError) {
                                if (request.isForMainFrame) error = "Fără conexiune la server (${err.description})."
                            }
                        }
                        loadUrl("$base/auth/login")
                    }
                },
            )
            error?.let { msg ->
                Column(
                    Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(msg, color = MaterialTheme.colorScheme.error)
                    Button(onClick = { error = null; webView?.loadUrl("$base/auth/login") }, Modifier.padding(top = 12.dp)) { Text("Reîncearcă") }
                }
            }
        }
    }
}
