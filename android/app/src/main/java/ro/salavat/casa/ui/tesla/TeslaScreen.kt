package ro.salavat.casa.ui.tesla

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AcUnit
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.BatteryChargingFull
import androidx.compose.material.icons.rounded.Campaign
import androidx.compose.material.icons.rounded.EvStation
import androidx.compose.material.icons.rounded.FlashlightOn
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.LockOpen
import androidx.compose.material.icons.rounded.Map
import androidx.compose.material.icons.rounded.PowerSettingsNew
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Charge
import ro.salavat.casa.data.Drive
import ro.salavat.casa.data.DriveDetail
import ro.salavat.casa.data.EntityState
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.TeslaLog
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.stateLabel
import ro.salavat.casa.ui.Commands
import ro.salavat.casa.ui.LocalCommands
import ro.salavat.casa.ui.LocalNav
import ro.salavat.casa.ui.Sub
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.KeyValue
import ro.salavat.casa.ui.components.Page
import ro.salavat.casa.ui.components.Ring
import ro.salavat.casa.ui.components.SectionTitle
import ro.salavat.casa.ui.components.Tile
import ro.salavat.casa.ui.devices.Pill
import ro.salavat.casa.ui.theme.Energy
import ro.salavat.casa.ui.theme.Numeric
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.roundToInt

private const val CAR = "salavat_t3"
private const val WAKE = "Comanda poate trezi mașina (consumă din bugetul API Tesla). Starea se schimbă când mașina confirmă."
private fun Snapshot.car(domain: String, key: String): EntityState? = states["$domain.${CAR}_$key"]
private fun Snapshot.carAll(domain: String) = states.values.filter { it.domain == domain && it.id.startsWith("$domain.${CAR}_") }.sortedBy { it.id }
private fun EntityState.short() = friendly.replace(Regex("^Salavat T3\\s*", RegexOption.IGNORE_CASE), "").ifBlank { id.substringAfter("${CAR}_") }

private val RO = Locale.forLanguageTag("ro")
private val TZ = TimeZone.getTimeZone("Europe/Bucharest")
private fun stamp(pattern: String, s: Long) = SimpleDateFormat(pattern, RO).apply { timeZone = TZ }.format(Date(s * 1000))
private fun duration(h: Double): String { val m = (h * 60).roundToInt(); return if (m < 60) "$m min" else "${m / 60} h ${"%02d".format(m % 60)}" }
private fun lei(v: Double?) = v?.let { "${fmt(it, 2)} lei" } ?: "--"

