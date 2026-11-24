# Tesla Fleet Telemetry - Casa Salavat

Instalat 2026-11-25 la cererea proprietarului. Document intern, fara parole, tokenuri, VIN
sau chei private. Citeste intai `AGENT-HANDOFF.md`; limitele de acolo se aplica integral.

## Stare la 2026-11-25

| Pas | Stare |
| --- | --- |
| Server `fleet-telemetry` + broker pe Pi5 | Instalat, ruleaza, testat din LAN si prin IP-ul public (hairpin) |
| Firewall (DOCKER-USER, ufw, fail2ban) | Activ, mod `public` (forward-ul 4443 exista deja pe router) |
| Integrarea MQTT in HA + consumatorul din `home_energy_policy` 0.6.0 | Activ, conectat prin TLS |
| Interfata Tesla (harta pe viteza, profil, card telemetrie) | Publicata |
| **Push config in masina** | **NEFACUT**: semnarea cere rularea `tesla-jws` in add-on-ul proxy (vezi Push). Pana atunci masina nu trimite nimic, iar costul este 0. |

## Fluxul datelor

```
Masina (LTE/WiFi) --TLS mutual, certificat client Tesla--> IP-ul public:4443 (router, doar TCP)
  -> 192.168.50.101:4443 (Pi5) -> lantul DOCKER-USER/FT-FILTER (limite pe IP, fail2ban)
  -> container fleet-telemetry (retea ft-edge: nu poate initia nicio conexiune)
  -> retea interna ft-bus (fara ruta) -> ft-mosquitto:1883 (user telemetry: doar publish tesla/#)
  -> 192.168.50.101:8883 TLS, acceptat DOAR de la 192.168.50.107 (user homeassistant: doar citire)
  -> HA: integrarea MQTT -> home_energy_policy/fleet.py (VIN verificat, max 40 mesaje/s)
  -> telemetry.Assembler (campurile unei inregistrari -> un punct; mph->km/h, mile->km)
  -> tesla_log.Journal.telemetry_point -> triplog.Sessions.feed -> SQLite -> API -> TeslaMap (OSM)
```

Cat timp stream-ul e live (mesaj in ultimele 120 s si fara DISCONNECTED), deplasarile vin din
telemetrie (punct la 5 s, viteza, consum din `EnergyRemaining`), iar snapshot-urile `tesla_custom`
actualizeaza doar incarcarile (`nodrive`). Incarcarile raman pe contorul `energy_added` al
integrarii (`nocharge` pe punctele de telemetrie). Fara stream, totul revine la citirile rare.

Campuri cerute masinii (`telemetry.FIELDS`, trimise doar la schimbare): Location 5 s,
VehicleSpeed 5 s, Gear 1 s, Odometer 30 s, Soc 60 s, EnergyRemaining 30 s, OutsideTemp 300 s,
DetailedChargeState 1 s, AC/DCChargingPower 30 s.

## Ce este accesibil din internet (exact)

- **Un singur port nou: TCP 4443** pe IP-ul public. Raspunde serverul TLS Go din fleet-telemetry,
  cu certificatul Let's Encrypt `salavat.home.ro` (deja public prin 443 si in jurnalele CT).
  Serverul impune `RequireAndVerifyClientCert` cu CA-ul de productie Tesla inclus in binar:
  fara certificat de vehicul Tesla, conexiunea se inchide in handshake (`certificate required`),
  fara niciun octet procesat de aplicatie. Fara status/metrics/profiler (neconfigurate).
- Limite in `FT-FILTER`: maximum 4 conexiuni simultane pe IP, 64 total, 10 conexiuni noi/minut
  pe IP; orice alt port/protocol spre container este aruncat. fail2ban (`fleet-telemetry`):
  3 handshake-uri fara certificat valid in 10 min -> ban 1 zi, crescator pana la 30 zile.
  EOF/reset/timeout NU se numara (masina pe semnal slab nu e blocata niciodata); LAN ignorat.
- Neschimbate: 80/443 (nginx, vhost-ul comun neatins), 2222 (SSH cu cheie). MQTT 8883 NU este
  expus in internet (routerul nu il redirectioneaza; firewall-ul accepta doar .107).
- IPv6: porturile sunt publicate doar pe 192.168.50.101; DNS-ul are doar A (IPv4).

