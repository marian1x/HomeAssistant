# Casa Salavat Android - predare pentru Claude din Android Studio

Verificat pe sisteme la 2026-11-10. Document intern, fara parole, tokenuri sau chei.
Citeste intai `AGENT-HANDOFF.md` din acelasi director: limitele de acolo (HA, Tesla,
baterie, nginx, comenzi fizice) se aplica integral si lucrului pe Android.

## Obiectiv

Un APK dedicat pentru controlul casei de pe telefon, cu TOATE functiile aplicatiei web
`https://salavat.home.ro/casa/`. Proprietarul instaleaza APK-ul direct (sideload).

## Decizia de arhitectura

Construieste un shell nativ Kotlin cu un singur WebView care incarca aplicatia web
de pe aceeasi origine. NU reimplementa ecranele nativ si NU apela API-ul din cod nativ.

De ce:

- Paritate completa si automata: orice imbunatatire a interfetei web apare imediat
  in APK, fara versiune noua.
- Securitatea ramane cea existenta, fara modificari pe server: OAuth HA cu MFA,
  cookie HttpOnly, CSRF + Origin, roluri verificate pe server, confirmarea comenzilor.
- Nicio modificare nginx pe vhost-ul comun, care gazduieste si alte aplicatii.

Variante respinse fara decizia proprietarului:

- Aplicatie nativa (Compose + client HTTP): ar trebui sa extraga cookie-ul de sesiune,
  sa trimita un header Origin de browser si sa refaca ~15 ecrane; mentenanta dubla.
- Trusted Web Activity / App Links verificate: cer `/.well-known/assetlinks.json` pe
  domeniul comun, adica o schimbare nginx. Nu o face din proiectul Android.

## Contractul serverului (nu il modifica)

- Aplicatie: `https://salavat.home.ro/casa/` (certificat TLS public valid).
- Login: `/casa/auth/login` -> 302 la `https://salavat.home.ro/home-assistant/auth/authorize`
  (pagina de login HA, cu MFA) -> `/casa/auth/callback` -> 303 la `/casa/`.
- Cookie de stare OAuth `__Secure-casa_oauth` (Path `/casa/auth`, 5 minute) si cookie de
  sesiune `__Secure-casa_session` (HttpOnly, Secure, SameSite=Lax, Path `/casa/`).
  Sesiunea expira dupa 30 de zile fara folosire; serverul reinnoieste cookie-ul la
  folosire (decizia proprietarului, 2026-11-10). `CookieManager` trebuie sa pastreze
  cookie-ul persistent (`flush()` la `onPause`). Setari -> `Deconecteaza toate
  dispozitivele` inchide si sesiunea din APK.
  Loginul trebuie facut in ACELASI WebView: un Custom Tab sau browserul extern au alt
  depozit de cookie-uri, iar sesiunea nu ar ajunge in aplicatie.
- Orice `/casa/api/*` raspunde 403 daca `Origin` exista si difera de
  `https://salavat.home.ro` sau daca `Sec-Fetch-Site` nu este `same-origin`. Scrierile cer
  in plus `X-CSRF-Token`. Un WebView pe aceeasi origine indeplineste deja conditiile.
- Date live prin SSE `/casa/api/events`; fiecare conexiune noua incepe cu un snapshot
  complet. Fara polling, fara reincarcari periodice.
- CSP strict (`script-src 'self'`): nu injecta scripturi externe in pagina.
- Sesiune expirata: API-ul intoarce 401, iar interfata arata `Conectare cu Home Assistant`
  si `Cont Casa`.
- Conturi Casa (fara HA, din 2026-11-10): dialog in pagina, `POST /casa/auth/local` si
  `/casa/auth/local/verify` pe aceeasi origine (parola + cod TOTP obligatoriu). Lasa
  Autofill-ul Android activ pentru campurile `username`/`password` si `one-time-code`.
  La prima conectare pagina arata un QR si un link `otpauth://...` (aplicatia de
  autentificare): deschide-l extern cu `Intent.ACTION_VIEW`, iar daca nu exista aplicatie,
  arata un Toast. Butonul `Copiaza` foloseste `navigator.clipboard.writeText`.
