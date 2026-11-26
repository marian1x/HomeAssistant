package ro.salavat.casa.ui.policy

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AcUnit
import androidx.compose.material.icons.rounded.Autorenew
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.Celebration
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.FlightTakeoff
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Spa
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import ro.salavat.casa.data.EnergyProfile
import ro.salavat.casa.data.POLICY_GROUPS
import ro.salavat.casa.data.Policy
import ro.salavat.casa.data.PolicyField
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.fmt
import ro.salavat.casa.ui.LocalCommands
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.KeyValue
import ro.salavat.casa.ui.components.Page
import ro.salavat.casa.ui.components.SectionTitle
import ro.salavat.casa.ui.devices.Pill
import ro.salavat.casa.ui.theme.Energy
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Policy read from the server; re-read whenever the server's policy stamp changes (another client saved). */
@Composable
fun rememberPolicy(repo: Repository, s: Snapshot): MutableState<Result<Policy>?> {
    val state = remember { mutableStateOf<Result<Policy>?>(null) }
    LaunchedEffect(s.policyStamp, s.connected) { state.value = runCatching { repo.policy() } }
    return state
}

/** Live policy status: the HA sensor's attributes (pushed by SSE) are fresher than the last read. */
fun liveStatus(s: Snapshot, policy: Policy?): JSONObject {
    val live = s.states["sensor.home_energy_policy_status"]?.attrs
    val base = policy?.status ?: JSONObject()
    if (live == null) return base
    if (live.optString("updated_at") < base.optString("updated_at")) return base
    val merged = JSONObject(base.toString())
    for (k in live.keys()) merged.put(k, live.get(k))
    return merged
}

val PROFILE_ICONS: List<Pair<String, ImageVector>> = listOf(
    "snow" to Icons.Rounded.AcUnit, "sun" to Icons.Rounded.WbSunny, "auto" to Icons.Rounded.Autorenew, "leaf" to Icons.Rounded.Spa,
    "home" to Icons.Rounded.Home, "away" to Icons.Rounded.FlightTakeoff, "moon" to Icons.Rounded.Bedtime, "bolt" to Icons.Rounded.Bolt,
    "star" to Icons.Rounded.Star, "party" to Icons.Rounded.Celebration,
)

fun profileIcon(key: String) = PROFILE_ICONS.firstOrNull { it.first == key }?.second ?: Icons.Rounded.Star

