# Casa Salavat - aplicatia Android nativa

Aplicatie Kotlin + Jetpack Compose pentru `https://salavat.home.ro/casa/`.
Decizii proprietar: aplicatie **nativa** (nu shell WebView), 2026-11-25; livrare automata prin
**GitHub Releases** (ca aplicatia de trading, fara Firebase), 2026-11-25.

## Serverul este sursa unica de adevar

Browserul si APK-ul sunt doua vederi ale aceleiasi stari de pe server (`server/app.py`):

- Snapshot-ul SSE (`/casa/api/events`) contine starile HA plus, din 2026-11-25:
  `layout` (ordine, grupuri, **favorite**, **vederi** ale utilizatorului), `profiles`,
  `active_profile` si `policy_stamp`. Orice salvare facuta din Casa (layout, politica, profil,
  limita Tesla, reluare automat) trimite imediat un snapshot nou tuturor sesiunilor; clientii
  recitesc politica atunci cand `policy_stamp` se schimba. Fara polling.
- Layout-ul e per utilizator; profilele si politica sunt comune casei.

## Ce face aplicatia

- **Acasa**: rezumat live, sugestii contextuale (surplus, baterie la rezerva, usi deschise,
  Tesla conectata fara incarcare, pauza automatizari...), fluxul energetic interactiv
  (atingi Solar/Casa/Baterie/Retea/Tesla/Boiler -> detalii), Favorite si Vederi proprii.
- **Detalii energie**: invertor (PV pe siruri, tensiune/curent/putere pe faze, frecventa,
  stare, program invertor doar citire), baterie (SOC, BMS din invertor, celule prin Bluetooth,
  istoric 24/48 h), casa (consumatori masurati, sarcina pe faze, aparate pornite), retea
  (import/injectie, valoarea energiei azi). Adminul vede si editeaza grupurile de parametri
  ale politicii relevante pentru fiecare ecran.
- **Politica energie si profile**: stare, aparate in control manual (reluare automat),
  buget Tesla API, profile (Iarna/Vara/Automat + oricate create de admin), toti parametrii.
- **Dispozitive**: cautare, grupare pe camera/categorie/lista, ordinea mea / cele mai folosite,
  mod Aranjeaza (sus/jos), favorite si vederi din foaia dispozitivului.
- **Tesla**: comenzi complete (incarcare pornit/oprit, curent, climatizare, incuiere, Sentry,
  portbagaj/frunk/port, scaune, program, claxon/lumini/trezire), limita proprietarului,
  jurnal incarcari (cu preturi la statii), deplasari cu traseu, statistici.
- **Setari**: tema, deblocare biometrica, pauza automatizari, actualizari, jurnal comenzi
  (admin HA), schimbare parola (cont Casa), deconectare.
- **Cautare rapida** (lupa din bara de sus): pagini, detalii energie si orice dispozitiv.

## Cum vorbeste cu serverul

- Sesiune: cookie-ul `__Secure-casa_session`, pastrat criptat (AES-GCM, cheie in
  Android Keystore, `SecureStore`). Fara backup/transfer (`allowBackup=false`).
- Citiri: `GET /casa/api/*` doar cu cookie. Date live prin SSE, deschis numai cat aplicatia
  e vizibila.
- Scrieri: `Origin: https://salavat.home.ro` + `X-CSRF-Token` (din snapshot), exact ca web.
- Login: cont Casa nativ (parola + TOTP) sau Home Assistant intr-un WebView intern blocat.
- Comenzi: luminile direct; restul cu confirmare. Fara stari optimiste, fara retry,
  fara coada offline. Comenzile Tesla se confirma, apar in jurnal si pot trezi masina
  (cost API Tesla); politica trece Tesla pe control manual dupa o comanda de incarcare.

`data/Model.kt` + `data/Domain.kt` sunt portarea lui `src/model.ts` / `src/arrange.ts` -
pastreaza-le sincronizate.

## Build local

JDK: cel din Android Studio (`C:\Program Files\Android\Android Studio1\jbr`).
AGP 9.5 / Gradle 9.6 / Kotlin 2.2 (built-in Kotlin), compileSdk 37, minSdk 26.

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio1\jbr"
cd android
.\gradlew.bat testDebugUnitTest assembleDebug     # productie, debug (fara auto-update)
.\gradlew.bat installMock                         # emulator + mock (vezi mai jos)
```

## Emulator pe date sintetice (fara HA, fara comenzi fizice)

```powershell
node android/tools/mock-server.mjs C:\Users\maria\home-control-web\tests\fixtures
.\gradlew.bat installMock      # build type `mock` -> http://10.0.2.2:8787/casa
```

Cont Casa pe mock: orice utilizator, parola `parola-test`, cod `123456`.

## Livrare automata (CI) prin GitHub Releases

`.github/workflows/android.yml`: orice push pe `main` care atinge `android/**`:
teste -> APK release semnat -> GitHub Release `android-v1.0.<rulare>` cu APK-ul atasat.
`versionCode` = numarul rularii GitHub Actions.

In aplicatie (`update/Updater.kt`): verificare la pornire (max. o data pe ora) si la 6 h in
fundal (WorkManager) -> notificare "Actualizare disponibila" -> Setari -> Descarca si
instaleaza. Inainte de instalare se verifica numele pachetului, SHA-256 (digestul publicat de
GitHub) si certificatul de semnare; Android cere confirmarea. Prima data trebuie permisa
"instalarea din aceasta sursa". Doar build-ul `release` se actualizeaza singur.

Repo-ul de release-uri: implicit `marian1x/HomeAssistant` (public). Cand repo-ul sursa
redevine privat, se publica intr-un repo public separat doar cu release-uri si se
construieste cu `-PupdateRepo=marian1x/<repo-release>` (vezi workflow-ul).

Secrete GitHub necesare (Settings -> Secrets -> Actions):

| Secret | Continut |
| --- | --- |
| `KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` | cheia de semnare (aceeasi pentru toate versiunile!) |

Keystore-ul de release NU este in repository. Pierderea lui inseamna ca actualizarile
nu se mai pot instala peste aplicatia existenta (trebuie dezinstalata).
