"""Bounded scheduling of cache refreshes. No wake operation exists here."""
import math


def at_home(location, zone):
    try:
        lat, lon = float(location['latitude']), float(location['longitude'])
        zlat, zlon = float(zone['latitude']), float(zone['longitude'])
        radius = float(zone['radius'])
        if not all(math.isfinite(n) for n in (lat, lon, zlat, zlon, radius)) or not 0 < radius <= 1000:
            return False
        dlat, dlon = math.radians(lat-zlat), math.radians(lon-zlon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(zlat))*math.sin(dlon/2)**2
        return 6371000*2*math.asin(min(1, math.sqrt(a))) <= radius
    except (KeyError, TypeError, ValueError):
        return False


def counters(memory, now):
    if memory.get('day') != now.strftime('%Y-%m-%d'):
        memory.update(day=now.strftime('%Y-%m-%d'), reads_day=0, commands_day=0, emergency_day=0)
    if memory.get('month') != now.strftime('%Y-%m'):
        memory.update(month=now.strftime('%Y-%m'), reads_month=0, commands_month=0, emergency_month=0)
    return memory


def command_allowed(c, q, emergency=False):
    if emergency:
        return q.get('emergency_day', 0) < 2 and q.get('emergency_month', 0) < 4
    return q.get('commands_day', 0) < c['ev_commands_daily'] - 2 and q.get('commands_month', 0) < c['ev_commands_monthly'] - 4


def read_allowed(c, q):
    return q.get('reads_day', 0) < c['ev_reads_daily'] and q.get('reads_month', 0) < c['ev_reads_monthly']


def due(c, q, o, now, active=False):
    if not c['enabled'] or not c['ev_monitor_enabled'] or o.get('kill') or not read_allowed(c, q) or q.get('backoff_until', 0) > now.timestamp():
        return False
    elapsed = now.timestamp() - q.get('last_poll', 0)
    if elapsed < c['ev_active_seconds']:
        return False
    if not o.get('sun_up'):
        hour, minute = map(int, c['ev_night_check_at'].split(':'))
        delta = (now.hour*60+now.minute - hour*60-minute) % 1440
        return delta < 5 and q.get('night_day') != now.strftime('%Y-%m-%d')
    if o.get('pv') is None or o['pv'] < c['solar_min_kw']:
        return False
    if active:
        return True
    relevant = o.get('export', 0) >= 1 and o.get('ev_home', False) and (o.get('ev_soc') or 0) < c['ev_target_soc']
    return elapsed >= (max(900, c['ev_active_seconds']) if relevant else c['ev_idle_minutes']*60)
