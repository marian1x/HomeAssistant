# Tesla: Re-enrollment Plan

Checked on 2026-11-08. No credentials, refresh tokens or private keys belong in this file.

## Current Installation

- Existing HA integration: Tesla Custom (`tesla_custom`), version 3.28.0. Authentication
  was restored by the owner on 2026-11-08 using the installed proxy's OAuth flow.
  The Windows `tesla_auth` ownerapi token did not belong to this Fleet developer client.
  The custom flow's `connect(test_login=True)` only returns supplied tokens without
  authenticating, explaining its misleading success message; the real exchange failed
  with 401 `login_required`. No vehicle wake or charging test was used for this diagnosis.
- Tesla HTTP Proxy add-on 2.3.0 is running. Client ID, client secret and the existing
  internal proxy/certificate configuration are present. Their values were not exported.
- The public key URL returns a valid public PEM key:
  `https://salavat.home.ro/.well-known/appspecific/com.tesla.3p.public-key.pem`.
- No signing key was rotated. No integration, vehicle entity or history was deleted.
- All Tesla automations and solar charging remain OFF. The solar-enable helper now
  restores its saved state rather than forcing ON after a HA restart.
- Native periodic polling is disabled. See ENERGY-POLICY.md for the bounded local
  monitoring schedule and the replacement controller; historical legacy rules stay off.
- The `/callback` placeholder returning 404 is expected for the legacy proxy flow;
  it must not fall through to the accounting application. Callback query strings must
  not be recorded in nginx access/error logs.

## Fleet Telemetry (2026-11-25)

Installed on the Pi5 (`FLEET-TELEMETRY.md`): server on TCP 4443, broker, HA consumer, budget guard.
The proxy add-on's `debug` option was turned off (it could log tokens). The add-on binary cannot
sign `fleet_telemetry_config`; the config is signed with the official `tesla-jws` (vehicle-command
v0.4.1) run inside the add-on, so the private key never leaves it. The push itself is pending
the owner. The published public key equals the proxy key (SHA-256 of DER `fec988f1...1b6d`).

## Preferred Next Step: Official Tesla Fleet

The old Tesla HTTP Proxy add-on repository states it has been unmaintained since
January 2025. Prefer the maintained HA Tesla Fleet integration for the next enrollment.
This is a migration, not a drop-in token replacement: existing custom-integration entity
IDs are used by charging, drives and session statistics, so bindings must be reviewed
before enabling any Tesla automation.

1. Keep the existing custom integration and automations stopped while preparing the
   migration. Back up current registries/configuration. Do not remove the vehicle's key
   in the mobile Tesla app as a troubleshooting shortcut.
2. Review the existing Tesla developer application's credentials and allowed OAuth
   redirect URIs. The official integration normally uses
   `https://my.home-assistant.io/redirect/oauth` with My Home Assistant enabled.
   Preserve any other redirect URIs still required by the legacy flow.
3. Add **Tesla Fleet** from HA's **Settings > Devices & services**. Reuse developer
   credentials securely inside HA. The account owner completes the Tesla login, MFA,
   vehicle selection and consent directly in the browser, never in chat.
4. Use the key generated/required by the new integration. Publishing a replacement at
   the same public-key URL must be coordinated with enrollment; do not overwrite the
   currently published key beforehand. Retain a rollback copy of the existing key/config.
5. Complete the virtual-key authorization in the mobile Tesla app if requested. This
   owner approval cannot be performed remotely by the coding agent.
6. Check one read-only vehicle update, authorization scopes and current Tesla billing
   limits. Do not run wake-up loops or repeatedly generate refresh tokens.
7. Map the new entities to charging power/current, charger connection, battery level,
   location and trip/session tracking. Preserve historical sensors and counters.
8. Review the solar controller before activation: house -> house battery -> Tesla ->
   boiler; 20% house-battery minimum reserve; no battery-grid charging; no Tesla charging
   powered by house-battery discharge; manual charging override and API-saving behavior.
9. Reconcile the charging cap explicitly: at 3 x 220 V, 12 A is 7.92 kW, not 7 kW.
   A strict 7 kW cap requires a current computed from actual voltage, commonly 10 A
   at nominal voltage. Do not enable the algorithm with contradictory power/current caps.
10. Only after enrollment and a supervised low-current test should Tesla solar automation
    be enabled. Non-Tesla household automations can remain active throughout preparation.

## Temporary Legacy Reauthentication

If explicitly choosing to retain the current integration temporarily, reauthenticate
the existing entry rather than creating duplicates. Use the installed proxy (not a
public third-party proxy), and keep **Use Fleet API Proxy** enabled. Its Web UI can
start **Login to Tesla account**. The account owner authorizes the app; the resulting
callback URL is entered only into the proxy's own UI, and its refresh token only into
the existing HA reauthentication form. The legacy UI can print tokens to its logs:
never paste those logs or tokens into chat. This does not remove the maintenance risk.

## References

- HA Tesla Fleet: https://www.home-assistant.io/integrations/tesla_fleet/
- Tesla Custom: https://github.com/alandtse/tesla
- Proxy maintenance notice: https://github.com/llamafilm/tesla-http-proxy-addon
- Legacy proxy procedure: https://github.com/llamafilm/tesla-http-proxy-addon/blob/main/tesla_http_proxy/DOCS.md
