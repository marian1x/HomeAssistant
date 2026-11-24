"""Tesla Fleet Telemetry: parsing, point assembly, stream health and cost budget.

Pure logic, no HA imports. fleet-telemetry (Pi5) publishes one MQTT message per field,
`tesla/<VIN>/v/<Field>` with a JSON value; all fields of one vehicle record arrive together.
Every message is one streamed signal, which Tesla bills (150 000 signals / $1).
"""
import json
import math
import time

MILE_KM = 1.609344
PRICE = {'signal': 1 / 150000, 'data': 1 / 500, 'command': 1 / 1000}  # USD, developer.tesla.com
REQUESTS_PER_READ = 2   # a no-wake read is a vehicle list query plus, when online, a data query
MONTH_BUDGET = 10.0     # owner: everything stays inside Tesla's $10 monthly credit
TRIAL_DAYS = 14
TRIAL_BUDGET = 2.0      # owner: stop streaming if the first two weeks cost more than $2
SAFETY = 1.2            # local count vs. Tesla's ledger: decide on a pessimistic estimate
LIVE_SECONDS = 120
MERGE_SECONDS = 1.0
MAX_RATE = 40           # messages/s accepted; anything above is dropped (defensive)

# Pushed to the car. Fields are sent only when they change (minimum_delta) and at most every
# interval_seconds, so a parked car costs almost nothing.
FIELDS = {
    'Location': {'interval_seconds': 5},
    'VehicleSpeed': {'interval_seconds': 5, 'minimum_delta': 1},
    'Gear': {'interval_seconds': 1},
    'Odometer': {'interval_seconds': 30, 'minimum_delta': 0.1},
    'Soc': {'interval_seconds': 60, 'minimum_delta': 0.5},
    'EnergyRemaining': {'interval_seconds': 30, 'minimum_delta': 0.1},
    'OutsideTemp': {'interval_seconds': 300, 'minimum_delta': 0.5},
    'DetailedChargeState': {'interval_seconds': 1},
    'ACChargingPower': {'interval_seconds': 30, 'minimum_delta': 0.2},
    'DCChargingPower': {'interval_seconds': 30, 'minimum_delta': 1},
}


def config(hostname, port, ca, exp, fields=None):
    """Claims of the fleet_telemetry_config (signed with tesla-jws as 'TelemetryClient')."""
    return {'hostname': hostname, 'port': int(port), 'ca': ca, 'exp': int(exp), 'fields': fields or FIELDS}


def _number(v):
    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _enum(v, prefix):
    return v[len(prefix):] if isinstance(v, str) and v.startswith(prefix) else None


def parse(field, raw):
    """(key, value) for a field the journal uses, (key, None) for a known field without a valid
    value, None for anything else. Units are converted to km, km/h, kWh, kW, C."""
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
    except ValueError:
        return None
    if field == 'Location':
        if not isinstance(value, dict):
            return ('loc', None)
        lat, lon = _number(value.get('latitude')), _number(value.get('longitude'))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            return ('loc', None)
        return ('loc', (round(lat, 6), round(lon, 6)))
    if field == 'Gear':
        g = _enum(value, 'ShiftState')
        return ('shift', g if g in ('P', 'R', 'N', 'D') else None)
    if field == 'DetailedChargeState':
        return ('charge_state', _enum(value, 'DetailedChargeState'))
    n = _number(value)
    if field == 'VehicleSpeed':
        return ('kmh', round(n * MILE_KM, 1) if n is not None and 0 <= n < 200 else None)
    if field == 'Odometer':
        return ('odo', round(n * MILE_KM, 2) if n is not None and n >= 0 else None)
    if field == 'Soc':
        return ('soc', round(n, 1) if n is not None and 0 <= n <= 100 else None)
    if field == 'EnergyRemaining':
        return ('energy', round(n, 3) if n is not None and 0 <= n <= 150 else None)
    if field == 'OutsideTemp':
        return ('outside', round(n, 1) if n is not None and -60 <= n <= 70 else None)
    if field in ('ACChargingPower', 'DCChargingPower'):
        return ('ac_kw' if field[0] == 'A' else 'dc_kw', round(n, 2) if n is not None and 0 <= n <= 400 else None)
    return None


