"""Tesla drive/charge journal kept next to the policy, in its own SQLite file.

It only listens to states HA already has (no extra car requests). Every successful no-wake read
becomes one snapshot; during a home charge the house supply is sampled every 30 s to split the
energy into solar, battery and grid. Fleet Telemetry points (fleet.py, pushed by the car through the Pi5 broker) feed the same
`Sessions`; while that stream is live, drives come from it and the sparse snapshots only update
charges.
"""
import json
import logging
import sqlite3
import threading
import time
from datetime import timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .quota import at_home
from .triplog import Sessions, charge_cost, split

_LOGGER = logging.getLogger(__name__)
CAR = 'salavat_t3'
E = {
    'soc': f'sensor.{CAR}_battery', 'odo': f'sensor.{CAR}_odometer', 'shift': f'sensor.{CAR}_shift_state',
    'tracker': f'device_tracker.{CAR}_location_tracker', 'charging': f'binary_sensor.{CAR}_charging',
    'plugged': f'binary_sensor.{CAR}_charger', 'added': f'sensor.{CAR}_energy_added', 'power': f'sensor.{CAR}_charger_power',
    'outside': f'sensor.{CAR}_temperature_outside', 'read': f'sensor.{CAR}_data_last_update_time',
}
USABLE = 'input_number.tesla_drive_usable_battery_kwh'
SUPPLY = {'load': 'sensor.consum_total_curent', 'pv': 'sensor.productie_solara_curenta',
          'battery': 'sensor.deye_battery_power', 'grid': 'sensor.deye_grid_power'}
