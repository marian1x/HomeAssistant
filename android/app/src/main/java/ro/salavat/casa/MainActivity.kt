package ro.salavat.casa

import android.Manifest
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import ro.salavat.casa.data.AuthState
import ro.salavat.casa.ui.AppRoot
import ro.salavat.casa.ui.theme.CasaTheme
import ro.salavat.casa.ui.theme.LocalDark

class MainActivity : FragmentActivity() {
    private val app get() = application as CasaApp
    private var route by mutableStateOf<String?>(null)
    private var locked by mutableStateOf(false)
    private var backgroundAt = 0L

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        route = intent.getStringExtra("route")
        locked = savedInstanceState?.getBoolean("locked") ?: shouldLock()

        setContent {
            val theme by app.prefs.theme.collectAsState()
            CasaTheme(theme) {
                val dark = LocalDark.current
                LaunchedEffect(dark) {
                    val style = if (dark) SystemBarStyle.dark(Color.TRANSPARENT) else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                    enableEdgeToEdge(style, style)
                }
                AppRoot(
                    repo = app.repo, prefs = app.prefs, updater = app.updater,
                    route = route, onRouteHandled = { route = null },
                    locked = locked, onUnlock = ::prompt,
                )
            }
        }

        // Live data only while the UI is visible: SSE opens on start, closes on stop.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                app.repo.auth.map { it != AuthState.SIGNED_OUT }.distinctUntilChanged().collectLatest { signedIn ->
                    if (signedIn) {
                        askNotifications()
                        app.repo.stayLive()
                    }
                }
            }
        }
        lifecycleScope.launch {
            app.prefs.keepScreenOn.collect { on ->
                if (on) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }
    }

    override fun onStart() {
        super.onStart()
        if (backgroundAt > 0 && System.currentTimeMillis() - backgroundAt > LOCK_AFTER_MS && shouldLock()) locked = true
        backgroundAt = 0
        if (locked) prompt()
        app.updater.checkOnStart()
    }

    override fun onStop() {
        super.onStop()
        backgroundAt = System.currentTimeMillis()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("locked", locked)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra("route")?.let { route = it }
    }

    private fun authenticators() = BIOMETRIC_WEAK or DEVICE_CREDENTIAL

    private fun shouldLock(): Boolean =
        app.prefs.biometric.value && app.repo.auth.value != AuthState.SIGNED_OUT &&
            BiometricManager.from(this).canAuthenticate(authenticators()) == BiometricManager.BIOMETRIC_SUCCESS

    private fun prompt() {
        if (!shouldLock()) { locked = false; return }
        BiometricPrompt(this, ContextCompat.getMainExecutor(this), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) { locked = false }
        }).authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Deblochează Casa Salavat")
                .setSubtitle("Amprentă, față sau PIN-ul telefonului")
                .setAllowedAuthenticators(authenticators())
                .build(),
        )
    }

    private fun askNotifications() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED &&
            !getSharedPreferences("settings", MODE_PRIVATE).getBoolean("asked_notif", false)
        ) {
            getSharedPreferences("settings", MODE_PRIVATE).edit().putBoolean("asked_notif", true).apply()
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private companion object { const val LOCK_AFTER_MS = 60_000L }
}
