package ro.salavat.casa.data

import org.json.JSONArray
import org.json.JSONObject

/*
 * Server contracts added on 2026-11-25 (layout favorites/views, energy profiles, policy,
 * Tesla journal, BMS). The server is the single source of truth: these are parsed views.
 */

// ---------- Layout: order, groups, favorites, named views (per user, synced by the server) ----------

data class ViewDef(val id: String, val name: String, val icon: String, val items: List<String>) {
    fun json(): JSONObject = JSONObject().put("id", id).put("name", name).put("icon", icon).put("items", JSONArray(items))
}

data class Layout(
    val sort: String = "default",
    val order: List<String> = emptyList(),
    val groups: List<String> = emptyList(),
    val favorites: List<String> = emptyList(),
    val views: List<ViewDef> = emptyList(),
) {
    fun json(): JSONObject = JSONObject()
        .put("sort", sort).put("order", JSONArray(order)).put("groups", JSONArray(groups))
        .put("favorites", JSONArray(favorites)).put("views", JSONArray(views.map { it.json() }))

    companion object {
        val GROUPS = listOf("lights", "climate", "water", "power", "media", "mobility")
        fun parse(o: JSONObject?): Layout = if (o == null) Layout() else Layout(
            sort = o.optString("sort", "default"),
            order = o.optJSONArray("order")?.strings() ?: emptyList(),
            groups = o.optJSONArray("groups")?.strings() ?: emptyList(),
            favorites = o.optJSONArray("favorites")?.strings() ?: emptyList(),
            views = o.optJSONArray("views")?.objects()?.map {
                ViewDef(it.optString("id"), it.optString("name"), it.optString("icon", "star"), it.optJSONArray("items")?.strings() ?: emptyList())
            } ?: emptyList(),
        )
    }
}

/** Port of src/arrange.ts: devices in the chosen order; unknown ones keep default order after. */
fun arrange(items: List<Device>, layout: Layout, usage: Map<String, Int> = emptyMap()): List<Device> {
    if (layout.sort == "default") return items
    val rank = layout.order.withIndex().associate { it.value to it.index }
    fun uses(d: Device) = (d.entries.map { it.id } + d.primary.id).toSet().sumOf { usage[it] ?: 0 }
    return items.withIndex()
        .sortedWith(compareByDescending<IndexedValue<Device>> { if (layout.sort == "usage") uses(it.value) else 0 }
            .thenBy { rank[it.value.id] ?: (layout.order.size + it.index) })
        .map { it.value }
}

/** Moves [id] to position [to] among [shown], keeping hidden ids where they were (src/arrange.ts move). */
fun move(order: List<String>, shown: List<String>, id: String, to: Int): List<String> {
    val visible = shown.filter { it != id }.toMutableList()
    visible.add(to.coerceIn(0, visible.size), id)
    val showing = shown.toSet()
    val base = order + shown.filter { it !in order }
    var next = 0
    return base.map { if (it in showing) visible[next++] else it }
}

fun groupOrder(layout: Layout): List<String> =
    layout.groups.filter { it in Layout.GROUPS } + Layout.GROUPS.filter { it !in layout.groups }

// ---------- Energy profiles (admin edits/applies, everyone sees) ----------

data class EnergyProfile(val id: String, val name: String, val icon: String, val values: JSONObject, val updated: Double?) {
    fun keys(): List<String> = values.keys().asSequence().toList()
}

data class ActiveProfile(val id: String, val at: Double)

fun parseProfiles(a: JSONArray?): List<EnergyProfile> = a?.objects()?.map {
    EnergyProfile(it.optString("id"), it.optString("name"), it.optString("icon", "star"), it.optJSONObject("values") ?: JSONObject(),
        if (it.has("updated") && !it.isNull("updated")) it.optDouble("updated") else null)
} ?: emptyList()

// ---------- Energy policy (HA integration home_energy_policy, via /api/v1/energy-policy) ----------

