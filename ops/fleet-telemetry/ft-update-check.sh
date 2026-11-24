#!/bin/sh
# Weekly: report newer fleet-telemetry / mosquitto releases to Home Assistant (retained MQTT
# message on ops/fleet-telemetry/update). It never updates by itself: an update is applied with
#   sudo /opt/fleet-telemetry/ft-update-apply.sh <fleet-tag> <mosquitto-tag>
# after reading the release notes (the server is internet-facing; no blind auto-updates).
set -eu
CUR_FT=$(grep -o 'fleet-telemetry@sha256:[0-9a-f]*' /opt/fleet-telemetry/docker-compose.yml | cut -d@ -f2)
CUR_MQ=$(grep -o 'eclipse-mosquitto@sha256:[0-9a-f]*' /opt/fleet-telemetry/docker-compose.yml | cut -d@ -f2)
latest() {  # newest semver-looking tag of a Docker Hub repo
  curl -fsS --max-time 20 "https://hub.docker.com/v2/repositories/$1/tags?page_size=50&ordering=last_updated" |
    python3 -c "import sys,json,re
tags=[t['name'] for t in json.load(sys.stdin)['results'] if re.fullmatch(r'$2',t['name'])]
key=lambda s:[int(x) for x in re.findall(r'\d+',s)]
print(max(tags,key=key) if tags else '')"
}
digest() { docker buildx imagetools inspect "$1" 2>/dev/null | awk '/^Digest:/{print $2; exit}'; }
FT=$(latest tesla/fleet-telemetry 'v\d+\.\d+\.\d+')
MQ=$(latest library/eclipse-mosquitto '2\.0\.\d+')
FT_D=$(digest "tesla/fleet-telemetry:$FT"); MQ_D=$(digest "eclipse-mosquitto:$MQ")
ft_new=false; mq_new=false
[ -n "$FT_D" ] && [ "$FT_D" != "$CUR_FT" ] && ft_new=true
[ -n "$MQ_D" ] && [ "$MQ_D" != "$CUR_MQ" ] && mq_new=true
MSG=$(printf '{"checked":%s,"fleet_telemetry":{"latest":"%s","update":%s},"mosquitto":{"latest":"%s","update":%s}}' \
  "$(date +%s)" "$FT" "$ft_new" "$MQ" "$mq_new")
logger -t ft-update-check "$MSG"
PASS=$(cat /etc/fleet-telemetry/ops.pass)
docker exec ft-mosquitto mosquitto_pub -h 172.30.41.3 -p 1883 -u ops -P "$PASS" -r -q 1 \
  -t ops/fleet-telemetry/update -m "$MSG"