private enum class View(val label: String) { NOW("Acum"), CHARGES("Încărcări"), DRIVES("Deplasări"), STATS("Statistici") }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeslaScreen(s: Snapshot, repo: Repository, padding: PaddingValues) {
    var view by rememberSaveable { mutableStateOf(View.NOW) }
    var days by rememberSaveable { mutableIntStateOf(90) }
    var log by remember { mutableStateOf<Result<TeslaLog>?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val canControl = s.user?.canControl == true
    LaunchedEffect(view != View.NOW, days, reload) {
        if (view != View.NOW && canControl) { log = null; log = runCatching { repo.teslaLog(days) } }
    }
    Page(padding, "Tesla", "Model 3 · ${status(s)}") {
        PrimaryTabRow(selectedTabIndex = view.ordinal, containerColor = Color.Transparent) {
            View.entries.forEach { v -> Tab(view == v, { view = v }, text = { Text(v.label) }) }
        }
        if (view != View.NOW) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(30 to "30 zile", 90 to "90 zile", 365 to "1 an").forEach { (d, t) -> FilterChip(days == d, { days = d }, { Text(t) }) }
        }
        when {
            view == View.NOW -> Now(s)
            !canControl -> Text("Istoricul deplasărilor necesită rolul Control.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            log == null -> Text("Se încarcă jurnalul…", color = MaterialTheme.colorScheme.onSurfaceVariant)
            log!!.isFailure -> Text(log!!.exceptionOrNull()?.message ?: "Jurnalul Tesla nu este disponibil.", color = MaterialTheme.colorScheme.error)
            else -> {
                val l = log!!.getOrThrow()
                when (view) {
                    View.CHARGES -> Charges(l, canControl, repo) { reload++ }
                    View.DRIVES -> Drives(l)
                    else -> Stats(l, days)
                }
            }
        }
    }
}

private fun status(s: Snapshot): String {
    val telemetry = s.states["sensor.home_energy_policy_status"]?.attrs?.optJSONObject("telemetry")
    return when {
        telemetry?.optBoolean("live") == true -> "Live prin Fleet Telemetry"
        s.car("binary_sensor", "asleep")?.state == "on" -> "Adormită"
        s.car("binary_sensor", "online")?.state == "on" -> "Online"
        else -> "Stare memorată, fără trezire"
    }
}

// ------------------------------- Now -------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Now(s: Snapshot) {
    val battery = s.car("sensor", "battery")?.number
    val limit = s.car("number", "charge_limit")?.number
    val charging = s.car("binary_sensor", "charging")?.state == "on"
    val plugged = s.car("binary_sensor", "charger")?.state == "on"
    val tracker = s.car("device_tracker", "location_tracker")
    GlassCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ring(battery?.toFloat()?.div(100f), Energy.tesla, size = 116.dp) {
                Text(battery?.let { "${fmt(it, 0)}%" } ?: "--", style = MaterialTheme.typography.headlineSmall)
            }
            Spacer(Modifier.width(16.dp))
            Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text("Autonomie ${s.car("sensor", "range")?.let { stateLabel(it) } ?: "--"}", style = MaterialTheme.typography.titleMedium)
                Text("Limită în mașină ${limit?.let { fmt(it, 0) + "%" } ?: "--"}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Pill(when { charging -> "Se încarcă ${fmt(s.car("sensor", "charger_power")?.number, 1)} kW"; plugged -> "Conectată, nu încarcă"; else -> "Deconectată" },
                    if (charging) Energy.load else if (plugged) Energy.solar else MaterialTheme.colorScheme.onSurfaceVariant)
                Text(when (tracker?.state) { "home" -> "Acasă"; "not_home" -> "În deplasare"; null -> "Locație necunoscută"; else -> tracker.state },
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
    if (s.user?.canControl == true) {
        Controls(s)
        LimitCard(s)
    } else Text("Comenzile Tesla necesită rolul Control.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp), maxItemsInEachRow = 2) {
        val m = Modifier.weight(1f)
        Tile("Interior", s.car("sensor", "temperature_inside")?.number?.let { "${fmt(it)} °C" } ?: "--", Energy.grid, m)
        Tile("Exterior", s.car("sensor", "temperature_outside")?.number?.let { "${fmt(it)} °C" } ?: "--", Energy.grid, m)
        Tile("Kilometraj", s.car("sensor", "odometer")?.number?.let { "${fmt(it, 0)} km" } ?: "--", Energy.tesla, m)
        Tile("Ultima sesiune", s.car("sensor", "energy_added")?.number?.let { "${fmt(it)} kWh" } ?: "--", Energy.load, m)
    }
    val lat = tracker?.attrDouble("latitude")
    val lon = tracker?.attrDouble("longitude")
    val ctx = LocalContext.current
    if (lat != null && lon != null) OutlinedButton(onClick = {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("geo:$lat,$lon?q=$lat,$lon(Tesla)")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }, Modifier.fillMaxWidth()) { Icon(Icons.Rounded.Map, null); Spacer(Modifier.width(6.dp)); Text("Arată mașina pe hartă") }
    val other = s.states.values.filter { it.id.contains("${CAR}_") && it.domain in setOf("sensor", "binary_sensor") }.sortedBy { it.short() }
    if (other.isNotEmpty()) GlassCard {
        Text("Toate citirile", style = MaterialTheme.typography.titleMedium)
        other.forEach { KeyValue(it.short(), stateLabel(it)) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Controls(s: Snapshot) {
    val c = LocalCommands.current
    val charger = s.car("switch", "charger")
    val amps = s.car("number", "charging_amps")
    val climate = s.carAll("climate").firstOrNull()
    val doors = s.car("lock", "doors")
    val sentry = s.car("switch", "sentry_mode")
    GlassCard {
        Text("Comenzi", style = MaterialTheme.typography.titleMedium)
        Text("Fiecare comandă se confirmă și apare în jurnal. Poate trezi mașina.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(10.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            charger?.let { e ->
                val on = e.state == "on"
                Action(if (on) "Oprește încărcarea" else "Pornește încărcarea", Icons.Rounded.EvStation, e, c) {
                    c.confirm(e.id, if (on) "turn_off" else "turn_on", null, if (on) "Oprești încărcarea?" else "Pornești încărcarea?",
                        "Politica energetică trece Tesla pe control manual până a doua zi la ora configurată. $WAKE")
                }
            }
            doors?.let { e ->
                val locked = e.state == "locked"
                Action(if (locked) "Descuie" else "Încuie", if (locked) Icons.Rounded.LockOpen else Icons.Rounded.Lock, e, c) {
                    c.confirm(e.id, if (locked) "unlock" else "lock", null, if (locked) "Descui mașina?" else "Încui mașina?", WAKE)
                }
            }
            sentry?.let { e ->
                val on = e.state == "on"
                Action(if (on) "Oprește Sentry" else "Pornește Sentry", Icons.Rounded.Shield, e, c) {
                    c.confirm(e.id, if (on) "turn_off" else "turn_on", null, if (on) "Oprești Sentry?" else "Pornești Sentry?", WAKE)
                }
            }
            s.car("button", "flash_lights")?.let { e -> Action("Semnalizează", Icons.Rounded.FlashlightOn, e, c) { c.confirm(e.id, "press", null, "Aprinzi farurile scurt?", WAKE) } }
            s.car("button", "horn")?.let { e -> Action("Claxon", Icons.Rounded.Campaign, e, c) { c.confirm(e.id, "press", null, "Claxonezi?", WAKE) } }
            s.car("button", "wake_up")?.let { e -> Action("Trezește", Icons.Rounded.PowerSettingsNew, e, c) { c.confirm(e.id, "press", null, "Trezești mașina?", "Consumă din bugetul API și din baterie.") } }
        }
        amps?.let { AmpsControl(it, c) }
        climate?.let { ClimateControl(it, c) }
        val covers = s.carAll("cover")
        if (covers.isNotEmpty()) {
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("Deschideri", style = MaterialTheme.typography.titleSmall)
            covers.forEach { e ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${e.short()} · ${if (e.state == "open") "deschis" else if (e.state == "closed") "închis" else stateLabel(e)}", Modifier.weight(1f))
                    TextButton(enabled = e.id !in c.busy, onClick = { c.confirm(e.id, "open_cover", null, "Deschizi ${e.short()}?", WAKE) }) { Text("Deschide") }
                    TextButton(enabled = e.id !in c.busy, onClick = { c.confirm(e.id, "close_cover", null, "Închizi ${e.short()}?", WAKE) }) { Text("Închide") }
                }
            }
        }
        s.carAll("lock").filter { it.id != doors?.id }.forEach { e ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${e.short()} · ${if (e.state == "locked") "blocat" else "deblocat"}", Modifier.weight(1f))
                TextButton(enabled = e.id !in c.busy, onClick = {
                    val unlock = e.state == "locked"
                    c.confirm(e.id, if (unlock) "unlock" else "lock", null, if (unlock) "Deblochezi ${e.short()}?" else "Blochezi ${e.short()}?", WAKE)
                }) { Text(if (e.state == "locked") "Deblochează" else "Blochează") }
            }
        }
        val selects = s.carAll("select")
        if (selects.isNotEmpty()) {
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("Încălzire scaune și volan", style = MaterialTheme.typography.titleSmall)
            selects.forEach { e ->
                Text(e.short(), style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 6.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    e.attrList("options").forEach { o ->
                        FilterChip(e.state == o, { if (e.state != o) c.confirm(e.id, "select_option", o, "${e.short()}: $o?", WAKE) }, { Text(o) }, enabled = e.id !in c.busy)
                    }
                }
            }
        }
        val extra = s.carAll("switch").filter { it.id != charger?.id && it.id != sentry?.id && listOf("polling", "valet").none { w -> w in it.id } }
        extra.forEach { e ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(e.short(), Modifier.weight(1f))
                Switch(e.state == "on", { on -> c.confirm(e.id, if (on) "turn_on" else "turn_off", null, "${e.short()} ${if (on) "pornit" else "oprit"}?", WAKE) }, enabled = e.id !in c.busy)
            }
        }
        s.carAll("time").forEach { ScheduleRow(it, c) }
    }
}

