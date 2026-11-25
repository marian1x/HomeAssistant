package ro.salavat.casa.data

import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class ApiException(val status: Int, message: String) : IOException(message)

/**
 * Thin client for the existing Casa backend (server/app.py). The server contract
 * is unchanged: reads need only the session cookie; every write sends our exact
 * Origin plus the session's X-CSRF-Token, like the web app does.
 */
class Api(baseUrl: String, val jar: SessionCookieJar) {
    val base = baseUrl.trimEnd('/')
    private val url = base.toHttpUrl()
    val host: String = url.host
    val origin: String = buildString {
        append(url.scheme).append("://").append(url.host)
        if (url.port != okhttp3.HttpUrl.defaultPort(url.scheme)) append(':').append(url.port)
    }
    val secure = url.isHttps

    val client: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(jar)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(false)
        .build()

    private val sseClient = client.newBuilder().readTimeout(70, TimeUnit.SECONDS).build()

    suspend fun get(path: String): Any = call(Request.Builder().url(base + path).get().build())

    suspend fun post(path: String, body: JSONObject = JSONObject(), csrf: String? = null): Any {
        val builder = Request.Builder().url(base + path)
            .post(body.toString().toRequestBody(JSON))
            .header("Origin", origin)
        csrf?.let { builder.header("X-CSRF-Token", it) }
        return call(builder.build())
    }

    fun events(listener: EventSourceListener): EventSource =
        EventSources.createFactory(sseClient).newEventSource(
            Request.Builder().url("$base/api/events").header("Accept", "text/event-stream").build(), listener,
        )

    private suspend fun call(request: Request): Any = suspendCancellableCoroutine { cont ->
        val call = client.newCall(request)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (cont.isActive) cont.resumeWithException(e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val text = it.body?.string().orEmpty()
                    val parsed = runCatching { JSONTokener(text).nextValue() }.getOrNull()
                    if (it.isSuccessful) cont.resume(parsed ?: JSONObject())
                    else cont.resumeWithException(ApiException(it.code, errorText(it.code, parsed)))
                }
            }
        })
    }

    companion object {
        private val JSON = "application/json".toMediaType()

        fun errorText(code: Int, body: Any?): String {
            if (body is JSONObject) {
                body.optString("error").takeIf { it.isNotBlank() }?.let { return it }
                (body.opt("detail") as? JSONArray)?.optJSONObject(0)?.optString("msg")?.takeIf { it.isNotBlank() }?.let { return it }
                body.optString("detail").takeIf { it.isNotBlank() }?.let { return it }
            }
            return when (code) {
                401 -> "Autentificare necesară."
                403 -> "Acces refuzat."
                429 -> "Prea multe cereri. Așteaptă puțin."
                in 500..599 -> "Serverul nu răspunde momentan."
                else -> "Eroare $code"
            }
        }
    }
}