Riscuri ramase: o vulnerabilitate pre-autentificare in stiva TLS Go sau in server (atenuata:
non-root UID 65532, rootfs read-only, `cap_drop: ALL`, `no-new-privileges`, fara iesire de
retea, CPU 0,5, 64 procese; limita de memorie NU se aplica: kernelul Pi5 porneste fara
`cgroup_enable=memory`, ar cere reboot); DoS pe 4443 (afecteaza doar telemetria; jurnalul
revine la citirile rare). Datele de locatie trec prin broker fara persistenta pe disc.

## Pi5: fisiere si servicii

| Ce | Unde |
| --- | --- |
| Compose (imagini fixate pe digest) | `/opt/fleet-telemetry/docker-compose.yml` (sursa: `ops/fleet-telemetry/`) |
| Config server, TLS copiat, broker, CA local, parole | `/etc/fleet-telemetry/` (root, 0750; parolele 0600) |
| Mod expunere | `/etc/fleet-telemetry/exposure` = `public` sau `lan` |
| Firewall | `ft-firewall.service` -> `/opt/fleet-telemetry/ft-firewall.sh` (lant `FT-FILTER` din `DOCKER-USER`) + ufw `deny in on ft-edge/ft-bus/ft-lan` |
| fail2ban | `/etc/fail2ban/jail.d/fleet-telemetry.conf`, `filter.d/fleet-telemetry.conf` (journald `SYSLOG_IDENTIFIER=fleet-telemetry`) |
| Certificat | `/etc/letsencrypt/renewal-hooks/deploy/fleet-telemetry.sh`: copiaza certul reinnoit si reporneste DOAR containerul |
| Actualizari | `ft-update-check.timer` (luni) publica pe MQTT; HA arata notificare. Aplicare: `sudo /opt/fleet-telemetry/ft-update-apply.sh <tag fleet> <tag mosquitto>` |
| Loguri | `journalctl -t fleet-telemetry -t ft-mosquitto` |

Retele Docker: `ft-edge` 172.30.40.0/29, `ft-bus` 172.30.41.0/29 (internal), `ft-lan`
172.30.42.0/29. Docker ocoleste ufw pentru porturile publicate: regulile reale sunt in `FT-FILTER`.
Nu publica porturile pe `0.0.0.0` si nu adauga alte servicii in aceste retele.

## HA

- Integrarea MQTT: broker `192.168.50.101:8883`, TLS cu CA-ul local `Casa Salavat MQTT CA`
  (`/etc/fleet-telemetry/mqtt-ca/` pe Pi5; certificatul serverului expira in 2031), user `homeassistant`.
- `home_energy_policy` 0.6.0: `telemetry.py` (logica pura), `fleet.py` (MQTT, sanatate, buget,
  apeluri Fleet API), atributul `telemetry` din `sensor.home_energy_policy_status`, campul
  `telemetry` din `home_energy_policy/tesla_log`. Stare persistata in `meta.telemetry` din
  `/config/home_energy_policy_tesla.db`.
- Serviciu admin `home_energy_policy.fleet_telemetry` (`return_response`):
  `status` (local), `remote` (config + `fleet_telemetry_errors` de la Tesla: 2 cereri),
  `push` (`token` semnat, `exp`), `stop` (sterge configul din masina: 1 cerere).
  Apelurile trec prin conexiunea `tesla_custom` si proxy-ul local; tokenul nu iese din HA.

## Bugetul (decizia proprietarului 2026-11-25)

Preturi Tesla: 150 000 semnale/$1, 500 cereri date/$1, 1 000 comenzi/$1, 50 wake/$1; credit
lunar $10. Limita implicita de facturare este 0: peste credit aplicatia e dezactivata si
configurile de telemetrie sunt sterse definitiv. Local, fiecare mesaj MQTT = 1 semnal, estimat
cu marja 1,2.

1. Primele 14 zile de la primul semnal: daca streamingul estimat depaseste **$2**, `fleet.py`
   sterge configul din masina (o singura cerere) si trimite o notificare.
2. Apoi, lunar: streaming + citiri/comenzi deja facute + **rezerva pentru toate citirile si
   comenzile ramase din plafoanele 900/900** trebuie sa ramana sub **$10**. Rezerva (pana la
   ~$4,50) protejeaza incarcarea solara si citirile fara wake-up; streamingul primeste restul.
3. Cat timp stream-ul e live, citirea "in mers la 10 min" este sarita (`quota.due`);
   citirile pentru incarcare, limita, salturi de consum si 00:00 raman neschimbate.

