# Casa Salavat - ghid pentru alt agent AI

Verificat direct pe sisteme la 2026-11-10; sectiunile datate sunt mai noi (ultima 2026-11-25). Document intern, fara parole,
tokenuri sau chei private. Starea dispozitivelor se poate schimba dupa verificare.
Acest document are prioritate fata de notele istorice de instalare din README.

## Mandat si limite

Proprietarul permite dezvoltarea si imbunatatirea interfetei web de pe Raspberry
Pi 5: design tactil cu profunzime vizuala, navigare, grafice, organizare pe camere,
utilizare pe telefon si controale mai ergonomice. Nu doreste obligatoriu o casa
modelata 3D. Aplicatia este deja functionala, nu trebuie inlocuita cu un demo.

Pastreaza integritatea autentificarii, autorizarii si automatizarilor existente.
O cerere de redesign NU autorizeaza comenzi fizice de test, modificarea setarilor
electrice, resetarea dispozitivelor sau activarea tuturor automatizarilor vechi.
Citeste implementarea si starea curenta inainte de editare. Pastreaza modificarile
proprietarului si ale altor agenti; nu suprascrie proiectul cu un snapshot vechi.

## Acces si topologie

| Sistem | Acces | Rol |
| --- | --- | --- |
| Raspberry Pi 5 | `ssh pi5@192.168.50.101` | Aplicatie web, nginx, alte aplicatii existente |
| Raspberry Pi 4 / HA OS | `ssh root@192.168.50.107` | Home Assistant si automatizari |
| HA local | `http://192.168.50.107:8123` | Autentificare cu cont HA |
| Aplicatie publica | `https://salavat.home.ro/casa/` | Interfata principala, login HA |
| HA prin nginx | `https://salavat.home.ro/home-assistant/` | Proxy HA existent, inclusiv OAuth |
| Logger Deye | `192.168.50.43` | Integrare locala deja configurata |

SSH cu cheile deja autorizate functioneaza din mediul de lucru actual.
Pe Pi5 functioneaza `sudo -n`. Nu publica si nu transfera cheile private.
Alt agent pe alta masina are nevoie de propria cheie publica autorizata de proprietar;
faptul ca acest mediu se conecteaza nu ofera acces automat oricarui serviciu AI.

IP-ul HA de referinta este `.107`. `.103` este adresa istorica Wi-Fi si apare in
workspace-ul Windows; nu o impune inapoi in configuratii. Samba, daca este
disponibila, se acceseaza prin `\\192.168.50.107\config`; foloseste SSH daca nu merge.

Versiunea Core verificata: **2026.11.0**, HA OS cu Supervisor. Nu face upgrade,
downgrade sau restart Core doar pentru modificari de frontend.

## Proiectul web

- Proiect live: `/home/pi5/proiecte/Home Assistant` (calea contine spatiu).
- Copie de lucru Windows: `C:\Users\maria\home-control-web`.
- React + TypeScript + Vite, lucide-react, Recharts.
- Backend FastAPI/Uvicorn: `server/app.py`, numai `127.0.0.1:8765`.
- Serviciu: `home-control.service`, utilizator neprivilegiat `homecontrol`.
- Setari productie: `/etc/home-control.env`; nu afisa integral fisierul in loguri.
- Stare privata: `/var/lib/home-control`, permisiuni 0700; baza SQLite si cheia
  de criptare trebuie pastrate impreuna. Nu sterge, nu publica, nu copia in `dist/`.
- Unitatea: `/etc/systemd/system/home-control.service`.
- Frontend construit: `dist/`; backendul il serveste, nginx nu foloseste un
  `root` spre directorul de proiect. Nu rezolva permisiuni cu `chmod -R 777`.

Puncte de lucru:

| Fisier | Responsabilitate |
| --- | --- |
| `src/HomeDashboard.tsx` | Dashboard, camere, categorii, controale compacte |
| `src/EnergyFlow.tsx`, `src/energy-flow.ts` | Flux energetic interactiv si calcule de afisare |
| `src/EnergyHistory.tsx` | Grafic istoric (Zi/Saptamana/Luna/An), rezumat, serii comutabile, vedere tabel |
| `src/home-control.css` | Aspectul statiei de control |
| `src/theme.css` | Tokenuri comune: culori energie, sina de navigare, ergonomie tactila |
| `src/nova.css` | Strat final de design (Nova): sticla, miscare, paleta de comenzi, tranzitii; se incarca ultimul |
| `src/Aurora.tsx`, `src/aurora-mix.ts` | Fundal WebGL viu, condus de mixul energetic real |
| `src/motion.tsx` | Valori animate (`Num`), View Transitions (`morph`, `reveal`), lumina dupa cursor |
| `src/CommandPalette.tsx` | Paleta de comenzi Ctrl/Cmd+K |
| `src/brief.ts` | Propozitia "Casa acum" si independenta energetica a zilei |
| `src/arrange.ts`, `src/ArrangeMode.tsx` | Ordinea dispozitivelor per utilizator, modul Aranjeaza |
| `src/Tesla.tsx`, `src/TeslaJournal.tsx`, `src/TeslaMap.tsx` | Pagina Tesla: stare, limita, jurnal, harta |
| `src/main.tsx` | Navigare (rute hash), dialoguri, pagini, confirmari |
| `src/model.ts` | Model entitati, filtre, capabilitati, asociere aparate |
| `server/house.json` | Inventar declarat si asocieri confirmate; NU adevar absolut despre integrare |
| `server/ha.py` | Legatura HA, cache si evenimente |
| `server/policy.py` | Permisiuni, liste de comenzi, limite de valori |
| `server/energy.py` | Costuri, statistici, prognoza |
| `server/store.py` | Sesiuni, roluri, conturi Casa, stocare privata |
| `server/accounts.py` | Conturi Casa: parole scrypt, TOTP RFC 6238, politica parolelor |
| `src/LocalLogin.tsx`, `src/LocalUsers.tsx`, `src/Qr.tsx` | Login cont Casa, administrare conturi, cod QR |
| `tests/test_local_accounts.py`, `tests/local-accounts.mjs` | Teste server si UI (mock) pentru conturile Casa |
| `tests/nova.mjs`, `tests/brief.mjs` | Teste UI (mock) si unitare pentru stratul Nova |
| `ops/fleet-telemetry/`, `FLEET-TELEMETRY.md` | Server Fleet Telemetry pe Pi5 (compose, firewall, fail2ban, actualizari) |
| `ha/custom_components/home_energy_policy/` | Sursa controlerului nativ HA |

