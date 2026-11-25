package ro.salavat.casa.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.ElectricCar
import androidx.compose.material.icons.rounded.Fingerprint
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Widgets
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.background
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import ro.salavat.casa.data.AuthState
import ro.salavat.casa.data.Device
import ro.salavat.casa.data.Live
import ro.salavat.casa.data.Prefs
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.buildDevices
import ro.salavat.casa.ui.components.AuroraBackground
import ro.salavat.casa.ui.components.EnergyMix
import ro.salavat.casa.ui.components.Flows
import ro.salavat.casa.ui.devices.DeviceSheet
import ro.salavat.casa.ui.devices.DevicesScreen
import ro.salavat.casa.ui.devices.Pill
import ro.salavat.casa.ui.energy.EnergyScreen
import ro.salavat.casa.ui.home.HomeScreen
import ro.salavat.casa.ui.login.LoginScreen
import ro.salavat.casa.ui.settings.SettingsScreen
import ro.salavat.casa.ui.tesla.TeslaScreen
import ro.salavat.casa.ui.theme.Energy
import ro.salavat.casa.update.Updater

enum class Tab(val route: String, val label: String, val icon: ImageVector) {
    HOME("home", "Acasă", Icons.Rounded.Home),
    ENERGY("energy", "Energie", Icons.Rounded.Bolt),
    DEVICES("devices", "Dispozitive", Icons.Rounded.Widgets),
    TESLA("tesla", "Tesla", Icons.Rounded.ElectricCar),
    SETTINGS("settings", "Setări", Icons.Rounded.Settings);

    companion object { fun of(route: String?) = entries.firstOrNull { it.route == route } }
}

@Composable
fun AppRoot(repo: Repository, prefs: Prefs, updater: Updater, route: String?, onRouteHandled: () -> Unit, locked: Boolean, onUnlock: () -> Unit) {
    val auth by repo.auth.collectAsState()
    val snapshot by repo.snapshot.collectAsState()
    val mix = remember(snapshot) { snapshot?.let { Flows.of(it).mix() } ?: EnergyMix() }
    AuroraBackground(mix) {
        when {
            auth == AuthState.SIGNED_OUT -> LoginScreen(repo)
            locked -> LockScreen(onUnlock)
            snapshot == null -> Loading(repo)
            else -> Main(repo, prefs, updater, route, onRouteHandled)
        }
    }
}

@Composable
private fun Loading(repo: Repository) {
    val live by repo.live.collectAsState()
    Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        CircularProgressIndicator()
        Spacer(Modifier.height(16.dp))
        Text(
            when (val l = live) { is Live.Offline -> "Fără conexiune: ${l.reason}\nReîncerc automat."; else -> "Se conectează la casă…" },
            textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun LockScreen(onUnlock: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Icon(Icons.Rounded.Fingerprint, null, Modifier.size(72.dp), tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(16.dp))
        Text("Casa Salavat este blocată", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(20.dp))
        Button(onClick = onUnlock) { Text("Deblochează") }
    }
}

@Composable
private fun Main(repo: Repository, prefs: Prefs, updater: Updater, route: String?, onRouteHandled: () -> Unit) {
    val s by repo.snapshot.collectAsState()
    val snapshot = s ?: return
    val live by repo.live.collectAsState()
    var tab by rememberSaveable { mutableStateOf(Tab.HOME) }
    Tab.of(route)?.let { tab = it; onRouteHandled() }
    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val commands = remember { Commands(repo, scope, snackbar) }
    val wide = LocalConfiguration.current.screenWidthDp >= 600

    CompositionLocalProvider(LocalCommands provides commands) {
        Row(Modifier.fillMaxSize()) {
            if (wide) NavigationRail(containerColor = Color.Transparent, modifier = Modifier.statusBarsPadding()) {
                Spacer(Modifier.height(12.dp))
                Tab.entries.forEach { t ->
                    NavigationRailItem(selected = tab == t, onClick = { tab = t }, icon = { Icon(t.icon, null) }, label = { Text(t.label) })
                }
            }
            Scaffold(
                modifier = Modifier.weight(1f),
                containerColor = Color.Transparent,
                contentWindowInsets = WindowInsets.safeDrawing,
                snackbarHost = { SnackbarHost(snackbar) },
                topBar = { StatusStrip(snapshot.connected, live, snapshot.user?.name) },
                bottomBar = {
                    if (!wide) NavigationBar(containerColor = MaterialTheme.colorScheme.surfaceContainer) {
                        Tab.entries.forEach { t ->
                            NavigationBarItem(
                                selected = tab == t, onClick = { tab = t }, icon = { Icon(t.icon, null) }, label = { Text(t.label) },
                                colors = NavigationBarItemDefaults.colors(indicatorColor = MaterialTheme.colorScheme.primaryContainer),
                            )
                        }
                    }
                },
            ) { padding ->
                AnimatedContent(tab, transitionSpec = { fadeIn(tween(220)) togetherWith fadeOut(tween(120)) }, label = "tab") { t ->
                    val open: (Device) -> Unit = { openId = it.id }
                    when (t) {
                        Tab.HOME -> HomeScreen(snapshot, padding, open)
                        Tab.ENERGY -> EnergyScreen(snapshot, repo, padding)
                        Tab.DEVICES -> DevicesScreen(snapshot, padding, open)
                        Tab.TESLA -> TeslaScreen(snapshot, padding)
                        Tab.SETTINGS -> SettingsScreen(snapshot, repo, prefs, updater, padding)
                    }
                }
            }
        }
        // The sheet follows live state: it re-resolves the device from each new snapshot.
        openId?.let { id ->
            val device = remember(snapshot, id) { buildDevices(snapshot).firstOrNull { it.id == id } }
            if (device == null) openId = null else DeviceSheet(device, snapshot.user) { openId = null }
        }
        ConfirmHost(commands)
    }
}

@Composable
private fun StatusStrip(connected: Boolean, live: Live, name: String?) {
    Row(
        Modifier.fillMaxWidth()
            .background(Brush.verticalGradient(listOf(MaterialTheme.colorScheme.background.copy(alpha = 0.96f), MaterialTheme.colorScheme.background.copy(alpha = 0.82f))))
            .statusBarsPadding().padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text("Casa Salavat", style = MaterialTheme.typography.titleMedium)
            name?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        val (text, color) = when {
            live is Live.Offline -> "Offline" to MaterialTheme.colorScheme.error
            live is Live.Connecting -> "Conectare…" to Energy.solar
            !connected -> "HA deconectat" to MaterialTheme.colorScheme.error
            else -> "HA Live" to Energy.load
        }
        Pill(text, color)
    }
}
