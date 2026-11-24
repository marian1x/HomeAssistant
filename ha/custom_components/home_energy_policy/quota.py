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
        memory.update(day=now.strftime('%Y-%m-%d'), reads_day=0, commands_day=0, emergency_day=0, steps_day=0)
    if memory.get('month') != now.strftime('%Y-%m'):
        memory.update(month=now.strftime('%Y-%m'), reads_month=0, commands_month=0, emergency_month=0)
    return memory


def command_allowed(c, q, emergency=False):
    if emergency:
        return q.get('emergency_day', 0) < 2 and q.get('emergency_month', 0) < 4
    return q.get('commands_day', 0) < c['ev_commands_daily'] - 2 and q.get('commands_month', 0) < c['ev_commands_monthly'] - 4


def read_allowed(c, q):
    return q.get('reads_day', 0) < c['ev_reads_daily'] and q.get('reads_month', 0) < c['ev_reads_monthly']


STEP_COOLDOWN = 600  # the 2-10 min baseline must hold only post-step samples before another step counts


def _median(values):
    values = sorted(values)
    n = len(values)
    return (values[n // 2] + values[(n - 1) // 2]) / 2


def load_step(samples, now, total_kw=3.0, phase_kw=.8):
    """+1 for a sustained, balanced three-phase rise (an EV charger starting), -1 for the
    matching drop, else 0. Samples are (timestamp, l1_kw, l2_kw, l3_kw). Single-phase
    appliances (boiler, oven, AC) do not move all three phases and are ignored."""
    recent = [s[1:] for s in samples if 0 <= now - s[0] <= 75]
    before = [s[1:] for s in samples if 120 <= now - s[0] <= 600]
    if len(recent) < 2 or len(before) < 3:
        return 0
    base = [_median(p) for p in zip(*before)]
    rise = [min(p) - b for p, b in zip(zip(*recent), base)]
    fall = [b - max(p) for p, b in zip(zip(*recent), base)]
    if sum(rise) >= total_kw and min(rise) >= phase_kw:
        return 1
    if sum(fall) >= total_kw and min(fall) >= phase_kw:
        return -1
    return 0


def ev_mode(online, shift, charging, plugged, home, located):
    """Last known car situation; every read refreshes the inputs."""
    if online and shift in ('D', 'R', 'N'):
        return 'driving'
    if charging:
        return 'charging'
    if plugged:
        return 'plugged'
    if home:
        return 'home'
    return 'away' if located else 'unknown'


def due(c, q, o, now, active=False):
    """Reason string when a no-wake read is due, else ''. Never wakes the car: a read of an
    asleep car is only the connectivity query. Driving/charging cars are awake anyway;
    idle cadences stay >= 30 min so a parked car can still fall asleep."""
    if not c['enabled'] or not c['ev_monitor_enabled'] or o.get('kill') or not read_allowed(c, q) or q.get('backoff_until', 0) > now.timestamp():
        return ''
    elapsed = now.timestamp() - q.get('last_poll', 0)
    if elapsed < c['ev_active_seconds']:
        return ''
    mode, step = o.get('ev_mode', 'unknown'), o.get('load_step', 0)
    if (c['ev_step_enabled'] and step and q.get('steps_day', 0) < c['ev_step_daily'] and elapsed >= 300
            and now.timestamp() - q.get('step_at', 0) >= STEP_COOLDOWN
            and (step > 0 and mode not in ('charging', 'driving') or step < 0 and mode == 'charging')):
        return 'step_up' if step > 0 else 'step_down'
    if mode == 'charging' and o.get('ev_limit_near'):
        return 'limit'
    # While Fleet Telemetry streams, the drive is already recorded point by point: the 10-minute
    # driving read would only cost API budget. Charging, limit and load-step reads stay.
    if mode == 'driving' and elapsed >= c['ev_driving_minutes'] * 60 and not o.get('telemetry_live'):
        return 'driving'
    if mode == 'charging' and not active and elapsed >= c['ev_charging_minutes'] * 60:
        return 'charging'
    if not o.get('sun_up'):
        hour, minute = map(int, c['ev_night_check_at'].split(':'))
        delta = (now.hour*60+now.minute - hour*60-minute) % 1440
        return 'night' if delta < 5 and q.get('night_day') != now.strftime('%Y-%m-%d') else ''
    solar = o.get('pv') is not None and o['pv'] >= c['solar_min_kw']
    if active and solar:
        return 'solar'
    if mode == 'plugged':
        return 'plugged' if elapsed >= c['ev_plugged_minutes'] * 60 else ''
    if mode == 'away':
        return 'away' if elapsed >= c['ev_away_minutes'] * 60 else ''
    if not solar:
        return ''
    relevant = o.get('export', 0) >= 1 and o.get('ev_home', False) and (o.get('ev_soc') or 0) < c['ev_target_soc']
    return 'idle' if elapsed >= (max(900, c['ev_active_seconds']) if relevant else c['ev_idle_minutes']*60) else ''
