package ro.salavat.casa.data

import org.json.JSONArray
import org.json.JSONObject
import java.text.NumberFormat
import java.util.Locale

/**
 * Kotlin port of the web app's src/model.ts. Keep the two in sync: the server's
 * snapshot is the single source of truth and both clients derive the same view.
 */

data class EntityState(
    val id: String,
    val state: String,
    val attrs: JSONObject,
    val lastUpdated: String?,
) {
    val domain: String get() = id.substringBefore('.')
    val valid: Boolean get() = state != "unknown" && state != "unavailable"
    val number: Double? get() = if (valid) state.trim().toDoubleOrNull()?.takeIf { it.isFinite() } else null
    val unit: String get() = attrs.optString("unit_of_measurement", "")
    val friendly: String get() = attrs.optString("friendly_name", "").ifBlank { id }
    fun attrDouble(key: String): Double? = if (attrs.has(key) && !attrs.isNull(key)) attrs.optDouble(key).takeIf { it.isFinite() } else null
    fun attrList(key: String): List<String> = attrs.optJSONArray(key)?.strings() ?: emptyList()

    companion object {
        fun parse(o: JSONObject) = EntityState(
            id = o.getString("entity_id"),
            state = o.optString("state", "unknown"),
            attrs = o.optJSONObject("attributes") ?: JSONObject(),
            lastUpdated = o.optString("last_updated").ifBlank { null },
        )
    }
}

data class User(val id: String, val name: String, val role: String, val local: Boolean, val admin: Boolean) {
    val canControl get() = role == "control" || role == "configure"
    val canConfigure get() = role == "configure"
    val roleLabel get() = when (role) {
        "configure" -> if (admin) "Administrator" else "Parametri și control"
        "control" -> "Control dispozitive"
        else -> "Vizualizare"
    }
}

data class RegistryEntry(val deviceId: String?, val areaId: String?, val hidden: Boolean, val disabled: Boolean, val category: Boolean)
data class HaDevice(val id: String, val name: String, val manufacturer: String, val areaId: String?)
data class Area(val id: String, val name: String, val floorId: String?)
data class Floor(val id: String, val name: String, val level: Int)
data class Room(val key: String, val name: String, val floor: String, val haAreaId: String?)
data class HouseItem(
    val id: String, val name: String, val kind: String, val room: String,
    val deviceIds: List<String>, val primaryEntity: String?, val manufacturer: String?,
    val note: String?, val coverage: String?, val external: Boolean, val ratedPower: Double?,
)

