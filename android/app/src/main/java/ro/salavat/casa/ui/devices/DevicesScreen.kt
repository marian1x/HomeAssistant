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
import androidx.compose.material.icons.rounded.ArrowDownward
import androidx.compose.material.icons.rounded.ArrowUpward
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.SwapVert
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Category
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.arrange
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.data.category
import ro.salavat.casa.data.deviceReading
import ro.salavat.casa.data.groupOrder
import ro.salavat.casa.data.houseFloorOrder
import ro.salavat.casa.data.move
import ro.salavat.casa.ui.LocalCommands
import ro.salavat.casa.ui.LocalNav
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.theme.Energy

private val SORTS = listOf("default" to "Implicit", "manual" to "Ordinea mea", "usage" to "Cele mai folosite")
private val GROUPINGS = listOf("room" to "Cameră", "category" to "Categorie", "none" to "Listă")

/**
 * Full inventory: search, floor filter, grouping (room / category / flat), the user's
 * order (same layout as the web's "Aranjează", saved on the server) and an arrange mode.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DevicesScreen(s: Snapshot, padding: PaddingValues) {
    val nav = LocalNav.current
    val commands = LocalCommands.current
    val layout = s.layout
    var usage by remember { mutableStateOf<Map<String, Int>>(emptyMap()) }
    LaunchedEffect(layout.sort) { if (layout.sort == "usage") usage = runCatching { commands.repo.usage() }.getOrDefault(emptyMap()) }
    val all = remember(s, usage) { arrange(buildDevices(s), layout, usage) }
    var query by rememberSaveable { mutableStateOf("") }
    var floor by rememberSaveable { mutableStateOf<String?>(null) }
    var offline by rememberSaveable { mutableStateOf(false) }
    var grouping by rememberSaveable { mutableStateOf("room") }
    var arranging by rememberSaveable { mutableStateOf(false) }
    val floors = remember(s) { houseFloorOrder(s).filter { f -> all.any { it.floor == f } } }
    val q = query.trim().lowercase()
    val shown = all.filter { d ->
        (floor == null || d.floor == floor) &&
            (offline || (d.primary.valid && !d.pending)) &&
            (q.isEmpty() || d.name.lowercase().contains(q) || d.area.lowercase().contains(q) || d.manufacturer.lowercase().contains(q))
    }
    val groups: List<Pair<String, List<Device>>> = when (grouping) {
        "category" -> groupOrder(layout).mapNotNull { key ->
            val c = Category.entries.first { it.key == key }
            shown.filter { category(it) == c }.takeIf { it.isNotEmpty() }?.let { c.label to it }
        }
        "none" -> listOf("" to shown)
        else -> shown.groupBy { it.area }.toList()
    }
    val ids = shown.map { it.id }

    fun step(d: Device, by: Int) {
        val at = ids.indexOf(d.id) + by
        if (at < 0 || at >= ids.size) return
        commands.layout { l -> l.copy(sort = "manual", order = move(l.order.ifEmpty { all.map { it.id } }, ids, d.id, at)) }
    }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Dispozitive", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.weight(1f))
                if (arranging) FilledTonalButton(onClick = { arranging = false }) { Icon(Icons.Rounded.Check, null); Spacer(Modifier.width(4.dp)); Text("Gata") }
                else IconButton(onClick = { arranging = true }) { Icon(Icons.Rounded.SwapVert, "Aranjează") }
            }
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
            Spacer(Modifier.size(6.dp))
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                GROUPINGS.forEachIndexed { i, (key, label) ->
                    SegmentedButton(grouping == key, { grouping = key }, SegmentedButtonDefaults.itemShape(i, GROUPINGS.size)) { Text(label) }
                }
            }
            if (arranging) {
                Spacer(Modifier.size(6.dp))
                Text("Ordinea se salvează pentru contul tău, pe toate dispozitivele (și în browser).",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(SORTS) { (key, label) -> FilterChip(layout.sort == key, { commands.layout { it.copy(sort = key) } }, { Text(label) }) }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(offline, { offline = it })
                Text("Arată și indisponibile / neintegrate", style = MaterialTheme.typography.bodyMedium)
            }
        }
        groups.forEach { (title, list) ->
            if (title.isNotEmpty()) item(key = "h-$title") {
                Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f))
                    if (arranging && grouping == "category") {
                        val key = Category.entries.first { it.label == title }.key
                        IconButton(onClick = { commands.layout { l -> l.copy(groups = shiftGroup(l.groups, key, -1)) } }) { Icon(Icons.Rounded.ArrowUpward, "Grup mai sus") }
                        IconButton(onClick = { commands.layout { l -> l.copy(groups = shiftGroup(l.groups, key, 1)) } }) { Icon(Icons.Rounded.ArrowDownward, "Grup mai jos") }
                    }
                }
            }
            items(list, key = { "d-$title-" + it.id }) { d ->
                val favorite = d.id in layout.favorites
                GlassCard(onClick = if (arranging) null else ({ nav.open(d.id) }), padding = 14.dp) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(40.dp).background(accent(d).copy(alpha = 0.16f), CircleShape), contentAlignment = Alignment.Center) {
                            Icon(icon(d), null, tint = accent(d))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(d.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                                if (favorite) Icon(Icons.Rounded.Star, "Favorit", Modifier.padding(start = 4.dp).size(14.dp), tint = Energy.solar)
                            }
                            Text(listOf(d.manufacturer, if (grouping == "room") d.floor else d.area).filter { it.isNotBlank() }.joinToString(" · "),
                                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (arranging) {
                            val at = ids.indexOf(d.id)
                            Text("${at + 1}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            IconButton(onClick = { step(d, -1) }, enabled = at > 0) { Icon(Icons.Rounded.ArrowUpward, "Mută ${d.name} mai sus") }
                            IconButton(onClick = { step(d, 1) }, enabled = at < ids.lastIndex) { Icon(Icons.Rounded.ArrowDownward, "Mută ${d.name} mai jos") }
                        } else Text(deviceReading(d), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                    }
                }
            }
        }
        if (shown.isEmpty()) item { Text("Niciun rezultat.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

private fun shiftGroup(saved: List<String>, group: String, by: Int): List<String> {
    val order = groupOrder(ro.salavat.casa.data.Layout(groups = saved)).toMutableList()
    val from = order.indexOf(group)
    val to = from + by
    if (from < 0 || to < 0 || to >= order.size) return order
    order.removeAt(from)
    order.add(to, group)
    return order
}
