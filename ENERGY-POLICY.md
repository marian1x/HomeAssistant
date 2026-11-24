# Energy and Comfort Policy

The controller lives in HA as `custom_components/home_energy_policy`. The Pi5 web
app is an authenticated editor and monitor, not the process keeping the house running.
The native config entry and HA `.storage/home_energy_policy` are included in full HA
backups. Never publish `.storage`, the session database or Tesla credentials.

## Default Policy

- House comfort -> house battery -> Tesla -> boiler -> extra HVAC thermal storage.
- Native Deye/BMS protections remain authoritative. No grid charging is enabled.
- Battery reserve 20%, native discharge limit 7 kW. Tesla battery assistance is only
  considered above 70% SOC after a full recharge, during daylight, with a conservative
  remaining-solar forecast sufficient to replenish the battery. No night EV start.
- The reserve is fixed at the owner's selected minimum, default 20%, across all six
  Deye ToU slots. Weather never raises it automatically. Native BMS protections are
  untouched. The former adaptive-reserve helpers remain only for compatibility.
- Winter profiles use **-15 C**, not +15 C. Low: 23/24 C, Med: 24/25 C,
  High: 25/27 C; numeric fan labels for TCL must be mapped after that AC is integrated.
- Boiler: winter 47 C, summer 43 C, solar 80 C, heating estimate 1.8 kW.
- Whirlpool winter: below 5 C outside, 20:00-21:00, 27 C, medium.
  Summer: above 30 C outside, 22 C/low in the Low profile.
- Manual device changes suspend that device until **06:00 the following day**.
  This time is editable. Native app/IR changes can only be detected once the integration
  reports them; an unreported remote-control change cannot be recognized by HA.
- The global HA killswitch suppresses all writes and scheduled Tesla monitoring.
  Backup creation and its staleness alert continue independently, per owner choice.

## Tesla API Budget

Native Tesla Custom periodic polling is disabled through its config-entry preference.
The local adapter shares that integration's controller/cache and always passes
`wake_if_asleep=False`. It never presses the native Force Data Update button, which
would wake the car. Requests go through the existing private proxy, not a public proxy.

- Cadence follows the last known car state (owner request 2026-11-24), always without
  wake-up: driving (online, shift D/R/N) every 10 min, also at night; charging without
  engine ownership every 10 min; plugged in but idle every 30 min by day; parked away
  every 120 min by day; at home unplugged every 90 min while PV production exists.
  Meaningful surplus with an eligible car at home permits a pre-start check after 15 min.
- Load-step trigger: a sustained (>= 60 s), balanced three-phase rise of the house load
  (default >= 3 kW total and >= 0.8 kW on each of `sensor.deye_load_l1/l2/l3_power`
  against the 2-10 min baseline) reads the car once, day or night, unless it is already
  known to be charging or driving; the matching drop reads a charging car once. Single-
  phase appliances do not trigger it. >= 5 min between reads, 10 min step cooldown,
  12 step reads/day, all inside the normal read budget. Idle cadences stay >= 30 min so
  a parked car can still fall asleep between reads.
- Engine-owned solar charging: reads at most every 120 seconds; electrical evaluation
  remains every 30 seconds. Requested current is written only when different.
- Night: besides driving/charging cadence and load steps, one check in the five-minute
  window starting at 00:00; no catch-up checks, and no waking a sleeping car.
- Defaults: 60 read cycles/day, 900/month; 60 automatic service commands/day, 900/month.
  Two daily/four monthly command slots are reserved for stopping owned charging.
- Counts are charged before I/O, persist across restarts and reset by local calendar.
  Failed operations trigger a 60-minute backoff. No immediate retry loops.
- A read cycle includes a connectivity/list query and, only if online, a data query.
  These counters are local attempts, not Tesla's billing ledger. Setup requests, native
  manual actions, third-party apps, proxy/library retries and Tesla's monthly credit
  accounting are outside this counter. Set a spending limit in the Tesla Developer
  portal; the local cap alone cannot guarantee a zero bill.
