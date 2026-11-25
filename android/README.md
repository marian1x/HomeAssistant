# Casa Salavat - aplicatia Android nativa

Aplicatie Kotlin + Jetpack Compose pentru `https://salavat.home.ro/casa/`.
Decizia proprietarului (2026-11-25): aplicatie **nativa** (nu shell WebView) si livrare
automata prin **Firebase App Distribution**. Serverul NU a fost modificat.

## Cum vorbeste cu serverul

Acelasi contract ca interfata web (`server/app.py`):

- Sesiune: cookie-ul `__Secure-casa_session`, pastrat criptat (AES-GCM, cheie in
  Android Keystore, `SecureStore`). Fara backup/transfer (`allowBackup=false`).
- Citiri: `GET /casa/api/*` doar cu cookie. Date live prin SSE `/casa/api/events`
  (snapshot + delte), deschis numai cat aplicatia e vizibila. Fara polling.
- Scrieri: `Origin: https://salavat.home.ro` + `X-CSRF-Token` (din snapshot), exact ca web.
- Login:
  - **Cont Casa** nativ: `POST /casa/auth/local` + `/casa/auth/local/verify` (parola + TOTP;
    la prima conectare: inrolare cod + parola noua).
  - **Home Assistant** (parola + MFA) intr-un WebView intern blocat pe `/casa/auth/` si
    `/home-assistant/auth/`; la intoarcerea pe `/casa/` cookie-ul trece in clientul nativ,
    iar depozitul WebView se goleste.
- Deblocare biometrica/PIN la pornire si dupa 60 s in fundal (setare, activa implicit).
- Comenzi: luminile direct; restul cu confirmare. Fara stari optimiste, fara retry,
  fara coada offline. Tesla: doar citire, nicio trezire.

`data/Model.kt` este portarea lui `src/model.ts` - pastreaza-le sincronizate.

## Build local

JDK: cel din Android Studio (`C:\Program Files\Android\Android Studio1\jbr`, Java 25).
AGP 9.5 / Gradle 9.6 / Kotlin 2.2 (built-in Kotlin), compileSdk 37, minSdk 26.

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio1\jbr"
cd android
.\gradlew.bat testDebugUnitTest assembleDebug     # productie, debug
.\gradlew.bat installMock                         # emulator + mock (vezi mai jos)
```

## Emulator pe date sintetice (fara HA, fara comenzi fizice)

```powershell
node android/tools/mock-server.mjs C:\Users\maria\home-control-web\tests\fixtures
.\gradlew.bat installMock      # build type `mock` -> http://10.0.2.2:8787/casa
```

Cont Casa pe mock: orice utilizator, parola `parola-test`, cod `123456`.
Mock-ul inregistreaza comenzile si raspunde cu delta SSE; nu atinge nimic real.

## Livrare automata (CI)

`.github/workflows/android.yml`: orice push pe `main` care atinge `android/**`:
teste -> APK release semnat -> artifact in Actions -> Firebase App Distribution
(grupul `owner`). Telefonul primeste notificare (email / App Tester), iar aplicatia
verifica la pornire (max. o data la 6 h) si ofera instalarea din Setari.
`versionCode` = numarul rularii GitHub Actions.

Secrete GitHub necesare (Settings -> Secrets -> Actions):

| Secret | Continut |
| --- | --- |
| `KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` | cheia de semnare (aceeasi pentru toate versiunile!) |
| `GOOGLE_SERVICES_JSON` | `google-services.json` al aplicatiei `ro.salavat.casa` |
| `FIREBASE_APP_ID` | ID-ul aplicatiei Android din Firebase |
| `FIREBASE_SERVICE_ACCOUNT` | JSON-ul unui service account cu rolul *Firebase App Distribution Admin* |

Fara secretele Firebase, APK-ul semnat ramane descarcabil ca artifact al rularii.

Keystore-ul de release NU este in repository. Pierderea lui inseamna ca actualizarile
nu se mai pot instala peste aplicatia existenta (trebuie dezinstalata).
