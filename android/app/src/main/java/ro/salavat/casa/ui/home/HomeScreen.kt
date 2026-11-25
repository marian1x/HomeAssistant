package ro.salavat.casa.ui.home

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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Category
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.data.category
import ro.salavat.casa.data.controllable
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.houseFloorOrder
import ro.salavat.casa.ui.components.AnimatedNumber
import ro.salavat.casa.ui.components.EnergyFlow
import ro.salavat.casa.ui.components.Flows
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.Ring
import ro.salavat.casa.ui.devices.DeviceTile
import ro.salavat.casa.ui.theme.Energy

/** "Casa acum": one factual sentence from live readings (port of src/brief.ts spirit). */
fun brief(f: Flows): String {
    val parts = ArrayList<String>()
    val solar = f.solar
    val load = f.load
    if (solar != null && solar > 0.05) parts += "Panourile dau ${fmt(solar)} kW"
    if (load != null) parts += "casa consumă ${fmt(load)} kW"
    val grid = f.gridNet
    when {
        grid == null -> {}
        grid > 0.05 -> parts += "din rețea vin ${fmt(grid)} kW"
        grid < -0.05 -> parts += "injectăm ${fmt(-grid)} kW"
    }
    f.soc?.let { parts += "bateria e la ${fmt(it, 0)}%" }
    if (parts.isEmpty()) return "Aștept citiri de la casă."
    return parts.joinToString(", ").replaceFirstChar { it.uppercase() } + "."
}

@Composable
fun HomeScreen(s: Snapshot, padding: PaddingValues, onOpen: (Device) -> Unit) {
    val flows = Flows.of(s)
    val all = remember(s) { buildDevices(s).filter { controllable(it) } }
    val floors = remember(s) { houseFloorOrder(s).filter { f -> all.any { it.floor == f } } }
    var floor by rememberSaveable { mutableStateOf<String?>(null) }
    var room by rememberSaveable { mutableStateOf<String?>(null) }
    var cat by rememberSaveable { mutableStateOf<String?>(null) }
    val inFloor = all.filter { floor == null || it.floor == floor }
    val rooms = inFloor.map { it.area }.distinct()
    val shown = inFloor.filter { (room == null || it.area == room) && (cat == null || category(it).key == cat) }
    val cats = Category.entries.filter { c -> inFloor.any { category(it) == c && (room == null || it.area == room) } }

    LazyVerticalGrid(
        columns = GridCells.Adaptive(158.dp),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(span = { GridItemSpan(maxLineSpan) }) {
            Column(Modifier.padding(top = 4.dp, bottom = 4.dp)) {
                Text("Casa acum", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                Text(brief(flows), style = MaterialTheme.typography.headlineSmall)
            }
        }
        item(span = { GridItemSpan(maxLineSpan) }) {
            GlassCard(padding = 8.dp) { EnergyFlow(flows) }
        }
        item(span = { GridItemSpan(maxLineSpan) }) { IndependenceCard(s) }
        item(span = { GridItemSpan(maxLineSpan) }) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Dispozitive", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
                ChipRow(listOf(null to "Toată casa") + floors.map { it to it }, floor) { floor = it; room = null }
                if (rooms.size > 1) ChipRow(listOf(null to "Toate camerele") + rooms.map { it to it }, room) { room = it }
                ChipRow(listOf(null to "Toate") + cats.map { it.key to it.label }, cat) { cat = it }
            }
        }
        items(shown, key = { it.id }) { d -> DeviceTile(d, s.user, onOpen = { onOpen(d) }) }
        if (shown.isEmpty()) item(span = { GridItemSpan(maxLineSpan) }) {
            Text("Niciun dispozitiv controlabil aici.", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(16.dp))
        }
    }
}

@Composable
private fun ChipRow(options: List<Pair<String?, String>>, selected: String?, onSelect: (String?) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(options, key = { it.first ?: "__all" }) { (key, label) ->
            FilterChip(selected = selected == key, onClick = { onSelect(key) }, label = { Text(label) })
        }
    }
}

/** Today's independence = 1 - import/consumption, from the Deye counters (a fact, not a forecast). */
@Composable
private fun IndependenceCard(s: Snapshot) {
    val imported = s.value("importToday")
    val load = s.value("loadToday")
    val solarToday = s.value("solarToday")
    val independence = if (imported != null && load != null && load > 0) (1 - imported / load).coerceIn(0.0, 1.0) else null
    GlassCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ring(independence?.toFloat(), Energy.load) {
                Text(independence?.let { "${fmt(it * 100, 0)}%" } ?: "--", style = MaterialTheme.typography.titleLarge)
            }
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Independență energetică azi", style = MaterialTheme.typography.titleMedium)
                Stat("Produs", solarToday, Energy.solar)
                Stat("Consumat", load, Energy.load)
                Stat("Din rețea", imported, Energy.grid)
            }
        }
    }
}

@Composable
private fun Stat(label: String, kwh: Double?, color: androidx.compose.ui.graphics.Color) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        AnimatedNumber(kwh, " kWh", style = MaterialTheme.typography.bodyLarge, color = color)
    }
    Spacer(Modifier.height(0.dp))
}