data class PolicyField(
    val key: String, val label: String, val group: String, val kind: String,
    val min: Double?, val max: Double?, val step: Double, val unit: String, val choices: List<String>,
)

data class Policy(val revision: Int, val config: JSONObject, val schema: List<PolicyField>, val status: JSONObject) {
    fun fields(group: String) = schema.filter { it.group == group }

    companion object {
        fun parse(o: JSONObject) = Policy(
            revision = o.optInt("revision"),
            config = o.optJSONObject("config") ?: JSONObject(),
            schema = o.optJSONArray("schema")?.objects()?.map {
                PolicyField(
                    it.optString("key"), it.optString("label"), it.optString("group"), it.optString("kind", "number"),
                    it.optDoubleOrNull("min"), it.optDoubleOrNull("max"), it.optDouble("step", 1.0).takeIf { s -> s.isFinite() } ?: 1.0,
                    it.optString("unit"), it.optJSONArray("choices")?.strings() ?: emptyList(),
                )
            } ?: emptyList(),
            status = o.optJSONObject("status") ?: JSONObject(),
        )
    }
}

/** Same labels as src/EnergyPolicy.tsx. */
val POLICY_GROUPS = linkedMapOf(
    "general" to "Program și control", "prices" to "Tarife energie", "planning" to "Estimări consum",
    "safety" to "Protecții și temporizări", "battery" to "Baterie și prognoză", "tesla" to "Tesla",
    "quota" to "Tesla / buget API", "boiler" to "Apă caldă", "bindings" to "Asociere aparate",
    "tcl" to "Program TCL", "comfort" to "Confort", "winter" to "Profiluri iarnă", "summer" to "Profiluri vară",
    "whirlpool" to "Program Whirlpool iarnă", "fans" to "Trepte ventilatoare", "boost" to "Surplus pentru climatizare",
)

// ---------- Tesla journal (/api/tesla/log, /api/tesla/drive/{id}) ----------

data class Charge(
    val id: Int, val start: Long, val end: Long, val startSoc: Double?, val endSoc: Double?, val home: Boolean,
    val kwh: Double, val hours: Double, val maxKw: Double, val solar: Double, val battery: Double, val grid: Double,
    val price: Double?, val note: String?, val cost: Double?, val lat: Double?, val lon: Double?,
)

data class Drive(
    val id: Int, val start: Long, val end: Long, val approx: Boolean, val startSoc: Double?, val endSoc: Double?,
    val km: Double, val kwh: Double?, val hours: Double, val whKm: Double?, val avgKmh: Double?, val maxKmh: Double?,
    val outside: Double?, val cost: Double?, val startHome: Boolean, val endHome: Boolean,
    val startLat: Double?, val startLon: Double?, val endLat: Double?, val endLon: Double?, val path: List<Pair<Double, Double>>,
)