Interfata, redesign 2026-11-10 (numai frontend; backend, nginx, HA neatinse):

- Paginile au rute hash: `#energie`, `#costuri`, `#politica`, `#dispozitive`,
  `#tesla`, `#automatizari`, `#setari`, `#jurnal` (doar in modul Admin). Acasa = fara hash.
  Reincarcarea si butonul Inapoi pastreaza pagina.
- Culorile entitatilor energetice sunt tokenuri in `theme.css` (`--energy-solar`,
  `--energy-load`, `--energy-battery`, `--energy-grid`, `--energy-export`), folosite
  de flux, istoric si costuri. Sunt validate pentru daltonism; nu le schimba izolat.
- Taburile de nivel/camera arata numarul de dispozitive controlabile; camerele fara
  dispozitive controlabile sunt ascunse in Acasa (raman in inventarul Dispozitive).
- Dialogul de temperatura/parametri are stepper -/+ limitat la min/max/pas din HA;
  modurile HVAC sunt traduse, valoarea trimisa ramane cea bruta din HA.
- Boilerul ramane neutru vizual dupa mod (ex. MANUAL); doar senzorul de rezistenta
  spune ca incalzeste.
- Backup si rollback: `/home/pi5/proiecte/.home-control-backups/ui-redesign-20261110-021201/ROLLBACK.md`.
- APK Android: vezi `ANDROID-HANDOFF.md`.

## Fleet Telemetry Tesla si securitate retea, cerere proprietar 2026-11-25

Detalii complete, suprafata expusa, buget si pasi: `FLEET-TELEMETRY.md`.

- Pi5: `fleet-telemetry` v0.10.0 + `ft-mosquitto` 2.0.23 (Docker, fixate pe digest) in
  `/opt/fleet-telemetry`, secrete in `/etc/fleet-telemetry`. **Singurul port nou din internet:
  TCP 4443** (forward pe router facut de proprietar), TLS mutual cu certificat de vehicul Tesla.
  Filtrul real e lantul `FT-FILTER` din `DOCKER-USER` (Docker ocoleste ufw), plus fail2ban
  `fleet-telemetry`. Containerele nu pot initia conexiuni. MQTT 8883 doar pentru HA (.107).
  Vhost-ul 443 si nginx NU au fost atinse.
- HA: integrare MQTT noua (TLS, CA local) si `home_energy_policy` 0.6.0 (`telemetry.py`, `fleet.py`).
  Cand stream-ul e live, drumurile vin din telemetrie, iar citirea "in mers" este sarita.
  Buget (proprietar): oprire automata daca primele 2 saptamani depasesc $2; lunar totul sub
  creditul de $10, cu rezerva pastrata pentru citirile/comenzile de incarcare.
- **Push-ul configului in masina NU este facut**: semnarea cere `tesla-jws` rulat in add-on-ul
  proxy (cheia privata ramane acolo); pasul a fost blocat de permisiunile agentului si asteapta
  proprietarul. Nu ocoli aceasta decizie.
- Tot la cererea proprietarului: MariaDB asculta doar pe loopback (drop-in
  `/etc/systemd/system/mariadb.socket.d/10-loopback.conf`; `bind-address` era ignorat de socket
  activation); `debug` oprit in add-on-ul Tesla HTTP Proxy (logurile puteau contine tokenuri).
  Add-on-ul proxy NU se opreste: prin el trec toate citirile/comenzile `tesla_custom`.
- Interfata Tesla: card Fleet Telemetry (stare, cost luna, buget), traseu colorat pe viteza
  (`--speed-1..5` in `theme.css`), profil de viteza, deplasare in curs live, sursa si baza consumului.
- Urmatorul proiect cerut: firewall "inteligent" pe 4443 (planul e in `FLEET-TELEMETRY.md`).
- Backup si rollback: Pi5 `/home/pi5/proiecte/.home-control-backups/fleet-telemetry-20261125-005328/ROLLBACK.md`,
  HA `/config/.policy-backups/telemetry-20261125-011233/ROLLBACK.md`.

## Panoul bateriei, cerere proprietar 2026-11-24

- Pagina `#baterie` (`src/Battery.tsx`), deschisa din bateria din fluxul energetic, din
  banda live si din pagina Energie. DOAR citire: SOC, putere, tensiune, curent, temperatura,
  SOH, cicluri, energie, alarme si valorile BMS transmise de Deye (atribute ale
  `sensor.deye_battery`: `BMS Charging/Discharging Current`, `BMS Max Charging/Discharging
  Current`, `BMS Charging Voltage`, `BMS SOC/Voltage/Current`, `BMS Other Symbol`,
  `Corrected Capacity`). Lista permisa este `BMS_ATTRS` in `server/policy.py`.
