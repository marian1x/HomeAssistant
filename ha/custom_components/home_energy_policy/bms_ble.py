"""Read-only BLE reader for the Easyway/ENW battery, running inside HA's Bluetooth stack.

It connects only to poll, then disconnects, so the phone app can still use Bluetooth between
polls (the module accepts one BLE connection at a time). It never writes a setting or firmware:
the only thing sent is the `read` request (cmd 05). All failures are swallowed so energy control
is never affected.
"""
import asyncio
import json
import logging
import sqlite3
import threading
import time

from homeassistant.components import bluetooth

from . import bms

_LOGGER = logging.getLogger(__name__)

MAC = '74:E9:D8:E7:97:B5'
SERVICE_UUID = 'e31c42f9-dd47-45bf-81eb-2b735d613659'
NOTIFY_UUID = 'e31c42f9-dd47-45bf-81eb-2b735d61365a'
WRITE_UUID = 'e31c42f9-dd47-45bf-81eb-2b735d61365b'
KNOWN_PACK = '00EY3126040204140150-P'
KNOWN_CTRL = '00EY3126040204140150'
DB_NAME = 'home_energy_policy_bms.db'
POLL_SECONDS = 180
FAIL_BACKOFF = 600
RESPONSE_TIMEOUT = 8
SCHEMA = '''
CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, data TEXT);
CREATE INDEX IF NOT EXISTS samples_ts ON samples(ts);
'''


class BleReader:
    def __init__(self, hass, manager):
        self.hass, self.manager = hass, manager
        self.path = hass.config.path(DB_NAME)
        self.db = None
        self.io = threading.Lock()
        self.latest = None
        self.status = 'Initializare'
        self.available = False
        self.next_poll = 0.0
        self._task = None
        self._stop = asyncio.Event()

    async def start(self):
        self.db = await self.hass.async_add_executor_job(self._open)
        self._task = self.hass.async_create_background_task(self._loop(), 'bms_ble_poll')

    def _open(self):
        db = sqlite3.connect(self.path, check_same_thread=False)
        db.executescript(SCHEMA)
        db.commit()
        return db

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self.db:
            db, self.db = self.db, None
            await self.hass.async_add_executor_job(db.close)

    async def _loop(self):
        await asyncio.sleep(20)  # let HA's bluetooth scanner settle after start
        while not self._stop.is_set():
            interval = POLL_SECONDS
            try:
                if time.time() >= self.next_poll:
                    await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.status = 'Eroare: ' + type(error).__name__
                self.next_poll = time.time() + FAIL_BACKOFF
                interval = FAIL_BACKOFF
                _LOGGER.debug('BMS BLE poll failed: %s', type(error).__name__)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=min(interval, POLL_SECONDS))
            except asyncio.TimeoutError:
                pass

    async def _poll(self):
        device = bluetooth.async_ble_device_from_address(self.hass, MAC, connectable=True)
        if device is None:
            self.available = False
            self.status = 'Bateria nu este in raza Bluetooth sau e ocupata de aplicatie'
            self.next_poll = time.time() + POLL_SECONDS
            return
        from bleak_retry_connector import establish_connection, BleakClientWithServiceCache
        stream = bms.Stream()
        frames = []
        event = asyncio.Event()

        def on_notify(_char, data):
            for frame in stream.feed(bytes(data)):
                frames.append(frame)
            event.set()

        client = await establish_connection(BleakClientWithServiceCache, device, 'battery-bms', max_attempts=3)
        try:
            await client.start_notify(NOTIFY_UUID, on_notify)
            devices = await self._list(client, frames, event)
            pack_sn = next((d for d in devices if d.endswith('-P')), KNOWN_PACK)
            ctrl_sn = next((d for d in devices if not d.endswith('-P')), KNOWN_CTRL)
            pack = await self._read(client, frames, event, pack_sn)
            ctrl = await self._read(client, frames, event, ctrl_sn)
        finally:
            try:
                await client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass
            await client.disconnect()
        if not pack:
            self.status = 'Conectat, dar fara raspuns valid'
            self.next_poll = time.time() + POLL_SECONDS
            return
        reading = self._compose(pack, ctrl)
        self.latest = reading
        self.available = True
        self.status = 'Citire reusita'
        self.next_poll = time.time() + POLL_SECONDS
        await self.hass.async_add_executor_job(self._store, reading)

    async def _exchange(self, client, frames, event, request, want):
        """Write a request, then wait for a frame that parses to the expected device."""
        seen = len(frames)
        await client.write_gatt_char(WRITE_UUID, request, response=True)
        deadline = time.time() + RESPONSE_TIMEOUT
        while time.time() < deadline:
            try:
                await asyncio.wait_for(event.wait(), timeout=deadline - time.time())
            except asyncio.TimeoutError:
                break
            event.clear()
            for frame in frames[seen:]:
                dev = bms.parse_device(frame)
                if dev and (want is None or dev['serial'] == want):
                    return dev
            seen = len(frames)
        return None

    async def _list(self, client, frames, event):
        self._seq = getattr(self, '_seq', 0) + 1
        await self._exchange(client, frames, event, bms.build_request(self._seq, bms.CMD_LIST), None)
        return [bms.parse_device(f)['serial'] for f in frames if bms.parse_device(f)]

    async def _read(self, client, frames, event, serial):
        self._seq = getattr(self, '_seq', 0) + 1
        return await self._exchange(client, frames, event, bms.build_request(self._seq, bms.CMD_READ, serial), serial)

    def _compose(self, pack, ctrl):
        reading = {'ts': time.time(), 'pack': bms.pack_reading(pack['fields']), 'pack_serial': pack['serial']}
        if ctrl:
            c = bms.controller_reading(ctrl['fields'])
            reading['controller'] = c
            reading['controller_serial'] = ctrl['serial']
            temps = reading['pack'].get('cell_temps') or []
            cell_t = min(temps) if temps else reading['pack'].get('mos_temp')
            reading['heater_phase'] = bms.heater_phase(cell_t)
        return reading

    def _store(self, reading):
        p = reading['pack']
        row = {'ts': reading['ts'], 'soc': p.get('soc'), 'current': p.get('current'), 'voltage': p.get('voltage'),
               'cell_min': p.get('cell_min'), 'cell_max': p.get('cell_max'), 'spread_mv': p.get('cell_spread_mv'),
               'temps': p.get('cell_temps'), 'heater_phase': reading.get('heater_phase')}
        with self.io:
            self.db.execute('INSERT OR REPLACE INTO samples(ts,data) VALUES(?,?)', (reading['ts'], json.dumps(row)))
            self.db.execute('DELETE FROM samples WHERE ts < ?', (time.time() - 14 * 86400,))
            self.db.commit()

    def _history(self, days):
        with self.io:
            rows = self.db.execute('SELECT data FROM samples WHERE ts >= ? ORDER BY ts', (time.time() - days * 86400,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    async def snapshot(self, days=2):
        history = await self.hass.async_add_executor_job(self._history, days) if self.db else []
        return {'available': self.available, 'status': self.status, 'latest': self.latest,
                'history': history, 'mac': MAC, 'poll_seconds': POLL_SECONDS}
