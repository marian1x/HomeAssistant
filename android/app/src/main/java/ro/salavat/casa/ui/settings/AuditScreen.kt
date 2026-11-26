package ro.salavat.casa.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import ro.salavat.casa.data.AuditRow
import ro.salavat.casa.data.Repository
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.components.Page
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Last 100 commands sent through Casa (HA administrators only, like the web "Jurnal"). */
@Composable
fun AuditScreen(repo: Repository, padding: PaddingValues, onBack: () -> Unit) {
    var rows by remember { mutableStateOf<Result<List<AuditRow>>?>(null) }
    LaunchedEffect(Unit) { rows = runCatching { repo.audit() } }
    val format = remember { SimpleDateFormat("dd.MM HH:mm", Locale.forLanguageTag("ro")) }
    Page(padding, "Jurnal de comenzi", "Ultimele 100 de acțiuni din aplicație și browser", onBack) {
        when (val r = rows) {
            null -> CircularProgressIndicator()
            else -> r.fold(
                onSuccess = { list ->
                    if (list.isEmpty()) Text("Nu există comenzi înregistrate.")
                    list.forEach { row ->
                        GlassCard {
                            Row {
                                Text(row.name, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                                Text(format.format(Date((row.at * 1000).toLong())), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Column {
                                Text("${row.action} · ${row.entity}", style = MaterialTheme.typography.bodySmall)
                                Text(row.result, style = MaterialTheme.typography.labelSmall,
                                    color = if (row.result.startsWith("Fara")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                },
                onFailure = { Text(it.message ?: "Jurnalul nu este disponibil.", color = MaterialTheme.colorScheme.error) },
            )
        }
    }
}
