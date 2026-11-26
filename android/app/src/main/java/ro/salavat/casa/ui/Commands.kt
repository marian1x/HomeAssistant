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
import ro.salavat.casa.data.Layout
import ro.salavat.casa.data.Repository

/** A confirmation waiting for the user; [run] is what happens on "Confirmă". */
data class PendingCommand(val title: String, val text: String, val key: String, val success: String?, val run: suspend () -> Unit)

/**
 * Sends commands exactly like the web UI: no optimistic state (the switch flips
 * only when HA reports the new state), a busy flag that ignores repeated taps,
 * confirmation for everything except lights, and no retries or offline queue.
 */
class Commands(val repo: Repository, private val scope: CoroutineScope, private val snackbar: SnackbarHostState) {
    val busy = mutableStateListOf<String>()
    var pending by mutableStateOf<PendingCommand?>(null)
        private set

    fun direct(entity: String, action: String, value: Any? = null) = launch(entity, null) { repo.command(entity, action, value) }

    fun confirm(entity: String, action: String, value: Any?, title: String, text: String) {
        pending = PendingCommand(title, text, entity, null) { repo.command(entity, action, value) }
    }

    /** Any confirmed server action (Tesla limit, profile, policy…), with an optional success message. */
    fun confirmRun(title: String, text: String, key: String, success: String? = null, run: suspend () -> Unit) {
        pending = PendingCommand(title, text, key, success, run)
    }

    fun launch(key: String, success: String? = null, run: suspend () -> Unit) {
        if (key in busy) return
        busy += key
        scope.launch {
            try {
                run()
                success?.let { snackbar.showSnackbar(it) }
            } catch (e: Exception) {
                snackbar.showSnackbar(e.message ?: "Comanda nu a fost acceptată.")
            } finally {
                busy -= key
            }
        }
    }

    /** Display preference of this user (favorites, views, order); saved on the server. */
    fun layout(change: (Layout) -> Layout) {
        val current = repo.snapshot.value?.layout ?: return
        launch("layout") { repo.saveLayout(change(current)) }
    }

    fun message(text: String) { scope.launch { snackbar.showSnackbar(text) } }

    fun accept() {
        pending?.let { launch(it.key, it.success, it.run) }
        pending = null
    }

    fun dismiss() { pending = null }
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