DB_NAME = 'home_energy_policy_tesla.db'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS drives (id INTEGER PRIMARY KEY, start REAL, end REAL, data TEXT);
CREATE TABLE IF NOT EXISTS charges (id INTEGER PRIMARY KEY, start REAL, end REAL, data TEXT, price_kwh REAL, note TEXT);
CREATE INDEX IF NOT EXISTS drives_start ON drives(start);
CREATE INDEX IF NOT EXISTS charges_start ON charges(start);
'''


class Journal:
    def __init__(self, hass, manager):
        self.hass, self.manager = hass, manager
        self.path = hass.config.path(DB_NAME)
        self.db = None
        self.io = threading.Lock()
        self.sessions = None
        self.unsub = []
        self.pending = None
        self.last_split = None
        self.fleet = None
        self.telemetry_saved = None

    # ---- storage (executor) ----------------------------------------------------------------
    def _open(self):
        db = sqlite3.connect(self.path, check_same_thread=False)
        db.executescript(SCHEMA)
        db.commit()
        row = db.execute("SELECT value FROM meta WHERE key='state'").fetchone()
        done = db.execute("SELECT value FROM meta WHERE key='backfilled'").fetchone()
        tele = db.execute("SELECT value FROM meta WHERE key='telemetry'").fetchone()
        self.telemetry_saved = json.loads(tele[0]) if tele else None
        return db, json.loads(row[0]) if row else None, bool(done)

    def _write_meta(self, key, value):
        with self.io:
            if self.db is None:
                return
            self.db.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (key, json.dumps(value)))
            self.db.commit()

    def _write(self, finished, state, backfilled=False):
        with self.io:
            for kind, item in finished:
                if kind == 'drive':
                    self.db.execute('INSERT INTO drives(start,end,data) VALUES(?,?,?)', (item['start'], item['end'], json.dumps(item)))
                else:
                    self.db.execute('INSERT INTO charges(start,end,data) VALUES(?,?,?)', (item['start'], item['end'], json.dumps(item)))
            self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('state',?)", (json.dumps(state),))
            if backfilled:
                self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('backfilled','1')")
            self.db.commit()

    def _query(self, since):
        with self.io:
            charges = [dict(json.loads(d), id=i, price_kwh=p, note=n) for i, d, p, n in
                       self.db.execute('SELECT id,data,price_kwh,note FROM charges WHERE start>=? ORDER BY start DESC LIMIT 2000', (since,))]
            drives = [dict(json.loads(d), id=i) for i, d in
                      self.db.execute('SELECT id,data FROM drives WHERE start>=? ORDER BY start DESC LIMIT 3000', (since,))]
        return charges, drives

    def _drive(self, drive_id):
        with self.io:
            row = self.db.execute('SELECT id,data FROM drives WHERE id=?', (drive_id,)).fetchone()
        return dict(json.loads(row[1]), id=row[0]) if row else None

    def _set_price(self, charge_id, price, note):
        with self.io:
            changed = self.db.execute('UPDATE charges SET price_kwh=?, note=? WHERE id=?', (price, note, charge_id)).rowcount
            self.db.commit()
        return changed

    # ---- lifecycle -----------------------------------------------------------------------------
    async def start(self):
        self.db, state, backfilled = await self.hass.async_add_executor_job(self._open)
        self.sessions = Sessions(state, self.usable())
        if not backfilled:
            try:
                await self.backfill()
            except Exception as error:  # never block the policy on history import
                _LOGGER.warning('Tesla journal backfill skipped: %s', type(error).__name__)
                await self.hass.async_add_executor_job(self._write, [], self.sessions.state, True)
        self.unsub.append(async_track_state_change_event(self.hass, list(E.values()), self.changed))
        self.unsub.append(async_track_time_interval(self.hass, self.sample, timedelta(seconds=30)))

    async def stop(self):
        for unsub in self.unsub:
            unsub()
        self.unsub = []
        if self.pending:
            self.pending()
        if self.db:
            await self.hass.async_add_executor_job(self._write, [], self.sessions.state)
            db, self.db = self.db, None
            await self.hass.async_add_executor_job(db.close)

    def usable(self):
        value = self.manager.number(USABLE)
        return value if value and 30 <= value <= 120 else 57.5

    # ---- live --------------------------------------------------------------------------------
    @callback
    def changed(self, _event):
        # One read updates many entities within a second: take one snapshot after it settles.
        if self.pending:
            self.pending()
        self.pending = async_call_later(self.hass, 3, self.snapshot_now)

    async def snapshot_now(self, _now=None):
        self.pending = None
        p = self.current()
        if self.fleet and self.fleet.live():
            p['nodrive'] = True  # the dense stream owns the drive; this read only updates charges
        self.feed([p])

    def telemetry_point(self, point):
        if self.sessions is not None:
            self.feed([point])

    async def save_telemetry(self, data):
        if self.db is not None:
            await self.hass.async_add_executor_job(self._write_meta, 'telemetry', json.loads(json.dumps(data)))

    def current(self):
        m = self.manager

        def on(key):
            s = m.state(E[key])
            return None if not s or s.state in ('unknown', 'unavailable') else s.state == 'on'
        tracker, zone = m.state(E['tracker']), m.state(m.config['ev_home_zone'])
        lat = lon = None
        if tracker and tracker.state not in ('unknown', 'unavailable'):
            lat, lon = tracker.attributes.get('latitude'), tracker.attributes.get('longitude')
        shift = m.state(E['shift'])
        return {'t': time.time(), 'soc': m.number(E['soc']), 'odo': m.number(E['odo']),
                'shift': shift.state if shift and shift.state not in ('unknown', 'unavailable') else None,
                'lat': lat, 'lon': lon, 'home': bool(tracker and zone and at_home(tracker.attributes, zone.attributes)),
                'charging': on('charging'), 'plugged': on('plugged'), 'added': m.number(E['added']),
                'power': m.number(E['power']), 'outside': m.number(E['outside'])}

    def feed(self, snapshots, backfilled=False):
        for p in snapshots:
            self.sessions.feed(p)
        finished, self.sessions.done = self.sessions.done, []
        rate = self.manager.rate()
        for kind, item in finished:
            if kind == 'charge':
                item['prices'] = {'import': rate['import_price'], 'export': rate['export_price']}
        # Executor job, not a task: async_create_task only accepts coroutines.
        self.hass.async_add_executor_job(self._write, finished, json.loads(json.dumps(self.sessions.state)), backfilled)

    async def sample(self, _now=None):
        c = self.sessions.state.get('charge') if self.sessions else None
        now = time.time()
        previous, self.last_split = self.last_split, now
        if not c or not c.get('home') or previous is None:
            return
        m = self.manager
        load, ev = m.kw(SUPPLY['load']), m.number(E['power'])
        if load is None or ev is None or load < ev * .8:
            return  # the car is not visibly drawing what its last reading says
        shares = split(load, ev, m.kw(SUPPLY['pv']), m.kw(SUPPLY['battery']), m.kw(SUPPLY['grid']))
        self.sessions.add_split(now - previous, shares)

    # ---- history import --------------------------------------------------------------------
    async def backfill(self):
        from homeassistant.components.recorder import get_instance, history
        end = dt_util.utcnow()
        start = end - timedelta(days=7)
        ids = list(E.values()) + [self.manager.config['ev_home_zone']]
        states = await get_instance(self.hass).async_add_executor_job(
            lambda: history.get_significant_states(self.hass, start, end, ids, significant_changes_only=False, include_start_time_state=True))
        events = sorted((s.last_updated.timestamp(), eid, s) for eid, rows in states.items() for s in rows)
        zone = None
        latest, snapshots, group_t = {}, [], None
        for t, eid, s in events:
            if eid == self.manager.config['ev_home_zone']:
                zone = s.attributes
                continue
            if group_t is not None and t - group_t > 5:
                snapshots.append(self._snap(group_t, latest, zone))
            if group_t is None or t - group_t > 5:
                group_t = t
            latest[eid] = s
        if group_t is not None:
            snapshots.append(self._snap(group_t, latest, zone))
        self.feed(snapshots, backfilled=True)
        _LOGGER.info('Tesla journal imported %d snapshots from the last 7 days', len(snapshots))

    def _snap(self, t, latest, zone):
        def value(key, number=True):
            s = latest.get(E[key])
            if not s or s.state in ('unknown', 'unavailable'):
                return None
            if not number:
                return s.state
            try:
                return float(s.state)
            except ValueError:
                return None
        tracker = latest.get(E['tracker'])
        ok = tracker and tracker.state not in ('unknown', 'unavailable')
        on = lambda key: None if value(key, False) is None else value(key, False) == 'on'
        return {'t': t, 'soc': value('soc'), 'odo': value('odo'), 'shift': value('shift', False),
                'lat': tracker.attributes.get('latitude') if ok else None, 'lon': tracker.attributes.get('longitude') if ok else None,
                'home': bool(ok and zone and at_home(tracker.attributes, zone)), 'charging': on('charging'), 'plugged': on('plugged'),
                'added': value('added'), 'power': value('power'), 'outside': value('outside')}

    # ---- API ---------------------------------------------------------------------------------
    async def listing(self, days):
        charges, drives = await self.hass.async_add_executor_job(self._query, time.time() - days * 86400)
        rate = self.manager.rate()
        now_prices = {'import': rate['import_price'], 'export': rate['export_price']}
        for c in charges:
            c['cost'] = charge_cost(c, c.get('prices') or now_prices)
        priced = [c for c in charges if c['cost'] is not None and c['end'] >= time.time() - 60 * 86400]
        kwh = sum(c['kwh'] for c in priced)
        per_kwh = sum(c['cost'] for c in priced) / kwh if kwh > 0 else now_prices['import']
        for d in drives:
            d['cost'] = round(d['kwh'] * per_kwh, 2) if d.get('kwh') is not None else None
            points = d.pop('points', [])
            step = max(1, len(points) // 60)
            path = [p[1:3] for p in points[::step]]
            if points and (not path or path[-1] != points[-1][1:3]):
                path.append(points[-1][1:3])
            d['path'] = path
        state = self.sessions.state if self.sessions else {}
        active = {k: {x: v for x, v in (state.get(k) or {}).items() if x != 'points'} or None for k in ('drive', 'charge')}
        telemetry = self.fleet.snapshot() if self.fleet else None
        if active['drive'] and telemetry and telemetry['live']:
            # live position of a drive in progress (the page shows it only to the control role)
            pts = (state.get('drive') or {}).get('points') or []
            active['drive']['trail'] = [p[1:3] for p in pts[-120:]]
            active['drive']['kmh'] = self.fleet.assembler.known.get('kmh')
        return {'charges': charges, 'drives': drives, 'active': active, 'cost_per_kwh': round(per_kwh, 3),
                'prices': now_prices, 'usable_kwh': self.usable(), 'days': days, 'telemetry': telemetry}

    async def drive(self, drive_id):
        return await self.hass.async_add_executor_job(self._drive, drive_id)

    async def set_price(self, charge_id, price, note):
        return await self.hass.async_add_executor_job(self._set_price, charge_id, price, note)
