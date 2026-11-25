package ro.salavat.casa.update

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.google.firebase.FirebaseApp
import com.google.firebase.appdistribution.FirebaseAppDistribution
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ro.salavat.casa.BuildConfig
import ro.salavat.casa.MainActivity
import ro.salavat.casa.R
import ro.salavat.casa.data.Prefs

sealed interface UpdateState {
    data object Unavailable : UpdateState            // build without Firebase config
    data object Idle : UpdateState
    data object Checking : UpdateState
    data object UpToDate : UpdateState
    data class Available(val version: String, val notes: String?) : UpdateState
    data class Downloading(val percent: Int) : UpdateState
    data class Failed(val message: String) : UpdateState
}

/**
 * In-app updates through Firebase App Distribution. CI publishes every build of
 * android/ there; this checks for a newer release, raises a system notification
 * and installs it on request. The first check asks the tester (owner) to sign in
 * with the Google account invited to the release group.
 */
class Updater(private val context: Context, private val prefs: Prefs) {
    private val _state = MutableStateFlow<UpdateState>(if (enabled) UpdateState.Idle else UpdateState.Unavailable)
    val state: StateFlow<UpdateState> = _state.asStateFlow()

    private val enabled: Boolean
        get() = BuildConfig.HAS_FIREBASE && FirebaseApp.getApps(context).isNotEmpty()

    private val distribution get() = FirebaseAppDistribution.getInstance()

    /** Quiet check on app start, at most every 6 hours and only if already signed in. */
    fun checkOnStart() {
        if (!enabled) return
        if (System.currentTimeMillis() - prefs.lastUpdateCheck < 6 * 3600_000L) return
        if (!distribution.isTesterSignedIn) return
        check(userInitiated = false)
    }

    fun check(userInitiated: Boolean = true) {
        if (!enabled) return
        _state.value = UpdateState.Checking
        val run = {
            distribution.checkForNewRelease()
                .addOnSuccessListener { release ->
                    prefs.lastUpdateCheck = System.currentTimeMillis()
                    if (release == null) {
                        _state.value = UpdateState.UpToDate
                    } else {
                        val version = "${release.displayVersion} (${release.versionCode})"
                        _state.value = UpdateState.Available(version, release.releaseNotes)
                        if (!userInitiated) notify(version)
                    }
                }
                .addOnFailureListener { _state.value = UpdateState.Failed(it.message ?: "Verificarea a eșuat") }
        }
        if (distribution.isTesterSignedIn) run()
        else distribution.signInTester()
            .addOnSuccessListener { run() }
            .addOnFailureListener { _state.value = UpdateState.Failed(it.message ?: "Autentificarea testerului a eșuat") }
    }

    fun install() {
        if (!enabled) return
        distribution.updateApp()
            .addOnProgressListener { p ->
                val total = p.apkFileTotalBytes
                _state.value = UpdateState.Downloading(if (total > 0) (p.apkBytesDownloaded * 100 / total).toInt() else 0)
            }
            .addOnFailureListener { _state.value = UpdateState.Failed(it.message ?: "Instalarea a eșuat") }
    }

    private fun notify(version: String) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, context.getString(R.string.update_channel), NotificationManager.IMPORTANCE_DEFAULT)
        )
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val intent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).putExtra("route", "settings").addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        NotificationManagerCompat.from(context).notify(
            1,
            NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_shortcut_energy)
                .setContentTitle("Actualizare Casa Salavat")
                .setContentText("Versiunea $version este disponibilă. Atinge pentru instalare.")
                .setContentIntent(intent)
                .setAutoCancel(true)
                .build(),
        )
    }

    private companion object { const val CHANNEL = "updates" }
}
