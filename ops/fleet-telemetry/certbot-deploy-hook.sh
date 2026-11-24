#!/bin/sh
# certbot deploy hook (/etc/letsencrypt/renewal-hooks/deploy/fleet-telemetry.sh).
# Copies the renewed salavat.home.ro certificate for fleet-telemetry (uid 65532, read-only)
# and restarts only that container. The vehicle trusts the CA roots sent in its telemetry
# config, so a new intermediate is fine; a new ROOT would need a re-signed config: logged.
set -eu
LIVE=/etc/letsencrypt/live/salavat.home.ro
DEST=/etc/fleet-telemetry/tls
case " ${RENEWED_DOMAINS:-salavat.home.ro} " in *" salavat.home.ro "*) ;; *) exit 0 ;; esac
install -d -m 0750 -o root -g 65532 "$DEST"
install -m 0640 -o root -g 65532 "$LIVE/fullchain.pem" "$DEST/fullchain.pem.new"
install -m 0640 -o root -g 65532 "$LIVE/privkey.pem" "$DEST/privkey.pem.new"
mv -f "$DEST/fullchain.pem.new" "$DEST/fullchain.pem"
mv -f "$DEST/privkey.pem.new" "$DEST/privkey.pem"
issuer=$(openssl x509 -in "$DEST/fullchain.pem" -noout -issuer 2>/dev/null || true)
logger -t fleet-telemetry-cert "certificate renewed ($issuer); restarting fleet-telemetry"
if docker ps --format '{{.Names}}' | grep -qx fleet-telemetry; then
  docker restart fleet-telemetry >/dev/null
fi
