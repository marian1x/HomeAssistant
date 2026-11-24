#!/bin/sh
# Fleet Telemetry firewall (Pi5). Idempotent; run by ft-firewall.service after Docker starts.
# Published Docker ports bypass ufw, so everything about the telemetry containers is decided here,
# in a chain jumped to from DOCKER-USER. Exposure mode: /etc/fleet-telemetry/exposure
#   lan    -> 4443 accepted only from 192.168.50.0/24 (testing)
#   public -> 4443 accepted from anywhere, with per-IP limits (the vehicle uses mobile IPs)
set -eu
IPT=/usr/sbin/iptables
CHAIN=FT-FILTER
LAN=192.168.50.0/24
HA=192.168.50.107
MODE=$(cat /etc/fleet-telemetry/exposure 2>/dev/null || echo lan)

$IPT -N $CHAIN 2>/dev/null || true
$IPT -F $CHAIN

# Replies to connections that were already accepted.
$IPT -A $CHAIN -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

# The containers never open connections out of their own networks (no LAN, no internet).
$IPT -A $CHAIN -i ft-edge -j DROP
$IPT -A $CHAIN -i ft-lan -j DROP
$IPT -A $CHAIN -i ft-bus ! -o ft-bus -j DROP

# 4443 -> fleet-telemetry: TCP only, new connections limited per source IP and overall.
if [ "$MODE" != public ]; then
  $IPT -A $CHAIN -o ft-edge -p tcp --dport 4443 ! -s $LAN -j DROP
fi
$IPT -A $CHAIN -o ft-edge -p tcp --dport 4443 --syn -m connlimit --connlimit-above 4 --connlimit-mask 32 -j DROP
$IPT -A $CHAIN -o ft-edge -p tcp --dport 4443 --syn -m connlimit --connlimit-above 64 --connlimit-mask 0 -j DROP
$IPT -A $CHAIN -o ft-edge -p tcp --dport 4443 --syn -m hashlimit --hashlimit-above 10/minute --hashlimit-burst 10 \
     --hashlimit-mode srcip --hashlimit-name ft4443 --hashlimit-htable-expire 600000 -j DROP
$IPT -A $CHAIN -o ft-edge -p tcp --dport 4443 -d 172.30.40.2 -j RETURN
$IPT -A $CHAIN -o ft-edge -j DROP

# 8883 -> mosquitto: only Home Assistant.
$IPT -A $CHAIN -o ft-lan -p tcp --dport 8883 -s $HA -d 172.30.42.2 -j RETURN
$IPT -A $CHAIN -o ft-lan -j DROP

# Nothing from outside reaches the internal bus.
$IPT -A $CHAIN -o ft-bus ! -i ft-bus -j DROP

# Hook into DOCKER-USER exactly once, at the top (fail2ban may insert its own jump above).
$IPT -N DOCKER-USER 2>/dev/null || true
while $IPT -D DOCKER-USER -j $CHAIN 2>/dev/null; do :; done
$IPT -I DOCKER-USER 1 -j $CHAIN
echo "ft-firewall: mode=$MODE"
