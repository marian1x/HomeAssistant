"""Persistent ownership, bounded native service calls, and local telemetry only."""
import asyncio
from datetime import timedelta
import logging
import math
import time
import json
from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from .const import DOMAIN, KILL, LEGACY, DEVICES
from .schema import DEFAULTS, FIELDS, validate
from .model import next_resume, plan, winter
from .quota import at_home, counters, command_allowed, read_allowed
from .tesla import refresh as refresh_tesla
from . import pricing

_LOGGER = logging.getLogger(__name__)
SOURCE = {
    'pv': 'sensor.productie_solara_curenta', 'load': 'sensor.consum_total_curent',
    'grid': 'sensor.deye_grid_power', 'battery': 'sensor.deye_battery_power',
    'soc': 'sensor.deye_battery', 'outside': 'weather.forecast_home',
    'forecast': 'sensor.prognoza_solar_energy_production_today_remaining',
}


class Policy:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.store = Store(hass, 1, DOMAIN)
        self.config, self.revision, self.memory = dict(DEFAULTS), 0, {}
        self.status = {'phase': 'Initializare'}
        self.lock = asyncio.Lock()
        self.unsub = []
        self.last_tick = 0
        self.listener = None
        self.contexts = {}
        self.before = {}

    async def load(self):
        saved = await self.store.async_load() or {}
        self.config = validate(saved.get('config', {}))
        self.revision = saved.get('revision', 0)
        self.memory = saved.get('memory', {})
        self.memory.setdefault('devices', {})
        self.memory.setdefault('tariffs', pricing.initial(self.config))
        for key in DEVICES:
            self.memory['devices'].setdefault(key, {})

    async def save(self):
        payload = {'config': self.config, 'revision': self.revision, 'memory': self.memory}
        serialized = json.dumps(payload, sort_keys=True)
        if serialized != getattr(self, '_saved', None):
            await self.store.async_save(payload)
            self._saved = serialized

    def snapshot(self):
        config = dict(self.config)
        for key, entity in [('base_reserve_soc','input_number.deye_battery_min_soc'),('max_discharge_kw','input_number.deye_battery_max_discharge_kw')]:
            value = self.number(entity)
            if value is not None: config[key] = value
        return {'config': config, 'revision': self.revision, 'schema': FIELDS, 'status': self.status, 'tariffs': self.memory['tariffs'], 'active_tariff': self.rate()}

    def rate(self):
        return pricing.active(self.memory['tariffs'], dt_util.now().date().isoformat())

    def entity(self, key):
        return self.config[{'tesla': 'ev_switch', 'boiler': 'boiler_entity'}.get(key, key + '_entity')]

    def state(self, entity):
        return self.hass.states.get(entity) if entity else None

    def available(self, entity):
        s = self.state(entity)
        return s is not None and s.state not in ('unknown', 'unavailable')

    def number(self, entity, max_age=None, attribute=None):
        s = self.state(entity)
        if not s or max_age and time.time() - s.last_reported.timestamp() > max_age:
            return None
        try:
            n = float(s.attributes.get(attribute) if attribute else s.state)
        except (TypeError, ValueError):
            return None
        return n if math.isfinite(n) else None

    def kw(self, entity):
        n = self.number(entity)
        s = self.state(entity)
        if n is None or s.attributes.get('unit_of_measurement') not in ('W', 'kW'):
            return None
        return n / 1000 if s.attributes['unit_of_measurement'] == 'W' else n

    def fingerprint(self, key):
        s = self.state(self.entity(key))
        if not s:
            return {}
        if key == 'tesla':
            return {'state': s.state, 'amps': self.number(self.config['ev_amps']), 'limit': self.number(self.config['ev_limit'])}
        attrs = s.attributes
        fp = {'state': s.state, **{name: attrs.get(name) for name in ('temperature', 'fan_mode') if name in attrs}}
        if key == 'boiler':
            power = self.state(self.config['boiler_power'])
            fp['power'] = power.state if power else None
        return fp

    def until(self, key):
        stamp = self.memory['devices'][key].get('manual_until', 0)
        return stamp > time.time()

    async def hold(self, key, reason='Interventie manuala'):
        m = self.memory['devices'][key]
        m.update(manual_until=next_resume(dt_util.now(), self.config['manual_resume_at']).timestamp(), owned=False, reason=reason)
        m.pop('expected', None)
        await self.save()

    async def resume(self, key):
        async with self.lock:
            self.memory['devices'][key].update(manual_until=0, reason='', owned=False)
            await self.save()
        await self.tick(force=True)

    async def configure(self, values, revision):
        async with self.lock:
            if revision != self.revision:
                raise ValueError('Configuratia s-a schimbat. Reincarca pagina inainte de salvare.')
            config = validate(values, self.config)
            if any(config[k] != self.config[k] for k in ('energy_import_price', 'energy_export_price', 'energy_tariff_from')):
                tariffs = pricing.update(self.memory['tariffs'], config)
                if len(tariffs) > 500:
                    raise ValueError('Istoric tarife prea mare')
            else:
                tariffs = self.memory['tariffs']
            domains = {'tcl_entity': 'climate', 'whirlpool_entity': 'climate', 'boiler_entity': 'water_heater',
                       'boiler_power': 'switch', 'ev_switch': 'switch', 'ev_amps': 'number', 'ev_limit': 'number',
                       'ev_soc': 'sensor', 'ev_power': 'sensor', 'ev_voltage': 'sensor', 'ev_connected': 'binary_sensor', 'ev_charging': 'binary_sensor', 'ev_tracker': 'device_tracker', 'ev_home_zone': 'zone'}
            for field, domain in domains.items():
                entity = config[field]
                if entity and (not entity.startswith(domain + '.') or entity in ('climate.heat', 'climate.bedroom_heat') or 'deye' in entity.lower()):
                    raise ValueError('Asociere nepermisa: ' + field)
                registered = er.async_get(self.hass).async_get(entity) if entity else None
                if registered and field in ('tcl_entity', 'whirlpool_entity', 'boiler_power') and registered.platform in ('tesla_custom','tesla_fleet','solarman'):
                    raise ValueError('Un consumator al casei nu poate comanda masina sau invertorul')
                if registered and field in ('ev_switch','ev_amps','ev_limit') and registered.platform not in ('tesla_custom','tesla_fleet'):
                    raise ValueError('Comenzile Tesla trebuie asociate integrarii masinii')
            for key in ('tcl', 'whirlpool'):
                s = self.state(config[key + '_entity'])
                if s and s.state != 'unavailable':
                    prefix = ('tcl_fan1', 'tcl_fan2', 'tcl_fan3', 'tcl_fan_boost') if key == 'tcl' else ('whirlpool_low', 'whirlpool_medium', 'whirlpool_high')
                    if any(config[name] not in s.attributes.get('fan_modes', []) for name in prefix):
                        raise ValueError('Mod ventilator nesuportat de ' + key)
            changed_bindings = [key for key in DEVICES if self.entity(key) != config[{'tesla': 'ev_switch', 'boiler': 'boiler_entity'}.get(key, key + '_entity')]]
            for name, helper in [('base_reserve_soc', 'input_number.deye_battery_min_soc'), ('max_discharge_kw', 'input_number.deye_battery_max_discharge_kw')]:
                if name in values and self.available(helper) and self.number(helper) != config[name]:
                    await self.hass.services.async_call('input_number', 'set_value', {'entity_id': helper, 'value': config[name]}, blocking=True)
            self.config = config
            self.memory['tariffs'] = tariffs
            for key in changed_bindings:
                self.memory['devices'][key] = {}
                fp = self.fingerprint(key)
                self.before[key] = fp
                active = key != 'boiler' and fp.get('state') not in (None, 'off', 'unknown', 'unavailable')
                manual_boiler = key == 'boiler' and (fp.get('power') == 'off' or fp.get('temperature') not in (None, config['boiler_summer_c'], config['boiler_winter_c']))
                # A newly associated device may already be running from its own app.
                if active or manual_boiler:
                    self.memory['devices'][key].update(manual_until=next_resume(dt_util.now(), config['manual_resume_at']).timestamp(), owned=False, reason='Setari existente la asociere')
            self.revision += 1
            await self.save()
        await self.tick(force=True)

    async def start(self):
        if not self.hass.is_running:
            self.unsub.append(self.hass.bus.async_listen_once('homeassistant_started', self.started))
            return
        await self.started()

    async def started(self, _event=None):
        for key in DEVICES:
            fp = self.fingerprint(key)
            self.before[key] = fp
            m = self.memory['devices'][key]
            if m.get('owned') and m.get('fingerprint') != fp:
                await self.hold(key, 'Setari schimbate in timpul opririi HA')
            elif not m.get('owned') and not m.get('manual_until') and key != 'boiler' and fp.get('state') not in (None, 'off', 'unknown', 'unavailable'):
                await self.hold(key, 'Dispozitiv deja pornit manual')
            elif key == 'boiler' and not m.get('owned') and not m.get('manual_until') and (fp.get('power') == 'off' or fp.get('temperature') not in (None, self.config['boiler_summer_c'], self.config['boiler_winter_c'])):
                await self.hold(key, 'Temperatura existenta pastrata')
        self.unsub.append(self.hass.bus.async_listen('state_changed', self.on_state))
        self.unsub.append(self.hass.bus.async_listen('call_service', self.on_service))
        self.unsub.append(async_track_time_interval(self.hass, self.tick, timedelta(seconds=10)))
        await self.tick(force=True)

    async def stop(self):
        for unsub in self.unsub:
            unsub()
        await self.save()

    async def on_service(self, event):
        if not event.context.user_id or event.context.id in self.contexts:
            return
        data = event.data
        if data.get('domain') not in ('climate', 'water_heater', 'number', 'switch'):
            return
        entities = data.get('service_data', {}).get('entity_id', [])
        if isinstance(entities, str):
            entities = [entities]
        for key in DEVICES:
            ids = [self.entity(key)]
            if key == 'tesla':
                ids += [self.config['ev_amps'], self.config['ev_limit']]
            if key == 'boiler':
                ids += [self.config['boiler_power']]
            if set(ids).intersection(entities):
                await self.hold(key)

    async def on_state(self, event):
        entity = event.data.get('entity_id')
        for key in DEVICES:
            ids = [self.entity(key)]
            if key == 'tesla':
                ids += [self.config['ev_amps'], self.config['ev_limit']]
            if key == 'boiler':
                ids += [self.config['boiler_power']]
            if entity not in ids:
                continue
            new, old = event.data.get('new_state'), event.data.get('old_state')
            if not new or not old or new.state in ('unknown', 'unavailable'):
                continue
            if old.state in ('unknown', 'unavailable'):
                m = self.memory['devices'][key]
                self.before[key] = self.fingerprint(key)
                if not m.get('owned') and not m.get('manual_until') and new.state not in ('off',) and entity == self.entity(key):
                    await self.hold(key, 'Dispozitiv revenit online cu setari existente')
                continue
            fp = self.fingerprint(key)
            previous = self.before.get(key, {})
            self.before[key] = fp
            power_changed = key == 'boiler' and entity == self.config['boiler_power'] and new.state != old.state
            if fp == previous and not power_changed:
                continue
            m = self.memory['devices'][key]
            changed = {name: value for name, value in fp.items() if value != previous.get(name)}
            expected = m.get('expected', {})
            own_echo = time.time() < m.get('echo_until', 0) and all(name in expected and expected[name] == value for name, value in changed.items())
            if event.context.id in self.contexts or own_echo:
                m['fingerprint'] = fp
                continue
            await self.hold(key)

    def observe(self):
        c = self.config
        pv, load, grid, bp = [self.kw(SOURCE[key]) for key in ('pv', 'load', 'grid', 'battery')]
        soc = self.number(SOURCE['soc'])
        connection = self.state('binary_sensor.deye_connection')
        reported = connection.attributes.get('timestamp') if connection else None
        try:
            stamp = float(reported) if isinstance(reported, (int, float)) else dt_util.parse_datetime(reported).timestamp()
            fresh = bool(connection and connection.state == 'on' and 0 <= time.time() - stamp < c['power_stale_seconds'])
        except (ValueError, TypeError, AttributeError):
            fresh = False
        o = {'pv': pv, 'load': load, 'soc': soc, 'import': max(0, grid or 0), 'export': max(0, -(grid or 0)), 'discharge': max(0, bp or 0),
             'power_ok': fresh and all(n is not None for n in (pv, load, grid, bp, soc)),
             'outside': self.number(SOURCE['outside'], c['weather_stale_seconds'], 'temperature'),
             'forecast_remaining': self.number(SOURCE['forecast'], c['forecast_max_age_seconds']),
             'kill': not self.available(KILL) or self.state(KILL).state != 'off',
             'conflict': any(self.state(e) and self.state(e).state == 'on' for e in LEGACY),
             'recharge_lock': self.memory.get('recharge_lock', True), 'owned_optional_kw': 0}
        o['reserve_soc'] = self.number('input_number.deye_battery_min_soc') or c['base_reserve_soc']
        sun = self.state('sun.sun')
        o['sun_up'] = bool(sun and sun.state == 'above_horizon')
        try:
            o['daylight_hours'] = max(0, (dt_util.parse_datetime(sun.attributes['next_setting']).timestamp() - time.time()) / 3600) if o['sun_up'] else 0
        except (AttributeError, ValueError, KeyError):
            o['daylight_hours'] = 0
        for key in DEVICES:
            m = self.memory['devices'][key]
            o[key + '_manual'] = self.until(key)
            o[key + '_available'] = self.available(self.entity(key))
            if key in ('tcl', 'whirlpool'):
                o[key + '_normal'] = m.get('owned') and m.get('mode') == 'normal'
                s = self.state(self.entity(key))
                if m.get('owned') and m.get('mode') == 'solar' and s and s.state in ('heat', 'cool'):
                    o['owned_optional_kw'] += c[key + '_boost_kw']
        boiler = self.state(c['boiler_entity'])
        bt = self.number(c['boiler_entity'], attribute='current_temperature')
        heating = self.state('binary_sensor.boiler_ariston_is_heating')
        o['boiler_done'] = bt is not None and bt >= c['boiler_solar_c'] - c['boiler_done_delta_c'] and heating is not None and heating.state == 'off'
        if self.memory['devices']['boiler'].get('owned') and self.memory['devices']['boiler'].get('mode') == 'solar' and heating and heating.state == 'on':
            o['owned_optional_kw'] += c['boiler_kw']
        o['ev_connected'] = self.available(c['ev_connected']) and self.state(c['ev_connected']).state == 'on'
        plug = self.state(c['ev_connected'])
        o['ev_complete'] = bool(plug and plug.attributes.get('charging_state') == 'Complete')
        native_limit = self.number(c['ev_limit'])
        o['ev_effective_target'] = min(c['ev_target_soc'], native_limit) if native_limit is not None else c['ev_target_soc']
        o['ev_soc'] = self.number(c['ev_soc'], c['ev_data_age_seconds'])
        o['ev_on'] = self.available(c['ev_switch']) and self.state(c['ev_switch']).state == 'on'
        o['ev_requested_amps'] = self.number(c['ev_amps'], c['ev_data_age_seconds']) or c['ev_min_amps']
        native_power = self.state('sensor.salavat_t3_charger_power')
        actual_amps = native_power.attributes.get('charger_amps_actual') if native_power else None
        o['ev_actual_amps'] = actual_amps if isinstance(actual_amps, (int, float)) else o['ev_requested_amps']
        o['ev_voltage'] = self.number(c['ev_voltage'], c['ev_data_age_seconds']) if c['ev_voltage'] else None
        if o['ev_voltage'] is not None and not 200 <= o['ev_voltage'] <= 250:
            o['ev_voltage'] = None
        ep = self.kw(c['ev_power'])
        if native_power and isinstance(actual_amps, (int, float)):
            volts = native_power.attributes.get('charger_volts')
            if isinstance(volts, (int, float)) and 200 <= volts <= 250 and self.state(c['ev_charging']) and self.state(c['ev_charging']).state == 'on':
                ep = actual_amps * volts * c['ev_phases'] / 1000
        previous_amps = self.memory['devices']['tesla'].get('requested_amps', o['ev_actual_amps'])
        o['ev_confirmed'] = self.number(c['ev_power'], c['ev_data_age_seconds']) is not None and ep is not None and ep > .2 and o['ev_actual_amps'] == previous_amps and self.available(c['ev_charging']) and self.state(c['ev_charging']).state == 'on'
        o['tesla_available'] = o['tesla_available'] and o['ev_soc'] is not None and self.available(c['ev_amps']) and self.available(c['ev_connected'])
        o['ev_owned_power'] = ep if o['ev_confirmed'] and self.memory['devices']['tesla'].get('owned') else 0
        o['owned_optional_kw'] += o['ev_owned_power']
        tracker, home = self.state(c['ev_tracker']), self.state(c['ev_home_zone'])
        o['ev_home'] = bool(tracker and tracker.state not in ('unknown', 'unavailable') and home and at_home(tracker.attributes, home.attributes))
        q = counters(self.memory.setdefault('tesla_quota', {}), dt_util.now())
        registered = er.async_get(self.hass).async_get(c['ev_switch'])
        entry = self.hass.config_entries.async_get_entry(registered.config_entry_id) if registered else None
        o['ev_polling_protected'] = bool(entry and entry.domain == 'tesla_custom' and entry.pref_disable_polling)
        updated = self.state('sensor.salavat_t3_data_last_update_time')
        try:
            o['ev_fresh'] = bool(updated and 0 <= time.time() - dt_util.parse_datetime(updated.state).timestamp() <= c['ev_active_seconds'] + 30)
        except (TypeError, AttributeError, ValueError):
            o['ev_fresh'] = False
        online = self.state('binary_sensor.salavat_t3_online')
        o['ev_awake'] = bool(online and online.attributes.get('state') == 'online')
        o['ev_control_ready'] = o['ev_polling_protected'] and o['ev_fresh'] and o['ev_awake'] and command_allowed(c, q) and read_allowed(c, q) and q.get('backoff_until', 0) <= time.time()
        voltage = self.number('sensor.deye_battery_voltage')
        battery_state = self.state(SOURCE['soc'])
        bms_amps = battery_state.attributes.get('BMS Discharging Current') if battery_state else None
        try:
            native_limit = self.number('input_number.deye_battery_max_discharge_kw')
            o['bms_discharge_kw'] = min(c['max_discharge_kw'], native_limit if native_limit is not None else 0, max(0, float(bms_amps) * voltage / 1000))
        except (TypeError, ValueError):
            o['bms_discharge_kw'] = 0
        return o

    async def tick(self, _now=None, force=False):
        if not self.hass.is_running or self.lock.locked() or not force and time.time() - self.last_tick < self.config['control_seconds']:
            return
        async with self.lock:
            self.last_tick = time.time()
            try:
                for field, helper in [('import_price', 'input_number.ariston_grid_cost_lei_kwh'), ('export_price', 'input_number.ariston_solar_cost_lei_kwh')]:
                    price = self.rate()[field]
                    if self.available(helper) and self.number(helper) != price:
                        await self.hass.services.async_call('input_number', 'set_value', {'entity_id':helper,'value':price}, blocking=True)
                o = self.observe()
                await refresh_tesla(self, o)
                o = self.observe()
                decision = plan(self.config, o, dt_util.now())
                self.memory['recharge_lock'] = decision['recharge_lock']
                active = self.config['enabled'] and not o['kill'] and not o['conflict']
                if active:
                    for key in ('tesla', 'boiler', 'tcl', 'whirlpool'):
                        await self.apply(key, decision['devices'][key], o)
                for key, d in decision['devices'].items():
                    m = self.memory['devices'][key]
                    d.update(entity_id=self.entity(key), manual_until=m.get('manual_until', 0), owned=bool(m.get('owned')), last_command=m.get('last_command', 0))
                self.status = decision | {'updated_at': dt_util.now().isoformat(), 'power_valid': o['power_ok'], 'outside_c': o['outside'], 'battery_soc': o['soc'],
                                         'pv_kw': o['pv'], 'import_kw': o['import'], 'export_kw': o['export'], 'forecast_remaining_kwh': o['forecast_remaining'],
                                         'ac_power_estimated': True, 'last_error': ''}
                self.status['tesla_quota'] = dict(self.memory.get('tesla_quota', {})) | {'polling_protected': o['ev_polling_protected'], 'awake': o['ev_awake'], 'at_home': o['ev_home']}
                self.status['battery_reserve_soc'] = o['reserve_soc']
                await self.save()
            except Exception as error:
                self.status = self.status | {'phase': 'Eroare, control suspendat', 'last_error': type(error).__name__, 'updated_at': dt_util.now().isoformat()}
                _LOGGER.error('Energy policy cycle failed: %s', type(error).__name__)
            async_dispatcher_send(self.hass, DOMAIN)

    async def call(self, domain, service, entity, data, key, expected=None):
        # Recheck immediately before every physical write, including multi-call sequences.
        if not self.config['enabled'] or not self.available(KILL) or self.state(KILL).state != 'off' or self.until(key) or any(self.state(e) and self.state(e).state == 'on' for e in LEGACY):
            return False
        m = self.memory['devices'][key]
        if key == 'tesla':
            q = counters(self.memory.setdefault('tesla_quota', {}), dt_util.now())
            o = self.observe()
            emergency = service == 'turn_off' and m.get('owned') and not o['ev_control_ready']
            if not o['ev_polling_protected'] or not o['ev_awake'] or not o['ev_fresh'] or not command_allowed(self.config, q, emergency) or not emergency and not o['ev_control_ready']:
                return False
            q.update(commands_day=q['commands_day']+1, commands_month=q['commands_month']+1)
            if emergency:
                q.update(emergency_day=q['emergency_day']+1, emergency_month=q['emergency_month']+1)
            await self.save()
        context = Context()
        self.contexts[context.id] = time.time()
        self.contexts = {k: t for k, t in self.contexts.items() if time.time() - t < 600}
        m.update(expected=m.get('expected', {}) | (expected or {}), echo_until=time.time() + self.config['echo_seconds'])
        m['last_command'] = time.time()
        try:
            await self.hass.services.async_call(domain, service, {'entity_id': entity, **data}, blocking=True, context=context)
        except Exception:
            if key == 'tesla':
                q.update(backoff_until=time.time()+self.config['ev_error_backoff_minutes']*60, status='Comanda nereusita; fara retry automat rapid')
                await self.save()
            raise
        m.update(owned=True, last_command=time.time(), fingerprint=self.fingerprint(key))
        return True

    async def apply(self, key, d, o):
        c, m = self.config, self.memory['devices'][key]
        if d['mode'] in ('manual', 'unavailable') or self.until(key):
            return
        entity = self.entity(key)
        state = self.state(entity)
        if not state or state.state in ('unknown', 'unavailable'):
            return
        desired = dict(d)
        # A stable surplus is required before adding discretionary demand.
        signature = d['mode']
        if signature != m.get('candidate'):
            m.update(candidate=signature, candidate_since=time.time())
        adding = d['mode'] == 'solar' and m.get('mode') != 'solar'
        wait = c['optional_start_seconds'] if adding else c['optional_stop_seconds'] if m.get('mode') == 'solar' and d['mode'] != 'solar' else 0
        if time.time() - m.get('candidate_since', 0) < wait:
            d['reason'] += ' (confirmare temporizata)'
            return
        cooldown = c['ev_command_seconds'] if key == 'tesla' else c['command_seconds']
        if time.time() - m.get('last_command', 0) < cooldown:
            return
        if key == 'boiler':
            # Native anti-legionella is authoritative and is never downgraded.
            health = self.state('binary_sensor.boiler_ariston_anti_legionella_cycle')
            if health and health.state == 'on':
                d['reason'] = 'Protectie sanitara nativa activa'
                return
            if (not health or health.state in ('unknown', 'unavailable')) and state.attributes.get('temperature', 0) >= 60 and d.get('temperature', 80) < state.attributes['temperature']:
                d['reason'] = 'Stare protectie sanitara necunoscuta; temperatura mare este pastrata'
                return
            if d['mode'] in ('normal', 'solar') and state.attributes.get('temperature') != d['temperature']:
                await self.call('water_heater', 'set_temperature', entity, {'temperature': d['temperature']}, key, {'temperature': d['temperature']})
            power = self.state(c['boiler_power'])
            if d['mode'] in ('normal', 'solar') and power and power.state == 'off':
                await self.call('switch', 'turn_on', c['boiler_power'], {}, key, {'power': 'on'})
        elif key in ('tcl', 'whirlpool'):
            if not c[key + '_enabled']:
                return
            if d['mode'] == 'idle':
                if m.get('owned') and state.state != 'off' and time.time() - m.get('started_at', 0) >= c['ac_min_on_minutes'] * 60:
                    await self.call('climate', 'set_hvac_mode', entity, {'hvac_mode': 'off'}, key, {'state': 'off'})
                    m['stopped_at'] = time.time()
            else:
                if state.state == 'off' and time.time() - m.get('stopped_at', 0) < c['ac_min_off_minutes'] * 60:
                    return
                attrs = state.attributes
                if d['hvac'] not in attrs.get('hvac_modes', []) or d['fan'] not in attrs.get('fan_modes', []):
                    d['reason'] = 'Mod sau ventilator nesuportat; verifica asocierea'
                    return
                if not attrs.get('min_temp', 0) <= d['temperature'] <= attrs.get('max_temp', 50):
                    return
                if state.state != d['hvac']:
                    await self.call('climate', 'set_hvac_mode', entity, {'hvac_mode': d['hvac']}, key, {'state': d['hvac']})
                    m['started_at'] = time.time()
                if attrs.get('temperature') != d['temperature']:
                    await self.call('climate', 'set_temperature', entity, {'temperature': d['temperature']}, key, {'temperature': d['temperature']})
                if attrs.get('fan_mode') != d['fan']:
                    await self.call('climate', 'set_fan_mode', entity, {'fan_mode': d['fan']}, key, {'fan_mode': d['fan']})
        elif key == 'tesla':
            if not c['ev_enabled']:
                return
            if d['mode'] == 'solar':
                limit = self.number(c['ev_limit'])
                if limit is None:
                    d['reason'] = 'Limita Tesla indisponibila; pornirea este blocata'
                    return
                if limit > c['ev_target_soc']:
                    await self.call('number', 'set_value', c['ev_limit'], {'value': c['ev_target_soc']}, key, {'limit': c['ev_target_soc']})
                if o['ev_requested_amps'] != d['amps']:
                    await self.call('number', 'set_value', c['ev_amps'], {'value': d['amps']}, key, {'amps': d['amps']})
                    m['requested_amps'] = d['amps']
                if state.state == 'off':
                    await self.call('switch', 'turn_on', entity, {}, key, {'state': 'on'})
            elif m.get('owned') and state.state == 'on':
                await self.call('switch', 'turn_off', entity, {}, key, {'state': 'off'})
        if d['mode'] != 'idle' or m.get('owned'):
            m['mode'] = desired['mode']
        m['fingerprint'] = self.fingerprint(key)
