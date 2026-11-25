package ro.salavat.casa.ui.login

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Key
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import ro.salavat.casa.data.LocalChallenge
import ro.salavat.casa.data.Repository
import ro.salavat.casa.ui.components.GlassCard
import ro.salavat.casa.ui.theme.Brand

private enum class Mode { CHOOSE, LOCAL, HA }

@Composable
fun LoginScreen(repo: Repository) {
    var mode by remember { mutableStateOf(Mode.CHOOSE) }
    if (mode == Mode.HA) {
        HaLogin(repo.api.base, onSession = repo::adoptSession, onCancel = { mode = Mode.CHOOSE })
        return
    }
    Box(Modifier.fillMaxSize().safeDrawingPadding().imePadding(), contentAlignment = Alignment.Center) {
        Column(
            Modifier.widthIn(max = 460.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Box(Modifier.size(84.dp), contentAlignment = Alignment.Center) {
                GlassCard(tint = Brand, padding = 18.dp) { Icon(Icons.Rounded.Home, null, Modifier.size(40.dp), tint = androidx.compose.ui.graphics.Color.White) }
            }
            Text("Casa Salavat", style = MaterialTheme.typography.displaySmall)
            Text("Controlul casei, energia și Tesla, live.", color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
            Spacer(Modifier.height(8.dp))
            AnimatedContent(mode, label = "login") { m ->
                when (m) {
                    Mode.CHOOSE -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Button(onClick = { mode = Mode.HA }, Modifier.fillMaxWidth().heightIn(min = 56.dp), shape = RoundedCornerShape(18.dp)) {
                            Icon(Icons.Rounded.Home, null); Spacer(Modifier.size(8.dp)); Text("Conectare cu Home Assistant")
                        }
                        OutlinedButton(onClick = { mode = Mode.LOCAL }, Modifier.fillMaxWidth().heightIn(min = 56.dp), shape = RoundedCornerShape(18.dp)) {
                            Icon(Icons.Rounded.Key, null); Spacer(Modifier.size(8.dp)); Text("Cont Casa")
                        }
                        Text(
                            "Home Assistant cere parola și codul MFA pe pagina lui. Contul Casa cere parolă și cod din aplicația de autentificare.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center,
                        )
                    }
                    else -> LocalLogin(repo, onBack = { mode = Mode.CHOOSE })
                }
            }
        }
    }
}

@Composable
private fun LocalLogin(repo: Repository, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var challenge by remember { mutableStateOf<LocalChallenge?>(null) }
    var code by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var newPassword2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun submit() {
        error = null
        val c = challenge
        if (c != null && c.mustChange) {
            if (newPassword.length < 12) { error = "Parola nouă trebuie să aibă minimum 12 caractere."; return }
            if (newPassword != newPassword2) { error = "Parolele noi nu coincid."; return }
        }
        busy = true
        scope.launch {
            try {
                if (c == null) {
                    challenge = repo.localLogin(username.trim(), password)
                    password = ""
                } else {
                    repo.localVerify(code.trim(), if (c.mustChange) newPassword else null)
                }
            } catch (e: Exception) {
                error = e.message ?: "Conectarea a eșuat."
                if (e.message?.contains("expirat") == true) challenge = null
            } finally {
                busy = false
            }
        }
    }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val c = challenge
        if (c == null) {
            OutlinedTextField(username, { username = it }, Modifier.fillMaxWidth(), label = { Text("Utilizator") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next))
            OutlinedTextField(password, { password = it }, Modifier.fillMaxWidth(), label = { Text("Parolă") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done))
        } else {
            Text("Bun venit, ${c.name}", style = MaterialTheme.typography.titleMedium)
            if (c.enrollSecret != null) GlassCard {
                Text("Configurează codul de autentificare", style = MaterialTheme.typography.titleSmall)
                Text("Adaugă acest cont în aplicația de autentificare, apoi introdu codul de 6 cifre.", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
                Text(c.enrollSecret.chunked(4).joinToString(" "), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodyLarge)
                Row {
                    TextButton(onClick = {
                        try {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(c.enrollUri)))
                        } catch (_: ActivityNotFoundException) {
                            Toast.makeText(context, "Nu există o aplicație de autentificare instalată.", Toast.LENGTH_LONG).show()
                        }
                    }) { Text("Deschide aplicația") }
                    TextButton(onClick = { clipboard.setText(AnnotatedString(c.enrollSecret)) }) { Text("Copiază") }
                }
            }
            OutlinedTextField(code, { if (it.length <= 8) code = it.filter(Char::isDigit) }, Modifier.fillMaxWidth(), label = { Text("Cod de 6 cifre") },
                singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done))
            if (c.mustChange) {
                Text("Alege o parolă nouă (minimum 12 caractere).", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(newPassword, { newPassword = it }, Modifier.fillMaxWidth(), label = { Text("Parolă nouă") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                OutlinedTextField(newPassword2, { newPassword2 = it }, Modifier.fillMaxWidth(), label = { Text("Repetă parola nouă") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(
            onClick = ::submit,
            enabled = !busy && if (c == null) username.isNotBlank() && password.isNotEmpty() else code.length == 6,
            modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp), shape = RoundedCornerShape(18.dp),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp) else Text(if (c == null) "Continuă" else "Conectare")
        }
        TextButton(onClick = { if (c != null) { challenge = null; code = "" } else onBack() }, Modifier.align(Alignment.CenterHorizontally)) { Text("Înapoi") }
    }
}
