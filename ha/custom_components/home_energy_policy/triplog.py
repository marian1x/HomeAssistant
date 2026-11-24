"""Drive and charge sessions from successive car snapshots. Pure logic, no HA imports.

A snapshot is a dict: t (epoch s), soc, odo (km), shift, lat, lon, home (bool), charging,
plugged, added (kWh, car counter for the current session), power (kW), outside (C).
Fleet Telemetry points add kmh (speed), energy (kWh remaining) and src='telemetry'.
Readings arrive sparsely (no-wake reads) or densely (Fleet Telemetry), so the logic only relies
on ordering, never on a fixed interval. While the stream is live, drives come from telemetry
(`nodrive` on the sparse snapshots) and charges from the integration snapshots (`nocharge` on
telemetry points), so the two sources never fight over one session.
"""
import math

MOVING = ('D', 'R', 'N')
SAME_PLACE_M = 150
DRIVE_KEYS = ('odo', 'shift', 'lat', 'lon', 'energy')
MAX_POINTS = 5000  # ~7 h at 5 s; longer drives keep every other point


def distance_m(a, b):
    try:
        lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (a['lat'], a['lon'], b['lat'], b['lon']))
    except (KeyError, TypeError, ValueError):
        return None
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def split(load, ev, pv, battery, grid):
    """Car share of the house supply in kW as (solar, battery, grid). The car is the marginal
    consumer: the rest of the house is served by solar first, the car gets what remains, and
    whatever solar does not cover comes from the battery and the grid in proportion."""
    load, ev = _num(load), _num(ev)
    if load is None or ev is None or ev <= 0 or load <= 0:
        return None
    ev = min(ev, load)
    discharge, imported = max(0, _num(battery) or 0), max(0, _num(grid) or 0)
    solar_to_load = max(0, load - discharge - imported)
    car_solar = max(0, min(ev, solar_to_load - (load - ev)))
    rest = ev - car_solar
    other = discharge + imported
    car_battery = rest * discharge / other if other > 0 else 0
    return car_solar, car_battery, rest - car_battery