data class Snapshot(
    val user: User?,
    val csrf: String,
    val connected: Boolean,
    val lastUpdate: Double,
    val states: Map<String, EntityState>,
    val registry: Map<String, RegistryEntry>,
    val devices: List<HaDevice>,
    val areas: List<Area>,
    val floors: List<Floor>,
    val houseFloors: List<String>,
    val rooms: List<Room>,
    val items: List<HouseItem>,
    val bindings: Map<String, String>,
) {
    fun binding(key: String): EntityState? = states[bindings[key] ?: DEFAULT_BINDINGS[key]]
    fun value(key: String): Double? = binding(key)?.number

    /** Applies an SSE delta: a null state means the entity disappeared. */
    fun withDelta(delta: JSONObject): Snapshot {
        val changed = delta.optJSONObject("states") ?: return this
        val next = states.toMutableMap()
        for (key in changed.keys()) {
            val item = changed.optJSONObject(key)
            if (item == null) next.remove(key) else next[key] = EntityState.parse(item)
        }
        return copy(
            states = next,
            connected = delta.optBoolean("connected", connected),
            lastUpdate = delta.optDouble("last_update", lastUpdate).takeIf { it.isFinite() } ?: lastUpdate,
        )
    }

    companion object {
        fun parse(o: JSONObject): Snapshot {
            val states = HashMap<String, EntityState>()
            o.optJSONObject("states")?.let { s ->
                for (key in s.keys()) s.optJSONObject(key)?.let { states[key] = EntityState.parse(it) }
            }
            val registry = HashMap<String, RegistryEntry>()
            o.optJSONArray("entities")?.objects()?.forEach { e ->
                registry[e.optString("entity_id")] = RegistryEntry(
                    e.str("device_id"), e.str("area_id"),
                    !e.isNull("hidden_by") && e.has("hidden_by"),
                    !e.isNull("disabled_by") && e.has("disabled_by"),
                    !e.isNull("entity_category") && e.has("entity_category"),
                )
            }
            val house = o.optJSONObject("house")
            val bindings = HashMap(DEFAULT_BINDINGS)
            o.optJSONObject("bindings")?.let { b -> for (k in b.keys()) bindings[k] = b.optString(k) }
            return Snapshot(
                user = o.optJSONObject("user")?.let {
                    User(it.optString("id"), it.optString("name"), it.optString("role", "viewer"), it.optBoolean("local"), it.optBoolean("admin"))
                },
                csrf = o.optString("csrf"),
                connected = o.optBoolean("connected"),
                lastUpdate = o.optDouble("last_update", 0.0).takeIf { it.isFinite() } ?: 0.0,
                states = states,
                registry = registry,
                devices = o.optJSONArray("devices")?.objects()?.map {
                    HaDevice(it.optString("id"), it.str("name_by_user") ?: it.str("name") ?: "", it.str("manufacturer") ?: "", it.str("area_id"))
                } ?: emptyList(),
                areas = o.optJSONArray("areas")?.objects()?.map { Area(it.optString("area_id"), it.optString("name"), it.str("floor_id")) } ?: emptyList(),
                floors = o.optJSONArray("floors")?.objects()?.map { Floor(it.optString("floor_id"), it.optString("name"), it.optInt("level")) } ?: emptyList(),
                houseFloors = house?.optJSONArray("floors")?.objects()?.map { it.optString("name") } ?: emptyList(),
                rooms = house?.optJSONArray("rooms")?.objects()?.map {
                    Room(it.optString("key"), it.optString("name"), it.optString("floor"), it.str("ha_area_id"))
                } ?: emptyList(),
                items = house?.optJSONArray("items")?.objects()?.map {
                    HouseItem(
                        it.optString("id"), it.optString("name"), it.optString("kind"), it.optString("room"),
                        it.optJSONArray("device_ids")?.strings() ?: emptyList(), it.str("primary_entity"), it.str("manufacturer"),
                        it.str("note"), it.str("coverage"), it.optBoolean("external_control"),
                        if (it.has("rated_power_kw")) it.optDouble("rated_power_kw") else null,
                    )
                } ?: emptyList(),
                bindings = bindings,
            )
        }
    }
}

val DEFAULT_BINDINGS: Map<String, String> = mapOf(
    "solar" to "sensor.productie_solara_curenta",
    "load" to "sensor.consum_total_curent",
    "import" to "sensor.consum_din_retea",
    "export" to "sensor.injectie_in_retea",
    "soc" to "sensor.deye_battery",
    "charge" to "sensor.baterie_incarcare_putere",
    "discharge" to "sensor.baterie_descarcare_putere",
    "batteryTemp" to "sensor.deye_battery_temperature",
    "solarToday" to "sensor.deye_productie_solara_astazi",
    "loadToday" to "sensor.deye_today_load_consumption",
    "importToday" to "sensor.deye_today_energy_import",
    "forecast" to "sensor.deye_prognoza_solar_maine",
    "reserve" to "sensor.deye_rezerva_recomandata",
    "limit" to "sensor.deye_putere_descarcare_recomandata",
    "tesla" to "sensor.tesla_charging_power",
    "boiler" to "sensor.ariston_boiler_power_estimated",
    "pause" to "input_boolean.ha_automation_killswitch",
    "manager" to "automation.deye_management_baterie_si_prognoza",
)

const val KILLSWITCH = "input_boolean.ha_automation_killswitch"

data class Device(
    val id: String,
    val name: String,
    val area: String,
    val floor: String,
    val manufacturer: String,
    val entries: List<EntityState>,
    val primary: EntityState,
    val kind: String,
    val pending: Boolean = false,
    val external: Boolean = false,
    val note: String? = null,
    val coverage: String? = null,
    val ratedPower: Double? = null,
)

enum class Category(val key: String, val label: String) {
    LIGHTS("lights", "Iluminat"), CLIMATE("climate", "Climatizare"), WATER("water", "Apă caldă"),
    POWER("power", "Prize"), MEDIA("media", "Media"), MOBILITY("mobility", "Mobilitate"),
}

private val PROTECTED = Regex("polling|firmware|update|access_point")

