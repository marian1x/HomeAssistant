package ro.salavat.casa.ui

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import ro.salavat.casa.data.Repository

data class PendingCommand(val entity: String, val action: String, val value: Any?, val title: String, val text: String)

/**
 * Sends commands exactly like the web UI: no optimistic state (the switch flips
 * only when HA reports the new state), a busy flag that ignores repeated taps,
 * confirmation for everything except lights, and no retries or offline queue.
 */
class Commands(private val repo: Repository, private val scope: CoroutineScope, private val snackbar: SnackbarHostState) {
    val busy = mutableStateListOf<String>()
    var pending by mutableStateOf<PendingCommand?>(null)
        private set

    fun direct(entity: String, action: String, value: Any? = null) = send(entity, action, value)

    fun confirm(entity: String, action: String, value: Any?, title: String, text: String) {
        pending = PendingCommand(entity, action, value, title, text)
    }

    fun accept() {
        pending?.let { send(it.entity, it.action, it.value) }
        pending = null
    }

    fun dismiss() { pending = null }

    private fun send(entity: String, action: String, value: Any?) {
        if (entity in busy) return
        busy += entity
        scope.launch {
            try {
                repo.command(entity, action, value)
            } catch (e: Exception) {
                snackbar.showSnackbar(e.message ?: "Comanda nu a fost acceptată.")
            } finally {
                busy -= entity
            }
        }
    }
}

val LocalCommands = staticCompositionLocalOf<Commands> { error("Commands not provided") }

@Composable
fun ConfirmHost(commands: Commands) {
    val p = commands.pending ?: return
    AlertDialog(
        onDismissRequest = commands::dismiss,
        title = { Text(p.title) },
        text = { Text(p.text) },
        confirmButton = { TextButton(onClick = commands::accept) { Text("Confirmă") } },
        dismissButton = { TextButton(onClick = commands::dismiss) { Text("Renunță") } },
    )
}