class Sessions:
    """Feed snapshots in time order; collects finished drives and charges in `done`."""

    def __init__(self, state=None, usable_kwh=57.5):
        self.state = state or {'drive': None, 'charge': None, 'last': None}
        self.usable = usable_kwh
        self.done = []

    def feed(self, p):
        last = self.state.get('last')
        if last and p['t'] < last['t']:
            return
        if not p.get('nodrive'):
            self._drive(p, last)
        if not p.get('nocharge'):
            self._charge(p)
        keep = {k: p.get(k) for k in ('t', 'soc', 'odo', 'shift', 'lat', 'lon', 'home', 'outside', 'energy', 'src')}
        if last:  # a reading without a field keeps the previous value
            for k, v in keep.items():
                if v is None or (p.get('nodrive') and k in DRIVE_KEYS):
                    keep[k] = last.get(k)
        self.state['last'] = keep

    # ---- drives -------------------------------------------------------------------------------
    def _drive(self, p, last):
        d = self.state.get('drive')
        odo, prev_odo = _num(p.get('odo')), _num((last or {}).get('odo'))
        moved = odo is not None and prev_odo is not None and odo - prev_odo >= .05
        moving = p.get('shift') in MOVING
        dense = p.get('src') == 'telemetry'
        if d is None:
            if not (moving or moved):
                return
            origin = last if last and (moved or p['t'] - last['t'] <= 1800) else p
            # A dense stream sees the moment the car leaves P: the start is this point, the
            # values (odometer, battery, place) are the ones the car had while parked.
            start = p['t'] if dense else origin['t']
            d = self.state['drive'] = {
                'start': start, 'approx_start': p['t'] - start > 180,
                'start_soc': origin.get('soc'), 'start_odo': origin.get('odo') if origin.get('odo') is not None else odo,
                'start_lat': origin.get('lat'), 'start_lon': origin.get('lon'), 'start_home': origin.get('home'),
                'start_energy': origin.get('energy') if origin.get('energy') is not None else p.get('energy'),
                'points': [], 'temps': [], 'still': 0, 'dense': 0, 'max_kmh': None}
            if origin is last and last.get('lat') is not None:
                d['points'].append([start if dense else last['t'], last['lat'], last['lon']])
        kmh = _num(p.get('kmh'))
        if dense:
            d['dense'] = d.get('dense', 0) + 1
        if kmh is not None:
            d['max_kmh'] = max(d.get('max_kmh') or 0, kmh)
        if p.get('lat') is not None and p.get('lon') is not None:
            if not d['points'] or d['points'][-1][1:3] != [p['lat'], p['lon']]:
                d['points'].append([p['t'], p['lat'], p['lon']] + ([kmh] if kmh is not None else []))
                if len(d['points']) > MAX_POINTS:
                    d['points'] = d['points'][:1] + d['points'][1:-1:2] + d['points'][-1:]
        if _num(p.get('outside')) is not None:
            d['temps'].append(p['outside'])
        if odo is not None:
            d['end_odo'] = odo
        if p.get('soc') is not None:
            d['end_soc'] = p['soc']
        if _num(p.get('energy')) is not None:
            d['end_energy'] = p['energy']
            if d.get('start_energy') is None:
                d['start_energy'] = p['energy']
        d.update(end=p['t'], end_lat=p.get('lat', d.get('end_lat')), end_lon=p.get('lon', d.get('end_lon')), end_home=p.get('home'))
        d['still'] = 0 if moving or moved else d['still'] + 1
        parked = p.get('shift') == 'P' or (p.get('shift') is None and d['still'] >= 2)
        if parked and not moving:
            self._close_drive()

    def _close_drive(self):
        d = self.state['drive']
        self.state['drive'] = None
        km = (d.get('end_odo') or 0) - (d.get('start_odo') or 0) if d.get('end_odo') is not None and d.get('start_odo') is not None else None
        if km is None or km < .1:
            return
        soc0, soc1 = d.get('start_soc'), d.get('end_soc')
        e0, e1 = _num(d.get('start_energy')), _num(d.get('end_energy'))
        if e0 is not None and e1 is not None and e0 >= e1:
            kwh, basis = e0 - e1, 'energy'  # the pack's own energy counter, not SOC x capacity
        elif soc0 is not None and soc1 is not None and soc0 >= soc1:
            kwh, basis = (soc0 - soc1) / 100 * self.usable, 'soc'
        else:
            kwh, basis = None, None
        hours = max(0, d['end'] - d['start']) / 3600
        temps = d.pop('temps')
        d.pop('still', None)
        dense = d.pop('dense', 0)
        d.update(km=round(km, 2), kwh=round(kwh, 2) if kwh is not None else None, hours=round(hours, 3),
                 wh_km=round(kwh * 1000 / km) if kwh is not None and km > 0 else None,
                 avg_kmh=round(km / hours, 1) if hours > 0 else None,
                 outside=round(sum(temps) / len(temps), 1) if temps else None,
                 energy_basis=basis, source='telemetry' if dense >= 3 else 'reads',
                 max_kmh=round(d['max_kmh']) if d.get('max_kmh') is not None else None)
        self.done.append(('drive', d))

    # ---- charges ------------------------------------------------------------------------------
    def _charge(self, p):
        c = self.state.get('charge')
        charging = p.get('charging')
        if c is None:
            if not charging:
                return
            c = self.state['charge'] = {
                'start': p['t'], 'start_soc': p.get('soc'), 'lat': p.get('lat'), 'lon': p.get('lon'), 'home': bool(p.get('home')),
                'added': _num(p.get('added')) or 0, 'max_kw': 0, 'solar_kwh': 0, 'battery_kwh': 0, 'grid_kwh': 0, 'split_s': 0}
        if _num(p.get('added')) is not None:
            c['added'] = max(c['added'], p['added']) if p['added'] >= c['added'] - .5 else c['added'] + p['added']
        if _num(p.get('power')) is not None:
            c['max_kw'] = max(c['max_kw'], p['power'])
        if p.get('soc') is not None:
            c['end_soc'] = p['soc']
        c['end'] = p['t']
        if charging is False or p.get('plugged') is False:
            self._close_charge()

    def add_split(self, seconds, shares):
        """Accumulate the car's share of the house supply for an active home charge."""
        c = self.state.get('charge')
        if not c or not c.get('home') or not shares or seconds <= 0 or seconds > 900:
            return
        h = seconds / 3600
        c['solar_kwh'] += shares[0] * h
        c['battery_kwh'] += shares[1] * h
        c['grid_kwh'] += shares[2] * h
        c['split_s'] += seconds

    def _close_charge(self):
        c = self.state['charge']
        self.state['charge'] = None
        if c['added'] < .1:
            return
        for key in ('solar_kwh', 'battery_kwh', 'grid_kwh'):
            c[key] = round(c[key], 3)
        c.update(kwh=round(c.pop('added'), 2), hours=round(max(0, c['end'] - c['start']) / 3600, 3), max_kw=round(c['max_kw'], 1))
        self.done.append(('charge', c))


def charge_cost(c, prices):
    """RON for a charge. Home: measured split priced at the tariff (solar at the export price it
    would otherwise earn, battery at that price over the round-trip efficiency). Away: the
    owner's price per kWh, if entered. Unmeasured home energy is priced as grid energy."""
    if c.get('price_kwh') is not None:
        return round(c['kwh'] * c['price_kwh'], 2)
    if not c.get('home'):
        return None
    # The house pays for AC energy (car battery energy plus charging losses). A split measured
    # over most of the session is scaled to the whole session; otherwise all of it is grid.
    duration = c.get('hours', 0) * 3600
    coverage = c.get('split_s', 0) / duration if duration > 0 else 0
    if coverage < .8:
        return round(c['kwh'] / prices.get('charging_efficiency', .9) * prices['import'], 2)
    return round((c['solar_kwh'] * prices['export'] + c['battery_kwh'] * prices['export'] / prices.get('efficiency', .9)
                  + c['grid_kwh'] * prices['import']) / min(1, coverage), 2)
