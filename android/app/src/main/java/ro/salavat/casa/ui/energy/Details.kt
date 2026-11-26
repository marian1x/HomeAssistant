package ro.salavat.casa.ui.energy

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import ro.salavat.casa.data.BatteryPoint
import ro.salavat.casa.data.Bms
import ro.salavat.casa.data.EntityState
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.data.controllable
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.kw
import ro.salavat.casa.ui.LocalCommands
import ro.salavat.casa.ui.components.Flows
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.KeyValue
import ro.salavat.casa.ui.components.MiniChart
import ro.salavat.casa.ui.components.Page
import ro.salavat.casa.ui.components.Ring
import ro.salavat.casa.ui.components.SectionTitle
import ro.salavat.casa.ui.components.ShareBar
import ro.salavat.casa.ui.components.StateValue
import ro.salavat.casa.ui.components.Tile
import ro.salavat.casa.ui.policy.PolicyEditor
import ro.salavat.casa.ui.policy.num
import ro.salavat.casa.ui.policy.rememberPolicy
import ro.salavat.casa.ui.theme.Energy
import ro.salavat.casa.ui.theme.Numeric

private fun Snapshot.st(id: String) = states[id]
private fun Snapshot.n(id: String) = states[id]?.number
private fun kwText(v: Double?) = v?.let { "${fmt(it, 2)} kW" } ?: "--"

/** Per-phase table: rows L1..L3, columns supplied as (title, entity pattern with {n}). */
@Composable
private fun PhaseTable(s: Snapshot, columns: List<Pair<String, String>>) {
    val present = columns.filter { (_, pattern) -> (1..3).any { s.st(pattern.replace("{n}", "$it")) != null } }
    if (present.isEmpty()) return
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text("Fază", Modifier.width(44.dp), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        present.forEach { (title, _) ->
            Text(title, Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.End, maxLines = 2)
        }
    }
    for (phase in 1..3) Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text("L$phase", Modifier.width(44.dp), fontWeight = FontWeight.SemiBold)
        present.forEach { (_, pattern) ->
            val e = s.st(pattern.replace("{n}", "$phase"))
            Text(e?.number?.let { "${fmt(it, if (e.unit == "W") 0 else 1)} ${e.unit}" } ?: "--", Modifier.weight(1f),
                style = MaterialTheme.typography.bodyMedium.merge(Numeric), textAlign = TextAlign.End)
        }
    }
}

