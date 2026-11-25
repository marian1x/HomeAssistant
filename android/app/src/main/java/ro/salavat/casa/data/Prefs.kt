package ro.salavat.casa.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class ThemeMode(val label: String) { SYSTEM("Sistem"), LIGHT("Luminos"), DARK("Întunecat") }

/** Local, non-secret preferences. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    private val _theme = MutableStateFlow(runCatching { ThemeMode.valueOf(sp.getString("theme", "SYSTEM")!!) }.getOrDefault(ThemeMode.SYSTEM))
    val theme: StateFlow<ThemeMode> = _theme.asStateFlow()

    private val _biometric = MutableStateFlow(sp.getBoolean("biometric", true))
    val biometric: StateFlow<Boolean> = _biometric.asStateFlow()

    private val _keepScreenOn = MutableStateFlow(sp.getBoolean("keep_on", false))
    val keepScreenOn: StateFlow<Boolean> = _keepScreenOn.asStateFlow()

    fun setTheme(mode: ThemeMode) { sp.edit().putString("theme", mode.name).apply(); _theme.value = mode }
    fun setBiometric(on: Boolean) { sp.edit().putBoolean("biometric", on).apply(); _biometric.value = on }
    fun setKeepScreenOn(on: Boolean) { sp.edit().putBoolean("keep_on", on).apply(); _keepScreenOn.value = on }

    var lastUpdateCheck: Long
        get() = sp.getLong("update_check", 0)
        set(v) = sp.edit().putLong("update_check", v).apply()
}
