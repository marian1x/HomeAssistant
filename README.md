# Casa Salavat Web

Private Home Assistant control station on Raspberry Pi 5. React and a
small FastAPI backend. HA on Pi4 remains the only automation/device engine.

Current infrastructure, verified HA inventory, nginx contracts and safe UI-development
handoff for another agent: [AGENT-HANDOFF.md](AGENT-HANDOFF.md).

## Deployment

- Project: `/home/pi5/proiecte/Home Assistant`
- URL: `https://salavat.home.ro/casa/` (public HTTPS, explicitly enabled by the owner).
- Backend: `127.0.0.1:8765`, systemd `home-control.service`, unprivileged `homecontrol`.
- Settings: `/etc/home-control.env`.
- Private runtime state: `/var/lib/home-control`, mode 0700. Never publish this directory.
- Nginx snippet: `/etc/nginx/snippets/home-control.conf`; rate-limit zones:
  `/etc/nginx/conf.d/home-control-limits.conf`. Existing virtual host has one
  include. Other applications and existing HA routes are unchanged.

Sign in using the existing Home Assistant account. Credentials and MFA are handled by HA.
HA administrators have configuration rights; other accounts start as viewers. After an
account has signed in, an administrator can grant it control from Settings. The UI's
User/Admin view switch is an extra usability guard, not the authorization boundary.

## Admin and User

Current controller, Tesla monitoring, energy economics and TCL setup notes are in
`ENERGY-POLICY.md`. It supersedes the historical activation snapshot below: the new
native energy policy owns boiler/HVAC commands, conflicting legacy actors stay OFF,
Tesla authentication is repaired, and the battery reserve is fixed at 20% by default.
On 2026-11-10 the owner enabled the complete unified policy, including solar Tesla
charging, and explicitly resumed device manual holds. Native Tesla polling remains
disabled and no night wake/start is allowed. Activation was checked at night; the
first physical solar charging cycle still needs observation in daylight.

On 2026-11-08 the owner explicitly enabled the reviewed non-Tesla household automations.
Global pause is OFF; the emergency-stop controller remains ON. Battery management,
Ariston solar/default-temperature controls, HVAC (Auto/Winter), weight routing, backup
and retention rules are enabled. Tesla rules, the Tesla-dependent boiler-restore rule
and street-lighting rules remain OFF. Activation state backup:
`/config/control_center/backups/activation-20261108-215832`. HVAC enable and Tesla solar
enable now restore saved choices instead of resetting their switch values at startup.

Manual controls are independent of global automation pause: lights and sockets, boiler
power/temperature/valid operation modes, supported AC modes/temperature, and Google/media
power/play/pause/volume/mute. Capability flags are checked server-side. No arbitrary
playback URL, alarm disarm, raw thermostat writes or unbounded inverter commands are
exposed. Admin settings include separate boiler/HVAC program switches. See `TESLA.md`
for the prepared re-enrollment plan; owner authentication is still required.

- Sign-in reuses HA accounts; the application does not create another password database.
- HA administrators have the `configure` server role. They start in **User** view and can
  switch to **Admin** from the top bar. Admin exposes configuration, role management,
  automation editing and the audit log; User view hides those administration tools.
- Non-administrators start with **Vizualizare** (read-only). In **Admin > Setari > Acces
  utilizatori**, an administrator can grant **User - control** (`control`) or return an
  account to read-only (`viewer`). The user must sign in once before appearing here.
- Admin rights come exclusively from HA's authoritative administrator status, never
  from the role editor. Self-edits, unknown accounts and edits to other HA administrators
  are rejected. The user list identifies HA administrators explicitly.
- Role edits are audited and push an updated session snapshot to active sessions. Server
  permission checks use the current stored role for every command, even before a browser
  receives its updated interface. The Admin/User view switch is not an impersonation
  mechanism and never grants a non-admin configuration rights.