- Interfata Nova (2026-11-10) foloseste un canvas WebGL de fundal, View Transitions si
  `backdrop-filter`: pastreaza accelerarea hardware a WebView-ului (implicita) si nu seta
  `LAYER_TYPE_SOFTWARE`. Paleta de comenzi este un `[role=dialog]` care se inchide cu
  Escape trimis pe `window`, deci scriptul pentru butonul Inapoi de mai jos o acopera.
  Tema implicita urmeaza sistemul (`prefers-color-scheme`): seteaza
  `WebSettingsCompat.setAlgorithmicDarkeningAllowed(settings, false)` ca WebView-ul sa nu
  intunece el pagina.
- Rute hash (noi): `#energie`, `#costuri`, `#politica`, `#tesla`, `#dispozitive`, `#automatizari`,
  `#setari`, `#jurnal` (doar Admin). Acasa = `/casa/` fara hash. Inapoi in istoricul
  WebView navigheaza intre pagini.

## Paritate: functiile web care trebuie sa mearga in APK

Le ofera WebView-ul; verifica fiecare manual, pe date sintetice (vezi Testare).

- Acasa: flux energetic live, distributia consumului, control pe nivel/camera/tip,
  comutatoare, luminozitate, climatizare (presetari + dialog cu stepper, mod, ventilator),
  boiler (alimentare, temperatura, mod), media (pornire, redare/pauza, volum), cautare.
- Energie: instrumente live, inspector, istoric Zi/Saptamana/Luna/An, serii comutabile,
  tabel.
- Costuri si prognoza: bilant, consum pe zile, prognoza 6 zile, tarife (Admin),
  export CSV (cere suport nativ, vezi mai jos).
- Politica Energie: vizualizare, editare cu revizie (Admin), reluare control dispozitiv.
- Aranjare dispozitive (`Aranjeaza`): tragere cu degetul de maner (`touch-action: none`),
  ordinea se salveaza pe server per cont. Nu intercepta gesturile de tragere in shell.
- Tesla (`#tesla`): doar citire (baterie, temperaturi, kilometraj, incarcare, locatie).
  Linkul `Deschide harta` este extern (openstreetmap.org): deschide-l in Custom Tab.
- Dispozitive: inventar, filtre nivel/camera, cautare. Automatizari: lista, regula noua (Admin).
- Setari: cont, tema, mod Admin, parametri baterie, roluri utilizatori. Jurnal (Admin).
- Bara de sus: cautare rapida, tema, stare HA, pauza globala (killswitch, cu confirmare),
  deconectare.

## Specificatia shell-ului Android

Proiect nou, separat: `C:\Users\maria\casa-salavat-android`. Nu il pune in proiectul web
si nu il copia pe Raspberry Pi.

- Kotlin, Android Gradle Plugin curent, `minSdk 26`, `targetSdk` cel mai recent stabil
  (35+ impune edge-to-edge). Dependinte: `androidx.webkit`, `androidx.browser`,
  `androidx.activity`, `androidx.core:core-splashscreen`.
- `applicationId` propus `ro.salavat.casa` (confirma cu proprietarul), nume `Casa Salavat`,
  culoare de marca `#287b65`, icon cu casa pe fundal verde.
- O singura Activity, un WebView. Setari:
  - `javaScriptEnabled = true`, `domStorageEnabled = true` (tema si preferinte locale).
  - `allowFileAccess = false`, `allowContentAccess = false`,
    `mixedContentMode = MIXED_CONTENT_NEVER_ALLOW`, `setGeolocationEnabled(false)`,
    `safeBrowsingEnabled = true`, `setSupportMultipleWindows(false)`.
  - `CookieManager`: accepta cookie-uri, fara cookie-uri terte; `flush()` in `onPause`.
  - `setWebContentsDebuggingEnabled(BuildConfig.DEBUG)`.
  - NU implementa `onReceivedSslError` cu `proceed()`. Release fara cleartext.
  - NU folosi `addJavascriptInterface`. Pentru mesaje pagina -> nativ foloseste
    `WebViewCompat.addWebMessageListener` cu `allowedOriginRules = setOf("https://salavat.home.ro")`.
