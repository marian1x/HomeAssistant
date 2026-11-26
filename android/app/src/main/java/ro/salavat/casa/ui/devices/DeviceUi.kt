package ro.salavat.casa.ui.devices

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Air
import androidx.compose.material.icons.rounded.DeviceThermostat
import androidx.compose.material.icons.rounded.ElectricCar
import androidx.compose.material.icons.rounded.Lightbulb
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Power
import androidx.compose.material.icons.rounded.PowerSettingsNew
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material.icons.rounded.Sensors
import androidx.compose.material.icons.rounded.Speaker
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarBorder
import androidx.compose.material3.IconButton
import ro.salavat.casa.data.Layout
import androidx.compose.material.icons.rounded.WaterDrop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.Category
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.EntityState
import ro.salavat.casa.data.User
import ro.salavat.casa.data.category
import ro.salavat.casa.data.controllable
import ro.salavat.casa.data.deviceReading
import ro.salavat.casa.data.directToggle
import ro.salavat.casa.data.fmt
import ro.salavat.casa.data.stateLabel
import ro.salavat.casa.ui.Commands
import ro.salavat.casa.ui.LocalCommands
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.theme.Energy
import ro.salavat.casa.ui.theme.Numeric
import kotlin.math.roundToInt

fun icon(d: Device): ImageVector = when {
    d.kind in setOf("door", "window", "smoke", "binary_sensor") -> Icons.Rounded.Sensors
    else -> when (category(d)) {
        Category.LIGHTS -> Icons.Rounded.Lightbulb
        Category.CLIMATE -> Icons.Rounded.Air
        Category.WATER -> Icons.Rounded.WaterDrop
        Category.MEDIA -> Icons.Rounded.Speaker
        Category.MOBILITY -> Icons.Rounded.ElectricCar
        Category.POWER -> Icons.Rounded.Power
    }
}

fun accent(d: Device): Color = when (category(d)) {
    Category.LIGHTS -> Energy.solar
    Category.CLIMATE -> Energy.grid
    Category.WATER -> Energy.boiler
    Category.MEDIA -> Energy.battery
    Category.MOBILITY -> Energy.tesla
    Category.POWER -> Energy.load
}

private fun isOn(st: EntityState) = st.state !in setOf("off", "unavailable", "unknown", "idle", "standby", "paused")
private fun toggles(d: Device) = d.primary.domain in setOf("light", "switch", "fan")

/** Tap action: lights toggle directly; other switches confirm; rich devices open the sheet. */
fun tap(d: Device, user: User?, commands: Commands, openSheet: () -> Unit) {
    if (!controllable(d) || user?.canControl != true || !d.primary.valid || !toggles(d)) {
        openSheet(); return
    }
    toggle(d, commands)
}

