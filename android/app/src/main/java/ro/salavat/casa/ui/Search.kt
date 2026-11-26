package ro.salavat.casa.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.data.deviceReading
import ro.salavat.casa.ui.devices.icon
import java.text.Normalizer

private data class Hit(val title: String, val subtitle: String, val icon: ImageVector, val keywords: String, val go: (Nav) -> Unit)

private fun plain(s: String) = Normalizer.normalize(s.lowercase(), Normalizer.Form.NFD).replace(Regex("\\p{M}"), "")

/** Quick jump (the web's Ctrl+K palette): pages, energy details and every device, diacritics-insensitive. */
@Composable
fun SearchDialog(s: Snapshot, onDismiss: () -> Unit) {
    val nav = LocalNav.current
    var query by remember { mutableStateOf("") }
    val hits = remember(s) {
        val pages = listOf(
            Hit("Acasă", "Pagină", Tab.HOME.icon, "home acasa favorite") { it.go(Tab.HOME) },
            Hit("Energie", "Pagină", Tab.ENERGY.icon, "energie istoric") { it.go(Tab.ENERGY) },
            Hit("Invertor", "Producție solară, faze", Tab.ENERGY.icon, "invertor solar panouri faze deye pv") { it.go(Tab.ENERGY); it.push(Sub.Inverter) },
            Hit("Baterie", "Celule, BMS, istoric", Tab.ENERGY.icon, "baterie bms celule soc") { it.go(Tab.ENERGY); it.push(Sub.Battery) },
            Hit("Consum casă", "Consumatori, faze", Tab.HOME.icon, "casa consum consumatori") { it.go(Tab.ENERGY); it.push(Sub.House) },
            Hit("Rețea", "Import, injecție, tarife", Tab.ENERGY.icon, "retea import export injectie tarif pret") { it.go(Tab.ENERGY); it.push(Sub.Grid) },
            Hit("Politică și profile", "Iarnă, vară, parametri", Tab.SETTINGS.icon, "politica profile iarna vara parametri configurare") { it.go(Tab.ENERGY); it.push(Sub.Policy) },
            Hit("Tesla", "Comenzi, încărcări, deplasări", Tab.TESLA.icon, "tesla masina incarcare deplasari") { it.go(Tab.TESLA) },
            Hit("Dispozitive", "Aranjare, căutare", Tab.DEVICES.icon, "dispozitive aranjeaza ordine") { it.go(Tab.DEVICES) },
            Hit("Setări", "Cont, actualizări", Tab.SETTINGS.icon, "setari actualizare cont parola") { it.go(Tab.SETTINGS) },
        )
        pages + buildDevices(s).filter { !it.pending }.map { d ->
            Hit(d.name, "${d.area} · ${deviceReading(d)}", icon(d), "${d.area} ${d.manufacturer} ${d.floor}") { it.open(d.id) }
        }
    }
    val q = plain(query.trim())
    val shown = if (q.isEmpty()) hits.take(10) else hits.filter { plain(it.title + " " + it.keywords).contains(q) }.take(30)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth(), placeholder = { Text("Caută pagini și dispozitive") },
                leadingIcon = { Icon(Icons.Rounded.Search, null) }, singleLine = true)
        },
        text = {
            LazyColumn(Modifier.heightIn(max = 420.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                items(shown, key = { it.title + it.subtitle }) { h ->
                    Row(Modifier.fillMaxWidth().clickable { h.go(nav); onDismiss() }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(h.icon, null, tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(h.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(h.subtitle, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                        }
                        Icon(Icons.Rounded.ChevronRight, null)
                    }
                }
                if (shown.isEmpty()) item { Text("Niciun rezultat.") }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Închide") } },
    )
}