- No precise short-trip/route history is promised with sparse polling. Fleet Telemetry
  (installed 2026-11-25, `FLEET-TELEMETRY.md`) records drives point by point when the car
  streams. While the stream is live (a message within 120 s), the 10-minute driving read is
  skipped and the live gear feeds `ev_mode`; charging, limit, load-step and night reads stay.
- Streaming budget (owner 2026-11-25): signals are counted locally (150 000/$1, x1.2 margin).
  If the first 14 days cost more than $2, or streaming + used API + the reserve for every
  remaining read/command of the 900/900 monthly caps would exceed the $10 monthly credit,
  `fleet.py` removes the car's telemetry config once (one API call) and notifies. Reads and
  charging commands keep their budget.

Automatic charging is restricted to the physical `zone.home` near the panels, not all
locations classified as "home" for historical charging statistics. A lower manual
Tesla charge limit remains effective. No native BMS or high-voltage controls are exposed.

The owner enabled all unified policy consumers on 2026-11-10 at 01:41 Bucharest time,
including Tesla solar charging (5-16 A, 80% target), boiler and both house ACs. Existing
manual holds were explicitly resumed. At activation there was no PV, the battery was
at its 20% reserve and Tesla was asleep; no car command or extra car read was issued.
This verifies the night guard, not a completed physical solar charging session.

## Web Interface and Security

`https://salavat.home.ro/casa/`, page **Politica Energie** (mobile **Control**).
User roles can read status; configuration requires HA Admin plus app Admin mode.
Device resume requires both app control rights and native HA entity control rights.
Config changes use a revision guard and bounded, typed parameters, never executable
templates/YAML or arbitrary service names. Existing CSRF, Origin, secure-cookie,
encrypted-token storage and nginx rate limits are retained; Host and browser permission
policies, same-origin resource/opener policies and a restricted form-action CSP are
also enforced. The versioned `/api/v1/energy-policy` API can serve a future
Android client. No APK, embedded privileged token or offline command queue is included.

Legacy Ariston/HVAC command automations are left installed but stopped. The controller
fails closed if a conflicting actor is manually restarted. Existing backups, statistics,
family health, battery manager, and discovery rules remain separate and intact.

## Energy Economics and Outlook

The web page **Costuri si prognoza** uses authenticated, read-only Recorder statistics,
not live device polling. Import defaults to 1.11 RON/kWh and export to 0.45 RON/kWh.
An HA administrator in app Admin mode can record a tariff and effective date; records
before the first known tariff use an explicitly labelled assumed initial rate. A new
rate does not silently reprice earlier dates. The separate current-price simulation
does not modify history. Native HA Energy also references the current price sensors.

Choose day/week/month/year or an arbitrary inclusive date range of at most five years.
Daily net credit = exported kWh * sell price - imported kWh * buy price. Missing data
remains missing; partial coverage is labelled. This is an energy-value estimate, not
the supplier invoice or statutory prosumer settlement. CSV follows the selected tab:
daily accounts, hourly consumption of one day, or the six-day forecast.

Weather comes from a fixed HTTPS Open-Meteo endpoint, cached hourly; HA coordinates
stay server-side. PV uses the existing HA forecasts (roof slope remains estimated).
New outdoor temperature/cloud measurement sensors build long-term local statistics.
Weather history is used only when coverage is adequate, never across unbounded gaps.
Until at least 14 paired historical days exist, thermal sensitivity is configurable
and confidence is low. Without paired temperatures, today's forecast mean is an
explicit provisional thermal reference, not a measured historical relationship.

Today plus five future days model hourly house load, solar, 16 kWh battery, current
SOC, fixed reserve, inverter/BMS power limits and configurable battery efficiency.
Today's result includes measured energy to date plus the remaining forecast. No grid
charging, extra Tesla charging or discretionary HVAC/boiler boosts are assumed. Missing
PV/battery/weather data prevents a false financial forecast. Uncertainty bands are
illustrative, not statistical confidence intervals. Recommendations never actuate devices.

