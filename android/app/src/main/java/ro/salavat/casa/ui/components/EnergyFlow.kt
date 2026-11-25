package ro.salavat.casa.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.BatteryChargingFull
import androidx.compose.material.icons.rounded.ElectricCar
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.Power
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.kw
import ro.salavat.casa.ui.theme.Energy
import ro.salavat.casa.ui.theme.Numeric

/** Live flows in kW, from the same bindings as the web energy flow. Unknown stays null. */
data class Flows(
    val solar: Double?, val load: Double?, val import: Double?, val export: Double?,
    val charge: Double?, val discharge: Double?, val soc: Double?, val tesla: Double?, val boiler: Double?,
) {
    val gridNet: Double? get() = if (import == null && export == null) null else (import ?: 0.0) - (export ?: 0.0)
    val batteryNet: Double? get() = if (charge == null && discharge == null) null else (discharge ?: 0.0) - (charge ?: 0.0)
    fun mix() = EnergyMix(
        solar = (solar ?: 0.0).toFloat(),
        grid = ((import ?: 0.0) + (export ?: 0.0)).toFloat(),
        battery = ((charge ?: 0.0) + (discharge ?: 0.0)).toFloat(),
        load = (load ?: 0.3).toFloat(),
    )

    companion object {
        fun of(s: Snapshot?) = Flows(
            solar = s?.binding("solar").kw(), load = s?.binding("load").kw(),
            import = s?.binding("import").kw(), export = s?.binding("export").kw(),
            charge = s?.binding("charge").kw(), discharge = s?.binding("discharge").kw(),
            soc = s?.value("soc"), tesla = s?.binding("tesla").kw(), boiler = s?.binding("boiler").kw(),
        )
    }
}

private const val ACTIVE_KW = 0.03

private data class Link(val from: Offset, val to: Offset, val kw: Double?, val color: Color)

/**
 * Whole-house energy flow: sparks run only on wires carrying > 0.03 kW, faster
 * with more power, in the real direction (import vs export, charge vs discharge).
 */