- User and viewer settings show their own account and appearance, not administrator
  configuration. Global emergency pause remains available to a control user; only an
  administrator can resume automations.

## Security Model

- OAuth authorization code and state-cookie validation. Access and refresh tokens never
  appear in JavaScript, localStorage, query results, or application audit records.
- Opaque Secure/HttpOnly/SameSite=Lax session cookies; encrypted server-side token storage
  using Fernet. The master key lives beside the private database, readable only by the
  service account/root. This protects against isolated database disclosure, not host compromise.
- Eight-hour app sessions. Logout/expiry revoke HA refresh tokens; failed revocation is
  retried by the cleanup task. Revoked authentication stops reconnect attempts.
- Server-side roles, CSRF + Origin checks, bounded request size, command rate limits,
  explicit service/entity allowlists and value bounds. No arbitrary HA/API forwarding.
- Battery maximum discharge cannot be increased above 7 kW through this application.
  BMS registers, inverter restart, grid charging and raw electrical settings are not exposed.
- Read-only HA entity events over one WebSocket per signed-in browser session. Browser
  updates use SSE deltas. No repeated device polling and no direct Tesla/Fleet API calls.
- No optimistic physical-state changes and no automatic command retries or replay after
  reconnection. A HA acknowledgement means accepted by HA, not proven device completion;
  the live entity state is the confirmation.
- Rules are saved to HA disabled and include the existing global killswitch condition.
  Existing YAML/package rules can be enabled/disabled, not silently rewritten.
- Global stop activates the existing HA killswitch. It stops automations, not electrical
  devices. Starting automations is blocked while the killswitch is active. Manual device
  control remains available subject to role/availability.

The URL shares an origin with existing Pi5 applications. Cookie paths do NOT isolate
applications against same-origin XSS. A dedicated HTTPS hostname is recommended for
stronger browser-origin isolation. The owner explicitly approved external access on
2026-11-03; the initial LAN-only ACL has been removed only for `/casa/`. The anonymous
frontend contains no live household data. API reads, events, history, user management
and commands still require an authenticated session. Enable MFA in HA's user profile
for each account; no MFA enrollment secret is generated or handled by this application.
Nginx limits login starts to 6/minute plus a burst of 6, and API requests to 10/second
plus a burst of 20 per source IP. SSE events do not create individual HTTP requests.
OAuth callback query strings are not logged by nginx; inspect backend service status
and explicit health checks for application troubleshooting instead.
Internal Pi5-to-Pi4 HA traffic currently uses trusted-LAN HTTP/WebSocket.
For untrusted networks, add TLS or a private encrypted tunnel.

## House Layout

The authenticated snapshot includes `server/house.json`, the owner's declared inventory.
It is not served as a public static asset. Real device bindings use HA registry IDs;
room/floor labels use HA metadata. Items without an actual HA entity are explicitly
marked **De integrat**, with no fabricated telemetry or interactive control. The Shelly
street relay remains **Control separat**, at the owner's prior request.

- Parter: Living, Bucatarie, Camera tehnica, Parter - comun.
- Etaj: Dormitor Mare, Dormitor Mic, Birou, Baie etaj, Hol etaj.
- Exterior: Instalatie solara, Carport, Strada, Terasa, Iarba.

Floor selectors precede room selectors in the overview and device catalog. Room filters
are strict: Whirlpool appears only in Hol etaj, TCL only in Living, and selecting a
bedroom never adds an AC from another room. Coverage is informational, not a filter
exception. The paired Office speakers and Xiaomi scale
registry aliases appear as logical devices rather than duplicate cards. Printer and
scale entities are included even though they only expose sensors. Unassigned older or
unidentified integrations remain separately discoverable, without guessed room bindings.
Registry updates refresh metadata and authoritative HA states through the existing WS
connection, without polling physical devices or Tesla's API.