fun controllable(d: Device): Boolean {
    if (d.pending || d.external) return false
    val id = d.primary.id
    val domain = d.primary.domain
    if (PROTECTED.containsMatchIn(id) || id.startsWith("switch.deye")) return false
    if (domain in setOf("switch", "light", "fan")) return true
    if (id == "climate.heat" || id == "climate.bedroom_heat") return false
    if (domain == "climate" || domain == "water_heater") return true
    return domain == "media_player" && (d.primary.attrs.optInt("supported_features") and (128 or 256 or 1 or 16384 or 4 or 8)) != 0
}

fun category(d: Device): Category = when {
    d.kind == "car" || d.kind == "charger" || d.manufacturer.equals("tesla", true) -> Category.MOBILITY
    d.kind == "light" || d.primary.id.startsWith("light.") -> Category.LIGHTS
    d.primary.id.startsWith("climate.") -> Category.CLIMATE
    d.primary.id.startsWith("water_heater.") -> Category.WATER
    d.primary.id.startsWith("media_player.") -> Category.MEDIA
    else -> Category.POWER
}

/** Lights switch directly (owner decision 2026-11-10); every other category confirms first. */
fun directToggle(d: Device) = category(d) == Category.LIGHTS

fun houseFloorOrder(s: Snapshot): List<String> {
    val plan = s.houseFloors
    if (s.floors.isEmpty()) return plan
    fun rank(n: String) = plan.indexOf(n).let { if (it < 0) 99 else it }
    return s.floors.map { it.name }.sortedBy { rank(it) }
}

private fun resolvedRoom(s: Snapshot, room: Room?): Pair<String, String> {
    val area = s.areas.firstOrNull { it.id == room?.haAreaId || it.name == room?.name }
    val floor = s.floors.firstOrNull { it.id == area?.floorId }?.name
    return (area?.name ?: room?.name ?: "Fără cameră") to (floor ?: room?.floor ?: "Neatribuite")
}

fun buildDevices(s: Snapshot): List<Device> {
    val allowed = setOf("light", "switch", "climate", "water_heater", "fan", "media_player", "alarm_control_panel", "cover", "vacuum")
    val rank = listOf("water_heater", "climate", "alarm_control_panel", "vacuum", "media_player", "light", "switch", "cover", "binary_sensor", "sensor")
    fun usable(st: EntityState): Boolean {
        val e = s.registry[st.id]
        return e?.disabled != true && e?.hidden != true && e?.category != true &&
            !st.id.startsWith("switch.deye") && !Regex("polling|firmware|access_point").containsMatchIn(st.id)
    }
    fun score(st: EntityState) = rank.indexOf(st.domain).let { if (it < 0) 99 else it }
    val order = compareBy<EntityState>({ score(it) }, { it.id })

    val assigned = HashSet<String>()
    val assignedEntities = HashSet<String>()
    val result = ArrayList<Device>()
    for (item in s.items) {
        assigned += item.deviceIds
        val auxiliary = if (item.id == "boiler") listOf("switch.boiler_ariston_power") else emptyList()
        assignedEntities += auxiliary
        val entries = s.states.values.filter { st ->
            usable(st) && (s.registry[st.id]?.deviceId in item.deviceIds || st.id == item.primaryEntity || st.id in auxiliary) && st.domain in rank
        }.sortedWith(order)
        val primary = entries.firstOrNull { it.id == item.primaryEntity } ?: entries.firstOrNull()
        item.primaryEntity?.let { assignedEntities += it }
        val room = resolvedRoom(s, s.rooms.firstOrNull { it.key == item.room })
        val meta = s.devices.firstOrNull { it.id in item.deviceIds }
        val areaId = primary?.let { s.registry[it.id]?.areaId } ?: meta?.areaId
        val nativeArea = s.areas.firstOrNull { it.id == areaId }
        val nativeFloor = s.floors.firstOrNull { it.id == nativeArea?.floorId }
        result += Device(
            id = item.id, name = item.name,
            area = nativeArea?.name ?: room.first, floor = nativeFloor?.name ?: room.second,
            manufacturer = item.manufacturer ?: meta?.manufacturer ?: "",
            entries = entries,
            primary = primary ?: EntityState("unconfigured.${item.id}", "unavailable", JSONObject().put("friendly_name", item.name), null),
            kind = item.kind, pending = primary == null, external = item.external, note = item.note,
            coverage = item.coverage?.let { nativeFloor?.name ?: room.second }, ratedPower = item.ratedPower,
        )
    }
    val groups = LinkedHashMap<String, MutableList<EntityState>>()
    for (st in s.states.values) {
        val entry = s.registry[st.id]
        if (!usable(st) || entry?.deviceId in assigned || st.id in assignedEntities) continue
        val security = st.domain == "binary_sensor" && st.attrs.optString("device_class") in setOf("door", "window", "smoke", "gas", "moisture")
        if (st.domain !in allowed && !security) continue
        groups.getOrPut(entry?.deviceId ?: st.id) { ArrayList() } += st
    }
    for ((id, entries) in groups) {
        val meta = s.devices.firstOrNull { it.id == id }
        val primary = entries.sortedWith(order).first()
        val areaId = s.registry[primary.id]?.areaId ?: meta?.areaId
        val area = s.areas.firstOrNull { it.id == areaId }
        result += Device(
            id = id, name = meta?.name?.ifBlank { null } ?: primary.friendly,
            area = area?.name ?: "Fără cameră",
            floor = s.floors.firstOrNull { it.id == area?.floorId }?.name ?: "Neatribuite",
            manufacturer = meta?.manufacturer ?: "", entries = entries.sortedWith(order), primary = primary,
            kind = if (primary.domain == "binary_sensor") primary.attrs.optString("device_class", "binary_sensor") else primary.domain,
        )
    }
    val floorOrder = houseFloorOrder(s)
    fun position(f: String) = floorOrder.indexOf(f).let { if (it < 0) 99 else it }
    val collator = java.text.Collator.getInstance(Locale.forLanguageTag("ro"))
    return result.sortedWith { a, b ->
        position(a.floor).compareTo(position(b.floor)).takeIf { it != 0 }
            ?: collator.compare(a.area, b.area).takeIf { it != 0 }
            ?: collator.compare(a.name, b.name)
    }
}

