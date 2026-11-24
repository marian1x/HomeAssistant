"""Fleet Telemetry consumer: MQTT (Pi5 broker) -> journal points, stream health, cost budget.

No polling and no wake-up: the car pushes data while it is awake. The only Fleet API calls made
here are the ones the owner/admin asks for (push a signed config, read its status) and, once,
removing the config when the cost budget would be exceeded. They go through the existing
tesla_custom connection and the local signing proxy; tokens never leave HA.
"""
import asyncio
import json
import logging
import time

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util
from datetime import timedelta

from .quota import at_home, counters
from .telemetry import LIVE_SECONDS, Assembler, Budget, RateGate, charging, parse

_LOGGER = logging.getLogger(__name__)
TOPIC = 'tesla'
NOTIFY_ID = 'home_energy_policy_fleet_telemetry'


class Fleet:
    def __init__(self, hass, manager):
        self.hass, self.manager = hass, manager
        self.assembler = Assembler()
        self.gate = RateGate()
        self.budget = Budget()
        self.unsub = []
        self.flush_handle = None
        self.vin = None
        self.last_msg = 0.0
        self.connection = None  # last connectivity event from the server
        self.errors = []
        self.update = None
        self.status = 'Neconfigurat'
        self.mqtt = False
        self.stopping = False
        self.charge_state = None
        self.meta = {}

    # ---- lifecycle -------------------------------------------------------------------------
    async def start(self, saved=None):
        self.budget = Budget((saved or {}).get('budget'))
        self.meta = (saved or {}).get('meta', {})
        self.unsub.append(async_track_time_interval(self.hass, self.housekeeping, timedelta(seconds=60)))
        if 'mqtt' not in self.hass.config.components and not self.hass.config_entries.async_entries('mqtt'):
            self.status = 'MQTT neconfigurat in HA'
            return
        from homeassistant.components import mqtt
        try:
            if not await mqtt.async_wait_for_mqtt_client(self.hass):
                self.status = 'Brokerul MQTT nu este disponibil'
                return
            for topic, handler in ((f'{TOPIC}/+/v/+', self.on_field), (f'{TOPIC}/+/connectivity', self.on_connectivity),
                                   (f'{TOPIC}/+/errors/+', self.on_error), ('ops/fleet-telemetry/update', self.on_update)):
                self.unsub.append(await mqtt.async_subscribe(self.hass, topic, handler, qos=1))
        except Exception as error:  # telemetry never blocks the policy or the journal
            self.status = 'Abonare MQTT esuata: ' + type(error).__name__
            return
        self.mqtt = True
        self.status = 'Asteapta date de la masina'

    async def stop(self):
        for unsub in self.unsub:
            unsub()
        self.unsub = []
        if self.flush_handle:
            self.flush_handle()
            self.flush_handle = None

    def saved(self):
        return {'budget': self.budget.state, 'meta': self.meta}

    # ---- car identity ------------------------------------------------------------------------
    def _tesla(self):
        for entry in self.hass.config_entries.async_entries('tesla_custom'):
            data = self.hass.data.get('tesla_custom', {}).get(entry.entry_id)
            if data and len(data.get('cars', {})) == 1:
                return data
        return None

    def car_vin(self):
        if self.vin is None:
            data = self._tesla()
            if data:
                self.vin = next(iter(data['cars']))
        return self.vin

    def _ours(self, topic):
        parts = topic.split('/')
        return len(parts) >= 3 and parts[0] == TOPIC and parts[1] == self.car_vin()

    # ---- MQTT handlers -----------------------------------------------------------------------
    @callback
    def on_field(self, msg):
        now = time.time()
        if not self.gate.allow(now) or not self._ours(msg.topic):
            return
        self.budget.count(now)
        self.last_msg = now
        parsed = parse(msg.topic.rsplit('/', 1)[-1], msg.payload)
        if parsed is None:
            return
        self.assembler.add(parsed[0], parsed[1], now)
        if self.flush_handle is None:
            self.flush_handle = async_call_later(self.hass, 1.0, self._flush)

    @callback
    def _flush(self, _now=None):
        self.flush_handle = None
        point = self.assembler.flush(time.time())
        journal = self.manager.journal
        if point is None or journal is None:
            return
        state, cfg = point.pop('charge_state'), self.manager.config
        point['charging'], point['plugged'] = charging(state)
        dc, ac = point.pop('dc_kw'), point.pop('ac_kw')
        point['power'] = dc if dc else ac
        zone = self.manager.state(cfg['ev_home_zone'])
        point['home'] = bool(zone and point.get('lat') is not None and at_home({'latitude': point['lat'], 'longitude': point['lon']}, zone.attributes))
        point['nocharge'] = True  # charges stay on the integration snapshots (energy-added counter)
        self.charge_state = state
        journal.telemetry_point(point)

    @callback
    def on_connectivity(self, msg):
        if not self._ours(msg.topic):
            return
        try:
            data = json.loads(msg.payload)
            self.connection = {'status': str(data.get('Status', ''))[:20], 'at': time.time()}
        except (ValueError, AttributeError):
            pass

    @callback
    def on_error(self, msg):
        if not self._ours(msg.topic):
            return
        try:
            data = json.loads(msg.payload)
            item = {'name': str(data.get('Name', ''))[:60], 'body': str(data.get('Body', ''))[:200], 'at': time.time()}
        except (ValueError, AttributeError):
            return
        self.errors = (self.errors + [item])[-5:]

    @callback
    def on_update(self, msg):
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        self.update = data
        pending = [f"{name} {info.get('latest')}" for name, info in data.items()
                   if isinstance(info, dict) and info.get('update')]
        key = ','.join(pending)
        if pending and self.meta.get('update_notified') != key:
            self.meta['update_notified'] = key
            self._notify('Actualizare Fleet Telemetry disponibila',
                         'Versiuni noi pe Pi5: ' + ', '.join(pending) + '. Se aplica manual dupa verificarea notelor de lansare '
                         '(`sudo /opt/fleet-telemetry/ft-update-apply.sh`). Vezi FLEET-TELEMETRY.md.')

    # ---- health --------------------------------------------------------------------------------
    def live(self, now=None):
        now = now or time.time()
        disconnected = self.connection and self.connection['status'] == 'DISCONNECTED' and self.connection['at'] >= self.last_msg
        return bool(self.mqtt and not disconnected and now - self.last_msg < LIVE_SECONDS)

    def gear(self):
        return self.assembler.known.get('shift') if self.live() else None

    def quota(self):
        c = self.manager.config
        q = counters(self.manager.memory.setdefault('tesla_quota', {}), dt_util.now())
        return {'reads_month': q.get('reads_month', 0), 'commands_month': q.get('commands_month', 0),
                'reads_cap': c['ev_reads_monthly'], 'commands_cap': c['ev_commands_monthly']}

    def snapshot(self):
        now = time.time()
        costs = self.budget.costs(now, **self.quota())
        b = self.budget.state
        return {'live': self.live(now), 'status': self.status, 'last_message': self.last_msg or None,
                'connection': self.connection, 'signals_day': b.get('signals_day', 0), 'signals_month': b.get('signals_month', 0),
                'signals_total': b.get('signals_total', 0), 'since': b.get('since'), 'costs': costs,
                'stopped': self.meta.get('stopped'), 'config_exp': self.meta.get('config_exp'),
                'pushed_at': self.meta.get('pushed_at'), 'errors': self.errors[-3:], 'update': self.update,
                'dropped': self.gate.dropped}

    async def housekeeping(self, _now=None):
        now = time.time()
        if self.mqtt:
            self.status = 'Activa' if self.live(now) else ('Oprita (buget)' if self.meta.get('stopped') else 'Masina adormita sau fara conexiune')
        reason = '' if self.meta.get('stopped') or not self.meta.get('pushed_at') else self.budget.over(now, **self.quota())
        if reason and not self.stopping:
            await self.stop_stream(reason)
        exp = self.meta.get('config_exp')
        if exp and not self.meta.get('stopped') and exp - now < 30 * 86400 and self.meta.get('exp_notified') != exp:
            self.meta['exp_notified'] = exp
            self._notify('Configul Fleet Telemetry expira curand',
                         'Configul semnat din masina expira la ' + dt_util.as_local(dt_util.utc_from_timestamp(exp)).strftime('%Y-%m-%d') +
                         '. Trebuie re-semnat si trimis din nou (FLEET-TELEMETRY.md, pasul Push).')
        journal = self.manager.journal
        if journal:
            await journal.save_telemetry(self.saved())

    def _notify(self, title, message):
        self.hass.async_create_task(self.hass.services.async_call(
            'persistent_notification', 'create', {'title': title, 'message': message, 'notification_id': NOTIFY_ID}))

    # ---- Fleet API (owner/admin actions; one budget stop) -------------------------------------
    async def _api(self, path, method='get', data=None):
        tesla = self._tesla()
        if not tesla:
            raise RuntimeError('Integrarea Tesla nu este pregatita')
        connection = tesla['controller']._Controller__connection
        self.budget.state['api_calls'] = self.budget.state.get('api_calls', 0) + 1
        try:
            async with asyncio.timeout(30):
                return await connection.post(path, method, data)
        finally:
            # Native refresh saves rotated tokens; with updates disabled it issues no vehicle poll.
            vin = self.car_vin()
            if vin and vin in tesla.get('coordinators', {}):
                await tesla['coordinators'][vin].async_refresh()

    async def remote_status(self):
        vin = self.car_vin()
        config = await self._api(f'vehicles/{vin}/fleet_telemetry_config')
        errors = await self._api(f'vehicles/{vin}/fleet_telemetry_errors')
        resp = (config or {}).get('response') or {}
        cfg = resp.get('config') or {}
        return {'synced': resp.get('synced'), 'key_paired': resp.get('key_paired'), 'limit_reached': resp.get('limit_reached'),
                'hostname': cfg.get('hostname'), 'port': cfg.get('port'), 'exp': cfg.get('exp'), 'fields': sorted((cfg.get('fields') or {}).keys()),
                'errors': [{k: str(e.get(k))[:200] for k in ('name', 'error', 'created_at')} for e in ((errors or {}).get('response') or {}).get('fleet_telemetry_errors', [])[:10]]}

    async def push(self, token, exp):
        """Send a config already signed (tesla-jws, 'TelemetryClient') in the proxy add-on."""
        vin = self.car_vin()
        result = await self._api('vehicles/fleet_telemetry_config_jws', 'post', {'vins': [vin], 'token': token})
        resp = (result or {}).get('response') or {}
        updated = resp.get('updated_vehicles')
        if updated:
            self.meta.update(pushed_at=time.time(), config_exp=int(exp) if exp else None, stopped=None)
            await self.manager.journal.save_telemetry(self.saved())
        return {'updated_vehicles': updated, 'skipped_vehicles': resp.get('skipped_vehicles')}

    async def stop_stream(self, reason):
        """Remove the car's telemetry config (one API call). Reads and commands for charging keep
        their budget; streaming is resumed only by a new signed push from the owner."""
        self.stopping = True
        try:
            vin = self.car_vin()
            await self._api(f'vehicles/{vin}/fleet_telemetry_config', 'delete')
            self.meta['stopped'] = {'reason': reason, 'at': time.time()}
            text = {'trial': 'costul estimat al primelor 2 saptamani a depasit $2',
                    'month': 'costul lunar estimat ar depasi bugetul de $10 (rezerva pentru incarcare si citiri pastrata)',
                    'owner': 'oprire ceruta de administrator'}.get(reason, reason)
            self._notify('Fleet Telemetry oprit', 'Streamingul a fost oprit: ' + text + '. Citirile fara wake-up si comenzile '
                         'de incarcare continua normal. Repornirea cere un push nou (FLEET-TELEMETRY.md).')
            _LOGGER.warning('Fleet Telemetry stopped: %s', reason)
            if self.manager.journal:
                await self.manager.journal.save_telemetry(self.saved())
            return True
        except Exception as error:
            _LOGGER.error('Fleet Telemetry stop failed: %s', type(error).__name__)
            self.meta['stop_failed'] = {'reason': reason, 'at': time.time(), 'error': type(error).__name__}
            return False
        finally:
            # one attempt per hour at most
            async_call_later(self.hass, 3600, self._clear_stopping)

    @callback
    def _clear_stopping(self, _now=None):
        self.stopping = False
