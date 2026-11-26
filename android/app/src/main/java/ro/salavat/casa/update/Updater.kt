package ro.salavat.casa.update

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.SigningInfo
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import ro.salavat.casa.BuildConfig
import ro.salavat.casa.CasaApp
import ro.salavat.casa.MainActivity
import ro.salavat.casa.R
import ro.salavat.casa.data.Prefs
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** A published APK: GitHub Release tagged android-v1.0.<versionCode>. */
data class Release(val version: String, val code: Int, val notes: String, val apkUrl: String, val size: Long, val sha256: String?)

sealed interface UpdateState {
    data object Unavailable : UpdateState            // debug/mock build: never self-updates
    data object Idle : UpdateState
    data object Checking : UpdateState
    data object UpToDate : UpdateState
    data class Available(val release: Release) : UpdateState
    data class Downloading(val percent: Int) : UpdateState
    data object NeedsPermission : UpdateState
    data class Failed(val message: String) : UpdateState
}

/**
 * In-app updates through GitHub Releases (same approach as the trading app, no Firebase).
 * CI builds every push to android/ and publishes a signed APK. The app checks on start and
 * every 6 h in the background, notifies, downloads on request and verifies package name,
 * SHA-256 (from the release asset digest) and signing certificate before the system
 * installer is shown. The user always confirms the installation.
 */
class Updater(private val context: Context, private val prefs: Prefs) {
    private val _state = MutableStateFlow<UpdateState>(if (BuildConfig.UPDATES) UpdateState.Idle else UpdateState.Unavailable)
    val state: StateFlow<UpdateState> = _state.asStateFlow()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    // Own client: follows GitHub's redirects to object storage, no cookies, no CSRF.
    private val client = OkHttpClient.Builder()
        .followRedirects(true).followSslRedirects(true)
        .connectTimeout(20, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS)
        .build()

    fun schedule() {
        if (!BuildConfig.UPDATES) return
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            "update-check", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<UpdateWorker>(6, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build(),
        )
    }

    /** Quiet check on app start, at most once an hour. */
    fun checkOnStart() {
        if (!BuildConfig.UPDATES || System.currentTimeMillis() - prefs.lastUpdateCheck < 3600_000L) return
        check()
    }

    fun check() {
        if (!BuildConfig.UPDATES || _state.value is UpdateState.Downloading) return
        _state.value = UpdateState.Checking
        scope.launch {
            _state.value = runCatching { latest() }.fold(
                onSuccess = { r -> if (r != null && r.code > BuildConfig.VERSION_CODE) UpdateState.Available(r) else UpdateState.UpToDate },
                onFailure = { UpdateState.Failed(it.message ?: "Verificarea a eșuat") },
            )
            prefs.lastUpdateCheck = System.currentTimeMillis()
        }
    }