- `GET /casa/api/battery/history?hours=24|48`: istoric HA (`history/history_during_period`)
  pentru SOC, temperatura, putere si limitele BMS, grupat la 5/10 minute, cache 60 s.
- Bateria: Easyway UNIV-16kWh (WP), cu autoincalzire, WiFi si Bluetooth proprii. NU
  transmite catre invertor date pe module/celule (registrele Deye 0x2738+ sunt 0). Nu afisa
  si nu estima valori pe celule.
- Constatare 2026-11-24: BMS-ul a coborat limita de incarcare la 10 A intre 06:33 si 12:28
  (bateria la 2,6-5 C); limita de descarcare a ramas 200 A.
- Teste: `tests/test_battery.py`, `tests/nova.mjs`.
- Backup si rollback: `/home/pi5/proiecte/.home-control-backups/battery-20261124-180317/ROLLBACK.md`.

## Injectie din retea pe frig (incalzire baterie), cerere proprietar 2026-11-25

Regula in controler (`coldcharge.py` + `runtime.cold_charge`): sub 3 C si in ultimele 3 ore
inainte de rasarit, porneste DOAR `switch.deye_battery_grid_charging` ca invertorul sa alimenteze
incalzitorul bateriei. NU ridica nivelul/programele Deye. Opreste la 6 C, la pornirea panourilor
sau la rasarit. Scriere doar la tranzitie, histerezis 3->6 C, respecta killswitch; opreste doar
comutatorul pe care l-a pornit el. Config grup `battery` (`cold_charge_*`), stare in atributul
`cold_charge`, vizibil in pagina Politica. Teste `tests/test_coldcharge.py`. Armat de proprietar.

## Jurnal Tesla si limita de incarcare, cerere proprietar 2026-11-24

- Jurnalul ruleaza IN HA (`tesla_log.py` + logica pura `triplog.py`), baza separata
  `/config/home_energy_policy_tesla.db` (tabele `drives`, `charges`, `meta`). Asculta doar
  starile existente (nicio cerere in plus catre masina); acasa, in timpul incarcarii,
  imparte energia solar/baterie/retea din fluxurile Deye la 30 s (masina = consumator
  marginal). La prima pornire a importat 7 zile din recorder (`meta.backfilled`).
- WebSocket HA: `home_energy_policy/tesla_log` {days}, `home_energy_policy/tesla_drive` {id};
  servicii `set_charge_price` {id, price_kwh?, note} si `set_ev_limit` {soc 20-100}.
- Server: `GET /casa/api/tesla/log` (rol control, cache 30 s, plus km pe luna din
  statisticile odometrului), `GET /casa/api/tesla/drive/{id}`, `POST /casa/api/tesla/limit`,
  `POST /casa/api/tesla/charge-price` (CSRF, audit). CSP permite plăcile
  `https://tile.openstreetmap.org` (harta Leaflet, fara cheie).
- Limita proprietarului (`evlimit.py`): >= 50% se scrie o data in masina; < 50% masina ramane
  la 50% si, NUMAI acasa si conectata, politica opreste incarcarea la tinta si reia doar o
  incarcare oprita de ea, sub tinta - 2%. Comenzi doar pe date proaspete, fara wake-up,
  in bugetul de comenzi; contexte proprii (nu creeaza `manual_until`). Tinta solara foloseste
  min(80, limita proprietarului).
- UI: `src/Tesla.tsx` (tab-uri Acum/Incarcari/Deplasari/Statistici + card limita cu
  confirmare), `src/TeslaJournal.tsx`, `src/TeslaMap.tsx`. Fleet Telemetry este instalat din 2026-11-25 (vezi `FLEET-TELEMETRY.md`);
  drumurile fara telemetrie raman aproximative.
- Teste: `tests/test_triplog.py`, `tests/test_tesla.py`, `tests/test_energy_policy.py`, `tests/nova.mjs`.

## Bateria prin Bluetooth (ENW BMS), constatari 2026-11-24

- Modulul WiFi/BT al bateriei: `X07EA21112D005FD`, BT `74:E9:D8:E7:97:B5`, WiFi
  `192.168.50.234` (fara porturi TCP deschise 1-10000; trimite numai in cloud).
  Controler `00EY3126040204140150`, pachet `00EY3126040204140150-P` (SN eticheta
  `20260425EYFFFBA361`). Firmware actualizat de proprietar V11.05 -> V12.05.
- Protocolul (din captura HCI a aplicatiei, NU din documentatie) este in `BATTERY-BLE.md`.
  Aplicatia are si comenzi de scriere/actualizare firmware: un cititor local trimite
  NUMAI cererea de citire (cmd 05). Cititorul read-only ESTE instalat (vezi `bms.py`/`bms_ble.py`, ruleaza in HA pe Bluetooth, la 180 s, se deconecteaza intre citiri). Incalzirea: logica fixa din manual (0/2->10 C, cere incarcare activa de la invertor); fara scriere, fara parola de instalator (nu e in manual).

## Ordinea dispozitivelor, cerere proprietar 2026-11-10

- Butonul `Aranjeaza` (Acasa si Dispozitive) deschide modul de aranjare: maner de
  tragere (mouse/touch), sageti sus/jos, tastele sageti pe maner si sageti pentru
  grupuri (Iluminat, Climatizare...). In acest mod cardurile sunt `inert`: o atingere nu
  poate comanda un aparat. Logica pura: `src/arrange.ts`; componente: `src/ArrangeMode.tsx`.
