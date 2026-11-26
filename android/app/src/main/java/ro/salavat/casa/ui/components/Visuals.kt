package ro.salavat.casa.ui.components

import android.provider.Settings
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.Spacer
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.fmt
import ro.salavat.casa.ui.theme.Energy
import ro.salavat.casa.ui.theme.LocalDark
import ro.salavat.casa.ui.theme.Numeric
import kotlin.math.cos
import kotlin.math.sin

/** Relative weights of the live flows; drive the aurora's colours like the web's aurora-mix. */
data class EnergyMix(val solar: Float = 0f, val grid: Float = 0f, val battery: Float = 0f, val load: Float = 1f)

@Composable
fun reducedMotion(): Boolean {
    val ctx = LocalContext.current
    return remember {
        Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    }
}

/**
 * Living background: four soft colour fields that drift slowly; their strength
 * follows the real energy mix (amber solar, blue grid, pink battery, green load).
 * A static frame is drawn when the system asks for reduced motion.
 */
@Composable
fun AuroraBackground(mix: EnergyMix, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val dark = LocalDark.current
    val still = reducedMotion()
    // States are read only inside the draw phase: the drift never recomposes the UI.
    val drift = rememberInfiniteTransition(label = "aurora").animateFloat(
        0f, (2 * Math.PI).toFloat(),
        infiniteRepeatable(tween(38_000, easing = LinearEasing), RepeatMode.Restart),
        label = "t",
    )
    val total = (mix.solar + mix.grid + mix.battery + mix.load).coerceAtLeast(0.001f)
    val solar = animateFloatAsState(mix.solar / total, tween(1500), label = "s")
    val grid = animateFloatAsState(mix.grid / total, tween(1500), label = "g")
    val battery = animateFloatAsState(mix.battery / total, tween(1500), label = "b")
    val load = animateFloatAsState(mix.load / total, tween(1500), label = "l")
    val base = MaterialTheme.colorScheme.background
    val alpha = if (dark) 0.55f else 0.35f
    Box(modifier.fillMaxSize()) {
        Spacer(
            Modifier.fillMaxSize().drawWithCache {
                // Gradients are built once per size/mix change and only translated per frame.
                val w = size.width
                val h = size.height
                val r = maxOf(w, h) * 0.75f
                data class Blob(val brush: Brush, val radius: Float, val phase: Float, val cx: Float, val cy: Float)
                fun blob(color: Color, weight: Float, phase: Float, cx: Float, cy: Float): Blob {
                    val strength = (0.25f + weight * 0.9f).coerceAtMost(1f) * alpha
                    val radius = r * (0.55f + weight * 0.45f)
                    return Blob(Brush.radialGradient(listOf(color.copy(alpha = strength), Color.Transparent), Offset.Zero, radius), radius, phase, cx, cy)
                }
                val blobs = listOf(
                    blob(Energy.solar, solar.value, 0f, 0.85f, 0.05f),
                    blob(Energy.grid, grid.value, 2.1f, 0.1f, 0.35f),
                    blob(Energy.battery, battery.value, 4.2f, 0.95f, 0.7f),
                    blob(Energy.load, load.value, 1.1f, 0.2f, 0.95f),
                )
                onDrawBehind {
                    drawRect(base)
                    val t = if (still) 0.8f else drift.value
                    for (b in blobs) {
                        translate(w * (b.cx + 0.12f * cos(t + b.phase)), h * (b.cy + 0.08f * sin(t * 1.3f + b.phase))) {
                            drawCircle(b.brush, b.radius, Offset.Zero)
                        }
                    }
                }
            },
        )
        // No Surface underneath: provide the content colour explicitly.
        CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onBackground) {
            content()
        }
    }
}

/** Frosted card: translucent surface + hairline border, no expensive blur. */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    tint: Color? = null,
    padding: Dp = 18.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    val dark = LocalDark.current
    val bg = (tint ?: MaterialTheme.colorScheme.surface).copy(alpha = if (dark) 0.62f else 0.78f)
    val border = BorderStroke(1.dp, Brush.verticalGradient(listOf(Color.White.copy(alpha = if (dark) 0.14f else 0.7f), Color.White.copy(alpha = 0.02f))))
    val shape = RoundedCornerShape(26.dp)
    // Cards always span their slot (column, grid cell or weighted row share).
    if (onClick != null) {
        Surface(onClick = onClick, modifier = modifier.fillMaxWidth(), shape = shape, color = bg, border = border) {
            Column(Modifier.padding(padding), content = content)
        }
    } else {
        Surface(modifier = modifier.fillMaxWidth(), shape = shape, color = bg, border = border) {
            Column(Modifier.padding(padding), content = content)
        }
    }
}

/** Glides between two real readings; never counts up from zero. */
@Composable
fun AnimatedNumber(value: Double?, suffix: String = "", digits: Int = 1, style: TextStyle = MaterialTheme.typography.headlineMedium, color: Color = Color.Unspecified) {
    if (value == null) {
        Text("--", style = style.merge(Numeric), color = color)
        return
    }
    val shown by animateFloatAsState(value.toFloat(), tween(900), label = "num")
    Text(fmt(shown.toDouble(), digits) + suffix, style = style.merge(Numeric), color = color)
}

/** Progress ring, e.g. today's energy independence or battery SOC. */
@Composable
fun Ring(fraction: Float?, color: Color, size: Dp = 92.dp, stroke: Dp = 10.dp, content: @Composable BoxScope.() -> Unit) {
    val track = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f)
    val sweep by animateFloatAsState((fraction ?: 0f).coerceIn(0f, 1f), tween(1200), label = "ring")
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val st = Stroke(stroke.toPx(), cap = StrokeCap.Round)
            val inset = stroke.toPx() / 2
            val arcSize = androidx.compose.ui.geometry.Size(this.size.width - 2 * inset, this.size.height - 2 * inset)
            drawArc(track, -90f, 360f, false, Offset(inset, inset), arcSize, style = st)
            if (fraction != null) drawArc(
                Brush.sweepGradient(listOf(color.copy(alpha = 0.6f), color, color.copy(alpha = 0.6f))),
                -90f, 360f * sweep, false, Offset(inset, inset), arcSize, style = st,
            )
        }
        content()
    }
}