@Composable
fun EnergyFlow(f: Flows, modifier: Modifier = Modifier) {
    val still = reducedMotion()
    val phase by rememberInfiniteTransition(label = "flow").animateFloat(
        0f, 1f, infiniteRepeatable(tween(2400, easing = LinearEasing), RepeatMode.Restart), label = "p",
    )
    val line = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.12f)
    BoxWithConstraints(modifier.fillMaxWidth().height(320.dp)) {
        val w = constraints.maxWidth.toFloat()
        val h = constraints.maxHeight.toFloat()
        val solar = Offset(w * 0.5f, h * 0.2f)
        val grid = Offset(w * 0.13f, h * 0.45f)
        val home = Offset(w * 0.5f, h * 0.48f)
        val battery = Offset(w * 0.87f, h * 0.45f)
        val tesla = Offset(w * 0.3f, h * 0.84f)
        val boiler = Offset(w * 0.7f, h * 0.84f)
        val gridNet = f.gridNet
        val batNet = f.batteryNet
        val links = listOf(
            Link(solar, home, f.solar, Energy.solar),
            if ((gridNet ?: 0.0) >= 0) Link(grid, home, gridNet, Energy.grid) else Link(home, grid, -gridNet!!, Energy.export),
            if ((batNet ?: 0.0) >= 0) Link(battery, home, batNet, Energy.battery) else Link(home, battery, -batNet!!, Energy.battery),
            Link(home, tesla, f.tesla, Energy.tesla),
            Link(home, boiler, f.boiler, Energy.boiler),
        )
        Canvas(Modifier.fillMaxSize()) {
            val dash = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 6.dp.toPx()))
            for (l in links) {
                val active = (l.kw ?: 0.0) > ACTIVE_KW
                drawLine(
                    if (active) l.color.copy(alpha = 0.35f) else line, l.from, l.to,
                    strokeWidth = if (active) 3.dp.toPx() else 1.5.dp.toPx(), cap = StrokeCap.Round,
                    pathEffect = if (active) null else dash,
                )
                if (active && !still) {
                    val speed = (0.6 + (l.kw ?: 0.0) / 3.0).coerceAtMost(3.0).toFloat()
                    val sparks = 3
                    for (i in 0 until sparks) {
                        val p = ((phase * speed) + i.toFloat() / sparks) % 1f
                        val c = Offset(l.from.x + (l.to.x - l.from.x) * p, l.from.y + (l.to.y - l.from.y) * p)
                        // Plain circles (no per-frame shader allocation): soft halo + bright core.
                        drawCircle(l.color.copy(alpha = 0.18f), 9.dp.toPx(), c)
                        drawCircle(l.color.copy(alpha = 0.45f), 5.dp.toPx(), c)
                        drawCircle(Color.White.copy(alpha = 0.95f), 2.2.dp.toPx(), c)
                    }
                }
            }
        }
        val gridLabel = when {
            gridNet == null -> "Rețea"
            gridNet < -ACTIVE_KW -> "Injecție"
            else -> "Rețea"
        }
        val batLabel = f.soc?.let { "Baterie ${fmt(it, 0)}%" } ?: "Baterie"
        Node(solar, Icons.Rounded.WbSunny, Energy.solar, "Solar", f.solar, labelOnTop = true)
        Node(grid, Icons.Rounded.Power, if ((gridNet ?: 0.0) < 0) Energy.export else Energy.grid, gridLabel, gridNet?.let { kotlin.math.abs(it) })
        Node(home, Icons.Rounded.Home, Energy.load, "Casa", f.load, big = true)
        Node(battery, Icons.Rounded.BatteryChargingFull, Energy.battery, batLabel, batNet?.let { kotlin.math.abs(it) }, fill = f.soc)
        Node(tesla, Icons.Rounded.ElectricCar, Energy.tesla, "Tesla", f.tesla)
        Node(boiler, Icons.Rounded.LocalFireDepartment, Energy.boiler, "Boiler", f.boiler)
    }
}

@Composable
private fun Node(at: Offset, icon: ImageVector, color: Color, label: String, kw: Double?, big: Boolean = false, fill: Double? = null, labelOnTop: Boolean = false) {
    val d = LocalDensity.current
    val size = if (big) 68.dp else 54.dp
    val width = 104.dp
    val labels = 40.dp // value + caption height
    val x = with(d) { at.x.toDp() } - width / 2
    val y = with(d) { at.y.toDp() } - size / 2 - if (labelOnTop) labels else 0.dp
    @Composable fun Captions() {
        Text(
            if (kw == null) "--" else "${fmt(kw, if (kw < 10) 2 else 1)} kW",
            style = MaterialTheme.typography.labelLarge.merge(Numeric), textAlign = TextAlign.Center,
        )
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
    }
    Column(Modifier.offset(x, y).width(width), horizontalAlignment = Alignment.CenterHorizontally) {
        if (labelOnTop) Column(Modifier.height(labels), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = androidx.compose.foundation.layout.Arrangement.Bottom) { Captions() }
        Box(
            Modifier.size(size)
                .background(
                    if (fill != null) Brush.verticalGradient(
                        0f to MaterialTheme.colorScheme.surface,
                        (1f - (fill / 100.0).toFloat()).coerceIn(0f, 1f) to MaterialTheme.colorScheme.surface,
                        (1f - (fill / 100.0).toFloat()).coerceIn(0f, 1f) to color.copy(alpha = 0.35f),
                        1f to color.copy(alpha = 0.35f),
                    ) else Brush.radialGradient(listOf(color.copy(alpha = 0.28f), MaterialTheme.colorScheme.surface)),
                    CircleShape,
                )
                .border(1.5.dp, color.copy(alpha = 0.7f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, null, tint = color, modifier = Modifier.size(if (big) 32.dp else 24.dp))
        }
        if (!labelOnTop) Captions()
    }
}