- Moduri: `Ordinea mea` (manual), `Cele mai folosite` (comenzile ACCEPTATE ale
  utilizatorului din ultimele 30 de zile, din tabelul `audit`), `Implicit`. Contorul se
  reincarca doar la intrarea in modul de aranjare si la incarcarea paginii, ca sa nu
  mute cardurile sub deget dupa fiecare comanda. O tragere trece automat pe manual.
- Server: `GET/POST /casa/api/layout`, tabel `layouts(user, data, updated)` in
  app.sqlite. Fiecare cont (HA sau Casa, orice rol, inclusiv Vizualizare) isi salveaza
  propria ordine; POST cere Origin + `X-CSRF-Token`, cheile sunt validate (regex, maxim
  500, fara duplicate). Nu ajunge niciodata la HA. Stergerea unui cont Casa sterge si
  ordinea lui. Copie locala in `localStorage` (`casa-layout:<user>`) doar pentru prima
  afisare; serverul are prioritate.
- Teste: `tests/test_layout.py`, `tests/brief.mjs` (logica), `tests/nova.mjs` (UI).
- Backup si rollback: `/home/pi5/proiecte/.home-control-backups/arrange-20261110-232441/ROLLBACK.md`.

## Lumini fara confirmare si pagina Tesla, decizie proprietar 2026-11-10

- Luminile (entitati `light.*` si dispozitivele din categoria `lights`, inclusiv
  intrerupatoarele Sonoff de iluminat) se comuta DIRECT la apasare, fara dialog; la fel
  butonul `Aplica` de la luminozitate si comenzile de lumini din paleta. Climatizarea,
  boilerul, prizele, media si pauza globala cer in continuare confirmare. Nu extinde
  comanda directa la alte categorii fara decizia proprietarului.
- Starea intrerupatorului NU este optimista: se schimba doar cand HA raporteaza starea
  noua. Cat timp cererea e in curs butonul are clasa `busy`, iar a doua apasare e ignorata.
  Serverul verifica in continuare rolul, CSRF, Origin si limita de 30 comenzi/minut.
- ATENTIE la teste pe productie: o apasare pe un intrerupator de lumina trimite acum
  comanda reala. Testeaza luminile numai pe mock.
- (Actualizat 2026-11-24: pagina are acum si limita de incarcare si jurnalul, vezi mai jos.)
  Pagina `#tesla` (`src/Tesla.tsx`) citeste starile HA existente
  (`*.salavat_t3_*`: baterie, autonomie, temperaturi, kilometraj, energie adaugata,
  putere, locatie, usi, geamuri, sentry). Nu are butoane de comanda, nu apeleaza
  `wake_up` / `force_data_update` si nu porneste polling. Arata ora ultimei citiri.
  Linkul `Deschide harta` duce la openstreetmap.org doar la click (coordonatele nu sunt
  trimise altfel nicaieri). Comenzi Tesla (climatizare, incarcare, incuiere) ar consuma
  cota API si ar trezi masina: numai cu decizia proprietarului.
- Backup si rollback: `/home/pi5/proiecte/.home-control-backups/lights-tesla-20261110-211756/ROLLBACK.md`.

## Stratul Nova, cerere proprietar 2026-11-10

Proprietarul a cerut o interfata foarte moderna si animata. Numai frontend; backend,
nginx si HA neatinse. Structura, rolurile ARIA si etichetele au ramas, deci testele
existente si shell-ul Android functioneaza neschimbat.

- Fundal: fotografia de interior a fost inlocuita cu `canvas.aurora` (un singur shader
  WebGL, fara three.js). Culorile si ritmul urmeaza fluxurile reale: solar = chihlimbar,
  retea = albastru, baterie = roz, consum = verde; fara citire recenta ramane pe un mix
  neutru. Randare la o treime din rezolutie, maxim 30 fps, oprita cand tabul e ascuns,
  un singur cadru la `prefers-reduced-motion`. Fara WebGL ramane gradientul CSS.
  Vechiul `src/Scene.tsx` (casa 3D) ramane neimportat.
- Cardurile din pagina NU au `backdrop-filter` (cost pe telefoane); doar sina, bara de
  sus, dock-ul mobil si dialogurile il pastreaza.
- Acasa: propozitia "Casa acum" (`brief.ts`) si inelul "independenta energetica azi"
  (1 - import/consum, din contoarele Deye). Sunt fapte din citiri, nu prognoze; nu
  adauga estimari (autonomie, ora de incarcare) fara date reale.
- Flux energetic: scanteile apar numai pe firele cu putere > 0,03 kW; viteza creste cu
  puterea. Cardul bateriei se umple pana la SOC.
- Valorile live folosesc `<Num>`: aluneca intre doua citiri reale, nu numara de la zero.
- Navigarea si tema folosesc View Transitions (`morph`, `reveal`); fara suport sau cu
  miscare redusa schimbarea este instantanee.
- Paleta Ctrl/Cmd+K (si butonul din bara de sus): pagini, dispozitive, actiuni. Comenzile
  se poarta ca butoanele din pagina: luminile direct, restul cu acelasi dialog de confirmare.
  Se inchide cu Escape trimis pe `window` (folosit de butonul Inapoi din APK).
- Tema implicita urmeaza sistemul cand utilizatorul nu a ales una.
- Fonturi gazduite local (`@fontsource-variable/geist`, `geist-mono`, versiuni fixe);
  CSP-ul nu permite fonturi externe.