- Navigare permisa in WebView (`shouldOverrideUrlLoading`), strict:
  `https://salavat.home.ro/casa/...` si `https://salavat.home.ro/home-assistant/auth/...`.
  Orice alt URL (interfata completa `/home-assistant/`, `open-meteo.com`, celelalte
  aplicatii de pe domeniu, `otpauth:`) se deschide extern: Custom Tab sau aplicatia Home Assistant
  Companion, daca este instalata. Pagina de login HA face cereri XHR (nu navigari), deci
  merge in aceasta lista.
- Butonul Inapoi (`OnBackPressedDispatcher`), in ordine:
  1. Inchide dialogul sau meniul lateral deschis, fara a modifica aplicatia web:
     `evaluateJavascript("(()=>{if(document.querySelector('[role=dialog]')){dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));return 'closed'}const s=document.querySelector('.sidebar.open');if(s){document.querySelector('.sidebar-shade')?.click();return 'closed'}return ''})()")`.
     Daca raspunsul este `"closed"`, opreste-te. Un dialog cu comanda in curs nu se
     inchide; este intentionat.
  2. Altfel `webView.canGoBack()` -> `goBack()` (paginile au rute hash).
  3. Altfel inchide Activity.
- Edge-to-edge: aplica `WindowInsets` (system bars, display cutout, IME) ca padding pe
  containerul WebView. Pagina nu foloseste `viewport-fit=cover`, deci insets se trateaza
  nativ. Iconitele barei de status urmeaza tema paginii: citeste
  `document.documentElement.dataset.theme` (`light`/`dark`) la `onPageFinished` si `onResume`.
- Revenire din fundal: SSE se reconecteaza singur. Daca aplicatia a stat in fundal mai
  mult de 5 minute, reincarca pagina o singura data la `onResume` (sesiunea poate fi
  expirata). Fara reincarcari periodice.
- Export CSV: butonul creeaza un `Blob` si un `<a download>` cu URL `blob:`, pe care
  `DownloadListener` nu il poate descarca. Adauga cu `WebViewCompat.addDocumentStartJavaScript`
  (doar pentru originea de mai sus) un script mic care intercepteaza click-ul pe
  `a[download][href^="blob:"]`, citeste blob-ul (`fetch(href)` -> text) si trimite
  `{name, text}` prin listener-ul de mesaje. Nativ: accepta doar nume `.csv` si maxim
  5 MB, apoi salveaza prin `ACTION_CREATE_DOCUMENT`. Verifica pe date sintetice ca
  scriptul ruleaza sub CSP-ul paginii.
- Fara retea sau server indisponibil: la eroare pe main frame arata un ecran nativ
  `Fara conexiune` cu buton Reincearca. Fara reincercari automate in bucla si fara
  cozi de comenzi offline.
- Scurtaturi launcher (statice): Energie, Dispozitive, Politica -> intent intern cu
  extra `route` -> incarca `https://salavat.home.ro/casa/#energie` etc.
- Optional pentru tableta de perete: setare `Ecran mereu pornit` (`FLAG_KEEP_SCREEN_ON`),
  oprita implicit.

## Ce NU face

- Nu stoca parole HA, tokenuri HA sau cookie-ul de sesiune in afara `CookieManager`.
- Nu cere token HA de lunga durata si nu apela direct HA (`192.168.50.107:8123`),
  Tesla, Deye sau alte servicii.
- Nu adauga proxy, polling, wake-up Tesla, reincarcari periodice sau comenzi automate.
- Nu ocoli confirmarile si nu trimite comenzi fizice in teste.
- Nu modifica serverul, nginx sau HA din proiectul Android.

