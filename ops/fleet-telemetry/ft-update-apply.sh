#!/bin/sh
# Apply a reviewed release: sudo /opt/fleet-telemetry/ft-update-apply.sh v0.10.1 2.0.24
# Pins the new digests, keeps the previous compose file for rollback, restarts the stack.
set -eu
[ $# -eq 2 ] || { echo "usage: $0 <fleet-telemetry tag> <mosquitto tag>"; exit 2; }
cd /opt/fleet-telemetry
digest() { docker buildx imagetools inspect "$1" | awk '/^Digest:/{print $2; exit}'; }
FT_D=$(digest "tesla/fleet-telemetry:$1"); MQ_D=$(digest "eclipse-mosquitto:$2")
[ -n "$FT_D" ] && [ -n "$MQ_D" ] || { echo "digest lookup failed"; exit 1; }
cp -a docker-compose.yml "docker-compose.yml.$(date +%Y%m%d-%H%M%S)"
sed -i -E "s|(tesla/fleet-telemetry@)sha256:[0-9a-f]+|\1$FT_D|; s|(# v)[0-9.]+(, pinned)|\1${1#v}\2|" docker-compose.yml
sed -i -E "s|(eclipse-mosquitto@)sha256:[0-9a-f]+(  # )[0-9.]+|\1$MQ_D\2$2|" docker-compose.yml
docker compose pull
docker compose up -d
/opt/fleet-telemetry/ft-firewall.sh
docker compose ps
echo "Rollback: cp the previous docker-compose.yml.<ts> back and run docker compose up -d"