/** Read-only list of the inverter's own program/settings entities, whatever they are called. */
@Composable
private fun InverterProgram(s: Snapshot) {
    val program = s.states.values.filter {
        (it.domain in setOf("select", "number", "time", "switch") && it.id.substringAfter('.').startsWith("deye")) ||
            it.id.startsWith("sensor.deye_device_state") || it.id == "sensor.deye_device_relay"
    }.sortedBy { it.friendly }
    if (program.isEmpty()) return
    GlassCard {
        Text("Program și setări invertor", style = MaterialTheme.typography.titleMedium)
        Text("Doar citire: invertorul se reglează din politica energetică sau din HA.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(6.dp))
        program.forEach { StateValue(it.friendly.removePrefix("Deye ").removePrefix("deye "), it) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun InverterScreen(s: Snapshot, repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    val f = Flows.of(s)
    val policy by rememberPolicy(repo, s)
    val pv = listOf(1, 2).filter { s.st("sensor.deye_pv${it}_power") != null }
    Page(padding, "Invertor", "Deye · producție solară și faze", onBack) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp), maxItemsInEachRow = 2) {
            val m = Modifier.weight(1f)
            Tile("Producție acum", kwText(f.solar), Energy.solar, m)
            Tile("Produs azi", s.value("solarToday")?.let { "${fmt(it)} kWh" } ?: "--", Energy.solar, m)
            Tile("Prognoză mâine", s.value("forecast")?.let { "${fmt(it)} kWh" } ?: "--", Energy.solar, m)
            Tile("Pierderi azi", s.n("sensor.deye_today_losses")?.let { "${fmt(it)} kWh" } ?: "--", MaterialTheme.colorScheme.onSurfaceVariant, m)
        }
        if (pv.isNotEmpty()) GlassCard {
            Text("Șiruri de panouri", style = MaterialTheme.typography.titleMedium)
            pv.forEach { i ->
                val p = s.st("sensor.deye_pv${i}_power").kw()
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("PV$i", fontWeight = FontWeight.SemiBold, modifier = Modifier.width(44.dp))
                    Column(Modifier.weight(1f)) {
                        ShareBar(((p ?: 0.0) / ((f.solar ?: 0.0).coerceAtLeast(0.01))).toFloat(), Energy.solar)
                        Text("${s.n("sensor.deye_pv${i}_voltage")?.let { fmt(it, 0) } ?: "--"} V · ${s.n("sensor.deye_pv${i}_current")?.let { fmt(it) } ?: "--"} A",
                            style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(kwText(p), style = MaterialTheme.typography.bodyMedium.merge(Numeric))
                }
            }
            s.st("sensor.deye_microinverter_power")?.let { StateValue("Microinvertor", it, 0) }
        }
        GlassCard {
            Text("Pe faze", style = MaterialTheme.typography.titleMedium)
            PhaseTable(s, listOf("Rețea V" to "sensor.deye_grid_l{n}_voltage", "Rețea P" to "sensor.deye_grid_l{n}_power",
                "Ieșire I" to "sensor.deye_output_l{n}_current", "Ieșire P" to "sensor.deye_output_l{n}_power", "Sarcină P" to "sensor.deye_load_l{n}_power"))
            Spacer(Modifier.height(6.dp))
            StateValue("Frecvență rețea", s.st("sensor.deye_grid_frequency"), 2)
            StateValue("Frecvență ieșire", s.st("sensor.deye_output_frequency"), 2)
        }
        GlassCard {
            Text("Stare", style = MaterialTheme.typography.titleMedium)
            StateValue("Stare aparat", s.st("sensor.deye_device_state"))
            StateValue("Alarmă", s.st("sensor.deye_device_alarm"))
            StateValue("Defect", s.st("sensor.deye_device_fault"))
            StateValue("Temperatură DC", s.st("sensor.deye_dc_temperature"))
            StateValue("Temperatură radiator", s.st("sensor.deye_temperature"))
            StateValue("Total produs", s.st("sensor.deye_total_production"), 0)
        }
        InverterProgram(s)
        policy?.getOrNull()?.let { PolicyEditor(s, it, listOf("safety", "prices"), "Configurare (protecții, tarife)") }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun BatteryScreen(s: Snapshot, repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    val f = Flows.of(s)
    val policy by rememberPolicy(repo, s)
    var bms by remember { mutableStateOf<Bms?>(null) }
    var hours by remember { mutableIntStateOf(24) }
    var points by remember { mutableStateOf<List<BatteryPoint>?>(null) }
    LaunchedEffect(Unit) { while (true) { runCatching { repo.bms() }.onSuccess { bms = it }; delay(30_000) } }
    LaunchedEffect(hours) { points = null; points = runCatching { repo.batteryHistory(hours) }.getOrDefault(emptyList()) }
    val main = s.st("sensor.deye_battery")
    fun attr(k: String) = main?.attrDouble(k)
    val power = s.n("sensor.deye_battery_power")
    val reserve = s.st("sensor.home_energy_policy_status")?.attrDouble("battery_reserve_soc")
    Page(padding, "Baterie casă", "Deye + BMS", onBack) {
        GlassCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Ring(f.soc?.toFloat()?.div(100f), Energy.battery, size = 116.dp) {
                    Text(f.soc?.let { "${fmt(it, 0)}%" } ?: "--", style = MaterialTheme.typography.headlineSmall)
                }
                Spacer(Modifier.width(16.dp))
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(when {
                        power == null -> "Fără citire"
                        power < -50 -> "Se încarcă ${fmt(-power / 1000, 2)} kW"
                        power > 50 -> "Se descarcă ${fmt(power / 1000, 2)} kW"
                        else -> "În repaus"
                    }, style = MaterialTheme.typography.titleMedium, color = Energy.battery)
                    Text("Rezervă ${reserve?.let { fmt(it, 0) + "%" } ?: "--"}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("${s.n("sensor.deye_battery_voltage")?.let { fmt(it, 1) } ?: "--"} V · ${s.n("sensor.deye_battery_current")?.let { fmt(it, 1) } ?: "--"} A",
                        style = MaterialTheme.typography.bodyMedium.merge(Numeric))
                }
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp), maxItemsInEachRow = 2) {
            val m = Modifier.weight(1f)
            Tile("Temperatură", s.n("sensor.deye_battery_temperature")?.let { "${fmt(it)} °C" } ?: "--", Energy.grid, m)
            Tile("Sănătate (SOH)", (s.n("sensor.deye_battery_soh") ?: bms?.soh)?.let { "${fmt(it, 0)} %" } ?: "--", Energy.load, m)
            Tile("Încărcat azi", s.n("sensor.deye_today_battery_charge")?.let { "${fmt(it)} kWh" } ?: "--", Energy.battery, m)
            Tile("Descărcat azi", s.n("sensor.deye_today_battery_discharge")?.let { "${fmt(it)} kWh" } ?: "--", Energy.battery, m)
            Tile("Cicluri total", (s.n("sensor.deye_total_battery_life_cycles") ?: bms?.cycles)?.let { fmt(it, 0) } ?: "--", MaterialTheme.colorScheme.onSurfaceVariant, m)
            Tile("Cicluri azi", s.n("sensor.deye_today_battery_life_cycles")?.let { fmt(it, 2) } ?: "--", MaterialTheme.colorScheme.onSurfaceVariant, m)
        }
        GlassCard {
            Text("Ce transmite BMS-ul prin invertor", style = MaterialTheme.typography.titleMedium)
            KeyValue("SOC BMS", attr("BMS SOC")?.let { "${fmt(it, 0)} %" })
            KeyValue("Tensiune / curent BMS", "${attr("BMS Voltage")?.let { fmt(it, 2) } ?: "--"} V · ${attr("BMS Current")?.let { fmt(it, 1) } ?: "--"} A")
            KeyValue("Curent încărcare (max)", "${attr("BMS Charging Current")?.let { fmt(it, 0) } ?: "--"} / ${attr("BMS Max Charging Current")?.let { fmt(it, 0) } ?: "--"} A")
            KeyValue("Curent descărcare (max)", "${attr("BMS Discharging Current")?.let { fmt(it, 0) } ?: "--"} / ${attr("BMS Max Discharging Current")?.let { fmt(it, 0) } ?: "--"} A")
            KeyValue("Tensiune încărcare", attr("BMS Charging Voltage")?.let { "${fmt(it, 1)} V" })
            KeyValue("Capacitate", attr("Corrected Capacity")?.let { "${fmt(it, 0)} Ah" })
            KeyValue("Cicluri nominale", attr("Life Cycle Rating")?.let { fmt(it, 0) })
        }
        bms?.let { BmsCard(it) }
        GlassCard {
            Text("Istoric", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(6.dp))
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf(24, 48).forEachIndexed { i, h ->
                    SegmentedButton(hours == h, { hours = h }, SegmentedButtonDefaults.itemShape(i, 2)) { Text("$h h") }
                }
            }
            val p = points
            if (p == null) Text("Se încarcă…") else {
                Text("Nivel (%)", style = MaterialTheme.typography.labelLarge)
                MiniChart(p.map { it.soc }, Energy.battery, fixedMin = 0.0, fixedMax = 100.0)
                Text("Temperatură (°C)", style = MaterialTheme.typography.labelLarge)
                MiniChart(p.map { it.temp }, Energy.grid)
                Text("Putere (W, negativ = încărcare)", style = MaterialTheme.typography.labelLarge)
                MiniChart(p.map { it.power }, Energy.load)
            }
        }
        policy?.getOrNull()?.let { PolicyEditor(s, it, listOf("battery"), "Configurare baterie") }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BmsCard(b: Bms) {
    GlassCard {
        Text("Celule (Bluetooth direct)", style = MaterialTheme.typography.titleMedium)
        if (!b.available || b.cells.isEmpty()) {
            Text(b.status.ifBlank { "Fără citire Bluetooth încă." }, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@GlassCard
        }
        val lo = b.cellMin ?: b.cells.min()
        val hi = b.cellMax ?: b.cells.max()
        b.at?.let { Text("Citit acum ${((System.currentTimeMillis() / 1000 - it) / 60).coerceAtLeast(0)} min", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), maxItemsInEachRow = 8) {
            b.cells.forEachIndexed { i, v ->
                val frac = if (hi > lo) ((v - lo) / (hi - lo)).toFloat() else 0.5f
                val color = when (v) { hi -> Energy.solar; lo -> Energy.grid; else -> Energy.battery }
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.width(18.dp).height(46.dp).clip(RoundedCornerShape(5.dp)).background(MaterialTheme.colorScheme.onSurface.copy(alpha = 0.08f)), contentAlignment = Alignment.BottomCenter) {
                        Box(Modifier.width(18.dp).height((46 * (0.4f + frac * 0.6f)).dp).background(color))
                    }
                    Text(fmt(v, 3), style = MaterialTheme.typography.labelSmall, maxLines = 1, overflow = TextOverflow.Clip)
                    Text("C${i + 1}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        KeyValue("Diferență celule", b.spreadMv?.let { "${fmt(it, 0)} mV" })
        KeyValue("Interval", "${fmt(lo, 3)} – ${fmt(hi, 3)} V")
        KeyValue("Temperaturi celule", b.cellTemps.joinToString(" · ") { fmt(it) }.ifBlank { null }?.let { "$it °C" })
        KeyValue("Placă (MOS)", b.mosTemp?.let { "${fmt(it)} °C" })
        KeyValue("Încălzire", b.heater)
        b.controller?.optString("firmware")?.takeIf { it.isNotBlank() }?.let { KeyValue("Firmware", it) }
        Text("Doar citire: nimic nu se scrie în baterie.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** Live power of a consumer, in kW, from sensors with device_class power. */
private data class Consumer(val name: String, val kw: Double, val entity: EntityState, val deviceId: String?)

private val SKIP_POWER = Regex("deye|productie|consum_total|consum_din|injectie|baterie_|tesla_charging_power|sensor\\.salavat_t3")

@Composable
fun HouseScreen(s: Snapshot, repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    val f = Flows.of(s)
    val policy by rememberPolicy(repo, s)
    val commands = LocalCommands.current
    val devices = remember(s) { buildDevices(s) }
    val consumers = remember(s) {
        val byEntity = devices.flatMap { d -> d.entries.map { it.id to d } }.toMap()
        val measured = s.states.values.filter {
            it.domain == "sensor" && it.attrs.optString("device_class") == "power" && !SKIP_POWER.containsMatchIn(it.id)
        }.mapNotNull { e -> e.kw()?.takeIf { it > 0.005 }?.let { Consumer(byEntity[e.id]?.name ?: e.friendly, it, e, byEntity[e.id]?.id) } }
        val known = listOfNotNull(
            f.tesla?.takeIf { it > 0.005 }?.let { Consumer("Tesla (încărcare)", it, s.binding("tesla")!!, null) },
            f.boiler?.takeIf { it > 0.005 }?.let { Consumer("Boiler (estimat)", it, s.binding("boiler")!!, "boiler") },
        )
        (measured + known).distinctBy { it.name }.sortedByDescending { it.kw }
    }
    val on = devices.filter { controllable(it) && it.primary.valid && it.primary.state == "on" }
    Page(padding, "Consum casă", "Ce consumă acum și astăzi", onBack) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Tile("Acum", kwText(f.load), Energy.load, Modifier.weight(1f))
            Tile("Azi", s.value("loadToday")?.let { "${fmt(it)} kWh" } ?: "--", Energy.load, Modifier.weight(1f))
        }
        GlassCard {
            Text("Sarcină pe faze", style = MaterialTheme.typography.titleMedium)
            val phases = (1..3).map { s.st("sensor.deye_load_l${it}_power").kw() }
            val max = phases.filterNotNull().maxOrNull()?.coerceAtLeast(0.1) ?: 1.0
            phases.forEachIndexed { i, p ->
                Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("L${i + 1}", Modifier.width(36.dp), fontWeight = FontWeight.SemiBold)
                    ShareBar(((p ?: 0.0) / max).toFloat(), Energy.load, Modifier.weight(1f))
                    Spacer(Modifier.width(8.dp))
                    Text(kwText(p), style = MaterialTheme.typography.bodyMedium.merge(Numeric))
                }
            }
            val total = phases.filterNotNull()
            if (total.size == 3 && total.sum() > 0.3) {
                val spread = (total.max() - total.min()) / total.sum() * 3
                Text(if (spread > 1.2) "Fazele sunt dezechilibrate: L${phases.indexOf(total.max()) + 1} duce cel mai mult." else "Fazele sunt echilibrate.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        GlassCard {
            Text("Consumatori măsurați acum", style = MaterialTheme.typography.titleMedium)
            if (consumers.isEmpty()) Text("Niciun consumator cu senzor de putere activ.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            val load = (f.load ?: consumers.sumOf { it.kw }).coerceAtLeast(0.01)
            consumers.take(12).forEach { c ->
                Column(Modifier.padding(vertical = 5.dp)) {
                    Row {
                        Text(c.name, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(kwText(c.kw), style = MaterialTheme.typography.bodyMedium.merge(Numeric))
                    }
                    ShareBar((c.kw / load).toFloat(), Energy.boiler, height = 6.dp)
                }
            }
            val covered = consumers.sumOf { it.kw }
            f.load?.let { if (it > covered) Text("Nemăsurat separat: ${kwText(it - covered)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        if (on.isNotEmpty()) GlassCard {
            Text("Pornite acum (${on.size})", style = MaterialTheme.typography.titleMedium)
            on.forEach { d ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(d.name, Modifier.weight(1f).padding(vertical = 4.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(d.area, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 12.dp))
                    if (s.user?.canControl == true && d.primary.domain in setOf("light", "switch", "fan")) Switch(true, onCheckedChange = {
                        if (d.primary.domain == "light") commands.direct(d.primary.id, "turn_off")
                        else commands.confirm(d.primary.id, "turn_off", null, "Oprești ${d.name}?", "Comanda se trimite către Home Assistant.")
                    }, enabled = d.primary.id !in commands.busy)
                }
            }
            Text("Atinge un dispozitiv din Acasă pentru mai multe controale.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        SectionTitle("Confort și apă caldă")
        policy?.getOrNull()?.let { PolicyEditor(s, it, listOf("general", "comfort", "winter", "summer", "boiler", "whirlpool", "tcl", "boost"), "Program casă") }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GridScreen(s: Snapshot, repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    val f = Flows.of(s)
    val result by rememberPolicy(repo, s)
    val policy = result?.getOrNull()
    val buy = policy?.config?.num("energy_import_price")
    val sell = policy?.config?.num("energy_export_price")
    val importToday = s.n("sensor.deye_today_energy_import")
    val exportToday = s.n("sensor.deye_today_energy_export")
    Page(padding, "Rețea", "Import, injecție și tarife", onBack) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp), maxItemsInEachRow = 2) {
            val m = Modifier.weight(1f)
            Tile("Import acum", kwText(f.import), Energy.grid, m)
            Tile("Injecție acum", kwText(f.export), Energy.export, m)
            Tile("Import azi", importToday?.let { "${fmt(it)} kWh" } ?: "--", Energy.grid, m)
            Tile("Injecție azi", exportToday?.let { "${fmt(it)} kWh" } ?: "--", Energy.export, m)
        }
        if (buy != null && sell != null && importToday != null && exportToday != null) GlassCard {
            val net = exportToday * sell - importToday * buy
            Text("Valoarea energiei azi", style = MaterialTheme.typography.titleMedium)
            Text("${if (net >= 0) "+" else ""}${fmt(net, 2)} lei", style = MaterialTheme.typography.headlineMedium.merge(Numeric),
                color = if (net >= 0) Energy.load else MaterialTheme.colorScheme.error)
            Text("Injecție ${fmt(exportToday)} kWh × ${fmt(sell, 2)} − import ${fmt(importToday)} kWh × ${fmt(buy, 2)} lei/kWh. Estimare, nu factura furnizorului.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        GlassCard {
            Text("Pe faze", style = MaterialTheme.typography.titleMedium)
            PhaseTable(s, listOf("Tensiune" to "sensor.deye_grid_l{n}_voltage", "Putere" to "sensor.deye_grid_l{n}_power", "CT extern" to "sensor.deye_external_ct{n}_current"))
            StateValue("Frecvență", s.st("sensor.deye_grid_frequency"), 2)
            StateValue("Total importat", s.st("sensor.deye_total_energy_import"), 0)
            StateValue("Total injectat", s.st("sensor.deye_total_energy_export"), 0)
        }
        policy?.let { PolicyEditor(s, it, listOf("prices"), "Tarife") }
    }
}