- Orice animatie noua trebuie oprita in blocul `prefers-reduced-motion` din `nova.css`;
  `tests/nova.mjs` verifica zero animatii active in acel mod.
- Backup si rollback: `/home/pi5/proiecte/.home-control-backups/nova-ui-20261110-210027/ROLLBACK.md`.

## Sesiuni, decizie proprietar 2026-11-10

- Sesiunea Casa expira dupa **30 de zile fara folosire** (`SESSION_IDLE` in
  `server/store.py`). Orice raspuns `/casa/api/*` reusit reinnoieste expirarea si
  cookie-ul (aceleasi flaguri Secure/HttpOnly/Lax, Path `/casa/`), cel mult o data pe ora.
  Se reinnoiesc doar sesiunile legate de un utilizator HA (coloana `sessions.user`,
  setata de `Peer` dupa `auth/current_user`); o sesiune delogata nu se mai reactiveaza.
- Conexiunea WebSocket HA a unei sesiuni se inchide dupa 10 minute fara cereri si fara
  SSE deschis (`PEER_IDLE`); urmatoarea cerere o redeschide. Sesiunea ramane valida.
- `POST /casa/api/logout-all` (Origin + CSRF) inchide toate sesiunile Casa ale
  utilizatorului curent, inclusiv cea curenta; tokenurile HA se revoca in bucla de
  curatare. Nu afecteaza sesiunile HA proprii sau aplicatia HA. Buton in Setari.
- Loginul HA prin `/home-assistant/auth/` nu este restrictionat la LAN (nginx si HA nu au
  allow/deny sau trusted_networks); pana la 2026-11-10 nu fusese folosit din afara.
- Backup si rollback (include eliminarea coloanei `user`, necesara pentru codul vechi):
  `/home/pi5/proiecte/.home-control-backups/session-30d-20261110-082815/ROLLBACK.md`.

## Conturi Casa fara HA, decizie proprietar 2026-11-10

Pe langa OAuth HA (neschimbat), administratorul HA creeaza conturi doar pentru Casa:
Setari -> mod Admin -> `Conturi Casa`. Utilizatorii acestia NU au cont in HA.

- Login: `POST /casa/auth/local` (utilizator + parola) apoi `POST /casa/auth/local/verify`
  (cod TOTP **obligatoriu**, 6 cifre/30 s, fereastra +-1 pas, un pas nu se refoloseste).
  Prima conectare: parola temporara + configurare cod + parola noua (minim 12 caractere).
  Origin exact obligatoriu; cookie intermediar `__Secure-casa_local` (Path `/casa/auth`,
  SameSite=Strict, 5 min). Blocare cont 15 min dupa 5 greseli; 10 greseli/15 min/IP
  (`X-Real-IP` de la nginx) -> 429. Nginx limiteaza doar `/casa/auth/login`; limitele
  pentru conturile Casa sunt in aplicatie.
- Stocare: tabel `local_users` in `app.sqlite`; parole scrypt (n=2^14, r=8, p=1, sare),
  secret TOTP criptat cu cheia Fernet existenta. Parola temporara se afiseaza o singura data.
- Roluri: `viewer` = Vizualizare, `control` = Control dispozitive, `configure` =
  Parametri si control (setarile bateriei din lista existenta, programe, **Politica
  Energie** inclusiv tarife). Limitele de valori si `command()` raman aceleasi.
  Utilizatori HA, conturi Casa, reguli, jurnal si contul tehnic: doar administratorul HA
  (`require_admin`; un cont Casa nu este niciodata administrator).
- Cont tehnic HA: conturile Casa ajung la HA printr-un singur `Peer` (`sid='service'`)
  conectat de administrator prin OAuth (`POST /casa/api/service/login`, acelasi callback).
  Tokenurile lui sunt un rand criptat in `sessions` (expira 2100, se termina doar la
  deconectare sau revocare in HA). Proprietarul a ales ca acest cont sa fie
  **administrator HA**, ca rolul Parametri sa poata salva Politica Energie
  (`home_energy_policy.configure` este serviciu admin). Risc acceptat: un server compromis
  ar avea drepturi de administrator HA. Nu expune acest Peer altfel decat prin API-ul ingust.
- Sesiunile conturilor Casa: payload `{'local': id}`, fara token HA, legate de cont;
  dezactivare/resetare/stergere le inchid. `POST /casa/api/me/password` schimba parola
  (inchide celelalte sesiuni). Snapshot `user` are `local` si `admin`.
- Backup si rollback: vezi `ROLLBACK.md` din `local-accounts-*` in directorul de backupuri.

Inventarul declarat poate ramane in urma HA: verifica registrii si entitatile reale
inainte de a spune ca un aparat lipseste sau de a crea o asociere noua.

## Ce este disponibil in HA

Integrari incarcate la verificare: Solarman/Deye, `home_energy_policy`, Tesla Custom,
Ariston, TCL Home Unofficial, Whirlpool, Tuya/SmartLife, Sonoff/eWeLink, Philips Hue,
Google Cast, Roborock, Reolink, Xiaomi BLE, imprimanta IPP, Met.no si prognoza solara
Open-Meteo. Exista si Bluetooth, Matter, mobile_app si servicii HA standard.

`loaded` confirma initializarea integrarii, NU disponibilitatea tuturor aparatelor.
Huawei Solar este in `setup_retry`; unele RGBW sunt de asemenea in retry/offline.
Reolink este incarcat, dar camerele Driveway sunt momentan indisponibile.
Alarma si unele televizoare sunt indisponibile. Nu masca aceste stari cu valori false.

Entitati utile, verificate; lista nu este exhaustiva:

| Zona / aparat | Entitati principale |
| --- | --- |
| Living / TCL FreshIN | `climate.living_living_air_cxbwrbfaaae_climate` |
| Living / Sonoff | `switch.living_lights_sonoff_100053f649` |
| Living / Hue | `light.living_room_light_1`, `light.living_room_light_3` |
| Living / temperatura | `climate.heat`, afisare corectata `sensor.hvac_downstairs_temperature` |
| Living / boxa | `media_player.living_nest_speaker` |
| Parter / aspirator | `vacuum.black_people` |
| Camera tehnica / Ariston | `water_heater.boiler`, `switch.boiler_ariston_power` |
| Boiler / rezistenta activa | `binary_sensor.boiler_ariston_is_heating` |
| Boiler / putere estimata | `sensor.ariston_boiler_power_estimated` |
| Dormitor Mare / Hue | `light.bedroom_reading_light` |
| Dormitor Mare / Spots | `switch.spots_sonoff_1000529656` |
| Dormitor Mare / boxa | `media_player.bedroom_speaker` |
| Dormitor Mare / temperatura | `climate.bedroom_heat`, `sensor.hvac_upstairs_temperature` |
| Dormitor Mic / Sonoff | `switch.baby_spots_sonoff_100262416b_1` (exista si alte entitati Baby Spots: confirma aparatul) |
| Birou / Office pair | `media_player.nest_left` |
| Birou / imprimanta | `sensor.hp_smart_tank_510_series` |
| Baie etaj / priza uscator | `switch.priza_uscator_socket_1` |
| Baie etaj / cantar | `sensor.mi_body_composition_scale_3341_weight` |
| Etaj / Whirlpool | `climate.air` |
| Etaj / aspirator | `vacuum.consuelo` |
| RGBW disponibil | `light.controller_rgbw_c81046` (nu ghici camera dupa ordinea listei) |
| Tesla / incarcare | `switch.salavat_t3_charger`, `number.salavat_t3_charging_amps` |
| Tesla / limita si SOC | `number.salavat_t3_charge_limit`, `sensor.salavat_t3_battery` |
| Tesla / putere | `sensor.salavat_t3_charger_power`, `sensor.tesla_charging_power` |
| Politica / stare | `sensor.home_energy_policy_status` |

Hue ESTE acum integrat, contrar unei note vechi din README. Grupurile Hue nu sunt
becuri suplimentare: evita dublarea dispozitivelor si a consumului in interfata.
Verifica localizarea reala pentru device-uri noi; nu muta automat entitati intre camere.
NAS, senzori individuali ai alarmei/fumului si alte pozitii declarate trebuie verificate
separat; nu genera telemetrie sau butoane functionale pentru simple placeholder-e.
Shelly pentru strada ramane in control separat; nu il integra/reactiva implicit.

## Energie si masurare

Deye SUN-20K-SG05LP3-EU-SM2 este principal; Huawei SUN2000-8KTL-M1 intra in portul
GEN al Deye. Baterie Easyway UNIV, **16 kWh**. Panouri: 3 kWp SV pe Huawei,
6 kWp SV + 6 kWp NE pe Deye. Total instalat 15 kWp, nu 20 kWp.

- Productie agregata folosita: `sensor.productie_solara_curenta`.
- Consum casa: `sensor.consum_total_curent`.
- Deye: `sensor.deye_pv_power`, `sensor.deye_microinverter_power`,
  `sensor.deye_load_power`, `sensor.deye_grid_power`, `sensor.deye_battery_power`.
- SOC: `sensor.deye_battery`.
- Cumulative: `sensor.deye_total_energy_import`, `sensor.deye_total_energy_export`,
  `sensor.deye_total_load_consumption`, `sensor.deye_productie_solara_total`.
- Preturi: `sensor.home_energy_import_price` si `sensor.home_energy_export_price`.
- Exterior/prognoza: `weather.forecast_home`, `sensor.home_energy_outdoor_temperature`,
  `sensor.home_energy_cloud_coverage` si prognozele existente.

Nu aduna din nou Huawei peste un total care il include deja. Nu considera PV direct
Deye drept intreaga productie. Verifica semnele import/export si incarcare/descarcare
in implementarea existenta, nu le deduce dintr-un screenshot.

W/kW sunt putere, kWh este energie. Nu transforma energia zilnica a AC-ului in kW
instantaneu. Boilerul este estimat la **1.8 kW numai cand rezistenta incalzeste**,
nu cand este doar pornit sau are Boost selectat. AC-urile fara wattmetru raman cu
putere necunoscuta; consumul lor ramane inclus in consumul rezidual al casei.
Nu trata `unavailable`, datele vechi sau lipsa istoricului ca zero.

Costuri: cumparare 1.11 RON/kWh, export 0.45 RON/kWh, tarife datate editabile,
perioade custom si export CSV deja implementate. Nu rescrie retroactiv preturile
istorice. Estimarile nu sunt factura furnizorului.

## Automatizari: ce trebuie pastrat

Controlerul activ ruleaza IN HA: `/config/custom_components/home_energy_policy/`.
Pi5 este editor/monitor, nu trebuie sa devina un al doilea motor de automatizare.
Starea persistenta este `/config/.storage/home_energy_policy`; nu o edita live.
Configurarea foloseste serviciile native si revision guard, nu rescrierea fisierului.

Prioritate: casa/confort -> bateria casei -> Tesla -> boiler -> extra climatizare.
Rezerva baterie **20%**, limita descarcare **7 kW**, incarcare din retea dezactivata.
Nu modifica BMS, protectii, registre brute sau cele sase sloturi Deye independent
de managerul deja existent. Prognoza NU ridica automat rezerva minima peste 20%.

