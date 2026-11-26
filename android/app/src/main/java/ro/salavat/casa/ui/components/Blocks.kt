package ro.salavat.casa.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.EntityState
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.stateLabel
import ro.salavat.casa.ui.theme.Numeric

/** Scrolling page body that respects the Scaffold insets; optional back header for detail screens. */
@Composable
fun Page(padding: PaddingValues, title: String? = null, subtitle: String? = null, onBack: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (title != null) Row(verticalAlignment = Alignment.CenterVertically) {
            if (onBack != null) IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Înapoi") }
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.headlineMedium)
                subtitle?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
        }
        content()
    }
}

@Composable
fun SectionTitle(text: String, action: (@Composable () -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(text, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        action?.invoke()
    }
}

/** Label on the left, value on the right; "--" when unknown (never invented). */
@Composable
fun KeyValue(label: String, value: String?, color: Color = Color.Unspecified) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Text(value ?: "--", style = MaterialTheme.typography.bodyMedium.merge(Numeric), color = color)
    }
}

@Composable
fun StateValue(label: String, st: EntityState?, digits: Int = 1) =
    KeyValue(label, st?.let { s -> s.number?.let { "${fmt(it, digits)} ${s.unit}".trim() } ?: stateLabel(s) })

/** Small coloured stat tile used in grids. */
@Composable
fun Tile(label: String, value: String, color: Color, modifier: Modifier = Modifier, sub: String? = null) {
    GlassCard(modifier, padding = 14.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(color, CircleShape))
            Spacer(Modifier.width(6.dp))
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.height(4.dp))
        Text(value, style = MaterialTheme.typography.titleLarge.merge(Numeric), color = color, maxLines = 1)
        sub?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2) }
    }
}

/** Horizontal share bar, e.g. a consumer's part of the house load. */
@Composable
fun ShareBar(fraction: Float, color: Color, modifier: Modifier = Modifier, height: Dp = 8.dp) {
    val f by animateFloatAsState(fraction.coerceIn(0f, 1f), tween(700), label = "share")
    Box(modifier.fillMaxWidth().height(height).clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f))) {
        Box(Modifier.fillMaxWidth(f).height(height).clip(RoundedCornerShape(50)).background(color))
    }
}

/** Minimal line chart: one series, nulls break the line, y range from the data. */
@Composable
fun MiniChart(values: List<Double?>, color: Color, modifier: Modifier = Modifier, height: Dp = 120.dp, fixedMin: Double? = null, fixedMax: Double? = null) {
    val known = values.filterNotNull()
    if (known.size < 2) {
        Box(modifier.fillMaxWidth().height(height), contentAlignment = Alignment.Center) {
            Text("Fără date în interval.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        }
        return
    }
    val lo = fixedMin ?: known.min()
    val hi = (fixedMax ?: known.max()).let { if (it - lo < 1e-6) lo + 1 else it }
    val grid = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.07f)
    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().height(height)) {
            for (i in 0..2) drawLine(grid, Offset(0f, size.height * i / 2f), Offset(size.width, size.height * i / 2f))
            val step = size.width / (values.size - 1).coerceAtLeast(1)
            val line = Path()
            val fill = Path()
            var open = false
            var lastX = 0f
            values.forEachIndexed { i, v ->
                if (v == null) {
                    if (open) { fill.lineTo(lastX, size.height); fill.close(); open = false }
                    return@forEachIndexed
                }
                val x = i * step
                val y = size.height - ((v - lo) / (hi - lo)).toFloat() * size.height
                if (!open) { line.moveTo(x, y); fill.moveTo(x, size.height); fill.lineTo(x, y); open = true } else { line.lineTo(x, y); fill.lineTo(x, y) }
                lastX = x
            }
            if (open) { fill.lineTo(lastX, size.height); fill.close() }
            drawPath(fill, Brush.verticalGradient(listOf(color.copy(alpha = 0.22f), Color.Transparent)))
            drawPath(line, color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        }
        Row(Modifier.fillMaxWidth()) {
            Text("min ${fmt(known.min())}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text("max ${fmt(known.max())}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