class Assembler:
    """Merges the fields of one vehicle record into a journal point and carries the last known
    values forward, so every point has gear, odometer and position (a point without a gear would
    look like a parked car to the session logic)."""
    CARRY = ('shift', 'odo', 'soc', 'energy', 'outside', 'lat', 'lon', 'kmh', 'charge_state', 'ac_kw', 'dc_kw')

    def __init__(self):
        self.known = {}
        self.pending = None
        self.first = None

    def add(self, key, value, t):
        if self.pending is None:
            self.pending, self.first = {}, t
        if key == 'loc':
            self.pending['lat'], self.pending['lon'] = value if value else (None, None)
        else:
            self.pending[key] = value

    def due(self, t):
        return self.pending is not None and t - self.first >= MERGE_SECONDS

    def flush(self, t):
        """The merged point, or None when nothing new arrived."""
        if self.pending is None:
            return None
        fresh, self.pending = self.pending, None
        for k, v in fresh.items():
            if v is not None:
                self.known[k] = v
            elif k in ('lat', 'lon', 'shift'):
                self.known.pop(k, None)  # an invalid gear/position must not be carried forward
        point = {k: self.known.get(k) for k in self.CARRY}
        point.update(t=self.first if self.first is not None else t, src='telemetry')
        return point


def charging(state):
    """DetailedChargeState -> (charging, plugged) as the journal understands them."""
    if state is None or state == 'Unknown':
        return None, None
    return state in ('Starting', 'Charging'), state != 'Disconnected'


class Budget:
    """Signals counted locally, priced with Tesla's rates, decisions against the owner's budget.
    State is a plain dict persisted by the journal."""

    def __init__(self, state=None):
        self.state = state or {}

    def count(self, now, n=1):
        s = self.state
        month = time.strftime('%Y-%m', time.localtime(now))
        day = time.strftime('%Y-%m-%d', time.localtime(now))
        if s.get('month') != month:
            s.update(month=month, signals_month=0)
        if s.get('day') != day:
            s.update(day=day, signals_day=0)
        s.setdefault('since', now)
        s['signals_total'] = s.get('signals_total', 0) + n
        s['signals_month'] = s.get('signals_month', 0) + n
        s['signals_day'] = s.get('signals_day', 0) + n

    def costs(self, now, reads_month=0, commands_month=0, reads_cap=900, commands_cap=900):
        s = self.state
        month = time.strftime('%Y-%m', time.localtime(now))
        signals_month = s.get('signals_month', 0) if s.get('month') == month else 0
        stream_month = signals_month * PRICE['signal'] * SAFETY
        api_month = reads_month * REQUESTS_PER_READ * PRICE['data'] + commands_month * PRICE['command']
        reserve = (max(0, reads_cap - reads_month) * REQUESTS_PER_READ * PRICE['data']
                   + max(0, commands_cap - commands_month) * PRICE['command'])
        since = s.get('since')
        trial = since is not None and now - since <= TRIAL_DAYS * 86400
        return {'stream_month_usd': round(stream_month, 3), 'api_month_usd': round(api_month, 3),
                'api_reserve_usd': round(reserve, 3), 'stream_total_usd': round(s.get('signals_total', 0) * PRICE['signal'] * SAFETY, 3),
                'trial': trial, 'stream_allowed_usd': round(max(0, MONTH_BUDGET - api_month - reserve), 3)}

    def over(self, now, **quota):
        """Reason to stop streaming, else ''. The reads/commands of the charging logic keep their
        full monthly allowance: streaming only gets what is left of the $10 after that reserve."""
        c = self.costs(now, **quota)
        if c['trial'] and c['stream_total_usd'] > TRIAL_BUDGET:
            return 'trial'
        if c['stream_month_usd'] + c['api_month_usd'] + c['api_reserve_usd'] > MONTH_BUDGET:
            return 'month'
        return ''


class RateGate:
    """Drops messages above MAX_RATE per second (a broken or hostile publisher cannot flood HA)."""

    def __init__(self):
        self.second, self.n, self.dropped = 0, 0, 0

    def allow(self, now):
        s = int(now)
        if s != self.second:
            self.second, self.n = s, 0
        self.n += 1
        if self.n > MAX_RATE:
            self.dropped += 1
            return False
        return True