`ops/organize-house.py --apply --plan /config/control_center/house.json` runs only inside
the HA administration environment, never as the public application. It backs up registries,
creates/reuses native floors and rooms, assigns confirmed device IDs, preserves entity IDs
and automation states, and corrects the boiler lookup helper. It sends no physical device
commands. Native HA backup: `/config/control_center/backups/house-layout-20261103-224633`.

Hue is not yet configured in HA. The three RGBW controllers are present, but their exact
mapping to kitchen/terrace/grass remains an owner-confirmation step. Do not assign these
by their list position. Alarm contacts and smoke detectors are declared inventory only
until integrations expose their individual entities.

### Boiler Estimate

The nominal resistance is 1.8 kW. The real Ariston heating binary sensor is authoritative:
when heating, estimated power is 1.8 kW; when idle or power is confirmed off, it is 0 kW.
An enabled Boost helper does not imply heating. Unknown heating state is not falsely
reported as zero. Energy is integrated using the left method with a one-minute maximum
subinterval for step-like loads: one hour actually heating equals 1.8 kWh.
The YAML source is `ha/ariston_solar_boiler.yaml`; its templates and integration method
are tested by `ha/test_boiler_estimation.py` inside HA's Python environment. Only measurement
templates, integration settings and the lookup helper default were changed; thermostat,
solar boost and manual-override automation actions were not rewritten or enabled.
Historical counters were preserved and were not retroactively corrected. Solar/grid
attribution remains an estimate, not a plug-level measurement; the legacy attribution
does not separately identify battery-supplied boiler energy.

## UI Features

- Light glass control station with tactile controls, recessed toggles, raised navigation,
  compact room/category device lists and a persistent optional dark theme. No house
  model or WebGL workload in the active frontend. The old Scene module is not imported.
- Weather and outdoor humidity come from the first available HA weather entity, not
  an inferred indoor value. Room tabs use real HA area assignments. Only climate devices
  with unscaled setpoints are writable. Temperature and brightness edits are local drafts
  until an explicit confirmation; read-only/offline controls are disabled.
- Generated interior and archived pendant illustrations are decorative, not live camera views or
  photographs of the user's actual home/devices. The active dashboard loads only the
  self-hosted 170 KB interior background; the oversized lamp illustration is removed.
  See `src/assets/README.md` for provenance and generation prompts.
- The home dashboard lists all controllable lights, ACs, water heaters, sockets, media
  and vehicle controls for the selected room or all rooms. Offline devices are hidden
  by default and can be inspected with a checkbox; unknown/unintegrated placeholders
  remain in the separate inventory. Mobile category choice uses a native menu.
- Interactive whole-house energy flow shows combined solar, grid import/export, battery
  charge/discharge/SOC and house demand. Consumer branches distinguish Tesla, estimated
  boiler resistance, AC meters where present, and residual unassigned load. kWh is never
  converted into instantaneous kW. Missing AC meters and stale Tesla data remain unknown;
  their consumption stays in the explicitly labelled residual, not fabricated estimates.
  Fresh vehicle power away from home is excluded. Clicking nodes only reads cached HA
  state, never polls a device or wakes Tesla. Command confirmations and authorization
  remain unchanged. Source unit/staleness and allocation behavior are tested by
  `node tests/energy-flow.mjs`.
- Combined solar production, consumption, grid, battery, forecast and battery-policy helpers.
- Dedicated energy accounts: editable dated tariffs (1.11/0.45 RON/kWh), custom date
  intervals, daily net credit/cost and consumption, contextual CSV, six-day weather/PV/
  battery outlook and read-only efficiency suggestions. See `ENERGY-POLICY.md`.
- Live device catalog with room/search filters, lights/switches/fans and temperature/mode
  controls for supported climate/water-heater entities.
- Tuya `climate.heat`/`climate.bedroom_heat` use corrected temperature sensors for display;
  raw temperature writes are blocked because their Tuya scaling needs an explicit adapter.
