package ro.salavat.casa.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Category
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.arrange
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.data.category
import ro.salavat.casa.data.controllable
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.houseFloorOrder
import ro.salavat.casa.ui.LocalNav
import ro.salavat.casa.ui.Sub
import ro.salavat.casa.ui.Tab
import ro.salavat.casa.ui.components.AnimatedNumber
import ro.salavat.casa.ui.components.EnergyFlow
import ro.salavat.casa.ui.components.Flows
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.Ring
import ro.salavat.casa.ui.devices.DeviceTile
import ro.salavat.casa.ui.devices.ViewEditor
import ro.salavat.casa.ui.devices.viewIcon
import ro.salavat.casa.ui.policy.profileIcon
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

private const val ALL = "__all"
private const val FAVORITES = "__fav"

@Composable
fun HomeScreen(s: Snapshot, padding: PaddingValues) {
    val nav = LocalNav.current
    val flows = Flows.of(s)
    val layout = s.layout
    val every = remember(s) { buildDevices(s) }
    val all = remember(s) { arrange(every.filter { controllable(it) }, layout) }
    val floors = remember(s) { houseFloorOrder(s).filter { f -> all.any { it.floor == f } } }
    var tab by rememberSaveable { mutableStateOf(if (layout.favorites.isNotEmpty()) FAVORITES else ALL) }
    var floor by rememberSaveable { mutableStateOf<String?>(null) }
    var room by rememberSaveable { mutableStateOf<String?>(null) }
    var cat by rememberSaveable { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<String?>(null) }   // view id, "" = new
    val view = layout.views.firstOrNull { it.id == tab }
    if (tab != ALL && tab != FAVORITES && view == null) tab = ALL

    val shown: List<Device> = when {
        tab == FAVORITES -> layout.favorites.mapNotNull { id -> every.firstOrNull { it.id == id } }
        view != null -> view.items.mapNotNull { id -> every.firstOrNull { it.id == id } }
        else -> all.filter { (floor == null || it.floor == floor) && (room == null || it.area == room) && (cat == null || category(it).key == cat) }
    }
    val inFloor = all.filter { floor == null || it.floor == floor }
    val rooms = inFloor.map { it.area }.distinct()
    val cats = Category.entries.filter { c -> inFloor.any { category(it) == c && (room == null || it.area == room) } }
    val tips = remember(s) { insights(s, flows) }
    val goTo: (String) -> Unit = { key ->
        when (key) {
            "solar" -> nav.push(Sub.Inverter)
            "battery" -> nav.push(Sub.Battery)
            "house" -> nav.push(Sub.House)
            "grid" -> nav.push(Sub.Grid)
            "policy" -> nav.push(Sub.Policy)
            "tesla" -> nav.go(Tab.TESLA)
            "boiler" -> nav.open("boiler")
        }
    }

    LazyVerticalGrid(
        columns = GridCells.Adaptive(158.dp),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(span = { GridItemSpan(maxLineSpan) }) {
            Column(Modifier.padding(top = 4.dp, bottom = 4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Casa acum", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f))
                    s.activeProfile?.let { a -> s.profiles.firstOrNull { it.id == a.id } }?.let { p ->
                        AssistChip(onClick = { nav.push(Sub.Policy) }, label = { Text("Profil ${p.name}") }, leadingIcon = { Icon(profileIcon(p.icon), null, Modifier.size(16.dp)) })
                    }
                }
                Text(brief(flows), style = MaterialTheme.typography.headlineSmall)
            }
        }
        if (tips.isNotEmpty()) item(span = { GridItemSpan(maxLineSpan) }) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                tips.forEach { t ->
                    val color = when (t.tone) { Tone.WARN -> MaterialTheme.colorScheme.error; Tone.GOOD -> Energy.load; Tone.INFO -> Energy.grid }
                    GlassCard(
                        onClick = t.target?.let { target -> {
                            when (target) {
                                is Target.Detail -> goTo(target.key)
                                is Target.Tab -> Tab.of(target.route)?.let { nav.go(it) }
                            }
                        } },
                        tint = color.copy(alpha = 0.10f), padding = 12.dp,
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(when (t.tone) { Tone.WARN -> Icons.Rounded.Warning; Tone.GOOD -> Icons.Rounded.CheckCircle; Tone.INFO -> Icons.Rounded.Info }, null, tint = color)
                            Spacer(Modifier.width(10.dp))
                            Text(t.text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
        }
        item(span = { GridItemSpan(maxLineSpan) }) {
            GlassCard(padding = 8.dp) {
                EnergyFlow(flows, onNode = goTo)
                // The bottom nodes' captions hang below the drawing: keep the hint clear of them.
                Text("Atinge un element pentru detalii", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 22.dp, bottom = 4.dp))
            }
        }
        item(span = { GridItemSpan(maxLineSpan) }) { IndependenceCard(s) }
        item(span = { GridItemSpan(maxLineSpan) }) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Dispozitive", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    item { FilterChip(tab == ALL, { tab = ALL }, { Text("Toate") }) }
                    item {
                        FilterChip(tab == FAVORITES, { tab = FAVORITES }, { Text("Favorite") },
                            leadingIcon = { Icon(Icons.Rounded.Star, null, Modifier.size(16.dp), tint = Energy.solar) })
                    }
                    items(layout.views, key = { it.id }) { v ->
                        FilterChip(tab == v.id, { tab = v.id }, { Text(v.name) }, leadingIcon = { Icon(viewIcon(v.icon), null, Modifier.size(16.dp)) })
                    }
                    item { AssistChip(onClick = { editing = "" }, label = { Text("Vedere") }, leadingIcon = { Icon(Icons.Rounded.Add, null, Modifier.size(16.dp)) }) }
                }
                when {
                    tab == ALL -> {
                        ChipRow(listOf(null to "Toată casa") + floors.map { it to it }, floor) { floor = it; room = null }
                        if (rooms.size > 1) ChipRow(listOf(null to "Toate camerele") + rooms.map { it to it }, room) { room = it }
                        ChipRow(listOf(null to "Toate") + cats.map { it.key to it.label }, cat) { cat = it }
                    }
                    view != null -> Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("${view.items.size} dispozitive", Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        TextButton(onClick = { editing = view.id }) { Icon(Icons.Rounded.Edit, null, Modifier.size(16.dp)); Spacer(Modifier.width(4.dp)); Text("Editează") }
                    }
                }
            }
        }
        items(shown, key = { it.id }) { d -> DeviceTile(d, s.user, onOpen = { nav.open(d.id) }) }
        if (shown.isEmpty()) item(span = { GridItemSpan(maxLineSpan) }) {
            Text(
                when {
                    tab == FAVORITES -> "Nicio favorită încă. Deschide un dispozitiv și atinge steaua."
                    view != null -> "Vederea e goală. Atinge Editează ca să alegi dispozitive."
                    else -> "Niciun dispozitiv controlabil aici."
                },
                color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(16.dp),
            )
        }
    }
    editing?.let { id ->
        ViewEditor(layout.views.firstOrNull { it.id == id }, every.filter { !it.pending }, layout.views) { editing = null }
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
private fun Stat(label: String, kwh: Double?, color: Color) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        AnimatedNumber(kwh, " kWh", style = MaterialTheme.typography.bodyLarge, color = color)
    }
}
