package ro.salavat.casa.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import ro.salavat.casa.data.ThemeMode

/** Energy colours mirror the web tokens in theme.css (validated for colour blindness). */
object Energy {
    val solar = Color(0xFFF2B33D)
    val grid = Color(0xFF4C8DF6)
    val battery = Color(0xFFE5689B)
    val load = Color(0xFF3FBF8F)
    val export = Color(0xFF2BB3C0)
    val tesla = Color(0xFFB98CFF)
    val boiler = Color(0xFFFF8A5C)
}

val Brand = Color(0xFF287B65)

private val DarkScheme = darkColorScheme(
    primary = Color(0xFF6FD8B4),
    onPrimary = Color(0xFF00382A),
    primaryContainer = Color(0xFF1C5A49),
    onPrimaryContainer = Color(0xFFB8F2DC),
    secondary = Color(0xFFB3CCC2),
    tertiary = Energy.solar,
    background = Color(0xFF0A1311),
    onBackground = Color(0xFFE3ECE8),
    surface = Color(0xFF0E1916),
    onSurface = Color(0xFFE3ECE8),
    surfaceVariant = Color(0xFF1B2A26),
    onSurfaceVariant = Color(0xFFA9BDB6),
    surfaceContainer = Color(0xFF13201C),
    surfaceContainerHigh = Color(0xFF1A2925),
    outline = Color(0xFF3B4F49),
    outlineVariant = Color(0xFF2A3A35),
    error = Color(0xFFFF8A80),
)

private val LightScheme = lightColorScheme(
    primary = Brand,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFBDEFDB),
    onPrimaryContainer = Color(0xFF002118),
    secondary = Color(0xFF4B635B),
    tertiary = Color(0xFFB7791F),
    background = Color(0xFFF3F7F5),
    onBackground = Color(0xFF14201C),
    surface = Color(0xFFFAFCFB),
    onSurface = Color(0xFF14201C),
    surfaceVariant = Color(0xFFDCE7E2),
    onSurfaceVariant = Color(0xFF42524C),
    surfaceContainer = Color(0xFFEAF1EE),
    surfaceContainerHigh = Color(0xFFE2EBE7),
    outline = Color(0xFF72847D),
    outlineVariant = Color(0xFFC3D2CC),
)

private val AppTypography = Typography().let { t ->
    t.copy(
        displaySmall = t.displaySmall.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.5).sp),
        headlineMedium = t.headlineMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.3).sp),
        headlineSmall = t.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
        titleLarge = t.titleLarge.copy(fontWeight = FontWeight.SemiBold),
        titleMedium = t.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelLarge = t.labelLarge.copy(fontWeight = FontWeight.SemiBold),
    )
}

/** Tabular figures for live values so digits don't jitter while animating. */
val Numeric = TextStyle(fontFamily = FontFamily.Default, fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold)

val LocalDark = staticCompositionLocalOf { true }

@Composable
fun CasaTheme(mode: ThemeMode, content: @Composable () -> Unit) {
    val dark = when (mode) {
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }
    CompositionLocalProvider(LocalDark provides dark) {
        MaterialTheme(colorScheme = if (dark) DarkScheme else LightScheme, typography = AppTypography, content = content)
    }
}