@Composable
private fun Action(label: String, icon: ImageVector, e: EntityState, c: Commands, onClick: () -> Unit) {
    AssistChip(onClick = onClick, enabled = e.id !in c.busy && e.state != "unavailable", label = { Text(label) }, leadingIcon = { Icon(icon, null, Modifier.size(18.dp)) })
}

@Composable
private fun AmpsControl(e: EntityState, c: Commands) {
    val current = e.number ?: return
    val min = (e.attrDouble("min") ?: 0.0).toFloat()
    val max = (e.attrDouble("max") ?: 16.0).toFloat().coerceAtMost(48f)
    var draft by remember(e.id, current) { mutableFloatStateOf(current.toFloat()) }
    HorizontalDivider(Modifier.padding(vertical = 8.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Curent de încărcare", Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
        Text("${draft.roundToInt()} A", style = MaterialTheme.typography.titleMedium.merge(Numeric))
    }
    Slider(draft, { draft = it }, valueRange = min..max, steps = (max - min).toInt().coerceAtLeast(1) - 1)
    Text("~${fmt(draft * 230.0 * 3 / 1000, 1)} kW pe trei faze. Politica solară poate reajusta curentul cât timp controlează încărcarea.",
        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    if (draft.roundToInt() != current.roundToInt()) FilledTonalButton(onClick = {
        c.confirm(e.id, "set_value", draft.roundToInt(), "Setezi ${draft.roundToInt()} A?", WAKE)
    }, enabled = e.id !in c.busy) { Text("Aplică ${draft.roundToInt()} A") }
}

@Composable
private fun ClimateControl(e: EntityState, c: Commands) {
    val on = e.state != "off" && e.state != "unavailable"
    val target = e.attrDouble("temperature") ?: 21.0
    var draft by remember(e.id, target) { mutableStateOf(target) }
    HorizontalDivider(Modifier.padding(vertical = 8.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.AcUnit, null, tint = Energy.grid)
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text("Climatizare", style = MaterialTheme.typography.titleSmall)
            Text("Interior ${e.attrDouble("current_temperature")?.let { fmt(it) + " °C" } ?: "--"}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Switch(on, { want -> c.confirm(e.id, if (want) "turn_on" else "turn_off", null, if (want) "Pornești climatizarea?" else "Oprești climatizarea?", WAKE) }, enabled = e.id !in c.busy)
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        FilledIconButton(onClick = { draft = (draft - 0.5).coerceAtLeast(e.attrDouble("min_temp") ?: 15.0) }) { Icon(Icons.Rounded.Remove, "Scade") }
        Text("${fmt(draft)}°", style = MaterialTheme.typography.headlineSmall.merge(Numeric))
        FilledIconButton(onClick = { draft = (draft + 0.5).coerceAtMost(e.attrDouble("max_temp") ?: 28.0) }) { Icon(Icons.Rounded.Add, "Crește") }
        Spacer(Modifier.weight(1f))
        if (draft != target) TextButton(onClick = { c.confirm(e.id, "set_temperature", draft, "Setezi ${fmt(draft)}° în mașină?", WAKE) }) { Text("Aplică") }
    }
    val presets = e.attrList("preset_modes")
    if (presets.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        presets.forEach { p ->
            FilterChip(e.attrs.optString("preset_mode") == p, { c.confirm(e.id, "set_preset_mode", p, "Mod $p?", WAKE) }, { Text(if (p == "defrost") "Dezghețare" else p) })
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ScheduleRow(e: EntityState, c: Commands) {
    var open by remember { mutableStateOf(false) }
    val current = e.state.take(5)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.Schedule, null)
        Spacer(Modifier.width(8.dp))
        Text(e.short(), Modifier.weight(1f))
        TextButton(onClick = { open = true }, enabled = e.id !in c.busy) { Text(if (e.valid) current else "Setează") }
    }
    if (open) {
        val parts = current.split(":").mapNotNull { it.toIntOrNull() }
        val state = rememberTimePickerState(parts.getOrElse(0) { 23 }, parts.getOrElse(1) { 0 }, is24Hour = true)
        AlertDialog(
            onDismissRequest = { open = false },
            title = { Text(e.short()) },
            text = { TimePicker(state) },
            confirmButton = {
                TextButton(onClick = {
                    open = false
                    val t = "%02d:%02d".format(state.hour, state.minute)
                    c.confirm(e.id, "set_value", t, "${e.short()} la $t?", WAKE)
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { open = false }) { Text("Renunță") } },
        )
    }
}

@Composable
private fun LimitCard(s: Snapshot) {
    val c = LocalCommands.current
    val owner = s.states["sensor.home_energy_policy_status"]?.attrs?.optJSONObject("ev_limit")
    val native = s.car("number", "charge_limit")?.number
    val current = owner?.optInt("soc")?.takeIf { it > 0 } ?: native?.roundToInt() ?: 80
    var draft by remember(current) { mutableFloatStateOf(current.toFloat()) }
    val shown = draft.roundToInt()
    GlassCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.BatteryChargingFull, null, tint = Energy.tesla)
            Spacer(Modifier.width(8.dp))
            Text("Limita ta de încărcare", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            Text("$shown %", style = MaterialTheme.typography.titleLarge.merge(Numeric))
        }
        Slider(draft, { draft = it }, valueRange = 20f..100f, steps = 79)
        Text(if (shown < 50) "Sub 50%: mașina rămâne la 50%, iar acasă încărcarea se oprește la $shown% și se reia sub ${shown - 2}%." else "Se setează în mașină la următoarea citire, fără trezire.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        KeyValue("În mașină", native?.let { "${fmt(it, 0)} %" })
        KeyValue("Stare", owner?.optString("status")?.ifBlank { null })
        if (shown != current) FilledTonalButton(onClick = {
            c.confirmRun("Trimiți limita $shown%?", "Limita trece prin politica energetică și se aplică la următoarea citire a mașinii.", "tesla-limit",
                "Limita $shown% a fost salvată.") { c.repo.teslaLimit(shown) }
        }, enabled = "tesla-limit" !in c.busy) { Text("Setează $shown%") }
    }
}

// ------------------------------- Journal -------------------------------

@Composable
private fun Split(c: Charge) {
    val total = c.solar + c.battery + c.grid
    if (!c.home || total <= 0) {
        Text(if (!c.home) "Stație externă" else "Fără măsurare", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    Row(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(50))) {
        if (c.solar > 0) Box(Modifier.weight(c.solar.toFloat()).height(8.dp).background(Energy.solar))
        if (c.battery > 0) Box(Modifier.weight(c.battery.toFloat()).height(8.dp).background(Energy.battery))
        if (c.grid > 0) Box(Modifier.weight(c.grid.toFloat()).height(8.dp).background(Energy.grid))
    }
    Text("Solar ${fmt(c.solar / total * 100, 0)}% · baterie ${fmt(c.battery / total * 100, 0)}% · rețea ${fmt(c.grid / total * 100, 0)}%",
        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun Charges(log: TeslaLog, canControl: Boolean, repo: Repository, reload: () -> Unit) {
    var editing by remember { mutableStateOf<Charge?>(null) }
    val home = log.charges.filter { it.home }
    val measured = home.sumOf { it.solar + it.battery + it.grid }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Tile("Încărcări", "${log.charges.size}", Energy.tesla, Modifier.weight(1f), "${home.size} acasă")
        Tile("Energie", "${fmt(log.charges.sumOf { it.kwh })} kWh", Energy.load, Modifier.weight(1f))
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Tile("Cost", lei(log.charges.sumOf { it.cost ?: 0.0 }), Energy.grid, Modifier.weight(1f))
        Tile("Din solar acasă", if (measured > 0) "${fmt(home.sumOf { it.solar } / measured * 100, 0)} %" else "--", Energy.solar, Modifier.weight(1f))
    }
    log.activeCharge?.let { a ->
        Pill("Încărcare în curs: ${fmt(a.optDouble("added"), 1)} kWh, ${fmt(a.optDouble("start_soc"), 0)}% → ${fmt(a.optDouble("end_soc"), 0)}%", Energy.load)
    }
    if (log.charges.isEmpty()) Text("Nicio încărcare în perioada aleasă.", color = MaterialTheme.colorScheme.onSurfaceVariant)
    log.charges.forEach { c ->
        GlassCard(onClick = if (canControl) ({ editing = c }) else null, padding = 14.dp) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stamp("EEE d MMM", c.start), style = MaterialTheme.typography.titleSmall)
                    Text("${stamp("HH:mm", c.start)} – ${stamp("HH:mm", c.end)} · ${duration(c.hours)} · ${if (c.home) "Acasă" else c.note ?: "Stație"}",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("${fmt(c.kwh)} kWh", style = MaterialTheme.typography.titleSmall.merge(Numeric))
                    Text(lei(c.cost), style = MaterialTheme.typography.labelSmall)
                }
            }
            Spacer(Modifier.height(6.dp))
            Text("${fmt(c.startSoc, 0)}% → ${fmt(c.endSoc, 0)}% · max ${fmt(c.maxKw)} kW", style = MaterialTheme.typography.bodySmall)
            Split(c)
        }
    }
    editing?.let { c -> PriceDialog(c, repo, onDone = { editing = null }, onSaved = reload) }
}

@Composable
private fun PriceDialog(c: Charge, repo: Repository, onDone: () -> Unit, onSaved: () -> Unit) {
    val commands = LocalCommands.current
    var price by remember { mutableStateOf(c.price?.toString() ?: "") }
    var note by remember { mutableStateOf(c.note ?: "") }
    val value = price.replace(',', '.').trim().let { if (it.isEmpty()) null else it.toDoubleOrNull() }
    val ok = price.isBlank() || (value != null && value in 0.0..20.0)
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text("Preț încărcare ${stamp("d MMM HH:mm", c.start)}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(price, { price = it }, label = { Text("Preț (lei/kWh)") }, placeholder = { Text(if (c.home) "tarif casă" else "ex. 2,35") },
                    isError = !ok, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                OutlinedTextField(note, { note = it.take(120) }, label = { Text("Notă") }, placeholder = { Text("ex. Kaufland, Supercharger") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(enabled = ok, onClick = {
                commands.launch("price-${c.id}", "Preț salvat.") { repo.chargePrice(c.id, value, note.trim()); onSaved() }
                onDone()
            }) { Text("Salvează") }
        },
        dismissButton = { TextButton(onClick = onDone) { Text("Renunță") } },
    )
}

@Composable
private fun Drives(log: TeslaLog) {
    val nav = LocalNav.current
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Tile("Deplasări", "${log.drives.size}", Energy.tesla, Modifier.weight(1f))
        Tile("Distanță", "${fmt(log.drives.sumOf { it.km }, 0)} km", Energy.load, Modifier.weight(1f))
    }
    log.activeDrive?.let { Pill("În mers acum", Energy.load) }
    if (log.drives.isEmpty()) Text("Nicio deplasare în perioada aleasă.", color = MaterialTheme.colorScheme.onSurfaceVariant)
    log.drives.forEach { d ->
        GlassCard(onClick = { nav.push(Sub.TeslaDrive(d)) }, padding = 14.dp) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stamp("EEE d MMM", d.start), style = MaterialTheme.typography.titleSmall)
                    Text("${if (d.approx) "~" else ""}${stamp("HH:mm", d.start)} – ${stamp("HH:mm", d.end)} · ${duration(d.hours)}",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("${if (d.startHome) "Acasă" else "Plecare"} → ${if (d.endHome) "Acasă" else "Sosire"}", style = MaterialTheme.typography.bodySmall)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("${fmt(d.km, 1)} km", style = MaterialTheme.typography.titleSmall.merge(Numeric))
                    Text(d.whKm?.let { "${fmt(it, 0)} Wh/km" } ?: "${fmt(d.startSoc, 0)}% → ${fmt(d.endSoc, 0)}%", style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

@Composable
private fun Stats(log: TeslaLog, days: Int) {
    val km = log.drives.sumOf { it.km }
    val kwh = log.drives.mapNotNull { it.kwh }.sum()
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Tile("Distanță", "${fmt(km, 0)} km", Energy.tesla, Modifier.weight(1f), "în $days zile")
        Tile("Consum mediu", if (km > 0 && kwh > 0) "${fmt(kwh * 1000 / km, 0)} Wh/km" else "--", Energy.load, Modifier.weight(1f))
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Tile("Cost încărcări", lei(log.charges.sumOf { it.cost ?: 0.0 }), Energy.grid, Modifier.weight(1f))
        Tile("Cost / 100 km", if (km > 0) lei(log.charges.sumOf { it.cost ?: 0.0 } / km * 100) else "--", Energy.solar, Modifier.weight(1f))
    }
    if (log.monthlyKm.isNotEmpty()) GlassCard {
        Text("Kilometri pe lună", style = MaterialTheme.typography.titleMedium)
        val max = log.monthlyKm.maxOf { it.second }.coerceAtLeast(1.0)
        log.monthlyKm.forEach { (start, value) ->
            val label = runCatching {
                val t = if (start > 1e11) start.toLong() / 1000 else start.toLong()
                stamp("MMM yy", t)
            }.getOrDefault("")
            Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(label, Modifier.width(64.dp), style = MaterialTheme.typography.labelMedium)
                Box(Modifier.weight(1f)) { ro.salavat.casa.ui.components.ShareBar((value / max).toFloat(), Energy.tesla) }
                Text(" ${fmt(value, 0)} km", style = MaterialTheme.typography.labelMedium.merge(Numeric))
            }
        }
    }
}

// ------------------------------- Drive detail -------------------------------

private val BANDS = listOf(30.0 to Color(0xFF3FBF8F), 60.0 to Color(0xFF4C8DF6), 90.0 to Color(0xFFF2B33D), 130.0 to Color(0xFFFF8A5C), Double.MAX_VALUE to Color(0xFFE5689B))
private fun speedColor(v: Double?) = v?.let { s -> BANDS.first { s <= it.first }.second } ?: Color.Gray

@Composable
fun DriveScreen(drive: Drive, repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    var detail by remember { mutableStateOf<DriveDetail?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(drive.id) { runCatching { repo.teslaDrive(drive.id) }.onSuccess { detail = it }.onFailure { error = it.message } }
    val ctx = LocalContext.current
    Page(padding, "Deplasare ${stamp("d MMM", drive.start)}", "${stamp("HH:mm", drive.start)} – ${stamp("HH:mm", drive.end)} · ${duration(drive.hours)}", onBack) {
        val path = detail?.path?.takeIf { it.size >= 2 } ?: drive.path
        GlassCard(padding = 10.dp) {
            if (path.size < 2) Text(error ?: if (detail == null) "Se încarcă traseul…" else "Traseu indisponibil (citiri rare).", Modifier.padding(16.dp))
            else Track(path, detail?.speeds ?: emptyList())
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                listOf("≤30", "≤60", "≤90", "≤130", ">130").forEachIndexed { i, t ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(8.dp).clip(RoundedCornerShape(50)).background(BANDS[i].second)); Text(" $t", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Tile("Distanță", "${fmt(drive.km, 1)} km", Energy.tesla, Modifier.weight(1f))
            Tile("Consum", drive.whKm?.let { "${fmt(it, 0)} Wh/km" } ?: "--", Energy.load, Modifier.weight(1f))
        }
        GlassCard {
            KeyValue("Viteză medie", drive.avgKmh?.let { "${fmt(it, 0)} km/h" })
            KeyValue("Viteză maximă", drive.maxKmh?.let { "${fmt(it, 0)} km/h" })
            KeyValue("Energie", drive.kwh?.let { "${fmt(it, 1)} kWh" })
            KeyValue("Baterie", "${fmt(drive.startSoc, 0)}% → ${fmt(drive.endSoc, 0)}%")
            KeyValue("Exterior", drive.outside?.let { "${fmt(it)} °C" })
            KeyValue("Cost estimat", lei(drive.cost))
        }
        listOf("Plecare" to (drive.startLat to drive.startLon), "Sosire" to (drive.endLat to drive.endLon)).forEach { (label, p) ->
            val (lat, lon) = p
            if (lat != null && lon != null) OutlinedButton(onClick = {
                ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("geo:$lat,$lon?q=$lat,$lon($label)")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }, Modifier.fillMaxWidth()) { Icon(Icons.Rounded.Map, null); Spacer(Modifier.width(6.dp)); Text("$label pe hartă") }
        }
        SectionTitle("Notă")
        Text("Traseul e desenat din punctele înregistrate de HA (Fleet Telemetry când rulează, altfel citiri rare).",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** The route drawn to scale (equirectangular), coloured by speed when known. */
@Composable
private fun Track(path: List<Pair<Double, Double>>, speeds: List<Double?>) {
    val lats = path.map { it.first }
    val lons = path.map { it.second }
    val midLat = Math.toRadians((lats.min() + lats.max()) / 2)
    val xs = lons.map { it * kotlin.math.cos(midLat) }
    val minX = xs.min(); val maxX = xs.max(); val minY = lats.min(); val maxY = lats.max()
    val span = maxOf(maxX - minX, maxY - minY, 1e-5)
    val track = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.15f)
    Canvas(Modifier.fillMaxWidth().height(260.dp)) {
        val pad = 16.dp.toPx()
        val scale = minOf(size.width - 2 * pad, size.height - 2 * pad) / span.toFloat()
        val ox = (size.width - (maxX - minX).toFloat() * scale) / 2
        val oy = (size.height - (maxY - minY).toFloat() * scale) / 2
        fun at(i: Int) = Offset(ox + ((xs[i] - minX) * scale).toFloat(), size.height - oy - ((lats[i] - minY) * scale).toFloat())
        for (i in 1 until path.size) drawLine(track, at(i - 1), at(i), 9.dp.toPx(), StrokeCap.Round)
        for (i in 1 until path.size) drawLine(speedColor(speeds.getOrNull(i)), at(i - 1), at(i), 4.dp.toPx(), StrokeCap.Round)
        drawCircle(Color(0xFF3FBF8F), 7.dp.toPx(), at(0))
        drawCircle(Color(0xFFE5689B), 7.dp.toPx(), at(path.lastIndex))
    }
}

