package ro.salavat.casa.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ro.salavat.casa.BuildConfig
import ro.salavat.casa.data.KILLSWITCH
import ro.salavat.casa.data.Prefs
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.Snapshot
import ro.salavat.casa.data.ThemeMode
import ro.salavat.casa.ui.LocalCommands
import ro.salavat.casa.ui.LocalNav
import ro.salavat.casa.ui.Sub
import androidx.compose.material3.OutlinedTextField
import androidx.compose.ui.text.input.PasswordVisualTransformation
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.update.UpdateState
import ro.salavat.casa.update.Updater

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(s: Snapshot, repo: Repository, prefs: Prefs, updater: Updater, padding: PaddingValues) {
    val commands = LocalCommands.current
    val scope = rememberCoroutineScope()
    val theme by prefs.theme.collectAsState()
    val biometric by prefs.biometric.collectAsState()
    val keepOn by prefs.keepScreenOn.collectAsState()
    val update by updater.state.collectAsState()
    var confirmAll by remember { mutableStateOf(false) }
    var password by remember { mutableStateOf(false) }
    val nav = LocalNav.current
    val user = s.user
    val paused = s.states[KILLSWITCH]?.state == "on"

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = padding.calculateBottomPadding() + 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Setări", style = MaterialTheme.typography.headlineMedium)

        GlassCard {
            Text(user?.name ?: "Cont", style = MaterialTheme.typography.titleLarge)
            Text(
                listOfNotNull(user?.roleLabel, if (user?.local == true) "Cont Casa" else "Cont Home Assistant").joinToString(" · "),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(if (s.connected) "HA conectat" else "HA deconectat", color = if (s.connected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelLarge)
        }

        GlassCard {
            Text("Aspect", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                ThemeMode.entries.forEachIndexed { i, m ->
                    SegmentedButton(theme == m, { prefs.setTheme(m) }, SegmentedButtonDefaults.itemShape(i, ThemeMode.entries.size)) { Text(m.label) }
                }
            }
            Toggle("Deblocare cu amprentă / PIN", "Cere autentificarea telefonului la deschidere", biometric, prefs::setBiometric)
            Toggle("Ecran mereu pornit", "Pentru tableta de perete", keepOn, prefs::setKeepScreenOn)
        }

        GlassCard {
            Text("Administrare", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            TextButton(onClick = { nav.push(Sub.Policy) }) { Text("Politică energie și profile") }
            if (user?.admin == true && user.canConfigure) TextButton(onClick = { nav.push(Sub.Audit) }) { Text("Jurnal de comenzi") }
            if (user?.local == true) TextButton(onClick = { password = true }) { Text("Schimbă parola") }
        }

        if (user?.canControl == true) GlassCard {
            Text("Pauză globală automatizări", style = MaterialTheme.typography.titleMedium)
            Text(
                if (paused) "Automatizările sunt OPRITE. Controlul manual rămâne disponibil." else "Automatizările rulează normal.",
                color = if (paused) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            if (!paused) Button(
                onClick = { commands.confirm(KILLSWITCH, "turn_on", null, "Oprești toate automatizările?", "Pauza oprește automatizările, nu aparatele. Reluarea cere drepturi de configurare.") },
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
            ) { Text("Activează pauza") }
            else if (user.canConfigure) Button(onClick = {
                commands.confirm(KILLSWITCH, "turn_off", null, "Reiei automatizările?", "Automatizările vor porni din nou.")
            }) { Text("Reia automatizările") }
        }

        GlassCard {
            Text("Actualizări aplicație", style = MaterialTheme.typography.titleMedium)
            Text("Versiune ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            when (val u = update) {
                UpdateState.Unavailable -> Text("Build de dezvoltare: actualizările vin doar în versiunea semnată din GitHub.", style = MaterialTheme.typography.bodySmall)
                UpdateState.Idle -> OutlinedButton(onClick = { updater.check() }) { Text("Caută actualizări") }
                UpdateState.Checking -> LinearProgressIndicator(Modifier.fillMaxWidth())
                UpdateState.UpToDate -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Ai ultima versiune.", Modifier.weight(1f)); TextButton(onClick = { updater.check() }) { Text("Verifică") }
                }
                UpdateState.NeedsPermission -> {
                    Text("Pentru actualizare, permite aplicației să instaleze aplicații (o singură dată).", style = MaterialTheme.typography.bodySmall)
                    Button(onClick = { updater.openInstallPermission() }) { Text("Deschide permisiunea") }
                }
                is UpdateState.Available -> {
                    Text("Disponibilă: ${u.release.version}", style = MaterialTheme.typography.titleSmall)
                    u.release.notes.takeIf { it.isNotBlank() }?.let { Text(it.take(600), style = MaterialTheme.typography.bodySmall) }
                    Button(onClick = { updater.install(u.release) }) { Text("Descarcă și instalează") }
                    Text("Verific semnătura APK-ului înainte de instalare; Android cere confirmarea ta.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                is UpdateState.Downloading -> {
                    Text("Se descarcă ${u.percent}%")
                    LinearProgressIndicator({ u.percent / 100f }, Modifier.fillMaxWidth())
                }
                is UpdateState.Failed -> {
                    Text(u.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = { updater.check() }) { Text("Reîncearcă") }
                }
            }
        }

        GlassCard {
            Text("Sesiune", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = { scope.launch { runCatching { repo.logout(false) } } }, Modifier.fillMaxWidth()) { Text("Deconectare") }
            if (user?.local != true) TextButton(onClick = { confirmAll = true }, Modifier.fillMaxWidth()) {
                Text("Deconectează toate dispozitivele", color = MaterialTheme.colorScheme.error)
            }
        }
    }

    if (password) PasswordDialog { password = false }

    if (confirmAll) AlertDialog(
        onDismissRequest = { confirmAll = false },
        title = { Text("Deconectezi toate dispozitivele?") },
        text = { Text("Se închid toate sesiunile Casa ale contului tău: telefon, tabletă, browsere.") },
        confirmButton = { TextButton(onClick = { confirmAll = false; scope.launch { runCatching { repo.logout(true) } } }) { Text("Deconectează") } },
        dismissButton = { TextButton(onClick = { confirmAll = false }) { Text("Renunță") } },
    )
}

/** Casa accounts change their own password (server checks length/strength, CSRF, audit). */
@Composable
private fun PasswordDialog(onDone: () -> Unit) {
    val commands = LocalCommands.current
    var current by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var again by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text("Schimbă parola") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(current, { current = it }, label = { Text("Parola actuală") }, singleLine = true, visualTransformation = PasswordVisualTransformation())
                OutlinedTextField(new, { new = it }, label = { Text("Parola nouă") }, singleLine = true, visualTransformation = PasswordVisualTransformation())
                OutlinedTextField(again, { again = it }, label = { Text("Repetă parola nouă") }, singleLine = true, isError = again.isNotEmpty() && again != new,
                    visualTransformation = PasswordVisualTransformation())
            }
        },
        confirmButton = {
            TextButton(enabled = current.isNotEmpty() && new.length >= 12 && new == again, onClick = {
                commands.launch("password", "Parola a fost schimbată.") { commands.repo.changePassword(current, new) }
                onDone()
            }) { Text("Schimbă") }
        },
        dismissButton = { TextButton(onClick = onDone) { Text("Renunță") } },
    )
}

@Composable
private fun Toggle(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Switch(checked, onChange)
    }
}