## TCL Home Setup

HACS repository `nemesa/ha-tcl-home-unofficial-integration`, release 3.16.0, is installed.
After Core 2026.11.0 restart, its initial configuration form was verified without
credentials or pairing. In HA: Settings -> Devices & services -> Add integration ->
**TCL Home - Unofficial**. Enter the TCL Home account, retain the offered application
URLs/app ID, leave verbose logging OFF. Device sharing to a separate account can reduce
the credentials' scope. No SmartLife reset or LocalTuya pairing is required for this path.

The owner's downstairs FreshIN now exposes
`climate.living_living_air_cxbwrbfaaae_climate`, with numeric fan modes 1 through 6,
Auto and Turbo. It is assigned to Living/Parter; winter policy uses 1/2/3 and solar
boost uses 6. The web inventory groups its climate, sensors and switches as one device.
The temperature dialog also exposes supported fan choices, with explicit confirmation.

New bindings preserve an already running device's existing settings until 06:00 the
following day, just like a manual change; changing another policy parameter does not
clear that hold. An off device is eligible for the configured automatic schedule.
For future replacements, choose the entity in app Admin -> Politica Energie ->
Asociere aparate -> AC parter TCL and verify its supported fan labels. Native-app/IR
overrides remain detectable only after the integration reports the changed settings.

## Verification

`python -m pytest tests -q`

`python tests/build-policy-fixture.py`, `npm run build`, `node tests/browser.mjs`.
Regenerate `tests/build-finance-fixture.py` before browser tests after accounting edits.

`ops/test-policy-runtime.py` runs against fake HA states/services inside HA's Python
environment; it does not call the real HA API or the vehicle. Commissioning is separate.
AC powers are estimates until dedicated meters are added; reserve margins and live
grid feedback limit discretionary consumption, but they are not revenue-grade metering.

## Owner Charge Limit and Tesla Journal (2026-11-24)

- `home_energy_policy.set_ev_limit` (20-100 %). At or above 50 % the native car limit is set
  once at the next fresh read. Below 50 % the native limit stays at 50 % and, only at home
  while plugged in, charging is stopped at the target and only a charge stopped this way is
  resumed 2 points below it. Commands use fresh data from an awake car, never wake it, count
  in the command budget and do not create manual holds. Solar target = min(80, owner limit).
- The journal records drives and charges from existing states into
  `/config/home_energy_policy_tesla.db`; home charges are split into solar, house battery and
  grid from the Deye flows every 30 s. Solar is valued at the export price, battery energy at
  the export price / 90 %, grid at the import price; station prices are entered per charge.

## Cold-morning grid heat assist (owner decision 2026-11-25)

New policy feature (`coldcharge.py` pure logic + `runtime.cold_charge`, config group `battery`).
When `cold_charge_enabled` and the battery temperature (`sensor.deye_battery_temperature`) is
below `cold_charge_temp_c` (3°C) AND now is within `cold_charge_hours_before_sunrise` (3h)
before `sun.sun` next_rising, it turns ON `switch.deye_battery_grid_charging` only — no SOC or
TOU-program writes. This makes the inverter "wait to charge" so the pack's self-heater runs;
the BMS still caps the real current at low temp, and the Deye program SOC (20%) bounds any grid
charge, so little grid energy is used. It turns the switch OFF at `cold_charge_recover_c` (6°C),
or when solar production starts (pv >= solar_min_kw), or when the window ends at sunrise.
Writes only on transition, with hysteresis (3→6°C) and a command cooldown; respects the kill
switch and legacy-conflict guard; only turns off a switch it turned on (never fights a manual
change). Status in the policy sensor attribute `cold_charge`; shown on the policy page. Tests:
`tests/test_coldcharge.py`. Armed by the owner for the next cold morning.