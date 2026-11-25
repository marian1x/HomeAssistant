package ro.salavat.casa.ui.energy

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.background
import ro.salavat.casa.data.History
import ro.salavat.casa.data.HistoryPoint
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.kw
import ro.salavat.casa.ui.components.AnimatedNumber
import ro.salavat.casa.ui.components.Flows
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.Ring
import ro.salavat.casa.ui.theme.Energy
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EnergyScreen(s: Snapshot, repo: Repository, padding: PaddingValues) {
    val f = Flows.of(s)
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Energie", style = MaterialTheme.typography.headlineMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp), maxItemsInEachRow = 2) {
            val m = Modifier.weight(1f)
            Metric("Producție solară", f.solar, "kW", Energy.solar, m)
            Metric("Consum casă", f.load, "kW", Energy.load, m)
            Metric("Import rețea", f.import, "kW", Energy.grid, m)
            Metric("Injecție", f.export, "kW", Energy.export, m)
            Metric("Tesla", f.tesla, "kW", Energy.tesla, m)
            Metric("Boiler (estimat)", f.boiler, "kW", Energy.boiler, m)
        }
        BatteryCard(s, f)
        HistoryCard(repo)
        GlassCard {
            Text("Azi și mâine", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Line("Produs azi", s.value("solarToday"), "kWh")
            Line("Consum azi", s.value("loadToday"), "kWh")
            Line("Import azi", s.value("importToday"), "kWh")
            Line("Prognoză solară mâine", s.value("forecast"), "kWh")
            Line("Rezervă recomandată", s.value("reserve"), "%")
        }
    }
}

@Composable
private fun Metric(label: String, value: Double?, unit: String, color: Color, modifier: Modifier) {
    GlassCard(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(color, CircleShape))
            Spacer(Modifier.width(8.dp))
            Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(6.dp))
        AnimatedNumber(value, " $unit", digits = 2, style = MaterialTheme.typography.headlineSmall, color = color)
    }
}

@Composable
private fun Line(label: String, value: Double?, unit: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value?.let { "${fmt(it)} $unit" } ?: "--", style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun BatteryCard(s: Snapshot, f: Flows) {
    val temp = s.binding("batteryTemp")?.number
    val net = f.batteryNet
    GlassCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ring(f.soc?.toFloat()?.div(100f), Energy.battery, size = 104.dp) {
                Text(f.soc?.let { "${fmt(it, 0)}%" } ?: "--", style = MaterialTheme.typography.headlineSmall)
            }
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Baterie casă", style = MaterialTheme.typography.titleMedium)
                Text(
                    when {
                        net == null -> "Fără date"
                        net > 0.03 -> "Se descarcă ${fmt(net, 2)} kW"
                        net < -0.03 -> "Se încarcă ${fmt(-net, 2)} kW"
                        else -> "În repaus"
                    },
                    color = Energy.battery,
                )
                Text("Temperatură ${temp?.let { fmt(it) + " °C" } ?: "--"}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("Limită descărcare ${s.binding("limit").kw()?.let { fmt(it) + " kW" } ?: "--"}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

private val PERIODS = listOf("day" to "Zi", "week" to "Săpt.", "month" to "Lună", "year" to "An")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HistoryCard(repo: Repository) {
    var period by rememberSaveable { mutableStateOf("day") }
    var data by remember { mutableStateOf<History?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(period) {
        data = null; error = null
        runCatching { repo.history(period) }.onSuccess { data = it }.onFailure { error = it.message }
    }
    GlassCard {
        Text("Istoric", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(10.dp))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            PERIODS.forEachIndexed { i, (key, label) ->
                SegmentedButton(selected = period == key, onClick = { period = key }, shape = SegmentedButtonDefaults.itemShape(i, PERIODS.size)) { Text(label) }
            }
        }
        Spacer(Modifier.height(12.dp))
        Box(Modifier.fillMaxWidth().height(210.dp), contentAlignment = Alignment.Center) {
            when {
                error != null -> Text(error!!, color = MaterialTheme.colorScheme.error)
                data == null -> CircularProgressIndicator()
                data!!.points.isEmpty() -> Text("Fără date pentru perioada aleasă.")
                else -> Chart(data!!, period)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), modifier = Modifier.padding(top = 8.dp)) {
            Legend("Solar", Energy.solar); Legend("Consum", Energy.load); Legend("Baterie", Energy.battery); Legend("Rețea", Energy.grid)
        }
        data?.let { Text("Unitate: ${it.unit}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun Legend(label: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(4.dp))
        Text(label, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun Chart(h: History, period: String) {
    val reveal by animateFloatAsState(1f, tween(900), label = "reveal")
    val grid = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f)
    val axis = MaterialTheme.colorScheme.onSurfaceVariant
    val series: List<Pair<Color, (HistoryPoint) -> Double?>> = listOf(
        Energy.solar to { p -> p.solar }, Energy.load to { p -> p.load }, Energy.battery to { p -> p.battery }, Energy.grid to { p -> p.grid },
    )
    val max = h.points.flatMap { p -> series.mapNotNull { it.second(p) } }.maxOrNull()?.coerceAtLeast(0.1) ?: 1.0
    val t0 = h.points.first().time
    val t1 = h.points.last().time.coerceAtLeast(t0 + 1)
    val fmtTime = SimpleDateFormat(if (period == "day") "HH:mm" else if (period == "year") "MMM" else "dd.MM", Locale.forLanguageTag("ro"))
    Column(Modifier.fillMaxSize()) {
        Canvas(Modifier.fillMaxWidth().weight(1f)) {
            for (i in 0..3) {
                val y = size.height * i / 3f
                drawLine(grid, Offset(0f, y), Offset(size.width, y))
            }
            fun x(t: Long) = (t - t0).toFloat() / (t1 - t0) * size.width
            fun y(v: Double) = size.height - (v / max).toFloat() * size.height
            for ((color, pick) in series) {
                val path = Path()
                val fill = Path()
                var started = false
                var lastX = 0f
                for (p in h.points) {
                    val v = pick(p) ?: continue
                    val px = x(p.time)
                    if (px > size.width * reveal) break
                    val py = y(v)
                    if (!started) { path.moveTo(px, py); fill.moveTo(px, size.height); fill.lineTo(px, py); started = true }
                    else { path.lineTo(px, py); fill.lineTo(px, py) }
                    lastX = px
                }
                if (!started) continue
                fill.lineTo(lastX, size.height); fill.close()
                drawPath(fill, Brush.verticalGradient(listOf(color.copy(alpha = 0.22f), Color.Transparent)))
                drawPath(path, color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
        }
        Row(Modifier.fillMaxWidth()) {
            Text(fmtTime.format(Date(t0)), style = MaterialTheme.typography.labelSmall, color = axis)
            Spacer(Modifier.weight(1f))
            Text("max ${fmt(max)} ${h.unit}", style = MaterialTheme.typography.labelSmall, color = axis)
            Spacer(Modifier.weight(1f))
            Text(fmtTime.format(Date(t1)), style = MaterialTheme.typography.labelSmall, color = axis)
        }
    }
}
