package ro.salavat.casa.ui.tesla

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ElectricCar
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.stateLabel
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.Ring
import ro.salavat.casa.ui.theme.Energy
import java.time.Duration
import java.time.OffsetDateTime

/**
 * Read-only Tesla page: shows the cached HA states only. No commands, no wake-up,
 * no Force Data Update, no polling (those would cost API quota and wake the car).
 */
@Composable
fun TeslaScreen(s: Snapshot, padding: PaddingValues) {
    val car = s.states.values.filter { it.id.contains("salavat_t3") && it.domain in setOf("sensor", "binary_sensor", "device_tracker", "number", "lock", "climate", "switch") }
        .sortedBy { it.friendly }
    val battery = s.states["sensor.salavat_t3_battery"]?.number
    val range = car.firstOrNull { it.id.contains("range") && it.domain == "sensor" }
    val charger = s.binding("tesla")
    val newest = car.mapNotNull { it.lastUpdated?.let { t -> runCatching { OffsetDateTime.parse(t) }.getOrNull() } }.maxOrNull()
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Tesla", style = MaterialTheme.typography.headlineMedium)
        GlassCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Ring(battery?.toFloat()?.div(100f), Energy.tesla, size = 116.dp) {
                    Text(battery?.let { "${fmt(it, 0)}%" } ?: "--", style = MaterialTheme.typography.headlineSmall)
                }
                Spacer(Modifier.width(18.dp))
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.ElectricCar, null, tint = Energy.tesla)
                        Spacer(Modifier.width(6.dp))
                        Text("Model 3", style = MaterialTheme.typography.titleMedium)
                    }
                    Text("Autonomie ${range?.let { stateLabel(it) } ?: "--"}")
                    Text("Încărcare ${charger?.let { stateLabel(it) } ?: "--"}", color = Energy.tesla)
                    Text(
                        newest?.let { "Ultima citire acum ${ago(it)}" } ?: "Fără citiri",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (car.isEmpty()) {
            Text("Nu există date Tesla în HA momentan.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else GlassCard {
            Text("Stare", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(6.dp))
            car.forEach { e ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text(e.friendly.removePrefix("Salavat T3 "), Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(stateLabel(e), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        Text(
            "Doar citire: aplicația nu trezește mașina și nu trimite comenzi Tesla.",
            style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private fun ago(t: OffsetDateTime): String {
    val m = Duration.between(t, OffsetDateTime.now()).toMinutes().coerceAtLeast(0)
    return when {
        m < 1 -> "câteva secunde"
        m < 60 -> "$m min"
        m < 48 * 60 -> "${m / 60} h"
        else -> "${m / 1440} zile"
    }
}
