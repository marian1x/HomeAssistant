package ro.salavat.casa.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import ro.salavat.casa.data.Drive

/** Detail screens opened over the tabs (energy-flow nodes, policy, Tesla drive, audit…). */
sealed interface Sub {
    val title: String
    data object Inverter : Sub { override val title = "Invertor și producție" }
    data object Battery : Sub { override val title = "Baterie casă" }
    data object House : Sub { override val title = "Consum casă" }
    data object Grid : Sub { override val title = "Rețea" }
    data object Policy : Sub { override val title = "Politică energie și profile" }
    data object Audit : Sub { override val title = "Jurnal de comenzi" }
    data class TeslaDrive(val drive: Drive) : Sub { override val title = "Deplasare" }
}

/** Tab + detail stack + open device sheet; one instance for the signed-in UI. */
class Nav(initial: Tab = Tab.HOME) {
    var tab by mutableStateOf(initial)
    var stack by mutableStateOf(emptyList<Sub>())
        private set
    var device by mutableStateOf<String?>(null)

    val top: Sub? get() = stack.lastOrNull()

    fun go(tab: Tab) { this.tab = tab; stack = emptyList() }
    fun push(sub: Sub) { stack = stack + sub }
    fun pop() { stack = stack.dropLast(1) }
    fun open(deviceId: String) { device = deviceId }

    companion object {
        /** The open tab survives rotation and process death; detail screens reopen from it. */
        val Saver = androidx.compose.runtime.saveable.Saver<Nav, String>(save = { it.tab.route }, restore = { Nav(Tab.of(it) ?: Tab.HOME) })
    }
}

val LocalNav = staticCompositionLocalOf<Nav> { error("Nav not provided") }