private val DEVICES = listOf("tesla" to "Tesla", "boiler" to "Boiler Ariston", "tcl" to "AC parter (TCL)", "whirlpool" to "AC etaj (Whirlpool)")
private val MODES = mapOf("manual" to "Manual", "normal" to "Confort", "solar" to "Surplus solar", "unavailable" to "Neconectat", "idle" to "În așteptare")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PolicyScreen(s: Snapshot, repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    val result by rememberPolicy(repo, s)
    val policy = result?.getOrNull()
    val status = liveStatus(s, policy)
    val user = s.user
    val commands = LocalCommands.current
    Page(padding, "Politică energie", "Casa → baterie → Tesla → boiler → climatizare", onBack) {
        result?.exceptionOrNull()?.let { Text(it.message ?: "Controlul energetic nu răspunde.", color = MaterialTheme.colorScheme.error) }
        GlassCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(status.optString("phase").ifBlank { "Conectare la HA" }, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Pill(if (status.optBoolean("power_valid")) "Date valide" else "Date incomplete", if (status.optBoolean("power_valid")) Energy.load else Energy.solar)
            }
            Spacer(Modifier.height(6.dp))
            Text(status.optString("reason").ifBlank { "Se încarcă starea controlerului." }, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            KeyValue("Surplus disponibil", status.num("solar_budget_kw")?.let { "${fmt(it, 2)} kW" })
            KeyValue("Bateria casei", status.num("battery_soc")?.let { "${fmt(it, 0)} %" })
            KeyValue("Rezervă", (status.num("battery_reserve_soc") ?: policy?.config?.num("base_reserve_soc"))?.let { "${fmt(it, 0)} %" })
            KeyValue("Exterior", status.num("outside_c")?.let { "${fmt(it)} °C" })
            KeyValue("Sezon", when (status.optString("season")) { "Winter" -> "Iarnă"; "Summer" -> "Vară"; else -> null })
            KeyValue("Prognoză rămasă azi", status.num("forecast_remaining_kwh")?.let { "${fmt(it)} kWh" })
        }

        ProfilesCard(s, policy)

        SectionTitle("Aparate controlate")
        val devices = status.optJSONObject("devices")
        DEVICES.forEach { (key, label) ->
            val d = devices?.optJSONObject(key) ?: JSONObject()
            val manualUntil = d.optDouble("manual_until", 0.0).takeIf { it.isFinite() } ?: 0.0
            val manual = manualUntil * 1000 > System.currentTimeMillis()
            GlassCard(padding = 14.dp) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(label, style = MaterialTheme.typography.titleSmall)
                        Text(d.optString("reason").ifBlank { "Fără comenzi" }, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        when {
                            d.has("temperature") && !d.isNull("temperature") -> Text("${fmt(d.optDouble("temperature"))} °C", style = MaterialTheme.typography.labelLarge)
                            d.has("amps") && !d.isNull("amps") -> Text("${fmt(d.optDouble("amps"), 0)} A", style = MaterialTheme.typography.labelLarge)
                        }
                    }
                    val mode = if (manual) "manual" else d.optString("mode")
                    Pill(MODES[mode] ?: "În așteptare", when (mode) {
                        "manual" -> Energy.solar
                        "unavailable", "idle", "" -> MaterialTheme.colorScheme.onSurfaceVariant
                        else -> Energy.load
                    })
                }
                if (manual) Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Manual până la ${SimpleDateFormat("dd.MM HH:mm", Locale.forLanguageTag("ro")).format(Date((manualUntil * 1000).toLong()))}",
                        Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                    if (user?.canControl == true) TextButton(onClick = {
                        commands.confirmRun("Reiei controlul automat?", "$label revine sub controlul politicii.", "resume-$key", "Control automat reluat.") { repo.resume(key) }
                    }) { Icon(Icons.Rounded.RestartAlt, null); Spacer(Modifier.width(4.dp)); Text("Reia automat") }
                }
            }
        }

        status.optJSONObject("tesla_quota")?.let { q ->
            GlassCard {
                Text("Buget Tesla API", style = MaterialTheme.typography.titleMedium)
                KeyValue("Citiri azi", "${q.optInt("reads_day")} / ${policy?.config?.optInt("ev_reads_daily") ?: "-"}")
                KeyValue("Citiri lună", "${q.optInt("reads_month")} / ${policy?.config?.optInt("ev_reads_monthly") ?: "-"}")
                KeyValue("Comenzi azi", "${q.optInt("commands_day")} / ${policy?.config?.optInt("ev_commands_daily") ?: "-"}")
                Text(q.optString("status"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        if (policy != null) PolicyEditor(s, policy, POLICY_GROUPS.keys.toList(), title = "Parametri de funcționare")
        else if (result == null) CircularProgressIndicator()
    }
}

// ---------------------------- Profiles ----------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProfilesCard(s: Snapshot, policy: Policy?) {
    val commands = LocalCommands.current
    val admin = s.user?.canConfigure == true
    var editing by remember { mutableStateOf<EnergyProfile?>(null) }
    var creating by remember { mutableStateOf(false) }
    GlassCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Profile", style = MaterialTheme.typography.titleMedium)
                Text(if (admin) "Atinge pentru a aplica. Profilul schimbă doar parametrii pe care îi conține." else "Doar administratorul aplică sau modifică profile.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (admin && policy != null) IconButton(onClick = { creating = true }) { Icon(Icons.Rounded.Add, "Profil nou") }
        }
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            s.profiles.forEach { p ->
                val active = s.activeProfile?.id == p.id
                val matches = policy?.let { pol -> p.keys().all { k -> pol.config.opt(k)?.toString() == p.values.opt(k)?.toString() } } ?: false
                FilterChip(
                    selected = active,
                    onClick = {
                        if (admin) commands.confirmRun(
                            "Aplici profilul „${p.name}”?",
                            "Se schimbă ${p.keys().size} parametri ai politicii. Aparatele cu control automat se pot adapta imediat.",
                            "profile-${p.id}", "Profilul ${p.name} a fost aplicat.",
                        ) { commands.repo.activateProfile(p.id) }
                    },
                    leadingIcon = { Icon(if (active && matches) Icons.Rounded.CheckCircle else profileIcon(p.icon), null, Modifier.size(18.dp)) },
                    label = { Text(p.name + if (active && !matches && policy != null) " (modificat)" else "") },
                    trailingIcon = if (admin && policy != null) ({
                        Icon(Icons.Rounded.Edit, "Editează", Modifier.size(16.dp).clickable { editing = p })
                    }) else null,
                )
            }
        }
        s.activeProfile?.let { a ->
            Spacer(Modifier.height(6.dp))
            Text("Aplicat ultima dată: ${SimpleDateFormat("dd.MM HH:mm", Locale.forLanguageTag("ro")).format(Date((a.at * 1000).toLong()))}",
                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    if (policy != null && (creating || editing != null)) ProfileEditor(s, policy, editing) { creating = false; editing = null }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileEditor(s: Snapshot, policy: Policy, profile: EnergyProfile?, onDone: () -> Unit) {
    val commands = LocalCommands.current
    var name by remember { mutableStateOf(profile?.name ?: "") }
    var icon by remember { mutableStateOf(profile?.icon ?: "star") }
    // Included parameters and their values; a new profile starts empty, the admin picks groups.
    val values = remember {
        mutableStateMapOf<String, Any?>().apply { profile?.values?.let { v -> v.keys().forEach { put(it, v.get(it)) } } }
    }
    var openGroup by remember { mutableStateOf<String?>(null) }
    val usable = policy.schema.filter { it.group != "bindings" && it.kind != "entity" }
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text(if (profile == null) "Profil nou" else "Editează profilul") },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it.take(40) }, label = { Text("Nume") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PROFILE_ICONS.forEach { (key, vector) ->
                        FilterChip(icon == key, { icon = key }, label = { Icon(vector, key, Modifier.size(18.dp)) })
                    }
                }
                Text("${values.size} parametri incluși. Bifează ce schimbă profilul; valoarea pornește de la configurația actuală.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                POLICY_GROUPS.forEach { (group, label) ->
                    val fields = usable.filter { it.group == group }
                    if (fields.isEmpty()) return@forEach
                    val included = fields.count { it.key in values }
                    Row(Modifier.fillMaxWidth().clickable { openGroup = if (openGroup == group) null else group }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                        if (included > 0) Pill("$included", Energy.load)
                        Icon(if (openGroup == group) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, null)
                    }
                    if (openGroup == group) fields.forEach { f ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(f.key in values, { on -> if (on) values[f.key] = policy.config.opt(f.key) else values.remove(f.key) })
                            Column(Modifier.weight(1f)) {
                                Text(f.label, style = MaterialTheme.typography.bodyMedium)
                                if (f.key in values) FieldEditor(f, values[f.key], true, s, policy.config) { values[f.key] = it }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && values.isNotEmpty() && values.values.none { it == null }, onClick = {
                val json = JSONObject()
                values.forEach { (k, v) -> json.put(k, v) }
                commands.launch("profile-save", "Profil salvat.") { commands.repo.saveProfile(profile?.id, name.trim(), icon, json) }
                onDone()
            }) { Text("Salvează") }
        },
        dismissButton = {
            Row {
                if (profile != null) TextButton(onClick = {
                    commands.confirmRun("Ștergi profilul „${profile.name}”?", "Configurația curentă nu se schimbă.", "profile-del", "Profil șters.") {
                        commands.repo.deleteProfile(profile.id)
                    }
                    onDone()
                }) { Icon(Icons.Rounded.Delete, null); Text("Șterge") }
                TextButton(onClick = onDone) { Text("Renunță") }
            }
        },
    )
}

// ---------------------------- Parameter editor ----------------------------

/**
 * Editable view of chosen policy groups. Admins (configure role) change a draft and apply
 * only the differences with the revision guard; everyone else reads. Same rules as the web.
 */
@Composable
fun PolicyEditor(s: Snapshot, policy: Policy, groups: List<String>, title: String = "Configurare") {
    val commands = LocalCommands.current
    val admin = s.user?.canConfigure == true
    val draft = remember(policy.revision) { mutableStateMapOf<String, Any?>() }
    var open by remember { mutableStateOf(if (groups.size == 1) groups.first() else null) }
    val dirty = draft.filter { (k, v) -> policy.config.opt(k)?.toString() != v?.toString() }
    GlassCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text((if (admin) "Admin" else "Doar vizualizare") + " · revizia ${policy.revision}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (admin && dirty.isNotEmpty()) TextButton(onClick = { draft.clear() }) { Text("Renunță") }
        }
        groups.forEach { group ->
            val fields = policy.fields(group)
            if (fields.isEmpty()) return@forEach
            HorizontalDivider(Modifier.padding(vertical = 4.dp))
            Row(Modifier.fillMaxWidth().clickable { open = if (open == group) null else group }.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(POLICY_GROUPS[group] ?: group, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                Text("${fields.size}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Icon(if (open == group) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, null)
            }
            if (open == group) fields.forEach { f ->
                Column(Modifier.padding(vertical = 4.dp)) {
                    Text(f.label, style = MaterialTheme.typography.bodyMedium)
                    FieldEditor(f, if (f.key in draft) draft[f.key] else policy.config.opt(f.key), admin, s, policy.config) { draft[f.key] = it }
                }
            }
        }
        if (admin && dirty.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Button(
                enabled = dirty.values.none { it == null },
                onClick = {
                    val values = JSONObject()
                    dirty.forEach { (k, v) -> values.put(k, v) }
                    commands.confirmRun(
                        "Aplici ${dirty.size} modificări?",
                        "Schimbările pot comanda aparatele cu control automat activ.",
                        "policy-save", "Configurație salvată în Home Assistant.",
                    ) { commands.repo.configure(values, policy.revision); draft.clear() }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Aplică ${dirty.size} modificări") }
        }
    }
}

/** Typed editor per schema kind; reports null while the input is invalid (blocks saving). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FieldEditor(f: PolicyField, value: Any?, enabled: Boolean, s: Snapshot, config: JSONObject, onChange: (Any?) -> Unit) {
    when (f.kind) {
        "boolean" -> Switch(checked = value == true, onCheckedChange = { onChange(it) }, enabled = enabled)
        "select", "fan" -> {
            val choices = if (f.kind == "fan") fanChoices(f, s, config) else f.choices
            if (choices.isEmpty()) TextValue(f, value, enabled, onChange)
            else FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                choices.forEach { c -> FilterChip(value?.toString() == c, { if (enabled) onChange(c) }, label = { Text(choiceLabel(c)) }, enabled = enabled) }
            }
        }
        "entity" -> EntityPicker(f, value?.toString().orEmpty(), enabled, s, onChange)
        "number" -> NumberValue(f, value, enabled, onChange)
        else -> TextValue(f, value, enabled, onChange)
    }
}

private fun choiceLabel(c: String) = mapOf("Auto" to "Automat", "Winter" to "Iarnă", "Summer" to "Vară")[c] ?: c

/** Fan steps offered by the AC currently bound to that role (as in the web editor). */
private fun fanChoices(f: PolicyField, s: Snapshot, config: JSONObject): List<String> {
    val entity = config.optString(if (f.key.startsWith("tcl")) "tcl_entity" else "whirlpool_entity")
    return s.states[entity]?.attrList("fan_modes") ?: emptyList()
}

@Composable
private fun NumberValue(f: PolicyField, value: Any?, enabled: Boolean, onChange: (Any?) -> Unit) {
    var text by remember(value is Number) { mutableStateOf((value as? Number)?.let { n -> if (f.step >= 1) n.toLong().toString() else n.toString() } ?: "") }
    val parsed = text.replace(',', '.').toDoubleOrNull()
    val ok = parsed != null && (f.min == null || parsed >= f.min) && (f.max == null || parsed <= f.max) && (f.step < 1 || parsed % 1.0 == 0.0)
    OutlinedTextField(
        text, { t -> text = t; val p = t.replace(',', '.').toDoubleOrNull()
            onChange(if (p != null && (f.min == null || p >= f.min) && (f.max == null || p <= f.max) && (f.step < 1 || p % 1.0 == 0.0)) (if (f.step >= 1) p.toLong() else p) else null) },
        enabled = enabled, singleLine = true, isError = !ok && text.isNotEmpty(),
        suffix = { Text(if (f.unit == "C") "°C" else f.unit) },
        supportingText = { if (f.min != null && f.max != null) Text("${fmt(f.min, 2)} – ${fmt(f.max, 2)}") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun TextValue(f: PolicyField, value: Any?, enabled: Boolean, onChange: (Any?) -> Unit) {
    var text by remember { mutableStateOf(value?.toString() ?: "") }
    val pattern = when (f.kind) {
        "time" -> Regex("""(?:[01]\d|2[0-3]):[0-5]\d""")
        "date" -> Regex("""\d{4}-\d{2}-\d{2}""")
        "months" -> Regex("""\d{1,2}(?:,\d{1,2}){0,11}""")
        else -> Regex(""".{1,32}""")
    }
    OutlinedTextField(
        text, { t -> text = t; onChange(if (pattern.matches(t)) t else null) }, enabled = enabled, singleLine = true,
        isError = !pattern.matches(text),
        placeholder = { Text(when (f.kind) { "time" -> "HH:MM"; "date" -> "AAAA-LL-ZZ"; "months" -> "10,11,12,1"; else -> "" }) },
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun EntityPicker(f: PolicyField, value: String, enabled: Boolean, s: Snapshot, onChange: (Any?) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val domains = mapOf(
        "tcl_entity" to "climate", "whirlpool_entity" to "climate", "boiler_entity" to "water_heater", "boiler_power" to "switch",
        "ev_switch" to "switch", "ev_amps" to "number", "ev_limit" to "number", "ev_connected" to "binary_sensor", "ev_charging" to "binary_sensor",
        "ev_soc" to "sensor", "ev_power" to "sensor", "ev_voltage" to "sensor", "ev_tracker" to "device_tracker", "ev_home_zone" to "zone",
    )
    val domain = domains[f.key] ?: value.substringBefore('.', "sensor")
    val options = s.states.values.filter { it.domain == domain && it.id !in setOf("climate.heat", "climate.bedroom_heat") }.sortedBy { it.friendly }
    Column {
        OutlinedButton(onClick = { expanded = true }, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
            Text(s.states[value]?.friendly ?: value.ifBlank { "Neasociat" }, maxLines = 1)
        }
        DropdownMenu(expanded, { expanded = false }) {
            DropdownMenuItem(text = { Text("Neasociat") }, onClick = { onChange(""); expanded = false })
            options.forEach { o -> DropdownMenuItem(text = { Text("${o.friendly} · ${o.id}") }, onClick = { onChange(o.id); expanded = false }) }
        }
    }
}

fun JSONObject.num(key: String): Double? = if (has(key) && !isNull(key)) optDouble(key).takeIf { it.isFinite() } else null