## Faza 2, doar cu decizia proprietarului

Notificarile, widgeturile si tile-urile rapide ar avea nevoie de apeluri API in fundal,
fara WebView. Serverul nu are inca un flux de autentificare pentru clienti nativi
(sesiunea este un cookie de browser de 30 de zile, protejat cu Origin si CSRF). Ar cere
proiectare pe server: sesiuni de dispozitiv revocabile, rate limit, audit si
teste de securitate. Nu extrage cookie-ul din `CookieManager` pentru servicii in fundal.
Alternativa existenta: aplicatia oficiala Home Assistant Companion are deja notificari,
widgeturi si tile-uri.

## Testare fara comenzi fizice

- Mock: `tests/browser.mjs` contine un server mock cu date sintetice care inregistreaza
  cererile POST si nu atinge HA. Extrage-l intr-un script de dezvoltare (de exemplu
  `tests/mock-server.mjs`) care asculta pe `0.0.0.0:<port>`; emulatorul il vede la
  `http://10.0.2.2:<port>/casa/`. Construieste intai frontend-ul in
  `C:\Users\maria\home-control-web` (Node >= 22.12: `npm ci`, `npm run build`).
- Build type `debug`: URL de baza configurabil prin `BuildConfig` si
  `network_security_config` care permite cleartext NUMAI catre `10.0.2.2`. `release`:
  doar `https://salavat.home.ro/casa/`, fara cleartext.
- Mock-ul nu verifica Origin/CSRF; productia da. In productie testeaza doar: login HA
  (credentialele le introduce proprietarul, niciodata agentul), navigare, citire,
  Inapoi, tema, deconectare. ATENTIE: din 2026-11-10 intrerupatoarele de LUMINA trimit
  comanda la prima apasare, fara dialog de confirmare; nu le atinge in productie.
  Nicio comanda (comutatoare, temperatura, volum, pauza
  globala, politica, reguli) fara cererea explicita a proprietarului. Nu testa alarma,
  Tesla sau releele.
- Lista manuala: fiecare functie din sectiunea Paritate, latimi 360/390/412 dp, tema
  luminoasa si intunecata, rotatie, Inapoi cu dialog/meniu/pagini, sesiune expirata,
  retea oprita, revenire din fundal (indicatorul revine la `HA Live`), export CSV.
- Teste automate: unit tests pentru lista de URL-uri permise si pentru scurtaturi;
  teste instrumentate (Espresso Web) numai pe mock.

## Build si livrare

- Keystore de release generat de proprietar, in afara proiectului si a oricarui
  repository. Nu il comite, nu il copia pe Pi, nu il trimite nicaieri.
- `gradlew assembleRelease` -> APK semnat (schema v2/v3). Instalare prin `adb install`
  sau fisier APK pe telefon.
- `versionCode` creste la fiecare APK. Schimbarile interfetei web NU cer APK nou.
- Nu publica APK-ul pe domeniul comun fara decizia proprietarului (ar fi un path nou
  pe vhost-ul partajat).

## Referinte

- Proiect web, copie de lucru Windows: `C:\Users\maria\home-control-web`.
  Productie: Raspberry Pi 5, `/home/pi5/proiecte/Home Assistant` (`ssh pi5@192.168.50.101`).
- `AGENT-HANDOFF.md`, `README.md`, `ENERGY-POLICY.md`, `TESLA.md` in proiectul web.
- Interfata: `src/main.tsx` (navigare, rute hash, dialoguri), `src/HomeDashboard.tsx`,
  `src/EnergyFlow.tsx`, `src/EnergyHistory.tsx`, `src/EnergyEconomics.tsx`,
  `src/EnergyPolicy.tsx`, `src/theme.css`.
- Backend (doar citire pentru acest proiect): `server/app.py` (rute, cookie-uri,
  Origin/CSRF, CSP), `server/policy.py` (comenzi si limite permise).