data class TeslaLog(
    val charges: List<Charge>, val drives: List<Drive>, val costPerKwh: Double?,
    val activeCharge: JSONObject?, val activeDrive: JSONObject?, val monthlyKm: List<Pair<Double, Double>>,
) {
    companion object {
        fun parse(o: JSONObject): TeslaLog {
            val active = o.optJSONObject("active")
            return TeslaLog(
                charges = o.optJSONArray("charges")?.objects()?.map {
                    Charge(
                        it.optInt("id"), it.optLong("start"), it.optLong("end"), it.optDoubleOrNull("start_soc"), it.optDoubleOrNull("end_soc"),
                        it.optBoolean("home"), it.optDouble("kwh", 0.0), it.optDouble("hours", 0.0), it.optDouble("max_kw", 0.0),
                        it.optDouble("solar_kwh", 0.0), it.optDouble("battery_kwh", 0.0), it.optDouble("grid_kwh", 0.0),
                        it.optDoubleOrNull("price_kwh"), it.optStringOrNull("note"), it.optDoubleOrNull("cost"),
                        it.optDoubleOrNull("lat"), it.optDoubleOrNull("lon"),
                    )
                } ?: emptyList(),
                drives = o.optJSONArray("drives")?.objects()?.map {
                    Drive(
                        it.optInt("id"), it.optLong("start"), it.optLong("end"), it.optBoolean("approx_start"),
                        it.optDoubleOrNull("start_soc"), it.optDoubleOrNull("end_soc"), it.optDouble("km", 0.0), it.optDoubleOrNull("kwh"),
                        it.optDouble("hours", 0.0), it.optDoubleOrNull("wh_km"), it.optDoubleOrNull("avg_kmh"), it.optDoubleOrNull("max_kmh"),
                        it.optDoubleOrNull("outside"), it.optDoubleOrNull("cost"), it.optBoolean("start_home"), it.optBoolean("end_home"),
                        it.optDoubleOrNull("start_lat"), it.optDoubleOrNull("start_lon"), it.optDoubleOrNull("end_lat"), it.optDoubleOrNull("end_lon"),
                        points(it.optJSONArray("path")),
                    )
                } ?: emptyList(),
                costPerKwh = o.optDoubleOrNull("cost_per_kwh"),
                activeCharge = active?.optJSONObject("charge"),
                activeDrive = active?.optJSONObject("drive"),
                monthlyKm = o.optJSONArray("monthly_km")?.objects()?.map { it.optDouble("start") to it.optDouble("km") } ?: emptyList(),
            )
        }
    }
}

data class DriveDetail(val path: List<Pair<Double, Double>>, val speeds: List<Double?>) {
    companion object {
        fun parse(o: JSONObject) = DriveDetail(
            points(o.optJSONArray("path")),
            o.optJSONArray("speeds")?.let { a -> (0 until a.length()).map { if (a.isNull(it)) null else a.optDouble(it) } } ?: emptyList(),
        )
    }
}

private fun points(a: JSONArray?): List<Pair<Double, Double>> = a?.let { arr ->
    (0 until arr.length()).mapNotNull { i -> arr.optJSONArray(i)?.let { p -> if (p.length() >= 2) p.optDouble(0) to p.optDouble(1) else null } }
} ?: emptyList()

// ---------- Battery BMS over Bluetooth (/api/battery/bms) and history ----------

data class Bms(
    val available: Boolean, val status: String, val at: Long?, val cells: List<Double>, val cellTemps: List<Double>,
    val spreadMv: Double?, val cellMin: Double?, val cellMax: Double?, val soh: Double?, val cycles: Double?,
    val mosTemp: Double?, val heater: String?, val controller: JSONObject?,
) {
    companion object {
        fun parse(o: JSONObject): Bms {
            val latest = o.optJSONObject("latest")
            val pack = latest?.optJSONObject("pack")
            fun list(k: String) = pack?.optJSONArray(k)?.let { a -> (0 until a.length()).map { a.optDouble(it) } } ?: emptyList()
            return Bms(
                o.optBoolean("available"), o.optString("status"), latest?.optLong("ts"), list("cells"), list("cell_temps"),
                pack?.optDoubleOrNull("cell_spread_mv"), pack?.optDoubleOrNull("cell_min"), pack?.optDoubleOrNull("cell_max"),
                pack?.optDoubleOrNull("soh"), pack?.optDoubleOrNull("cycles"), pack?.optDoubleOrNull("mos_temp"),
                latest?.optStringOrNull("heater_phase"), latest?.optJSONObject("controller"),
            )
        }
    }
}

data class BatteryPoint(val time: Long, val soc: Double?, val temp: Double?, val power: Double?)

data class AuditRow(val at: Double, val name: String, val action: String, val entity: String, val result: String)

fun JSONObject.optDoubleOrNull(key: String): Double? =
    if (has(key) && !isNull(key)) optDouble(key).takeIf { it.isFinite() } else null

fun JSONObject.optStringOrNull(key: String): String? =
    if (has(key) && !isNull(key)) optString(key).ifBlank { null } else null