Politica completa este activata de proprietar, inclusiv Tesla. Reguli vechi care scriu
pe aceleasi aparate trebuie sa ramana oprite; controlerul detecteaza conflictele.
Nu apasa Enable All pe `automation.*`. Detalii actuale in `ENERGY-POLICY.md`.

- Boiler: iarna 47 C, vara 43 C, surplus pana la 80 C; nu bloca anti-legionella.
- TCL Low iarna: 23 C normal, 24 C la -15 C; ventilator 1/2/3 dupa frig.
- Whirlpool: program iarna 20:00-21:00 daca afara <5 C; vara racire conform profilului.
- Modificarile manuale din aplicatiile native/telecomanda suspenda controlul HA al
  aparatului pana la 06:00 in ziua urmatoare, dupa ce integrarea le raporteaza.
- Killswitch: `input_boolean.ha_automation_killswitch`. Opreste automatizari/comenzi
  automate, NU taie fizic toate dispozitivele. Controlul manual ramane disponibil.
- Backupurile si alerta lor continua chiar daca pauza globala este activa.

Tesla: nu introduce polling, wake-up sau Force Data Update in componentele UI.
Nativ `tesla_custom` are polling periodic dezactivat intentionat. Adaptorul comun
foloseste cache-ul integrarii si `wake_if_asleep=False`; nu creeaza alt client.
Evaluare electrica la 30 s, citiri/comenzi pentru incarcare detinuta la minimum 120 s.
Din 2026-11-24 (cerere proprietar) cadenta urmeaza ultima stare cunoscuta: in mers 10 min,
incarcare 10 min, conectata fara incarcare 30 min (zi), departe 120 min (zi), acasa
neconectata 90 min (zi, cu PV), plus o citire la salt de consum trifazat echilibrat
(>= 3 kW, >= 0,8 kW pe faza, sustinut) si la scaderea corespunzatoare cand se incarca.
Noaptea: in mers/incarcare/salturi + verificarea de la 00:00. Totul fara trezire.
Cod: `quota.py` (`due`, `load_step`, `ev_mode`), test `tests/test_energy_policy.py`.
Backup: `/config/.policy-backups/tesla-reads-<ts>/ROLLBACK.md` pe HA. Exista bugete persistente si backoff; nu le ocoli la depanare.
Auto Tesla: doar la casa fizica, tinta 80%, trifazat 5-16 A; 1 A aprox. 0.66 kW.
Asistenta bateriei este conditionata de SOC/prognoza/zi, nu incarcare EV noaptea.
La activarea de noapte nu s-a trimis nicio comanda Tesla; prima sesiune solara reala
nu era inca validata fizic. Polling rar nu garanteaza captarea tuturor drumurilor scurte.

Backup HA complet + Recorder SQLite: 07:00 si 19:00 Europe/Bucharest. Google Drive
Backup pastreaza ultimele **5 complete** local si pe Drive. Nu introduce alte joburi
de stergere/retentie sau un program duplicat. Nu sterge arhive pentru a testa UI.
Backup HA NU include aplicatia/starea privata de pe Pi5. Nu afirma ca exista un
restore complet testat: s-au verificat arhive/SQLite, nu restaurarea pe alt hardware.

## API si securitate

Browserul discuta cu backendul existent, nu direct cu Tesla/invertoarele si nu cu un
token HA incorporat. Foloseste API-ul deja implementat:

- `/casa/api/session`, `/casa/api/events` (SSE).
- `/casa/api/command`, `/casa/api/history`, `/casa/api/rules`.
- `/casa/api/v1/energy-policy`, `/casa/api/v1/energy-policy/resume`.
- `/casa/api/v1/energy-dashboard`.
- `/casa/api/users`, `/casa/api/audit` pentru administrator.
- `/casa/auth/login`, `/casa/auth/callback`, `/casa/api/logout`, `/casa/api/logout-all`.
- Conturi Casa: `/casa/auth/local`, `/casa/auth/local/verify`, `/casa/api/me/password`,
  `/casa/api/local-users` (+ `/{id}`, `/{id}/reset`, `/{id}/delete`),
  `/casa/api/service/login`, `/casa/api/service/disconnect` (ultimele doar admin HA).

REST HA local: `/api/states`, `/api/services/...`; WebSocket `/api/websocket`.
Accesul lor cere autentificare. Pentru inventariere administrativa exista helperul
`/config/control_center/deye_ops.py` pe HA, cu comenzi `api GET states` si
`ws '{"type":"home_energy_policy/get"}'`. Acesta necesita contextul de autentificare
local autorizat; nu publica tokenul Supervisor si nu-l muta in backendul public.

Pastreaza obligatoriu: OAuth HA, MFA al contului, TOTP obligatoriu pentru conturile Casa,
cookie-uri Secure/HttpOnly/Lax,
rolurile viewer/control/configure verificate pe server, CSRF + Origin, CSP,
listele de servicii/entitati si limitele de valori. Mod Admin din UI nu este
autorizare. Tokenurile raman criptate pe server, nu in JS/localStorage/loguri/git.
Nu adauga proxy generic HA, YAML executabil primit din browser, parole comune,
acces anonim la datele casei sau reguli controlabile doar prin ascunderea butoanelor.
Pastreaza confirmarea comenzilor; nu inventa stari optimiste, retry-uri necontrolate
sau cozi offline de comenzi. Nu testa alarma, Tesla sau relee reale prin Playwright.
Nu dezactiva verificarile ca sa faci mock-urile mai usor de folosit.