Estimare: ~1 700 semnale/ora de mers (~$0,011/h), ~300/ora de incarcare. Recomandare:
seteaza si in Tesla Developer Portal -> Billing o limita explicita (de ex. $10).

## Push (de facut o data, apoi la expirarea configului, ~1 an)

`tesla_custom` foloseste add-on-ul Tesla HTTP Proxy 2.3.0, al carui binar (vehicle-command din
2025) NU stie sa semneze `fleet_telemetry_config`. Varianta aleasa: utilitarul oficial
`tesla-jws` din vehicle-command **v0.4.1** (commit `49977a18fd68567501d59e16a6c9e4a8b9348544`),
construit static arm64 pe Pi5 (`/opt/fleet-telemetry/tools/tesla-jws`, sha256 in `tesla-jws.sha256`; configul de semnat in `tools/ft-config.json`), rulat
IN containerul add-on-ului cu keyring-ul existent (`pass`, cheia `myself`). Cheia privata nu
iese din add-on; rezultatul este un JWS cu configul (nu un secret de cont).

Claims (`telemetry.config`): `hostname` salavat.home.ro, `port` 4443, `ca` = intermediarele
din fullchain + ISRG Root X1 + X2 (rezista la schimbarea intermediarului LE), `exp` (+360 zile),
`fields`. Lantul a fost verificat cu doar acest bundle: `Verify return code: 0`.

Pasi (proprietarul sau un agent autorizat explicit pentru acest pas):

```sh
# pe HA (ssh root@192.168.50.107), cu fisierele tesla-jws si ft-config.json copiate in /tmp
C=app_c03d64a7_tesla_http_proxy
docker exec -i $C sh -c 'cat > /tmp/tesla-jws && chmod 700 /tmp/tesla-jws' < /tmp/tesla-jws
docker exec -i $C sh -c 'cat > /tmp/ft-config.json' < /tmp/ft-config.json
docker exec -e GNUPGHOME=/data/gnugpg -e PASSWORD_STORE_DIR=/data/password-store $C \
  /tmp/tesla-jws -keyring-type pass -key-name myself -fleet sign TelemetryClient /tmp/ft-config.json > /tmp/ft-token
docker exec $C rm -f /tmp/tesla-jws /tmp/ft-config.json
# trimite: serviciul admin home_energy_policy.fleet_telemetry {action: push, token: <ft-token>, exp: <exp>}
# apoi:    {action: remote} -> synced, key_paired, errors
```

Raspunsul `skipped_vehicles` cu `missing_key` inseamna ca cheia virtuala a aplicatiei nu e
asociata in masina (proprietarul: `https://tesla.com/_ak/salavat.home.ro` din aplicatia Tesla).

## Verificare si diagnostic

```sh
# Pi5
cd /opt/fleet-telemetry && sudo docker compose ps
sudo iptables -S FT-FILTER ; sudo fail2ban-client status fleet-telemetry
journalctl -t fleet-telemetry --since -1h | tail
openssl s_client -connect 192.168.50.101:4443 -servername salavat.home.ro </dev/null   # trebuie: certificate required
# HA: home_energy_policy.fleet_telemetry {action: status}
```

Teste: `tests/test_telemetry.py` (pytest), `ops/test-fleet-runtime.py <dir>` in Python-ul HA
(fake hass/MQTT/Tesla), `tests/nova.mjs` (UI). Niciunul nu atinge masina sau brokerul real.

## Rollback

- Pi5: `/home/pi5/proiecte/.home-control-backups/fleet-telemetry-20261125-005328/ROLLBACK.md`.
- HA: `/config/.policy-backups/telemetry-20261125-011233/ROLLBACK.md` (componenta 0.5.0, config entries, DB jurnal).

## Proiectul urmator: firewall "inteligent" pe 4443 (cerut de proprietar)

Mai poate fi blocat doar traficul care NU vine de la masina; IP-urile ei sunt mobile, deci nu
exista lista fixa. Plan: (1) invatare 2-3 saptamani: IP/ASN/tara pentru fiecare conexiune mTLS
reusita (logul `fleet-telemetry` are `remote_ip` si VIN); (2) blocare: ipset GeoIP (tarile
configurate) + ASN-urile invatate, restul DROP inainte de handshake; ban escaladat pentru orice
handshake esuat; liste de scanere (FireHOL level1 / CrowdSec community); (3) panou in aplicatie
cu incercarile blocate. Bazele exista: loguri JSON, lantul `FT-FILTER`, jail-ul fail2ban.
