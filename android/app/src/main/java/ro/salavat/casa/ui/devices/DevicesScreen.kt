package ro.salavat.casa.ui.devices

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.data.deviceReading
import ro.salavat.casa.data.houseFloorOrder
import ro.salavat.casa.ui.components.GlassCard

/** Full inventory with floor filter and search; offline devices hidden unless asked. */
@Composable
fun DevicesScreen(s: Snapshot, padding: PaddingValues, onOpen: (Device) -> Unit) {
    val all = remember(s) { buildDevices(s) }
    var query by rememberSaveable { mutableStateOf("") }
    var floor by rememberSaveable { mutableStateOf<String?>(null) }
    var offline by rememberSaveable { mutableStateOf(false) }
    val floors = remember(s) { houseFloorOrder(s).filter { f -> all.any { it.floor == f } } }
    val q = query.trim().lowercase()
    val shown = all.filter { d ->
        (floor == null || d.floor == floor) &&
            (offline || (d.primary.valid && !d.pending)) &&
            (q.isEmpty() || d.name.lowercase().contains(q) || d.area.lowercase().contains(q) || d.manufacturer.lowercase().contains(q))
    }
    val grouped = shown.groupBy { it.area }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text("Dispozitive", style = MaterialTheme.typography.headlineMedium)
            OutlinedTextField(
                query, { query = it }, Modifier.fillMaxWidth().padding(top = 8.dp),
                placeholder = { Text("Caută după nume, cameră, producător") },
                leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true, shape = RoundedCornerShape(18.dp),
            )
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item { FilterChip(floor == null, { floor = null }, { Text("Toate nivelurile") }) }
                items(floors) { f -> FilterChip(floor == f, { floor = f }, { Text(f) }) }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(offline, { offline = it })
                Text("Arată și indisponibile / neintegrate", style = MaterialTheme.typography.bodyMedium)
            }
        }
        grouped.forEach { (area, list) ->
            item(key = "h-$area") {
                Text(area, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 8.dp))
            }
            items(list, key = { "d-" + it.id }) { d ->
                GlassCard(onClick = { onOpen(d) }, padding = 14.dp) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(40.dp).background(accent(d).copy(alpha = 0.16f), CircleShape), contentAlignment = Alignment.Center) {
                            Icon(icon(d), null, tint = accent(d))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(d.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(listOf(d.manufacturer, d.floor).filter { it.isNotBlank() }.joinToString(" · "), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text(deviceReading(d), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                    }
                }
            }
        }
        if (shown.isEmpty()) item { Text("Niciun rezultat.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