## Contractul nginx: NU il strica

Vhost activ: `/etc/nginx/sites-available/salavat.home.ro-nonconflict.conf`, inclus
prin symlink in `sites-enabled`. Acest host gazduieste MAI MULTE aplicatii.

1. Pastreaza `base: '/casa/'` in Vite si prefixul `/casa` in backend/API/assets.
2. Include-ul aplicatiei este `/etc/nginx/snippets/home-control.conf`.
3. `location = /casa` redirectioneaza la `/casa/`.
4. `location ^~ /casa/` foloseste `proxy_pass http://127.0.0.1:8765;`
   **fara slash final**: backendul trebuie sa primeasca prefixul `/casa/` intact.
5. Pastreaza Host, X-Real-IP, X-Forwarded-For si X-Forwarded-Proto https,
   HTTP/1.1, `proxy_buffering off` si timeout-urile SSE. Nu transforma SSE in polling.
6. Zonele rate-limit sunt in `/etc/nginx/conf.d/home-control-limits.conf`, context
   HTTP: login 6/min, API 10/s. Pastreaza limita body 64k si protectia logurilor OAuth.
7. `/home-assistant/` este ALT proxy, spre `.107:8123`, care elimina prefixul si
   are rescrieri speciale, Upgrade/Connection pentru WS si rute de autentificare.
   Nu copia tratamentul de prefix `/casa/` peste HA sau invers.
8. Setari dependente: `PUBLIC_URL=https://salavat.home.ro/casa`,
   `HA_AUTH_URL=https://salavat.home.ro/home-assistant/auth/authorize`,
   `HA_URL=http://192.168.50.107:8123`. Pastreaza OAuth callback
   `https://salavat.home.ro/casa/auth/callback` si identitatea OAuth existenta.
9. Nu ocupa global `/api/`, `/auth/`, `/static/`, `/callback`, `/` pentru aceasta
   aplicatie. Sunt utilizate de alte servicii. Nu modifica `/conta/`, trading,
   Plex, IDE sau cheia publica Tesla de la `/.well-known/appspecific/...`.
10. Nu reinstala `deploy/nginx-site.*.conf` peste vhost-ul live: sunt snapshot-uri
    istorice. Nu crea al doilea `server_name salavat.home.ro` concurent.
11. Nu expune 8765 sau 8123 direct pe internet si nu folosi Vite dev server in productie.
12. Orice schimbare nginx: copie de siguranta, edit minim, `sudo nginx -t`, apoi
    `sudo systemctl reload nginx`. Daca validarea esueaza, nu reincarca.

Domeniul este comun mai multor aplicatii; path-urile cookie nu izoleaza un XSS
same-origin. Un hostname separat ar imbunatati izolarea, dar cere migrare planificata
OAuth/nginx, nu o redenumire facuta implicit in cadrul unui redesign.

## Publicare si verificare

Salveaza versiunea curenta a fisierelor pe care le atingi intr-un director privat,
in afara radacinii servite. Documenteaza rollback-ul inainte de publicare.
Node implicit pe Pi5 este 18, iar NVM are si 20: nu sunt suficiente pentru build-ul
Vite actual. Foloseste Node >=22.12 intr-un mediu separat sau construieste local;
nu schimba Node global folosit de celelalte aplicatii. Pastreaza lockfile-urile.

```sh
# In copia de lucru, cu Node corespunzator:
npm ci
npm run build
node tests/model.mjs
node tests/energy-flow.mjs
node tests/brief.mjs
npm run test:browser
node tests/local-accounts.mjs
node tests/nova.mjs

# Pe Pi5, in proiect (backend existent, dependinte deja instalate):
cd '/home/pi5/proiecte/Home Assistant'
.venv/bin/python -m pytest tests -q
sudo systemctl status home-control --no-pager
sudo nginx -t
```

Testele browser folosesc date sintetice, nu dispozitive. Adapteaza doar lansatorul
Playwright la platforma: unele teste actuale folosesc Edge Windows. Verifica desktop,
tableta si telefon (360/390 px), text, scroll, filtre stricte pe camera, stari offline,
teme, permisiuni si confirmari. Nu adauga asset-uri inexistente sau date simulate in live.

Publica assets noi inainte de `dist/index.html`; pastreaza temporar assets vechi pentru
clientii cu pagina deja deschisa. Backend modificat: copiaza fisierele necesare si
reporneste NUMAI `home-control`, dupa teste. Restartul inchide temporar SSE; nu trebuie
sa afecteze motorul nativ HA. Pentru frontend simplu nu reporni HA si nu modifica nginx.

Verificari sigure pe Pi5, fara autentificare si fara comenzi catre aparate:

```sh
curl -fsS -H 'Host: salavat.home.ro' http://127.0.0.1:8765/casa/api/health
curl -I https://salavat.home.ro/casa/
curl -s -o /dev/null -w '%{http_code}\n' https://salavat.home.ro/casa/api/v1/energy-policy
```

Ultima comanda trebuie sa intoarca **401 fara sesiune**; frontendul poate fi 200.
Testeaza loginul HA, SSE si o lectura autentificata cu sesiunea proprietarului cand
este disponibila, fara sa copiezi tokenuri in fixture-uri. Nu declara controlul fizic
validat daca ai testat doar pagina de login sau mock-uri.

Continua cu `README.md`, `ENERGY-POLICY.md` si `TESLA.md`, tinand cont ca notele
vechi despre Hue lipsa, TCL neconfigurat sau Tesla neautentificat sunt depasite.
