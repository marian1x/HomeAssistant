package ro.salavat.casa.ui.devices

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bed
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.ChildCare
import androidx.compose.material.icons.rounded.ElectricCar
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Kitchen
import androidx.compose.material.icons.rounded.Lightbulb
import androidx.compose.material.icons.rounded.Power
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.Thermostat
import androidx.compose.material.icons.rounded.Tv
import androidx.compose.material.icons.rounded.WaterDrop
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material.icons.rounded.Weekend
import androidx.compose.material.icons.rounded.Work
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.ViewDef
import ro.salavat.casa.ui.LocalCommands

val VIEW_ICONS: List<Pair<String, ImageVector>> = listOf(
    "star" to Icons.Rounded.Star, "home" to Icons.Rounded.Home, "sofa" to Icons.Rounded.Weekend, "bed" to Icons.Rounded.Bed,
    "kitchen" to Icons.Rounded.Kitchen, "light" to Icons.Rounded.Lightbulb, "climate" to Icons.Rounded.Thermostat, "power" to Icons.Rounded.Power,
    "car" to Icons.Rounded.ElectricCar, "sun" to Icons.Rounded.WbSunny, "moon" to Icons.Rounded.Bedtime, "shield" to Icons.Rounded.Shield,
    "water" to Icons.Rounded.WaterDrop, "media" to Icons.Rounded.Tv, "child" to Icons.Rounded.ChildCare, "work" to Icons.Rounded.Work,
)

fun viewIcon(key: String) = VIEW_ICONS.firstOrNull { it.first == key }?.second ?: Icons.Rounded.Star

private fun slug(name: String, taken: Set<String>): String {
    val base = java.text.Normalizer.normalize(name.lowercase(), java.text.Normalizer.Form.NFD)
        .replace(Regex("\\p{M}"), "").replace(Regex("[^a-z0-9]+"), "-").trim('-').take(32).ifBlank { "vedere" }
    var id = base
    var n = 2
    while (id in taken) id = "$base-${n++}"
    return id
}

/**
 * Create or edit a named view ("Seara", "Copii"…): a user-chosen set of devices shown as a
 * tab on Home. Saved in the user's layout on the server, so the browser shows the same.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ViewEditor(view: ViewDef?, devices: List<Device>, views: List<ViewDef>, onDone: () -> Unit) {
    val commands = LocalCommands.current
    var name by remember { mutableStateOf(view?.name ?: "") }
    var icon by remember { mutableStateOf(view?.icon ?: "star") }
    val items = remember { mutableStateListOf<String>().apply { addAll(view?.items ?: emptyList()) } }
    var query by remember { mutableStateOf("") }
    val q = query.trim().lowercase()
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text(if (view == null) "Vedere nouă" else "Editează vederea") },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it.take(40) }, label = { Text("Nume") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    VIEW_ICONS.forEach { (key, vector) -> FilterChip(icon == key, { icon = key }, label = { Icon(vector, key, Modifier.size(18.dp)) }) }
                }
                OutlinedTextField(query, { query = it }, label = { Text("Caută dispozitive") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Text("${items.size} dispozitive alese", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                devices.filter { q.isEmpty() || it.name.lowercase().contains(q) || it.area.lowercase().contains(q) }.forEach { d ->
                    Row(Modifier.fillMaxWidth().clickable { if (d.id in items) items.remove(d.id) else items.add(d.id) }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(d.id in items, { on -> if (on) items.add(d.id) else items.remove(d.id) })
                        Column(Modifier.weight(1f)) {
                            Text(d.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(d.area, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && (view != null || views.size < 12), onClick = {
                val saved = ViewDef(view?.id ?: slug(name, views.map { it.id }.toSet()), name.trim(), icon, items.distinct().take(200))
                commands.layout { l -> l.copy(views = if (view == null) l.views + saved else l.views.map { if (it.id == view.id) saved else it }) }
                onDone()
            }) { Text("Salvează") }
        },
        dismissButton = {
            Row {
                if (view != null) TextButton(onClick = {
                    commands.layout { l -> l.copy(views = l.views.filter { it.id != view.id }) }
                    onDone()
                }) { Text("Șterge", color = MaterialTheme.colorScheme.error) }
                TextButton(onClick = onDone) { Text("Renunță") }
            }
        },
    )
}