private fun toggle(d: Device, commands: Commands) {
    val action = if (d.primary.state == "on") "turn_off" else "turn_on"
    if (directToggle(d)) commands.direct(d.primary.id, action)
    else commands.confirm(
        d.primary.id, action, null,
        if (action == "turn_on") "Pornești ${d.name}?" else "Oprești ${d.name}?",
        "Comanda se trimite către Home Assistant. Starea se schimbă când aparatul o confirmă.",
    )
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun DeviceTile(d: Device, user: User?, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    val commands = LocalCommands.current
    val on = d.primary.valid && isOn(d.primary) && !d.pending
    val busy = d.primary.id in commands.busy
    val color = accent(d)
    val bg by animateColorAsState(if (on) color.copy(alpha = 0.22f) else MaterialTheme.colorScheme.surface, label = "bg")
    GlassCard(
        modifier = modifier
            .clip(RoundedCornerShape(26.dp))
            .combinedClickable(onClick = { tap(d, user, commands, onOpen) }, onLongClick = onOpen),
        tint = bg, padding = 16.dp,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(42.dp).background(if (on) color else color.copy(alpha = 0.14f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = if (on) Color.White else color)
                else Icon(icon(d), null, tint = if (on) Color.White else color, modifier = Modifier.size(22.dp))
            }
            Spacer(Modifier.weight(1f))
            if (d.pending) Text("De integrat", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(14.dp))
        Text(d.name, style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Text(
            deviceReading(d), style = MaterialTheme.typography.bodySmall.merge(Numeric),
            color = if (on) color else MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
        Text(d.area, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f), maxLines = 1)
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun DeviceSheet(d: Device, user: User?, layout: Layout, onDismiss: () -> Unit) {
    val commands = LocalCommands.current
    val favorite = d.id in layout.favorites
    val canControl = user?.canControl == true && controllable(d) && d.primary.valid
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 22.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(52.dp).background(accent(d).copy(alpha = 0.18f), CircleShape), contentAlignment = Alignment.Center) {
                    Icon(icon(d), null, tint = accent(d))
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(d.name, style = MaterialTheme.typography.titleLarge)
                    Text(listOf(d.area, d.manufacturer).filter { it.isNotBlank() }.joinToString(" · "), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                }
                IconButton(onClick = {
                    commands.layout { l -> l.copy(favorites = if (favorite) l.favorites - d.id else (l.favorites + d.id).take(100)) }
                }) {
                    Icon(if (favorite) Icons.Rounded.Star else Icons.Rounded.StarBorder, if (favorite) "Scoate din favorite" else "Adaugă la favorite",
                        tint = if (favorite) Energy.solar else MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (layout.views.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                layout.views.forEach { v ->
                    val inside = d.id in v.items
                    FilterChip(inside, {
                        commands.layout { l -> l.copy(views = l.views.map { if (it.id == v.id) it.copy(items = if (inside) it.items - d.id else it.items + d.id) else it }) }
                    }, label = { Text(v.name) }, leadingIcon = { Icon(viewIcon(v.icon), null, Modifier.size(16.dp)) })
                }
            }
            Text(deviceReading(d), style = MaterialTheme.typography.headlineSmall.merge(Numeric), color = accent(d))
            d.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            if (user?.canControl != true) Text("Contul tău are acces doar pentru vizualizare.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            if (canControl) when (d.primary.domain) {
                "light", "switch", "fan" -> PowerRow(d, commands)
                "climate" -> ClimateControls(d, commands)
                "water_heater" -> WaterHeaterControls(d, commands)
                "media_player" -> MediaControls(d, commands)
            }
            if (canControl && d.primary.domain == "light") BrightnessControl(d.primary, commands)
            // Auxiliary power switch (e.g. boiler supply) shown beside the main control.
            if (canControl) d.entries.filter { it.id != d.primary.id && it.domain == "switch" && it.valid }.forEach { aux ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(aux.friendly, Modifier.weight(1f))
                    Switch(checked = aux.state == "on", enabled = aux.id !in commands.busy, onCheckedChange = { on ->
                        commands.confirm(aux.id, if (on) "turn_on" else "turn_off", null, if (on) "Pornești alimentarea?" else "Oprești alimentarea?", aux.friendly)
                    })
                }
            }

            if (d.entries.isNotEmpty()) {
                HorizontalDivider()
                Text("Citiri", style = MaterialTheme.typography.titleSmall)
                d.entries.forEach { e ->
                    Row {
                        Text(e.friendly, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(stateLabel(e), style = MaterialTheme.typography.bodyMedium.merge(Numeric), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }
}

@Composable
private fun PowerRow(d: Device, commands: Commands) {
    val on = d.primary.state == "on"
    val busy = d.primary.id in commands.busy
    FilledTonalButton(
        onClick = { toggle(d, commands) },
        enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
    ) {
        Icon(Icons.Rounded.PowerSettingsNew, null)
        Spacer(Modifier.width(8.dp))
        Text(if (on) "Oprește" else "Pornește")
    }
}

@Composable
private fun BrightnessControl(st: EntityState, commands: Commands) {
    val modes = st.attrList("supported_color_modes")
    if (modes.none { it != "onoff" && it != "unknown" }) return
    val current = st.attrDouble("brightness")?.let { (it / 255.0 * 100).roundToInt().coerceIn(1, 100) } ?: 100
    var draft by remember(st.id, current) { mutableFloatStateOf(current.toFloat()) }
    Text("Luminozitate ${draft.roundToInt()}%", style = MaterialTheme.typography.titleSmall)
    Slider(value = draft, onValueChange = { draft = it }, valueRange = 1f..100f)
    FilledTonalButton(onClick = { commands.direct(st.id, "set_brightness", draft.roundToInt()) }, enabled = draft.roundToInt() != current) {
        Text("Aplică")
    }
}

@Composable
private fun TemperatureStepper(st: EntityState, commands: Commands, title: String) {
    val min = st.attrDouble("min_temp") ?: 5.0
    val max = st.attrDouble("max_temp") ?: 80.0
    val step = st.attrDouble("target_temp_step") ?: if (st.domain == "water_heater") 1.0 else 0.5
    val target = st.attrDouble("temperature") ?: return
    var draft by remember(st.id, target) { mutableStateOf(target) }
    Text(title, style = MaterialTheme.typography.titleSmall)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        FilledIconButton(onClick = { draft = (draft - step).coerceAtLeast(min) }, enabled = draft > min) { Icon(Icons.Rounded.Remove, "Scade") }
        Text("${fmt(draft)}°", style = MaterialTheme.typography.displaySmall.merge(Numeric))
        FilledIconButton(onClick = { draft = (draft + step).coerceAtMost(max) }, enabled = draft < max) { Icon(Icons.Rounded.Add, "Crește") }
        Spacer(Modifier.weight(1f))
        FilledTonalButton(
            onClick = { commands.confirm(st.id, "set_temperature", draft, "Setezi ${fmt(draft)}°?", "${st.friendly}: de la ${fmt(target)}° la ${fmt(draft)}°.") },
            enabled = draft != target && st.id !in commands.busy,
        ) { Text("Aplică") }
    }
}

private val HVAC = mapOf("off" to "Oprit", "heat" to "Încălzire", "cool" to "Răcire", "auto" to "Auto", "heat_cool" to "Auto", "dry" to "Uscare", "fan_only" to "Ventilație")

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ClimateControls(d: Device, commands: Commands) {
    val st = d.primary
    TemperatureStepper(st, commands, "Temperatură țintă")
    val modes = st.attrList("hvac_modes")
    if (modes.isNotEmpty()) {
        Text("Mod", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            modes.forEach { m ->
                FilterChip(selected = st.state == m, onClick = {
                    if (st.state != m) commands.confirm(st.id, "set_hvac_mode", m, "Mod ${HVAC[m] ?: m}?", "${d.name} trece în modul ${HVAC[m] ?: m}.")
                }, label = { Text(HVAC[m] ?: m) })
            }
        }
    }
    val fans = st.attrList("fan_modes")
    if (fans.isNotEmpty()) {
        Text("Ventilator", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val current = st.attrs.optString("fan_mode")
            fans.forEach { f ->
                FilterChip(selected = current == f, onClick = {
                    if (current != f) commands.confirm(st.id, "set_fan_mode", f, "Ventilator $f?", d.name)
                }, label = { Text(f) })
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WaterHeaterControls(d: Device, commands: Commands) {
    val st = d.primary
    TemperatureStepper(st, commands, "Temperatură apă")
    val ops = st.attrList("operation_list")
    if (ops.isNotEmpty()) {
        Text("Mod de funcționare", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ops.forEach { m ->
                FilterChip(selected = st.state == m, onClick = {
                    if (st.state != m) commands.confirm(st.id, "set_operation_mode", m, "Mod $m?", d.name)
                }, label = { Text(m) })
            }
        }
    }
}

@Composable
private fun MediaControls(d: Device, commands: Commands) {
    val st = d.primary
    val f = st.attrs.optInt("supported_features")
    val on = st.state !in setOf("off", "standby")
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (f and (128 or 256) != 0) FilledTonalButton(onClick = {
            val a = if (on) "turn_off" else "turn_on"
            commands.confirm(st.id, a, null, if (on) "Oprești ${d.name}?" else "Pornești ${d.name}?", d.name)
        }) { Icon(Icons.Rounded.PowerSettingsNew, null); Spacer(Modifier.width(6.dp)); Text(if (on) "Oprește" else "Pornește") }
        if (on && f and (16384 or 1) != 0) FilledTonalButton(onClick = {
            val a = if (st.state == "playing") "media_pause" else "media_play"
            commands.confirm(st.id, a, null, if (a == "media_pause") "Pauză?" else "Redare?", d.name)
        }) { Icon(if (st.state == "playing") Icons.Rounded.Pause else Icons.Rounded.PlayArrow, null) }
    }
    if (f and 4 != 0) {
        val current = ((st.attrDouble("volume_level") ?: 0.0) * 100).roundToInt()
        var draft by remember(st.id, current) { mutableFloatStateOf(current.toFloat()) }
        Text("Volum ${draft.roundToInt()}%", style = MaterialTheme.typography.titleSmall)
        Slider(value = draft, onValueChange = { draft = it }, valueRange = 0f..100f)
        FilledTonalButton(
            onClick = { commands.confirm(st.id, "set_volume", draft.roundToInt(), "Volum ${draft.roundToInt()}%?", d.name) },
            enabled = draft.roundToInt() != current,
        ) { Text("Aplică volumul") }
    }
}

@Composable
fun Pill(text: String, color: Color, modifier: Modifier = Modifier) {
    Surface(modifier, shape = RoundedCornerShape(50), color = color.copy(alpha = 0.16f)) {
        Row(Modifier.padding(horizontal = 10.dp, vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(7.dp).background(color, CircleShape))
            Spacer(Modifier.width(6.dp))
            Text(text, style = MaterialTheme.typography.labelMedium, color = color)
        }
    }
}
