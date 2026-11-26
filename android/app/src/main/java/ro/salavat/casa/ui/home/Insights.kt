package ro.salavat.casa.ui.home

import ro.salavat.casa.data.KILLSWITCH
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.fmt
import ro.salavat.casa.ui.components.Flows

enum class Tone { WARN, INFO, GOOD }

/** Where tapping a suggestion leads: a detail screen or a tab. */
sealed interface Target {
    data class Detail(val key: String) : Target   // battery, house, grid, policy
    data class Tab(val route: String) : Target
}

data class Insight(val text: String, val tone: Tone, val target: Target? = null)

/**
 * Contextual, factual suggestions from live readings only (no forecasts invented, no
 * automatic action): the "smart" summary on Home. Most important first, at most [limit].
 */
fun insights(s: Snapshot, f: Flows = Flows.of(s), limit: Int = 4): List<Insight> {
    val out = ArrayList<Insight>()
    if (!s.connected) out += Insight("Home Assistant este deconectat: valorile pot fi vechi.", Tone.WARN)
    if (s.states[KILLSWITCH]?.state == "on") out += Insight("Automatizările sunt în pauză. Controlul manual merge în continuare.", Tone.WARN, Target.Tab("settings"))

    val open = s.states.values.filter {
        it.domain == "binary_sensor" && it.state == "on" && it.attrs.optString("device_class") in setOf("door", "window", "garage_door") && s.registry[it.id]?.hidden != true
    }
    if (open.isNotEmpty()) out += Insight(
        if (open.size == 1) "Deschis acum: ${open.first().friendly}." else "${open.size} uși/ferestre deschise: ${open.take(3).joinToString { it.friendly }}.",
        Tone.WARN,
    )
    s.states.values.firstOrNull { it.domain == "binary_sensor" && it.state == "on" && it.attrs.optString("device_class") in setOf("smoke", "gas", "moisture") }
        ?.let { out += Insight("Alarmă: ${it.friendly}!", Tone.WARN) }

    val soc = f.soc
    val reserve = s.states["sensor.home_energy_policy_status"]?.attrDouble("battery_reserve_soc") ?: 20.0
    val grid = f.gridNet
    if (soc != null && soc <= reserve + 3 && (grid ?: 0.0) > 0.2) {
        out += Insight("Bateria e la rezervă (${fmt(soc, 0)}%): casa trage ${fmt(grid)} kW din rețea.", Tone.WARN, Target.Detail("battery"))
    }
    s.binding("batteryTemp")?.number?.let { t ->
        if (t < 5) out += Insight("Bateria e rece (${fmt(t)} °C): încărcarea poate fi limitată de BMS.", Tone.INFO, Target.Detail("battery"))
    }

    val export = f.export ?: 0.0
    val plugged = s.states["binary_sensor.salavat_t3_charger"]?.state == "on"
    val carCharging = s.states["binary_sensor.salavat_t3_charging"]?.state == "on"
    val atHome = s.states["device_tracker.salavat_t3_location_tracker"]?.state == "home"
    if (export > 1.0) {
        when {
            plugged && !carCharging && atHome -> out += Insight("Injectezi ${fmt(export)} kW și Tesla e conectată fără să încarce: surplusul poate merge în mașină.", Tone.GOOD, Target.Tab("tesla"))
            (soc ?: 0.0) >= 95 -> out += Insight("Bateria e plină și injectezi ${fmt(export)} kW: moment bun pentru mașina de spălat, boiler sau climatizare.", Tone.GOOD, Target.Detail("house"))
            else -> out += Insight("Surplus solar de ${fmt(export)} kW injectat în rețea.", Tone.GOOD, Target.Detail("grid"))
        }
    }
    s.states["sensor.salavat_t3_battery"]?.number?.let { car ->
        if (car < 25 && !carCharging) out += Insight("Tesla are ${fmt(car, 0)}%${if (plugged) " și nu încarcă" else ", nu e conectată"}.", Tone.INFO, Target.Tab("tesla"))
    }
    val lights = s.states.values.count { it.domain == "light" && it.state == "on" && s.registry[it.id]?.hidden != true }
    if (lights >= 6) out += Insight("$lights lumini aprinse acum.", Tone.INFO, Target.Detail("house"))
    s.value("forecast")?.let { kwh ->
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        if (hour >= 17 && kwh < 4) out += Insight("Prognoză solară slabă mâine (${fmt(kwh)} kWh): bateria va conta mai mult.", Tone.INFO, Target.Detail("policy"))
    }
    if (out.isEmpty() && (f.solar ?: 0.0) > 0.05 && (grid ?: 0.0) <= 0.05) out += Insight("Casa merge acum fără energie din rețea.", Tone.GOOD, Target.Detail("house"))
    return out.take(limit)
}
