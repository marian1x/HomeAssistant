package ro.salavat.casa.data

import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import org.json.JSONArray
import org.json.JSONObject

/**
 * Cookie jar for the single Casa origin. Persistent cookies (the 30-day session)
 * are sealed in [SecureStore]; short-lived login cookies stay in memory.
 * Cookies for any other host are dropped.
 */
class SessionCookieJar(private val store: SecureStore, private val host: String) : CookieJar {
    private val cookies = ArrayList<Cookie>()

    init {
        store.get(KEY)?.let { raw ->
            runCatching {
                val arr = JSONArray(raw)
                for (i in 0 until arr.length()) decode(arr.getJSONObject(i))?.let { cookies += it }
            }
        }
        prune()
    }

    @Synchronized
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        if (url.host != host) return
        for (c in cookies) {
            this.cookies.removeAll { it.name == c.name && it.path == c.path && it.domain == c.domain }
            if (c.expiresAt > System.currentTimeMillis()) this.cookies += c
        }
        persist()
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        if (url.host != host) return emptyList()
        prune()
        return cookies.filter { it.matches(url) }
    }

    @Synchronized
    fun hasSession(): Boolean {
        prune()
        return cookies.any { it.name.endsWith("casa_session") }
    }

    /** Adopts the session cookie created by the in-app HA login WebView. */
    @Synchronized
    fun adopt(name: String, value: String, secure: Boolean) {
        val cookie = Cookie.Builder()
            .name(name).value(value).hostOnlyDomain(host).path("/casa/")
            .expiresAt(System.currentTimeMillis() + 30L * 24 * 3600 * 1000)
            .httpOnly()
            .apply { if (secure) secure() }
            .build()
        cookies.removeAll { it.name == name }
        cookies += cookie
        persist()
    }

    @Synchronized
    fun clear() {
        cookies.clear()
        store.put(KEY, null)
    }

    private fun prune() {
        val now = System.currentTimeMillis()
        cookies.removeAll { it.expiresAt <= now }
    }

    private fun persist() {
        val arr = JSONArray()
        cookies.filter { it.persistent }.forEach { arr.put(encode(it)) }
        store.put(KEY, if (arr.length() == 0) null else arr.toString())
    }

    private fun encode(c: Cookie) = JSONObject()
        .put("n", c.name).put("v", c.value).put("d", c.domain).put("p", c.path)
        .put("e", c.expiresAt).put("s", c.secure).put("h", c.httpOnly).put("o", c.hostOnly)

    private fun decode(o: JSONObject): Cookie? = runCatching {
        Cookie.Builder().name(o.getString("n")).value(o.getString("v")).path(o.getString("p"))
            .expiresAt(o.getLong("e"))
            .apply {
                if (o.optBoolean("o", true)) hostOnlyDomain(o.getString("d")) else domain(o.getString("d"))
                if (o.optBoolean("s")) secure()
                if (o.optBoolean("h")) httpOnly()
            }.build()
    }.getOrNull()

    private companion object { const val KEY = "cookies" }
}