- Security/alarm/media/cover entities may be displayed without unsupported commands.
- Day/week/month/year recorder statistics, existing automation toggles, a small time/sun/
  numeric-threshold rule builder, per-user access administration, command audit.
- No offline service worker and no caching/replay of device commands.

Forecast assumptions and Deye limits are not changed just by viewing the app.
Enabling the battery manager remains an explicit action in HA. Existing Tesla authentication
errors must be repaired in HA; this interface cannot bypass integration authentication.

## Development

Frontend builds require Node >=22.12 (Pi5's existing global Node 18 is left untouched).

```sh
npm ci
npm run build
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
STATE_DIR=/tmp/casa-dev PUBLIC_URL=http://127.0.0.1:8765/casa \
  .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8765
```

Use an appropriate browser-reachable `HA_AUTH_URL` for local development. No production
token is needed or embedded at build time. `requirements.lock` records the tested Python
environment; `package-lock.json` pins frontend packages.

```sh
.venv/bin/python -m pytest tests/test_security.py -q
node tests/build-fixture.mjs /path/to/redacted-ha-snapshot.json
npm run test:browser
```

Browser tests use isolated synthetic chart samples and redacted states, mocked services,
desktop/tablet/mobile screenshots at 360, 390, 768, 1024 and 1440 pixels, theme persistence,
asset rendering, nonoverlapping layouts, role restrictions and local draft controls. They never command
physical devices. `tests/live.mjs` tests the deployed login screen and HA authorization page
without entering credentials. A full production OAuth/control test requires human sign-in.
The existing HA subpath proxy emits a native HA service-worker registration warning;
the authorization form renders. This application registers no service worker of its own.

## Operations

### HA Backup Policy

Full Pi4 backups, including the Recorder SQLite database, run at 07:00 and 19:00 in
Europe/Bucharest. `ha/backup_strategy.yaml` declares the schedule and an hourly alert
if no scheduled full backup has reached Drive for 18 hours. A full backup job uses
`homeassistant_exclude_database: false`. The native automatic-backup scheduler is not
also enabled, so it does not create a duplicate schedule.

Google Drive Backup owns retention: latest five full copies on Drive and locally,
no generational extras, no delete-before-create, no immediate local deletion after
upload. Upgrade-only partial backups are ignored for upload/retention and expire
locally after one day. The former independent 14-day local prune job is retired.
Backup creation and its integrity/staleness monitor are explicitly excluded from the
household killswitch, as approved by the owner. Other automations retain their pause
behavior; turning on backup maintenance through the web app still requires HA Admin.

The retention migration verifies the archives' gzip CRCs, required configuration,
SQLite `quick_check` and history/statistics tables before cleanup; reported uploaded
sizes must match. Only records in this add-on's own backup inventory are removed.
This is not a full recovery test on spare hardware. Verification records are private,
and no backup credentials or archive contents are exposed by the web app. The public
application has no backup-deletion endpoint. HA backups do not include the Pi5 app;
see the separate Pi5 backup guidance below.

```sh
sudo systemctl status home-control
sudo journalctl -u home-control -n 50
sudo systemctl restart home-control
sudo nginx -t
```

Uvicorn allows 10 seconds for live connections to close during a restart; systemd
caps service shutdown at 30 seconds so long-lived event streams cannot stall a rollout.

For source updates, copy built assets before the new `dist/index.html`, copy backend source,
then restart this service. Do not reinstall the complete original nginx virtual-host copy;
it is a first-install snapshot and later unrelated changes must be preserved.

HA backups do not automatically include this Pi5 application. Back up the source/build,
environment file, nginx snippet, systemd unit and the private database/master key together
to a restricted destination. Use SQLite's online backup API or stop this service while
copying its runtime state. Treat backups as credentials and do not expose them in the app.

The former LAN-only ACL could reject a home PC using a commercial VPN. That ACL no
longer applies to `/casa/`. The optional Windows split-DNS helper in `ops/` is not
required for public access and has not been silently elevated or run by the application.