    suspend fun latest(): Release? = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("https://api.github.com/repos/${BuildConfig.UPDATE_REPO}/releases/latest")
            .header("Accept", "application/vnd.github+json")
            .build()
        client.newCall(request).execute().use { r ->
            if (r.code == 404) return@withContext null
            if (!r.isSuccessful) throw IOException("GitHub a răspuns ${r.code}")
            parseRelease(JSONObject(r.body?.string().orEmpty()))
        }
    }

    fun install(release: Release) {
        if (!canInstall()) { _state.value = UpdateState.NeedsPermission; return }
        _state.value = UpdateState.Downloading(0)
        scope.launch {
            try {
                val file = download(release)
                if (!verify(file, release)) {
                    file.delete()
                    _state.value = UpdateState.Failed("APK-ul descărcat nu are semnătura aplicației. Nu l-am instalat.")
                    return@launch
                }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                context.startActivity(
                    Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK),
                )
                _state.value = UpdateState.Available(release)
            } catch (e: Exception) {
                _state.value = UpdateState.Failed(e.message ?: "Descărcarea a eșuat")
            }
        }
    }

    fun canInstall() = context.packageManager.canRequestPackageInstalls()

    fun openInstallPermission() {
        context.startActivity(
            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
        _state.value = UpdateState.Idle
    }

    private suspend fun download(release: Release): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "updates").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
        val out = File(dir, "casa-salavat-${release.code}.apk")
        client.newCall(Request.Builder().url(release.apkUrl).build()).execute().use { r ->
            if (!r.isSuccessful) throw IOException("Descărcare eșuată (HTTP ${r.code})")
            val body = r.body ?: throw IOException("Răspuns gol")
            val total = if (release.size > 0) release.size else body.contentLength()
            body.byteStream().use { input ->
                out.outputStream().use { output ->
                    val buffer = ByteArray(32 * 1024)
                    var done = 0L
                    var last = -1
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        output.write(buffer, 0, n)
                        done += n
                        val percent = if (total > 0) (done * 100 / total).toInt() else 0
                        if (percent != last) { last = percent; _state.value = UpdateState.Downloading(percent) }
                    }
                }
            }
        }
        out
    }

    /** Package name, SHA-256 (when GitHub publishes the digest) and signer must all match. */
    private fun verify(file: File, release: Release): Boolean {
        release.sha256?.let { expected ->
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { s -> val b = ByteArray(32 * 1024); while (true) { val n = s.read(b); if (n < 0) break; digest.update(b, 0, n) } }
            if (!digest.digest().hex().equals(expected, ignoreCase = true)) return false
        }
        val pm = context.packageManager
        val modern = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
        @Suppress("DEPRECATION")
        val flags = if (modern) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val archive = pm.getPackageArchiveInfo(file.absolutePath, flags) ?: return false
        if (archive.packageName != context.packageName) return false
        val own = runCatching { pm.getPackageInfo(context.packageName, flags) }.getOrNull() ?: return false
        @Suppress("DEPRECATION")
        fun of(p: android.content.pm.PackageInfo): Set<String> =
            if (modern) signers(p.signingInfo) else (p.signatures ?: emptyArray()).map { it.toByteArray().sha() }.toSet()
        val mine = of(own)
        return mine.isNotEmpty() && mine.intersect(of(archive)).isNotEmpty()
    }

    @androidx.annotation.RequiresApi(Build.VERSION_CODES.P)
    private fun signers(info: SigningInfo?): Set<String> {
        val list = info?.let { if (it.hasMultipleSigners()) it.apkContentsSigners else it.signingCertificateHistory } ?: return emptySet()
        return list.map { it.toByteArray().sha() }.toSet()
    }

    private fun ByteArray.sha() = MessageDigest.getInstance("SHA-256").digest(this).hex()

    fun notifyAvailable(release: Release) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, context.getString(R.string.update_channel), NotificationManager.IMPORTANCE_DEFAULT))
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val intent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).putExtra("route", "settings").addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION,
            NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_shortcut_energy)
                .setContentTitle("Actualizare Casa Salavat ${release.version}")
                .setContentText(release.notes.lineSequence().firstOrNull { it.isNotBlank() } ?: "Atinge pentru instalare.")
                .setContentIntent(intent)
                .setAutoCancel(true)
                .build(),
        )
    }

    companion object {
        private const val CHANNEL = "updates"
        private const val NOTIFICATION = 1

        /** Tag "android-v1.0.42" -> code 42; the APK asset and its optional "sha256:" digest. */
        fun parseRelease(o: JSONObject): Release? {
            val tag = o.optString("tag_name")
            val match = Regex("""(\d+)\.(\d+)\.(\d+)""").find(tag) ?: return null
            val assets = o.optJSONArray("assets") ?: return null
            val apk = (0 until assets.length()).mapNotNull { assets.optJSONObject(it) }
                .firstOrNull { it.optString("name").endsWith(".apk", ignoreCase = true) } ?: return null
            return Release(
                version = match.value,
                code = match.groupValues[3].toInt(),
                notes = o.optString("body").trim(),
                apkUrl = apk.optString("browser_download_url"),
                size = apk.optLong("size"),
                sha256 = apk.optString("digest").takeIf { it.startsWith("sha256:") }?.removePrefix("sha256:"),
            )
        }

        private fun ByteArray.hex() = joinToString("") { "%02x".format(it) }
    }
}

/** Background check every 6 h; one notification per new version. */
class UpdateWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as CasaApp
        val release = runCatching { app.updater.latest() }.getOrElse { return Result.retry() } ?: return Result.success()
        if (release.code > BuildConfig.VERSION_CODE && app.prefs.notifiedVersion != release.code) {
            app.prefs.notifiedVersion = release.code
            app.updater.notifyAvailable(release)
        }
        return Result.success()
    }
}
