package ro.salavat.casa.data

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import org.json.JSONArray
import org.json.JSONObject

enum class AuthState { CHECKING, SIGNED_OUT, SIGNED_IN }

sealed interface Live {
    data object Connecting : Live
    data object Online : Live
    data class Offline(val reason: String) : Live
}

data class HistoryPoint(val time: Long, val solar: Double?, val load: Double?, val battery: Double?, val grid: Double?)
data class History(val unit: String, val points: List<HistoryPoint>)

/** First step of a Casa-account login, as returned by POST /auth/local. */
data class LocalChallenge(val name: String, val mustChange: Boolean, val enrollSecret: String?, val enrollUri: String?)

class Repository(val api: Api) {
    private val _auth = MutableStateFlow(if (api.jar.hasSession()) AuthState.CHECKING else AuthState.SIGNED_OUT)
    val auth: StateFlow<AuthState> = _auth.asStateFlow()

    private val _snapshot = MutableStateFlow<Snapshot?>(null)
    val snapshot: StateFlow<Snapshot?> = _snapshot.asStateFlow()

    private val _live = MutableStateFlow<Live>(Live.Connecting)
    val live: StateFlow<Live> = _live.asStateFlow()

    private fun signedOut() {
        api.jar.clear()
        _snapshot.value = null
        _auth.value = AuthState.SIGNED_OUT
    }

    /**
     * Holds the SSE stream open while the caller's scope is active (the UI is
     * started). Each new connection begins with a full snapshot, so no polling is
     * needed. Reconnects with backoff; stops for good on 401.
     */
    suspend fun stayLive() {
        var backoff = 2_000L
        while (_auth.value != AuthState.SIGNED_OUT) {
            _live.value = Live.Connecting
            val result = runCatching { stream { backoff = 2_000L } }
            val error = result.exceptionOrNull()
            if (error is ApiException && error.status == 401) {
                signedOut()
                return
            }
            if (_snapshot.value == null && _auth.value == AuthState.CHECKING && error is ApiException && error.status == 403) {
                signedOut()
                return
            }
            _live.value = Live.Offline(error?.message ?: "Conexiune închisă")
            delay(backoff)
            backoff = (backoff * 2).coerceAtMost(60_000L)
        }
    }

    private suspend fun stream(onOpen: () -> Unit) {
        callbackFlow<Unit> {
            val source = api.events(object : EventSourceListener() {
                override fun onOpen(eventSource: EventSource, response: Response) {
                    onOpen()
                    _live.value = Live.Online
                }

                override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                    val packet = runCatching { JSONObject(data) }.getOrNull() ?: return
                    if (packet.optString("type") == "delta") {
                        _snapshot.value?.let { _snapshot.value = it.withDelta(packet) }
                    } else {
                        _snapshot.value = Snapshot.parse(packet)
                        _auth.value = AuthState.SIGNED_IN
                    }
                }

                override fun onClosed(eventSource: EventSource) {
                    close()
                }

                override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                    val error = response?.let {
                        val body = runCatching { it.body?.string() }.getOrNull()
                        ApiException(it.code, Api.errorText(it.code, runCatching { JSONObject(body ?: "") }.getOrNull()))
                    } ?: t ?: IllegalStateException("Conexiune întreruptă")
                    close(error)
                }
            })
            awaitClose { source.cancel() }
        }.collect {}
    }

    suspend fun command(entityId: String, action: String, value: Any? = null) {
        val csrf = _snapshot.value?.csrf ?: throw ApiException(401, "Sesiune expirată.")
        val body = JSONObject().put("entity_id", entityId).put("action", action)
        if (value != null) body.put("value", value)
        try {
            api.post("/api/command", body, csrf)
        } catch (e: ApiException) {
            if (e.status == 401) signedOut()
            throw e
        }
    }

    suspend fun history(period: String): History {
        val o = api.get("/api/history?period=$period") as JSONObject
        val pts = o.optJSONArray("points") ?: JSONArray()
        fun JSONObject.d(k: String) = if (has(k) && !isNull(k)) optDouble(k).takeIf { it.isFinite() } else null
        return History(
            unit = o.optString("unit", "kW"),
            points = (0 until pts.length()).mapNotNull { pts.optJSONObject(it) }.map {
                HistoryPoint(it.optDouble("time").toLong(), it.d("solar"), it.d("load"), it.d("battery"), it.d("grid"))
            },
        )
    }

    // ---- Casa accounts (password + mandatory TOTP), POST /casa/auth/local[/verify] ----

    suspend fun localLogin(username: String, password: String): LocalChallenge {
        val o = api.post("/auth/local", JSONObject().put("username", username).put("password", password)) as JSONObject
        val enroll = o.optJSONObject("enroll")
        return LocalChallenge(
            name = o.optString("name"),
            mustChange = o.optBoolean("must_change"),
            enrollSecret = enroll?.optString("secret"),
            enrollUri = enroll?.optString("uri"),
        )
    }

    suspend fun localVerify(code: String, newPassword: String?) {
        val body = JSONObject().put("code", code)
        if (newPassword != null) body.put("new_password", newPassword)
        api.post("/auth/local/verify", body)
        _auth.value = AuthState.CHECKING
    }

    /** Session cookie captured from the in-app Home Assistant login. */
    fun adoptSession(name: String, value: String) {
        api.jar.adopt(name, value, api.secure)
        _auth.value = AuthState.CHECKING
    }

    suspend fun logout(everywhere: Boolean) {
        val csrf = _snapshot.value?.csrf
        try {
            api.post(if (everywhere) "/api/logout-all" else "/api/logout", JSONObject(), csrf)
        } finally {
            signedOut()
        }
    }
}
