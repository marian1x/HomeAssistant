package ro.salavat.casa

import android.app.Application
import ro.salavat.casa.data.Api
import ro.salavat.casa.data.Prefs
import ro.salavat.casa.data.Repository
import ro.salavat.casa.data.SecureStore
import ro.salavat.casa.data.SessionCookieJar
import ro.salavat.casa.update.Updater
import okhttp3.HttpUrl.Companion.toHttpUrl

/** Manual DI: one instance of each collaborator for the whole process. */
class CasaApp : Application() {
    lateinit var repo: Repository private set
    lateinit var prefs: Prefs private set
    lateinit var updater: Updater private set

    override fun onCreate() {
        super.onCreate()
        val host = BuildConfig.BASE_URL.toHttpUrl().host
        val api = Api(BuildConfig.BASE_URL, SessionCookieJar(SecureStore(this), host))
        repo = Repository(api)
        prefs = Prefs(this)
        updater = Updater(this, prefs)
        updater.schedule()
    }
}