private val RO = Locale.forLanguageTag("ro-RO")

fun fmt(n: Double?, digits: Int = 1): String {
    if (n == null) return "--"
    val f = NumberFormat.getNumberInstance(RO)
    f.maximumFractionDigits = digits
    return f.format(n)
}

fun stateLabel(st: EntityState?): String {
    if (st == null) return "Fără date"
    val words = mapOf(
        "on" to "Pornit", "off" to "Oprit", "unavailable" to "Indisponibil", "unknown" to "Fără date",
        "heat" to "Încălzire", "cool" to "Răcire", "idle" to "În așteptare", "charging" to "Încărcare",
        "discharging" to "Descărcare", "playing" to "Redă", "paused" to "Pauză", "standby" to "Standby",
        "auto" to "Automat", "dry" to "Dezumidificare", "fan_only" to "Ventilație", "heat_cool" to "Auto",
    )
    return words[st.state] ?: st.number?.let { "${fmt(it)} ${st.unit}".trim() } ?: st.state
}

fun deviceReading(d: Device): String {
    if (d.pending) return if (d.external) "Control separat" else "De integrat"
    val p = d.primary
    if (!p.valid) return stateLabel(p)
    if (d.kind in setOf("door", "window") && p.state in setOf("on", "off")) return if (p.state == "on") "Deschis" else "Închis"
    if (d.kind == "smoke" && p.state in setOf("on", "off")) return if (p.state == "on") "Fum detectat" else "Fără fum"
    val words = mapOf(
        "disarmed" to "Dezarmată", "armed_away" to "Armată - plecat", "armed_home" to "Armată - acasă",
        "triggered" to "Alarmă declanșată", "arming" to "Se armează", "cleaning" to "În curățare",
        "docked" to "La stație", "returning" to "Revine la stație", "printing" to "Imprimare", "error" to "Eroare",
    )
    if (p.domain == "climate" || p.domain == "water_heater") {
        val cur = p.attrDouble("current_temperature")
        val target = p.attrDouble("temperature")
        val mode = stateLabel(p)
        return listOfNotNull(cur?.let { "${fmt(it)}°" }, target?.let { "→ ${fmt(it)}°" }, mode).joinToString(" · ")
    }
    return words[p.state] ?: stateLabel(p)
}

/** Power in kW regardless of the sensor's W/kW unit; null when unknown (never 0). */
fun EntityState?.kw(): Double? {
    val n = this?.number ?: return null
    return when (unit.lowercase()) {
        "w" -> n / 1000.0
        "mw" -> n * 1000.0
        else -> n
    }
}

fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
fun JSONArray.strings(): List<String> = (0 until length()).map { optString(it) }
private fun JSONObject.str(key: String): String? = if (has(key) && !isNull(key)) optString(key).ifBlank { null } else null
