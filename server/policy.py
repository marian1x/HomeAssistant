"""Explicit, narrow service permissions; never expose a generic HA proxy."""
import math
import re

BASE = '/casa'
KILL = 'input_boolean.ha_automation_killswitch'
RULE_PREFIX = 'web_casa_'
BINDINGS = {
    'solar': 'sensor.productie_solara_curenta', 'load': 'sensor.consum_total_curent',
    'import': 'sensor.consum_din_retea', 'export': 'sensor.injectie_in_retea',
    'soc': 'sensor.deye_battery', 'charge': 'sensor.baterie_incarcare_putere',
    'discharge': 'sensor.baterie_descarcare_putere', 'batteryTemp': 'sensor.deye_battery_temperature',
    'solarToday': 'sensor.deye_productie_solara_astazi', 'loadToday': 'sensor.deye_today_load_consumption',
    'importToday': 'sensor.deye_today_energy_import', 'forecast': 'sensor.deye_prognoza_solar_maine',
    'forecastValid': 'binary_sensor.deye_prognoza_valida', 'reserve': 'sensor.deye_rezerva_recomandata',
    'limit': 'sensor.deye_putere_descarcare_recomandata', 'tesla': 'sensor.tesla_charging_power',
    'boiler': 'sensor.ariston_boiler_power_estimated', 'pause': KILL,
    'manager': 'automation.deye_management_baterie_si_prognoza',
}
HISTORY_POWER = ['sensor.productie_solara_curenta', 'sensor.consum_total_curent', 'sensor.baterie_descarcare_putere', 'sensor.consum_din_retea']
HISTORY_ENERGY = ['sensor.deye_productie_solara_total', 'sensor.deye_total_load_consumption', 'sensor.deye_total_battery_discharge', 'sensor.deye_total_energy_import']
HELPERS = {
    'input_number.deye_battery_min_soc': (20, 80), 'input_number.deye_battery_max_discharge_kw': (.5, 7),
    'input_number.deye_battery_priority_soc': (50, 100), 'input_number.deye_forecast_confidence_percent': (30, 90),
    'input_number.deye_forecast_max_reserve_soc': (20, 90), 'input_number.deye_forecast_fallback_soc': (20, 80),
    'input_number.deye_baseload_kw': (.1, 3), 'input_number.tesla_solar_max_amps': (5, 12),
    'input_number.ariston_normal_temperature': (40, 80), 'input_number.hvac_summer_target_c': (18, 30),
    'input_number.hvac_winter_target_c': (16, 28),
}
ATTRS = {'friendly_name', 'unit_of_measurement', 'device_class', 'state_class', 'supported_features', 'current_temperature', 'temperature', 'humidity', 'min_temp', 'max_temp', 'target_temp_step', 'hvac_modes', 'hvac_action', 'operation_list', 'temperature_unit', 'brightness', 'supported_color_modes', 'color_mode', 'min', 'max', 'step', 'options', 'id', 'icon', 'last_triggered', 'volume_level', 'is_volume_muted'}
LEVEL = {'viewer': 0, 'control': 1, 'configure': 2}
AUTO_FLAGS = {'input_boolean.ariston_solar_boost_enabled', 'input_boolean.hvac_solar_climate_enabled'}
LEGACY_POLICY = {'automation.hvac_solar_climate_control', 'automation.ariston_solar_boiler_boost_from_surplus', 'automation.ariston_solar_boiler_stop_when_surplus_drops', 'automation.ariston_solar_boiler_restore_after_tesla', 'automation.ariston_summer_default_temperature_manager'}
BACKUP_MAINTENANCE = {'automation.ha_full_backup_morning_and_evening', 'automation.ha_backup_integrity_monitor'}
ATTRS.update({'fan_mode', 'fan_modes', 'phase', 'reason', 'devices', 'updated_at', 'power_valid', 'battery_soc', 'pv_kw', 'import_kw', 'export_kw', 'solar_budget_kw', 'battery_support_kw', 'recharge_lock', 'forecast_remaining_kwh', 'last_error', 'tesla_quota', 'ev_limit', 'cold_charge'})
ATTRS.add('battery_reserve_soc')
# BMS values the Deye inverter forwards; Solarman exposes them as attributes of
# sensor.deye_battery. Read-only, used by the battery panel.
BMS_ATTRS = ('BMS SOC', 'BMS Current', 'BMS Voltage', 'BMS Other Symbol', 'BMS Charging Voltage', 'BMS Discharging Voltage',
             'BMS Charging Current', 'BMS Discharging Current', 'BMS Max Charging Current', 'BMS Max Discharging Current',
             'Corrected Capacity', 'Nominal Voltage', 'Life Cycle Rating')
ATTRS.update(BMS_ATTRS)
BATTERY_HISTORY = ('sensor.deye_battery', 'sensor.deye_battery_temperature', 'sensor.deye_battery_power')


class Rejected(Exception):
    def __init__(self, message, status=403):
        self.message, self.status = message, status


def visible(entity_id, registry):
    entry = registry.get(entity_id, {})
    return not entry.get('disabled_by') and not entry.get('hidden_by') and not entry.get('entity_category')


def clean_state(state):
    return {key: state[key] for key in ('entity_id', 'state', 'last_changed', 'last_updated') if key in state} | {'attributes': {k: v for k, v in state.get('attributes', {}).items() if k in ATTRS}}


def command(role, entity_id, action, value, states, registry):
    if LEVEL.get(role, -1) < 1:
        raise Rejected('Acces doar pentru vizualizare.')
    state = states.get(entity_id)
    if not state or state['state'] in ('unknown', 'unavailable'):
        raise Rejected('Dispozitivul nu este disponibil.', 409)
    domain = entity_id.split('.')[0]
    attrs = state.get('attributes', {})
    if action == 'turn_on' and (entity_id in LEGACY_POLICY or entity_id in AUTO_FLAGS) and 'sensor.home_energy_policy_status' in states:
        raise Rejected('Control preluat de Politica Energie; regula veche este dezactivata.', 409)
    if entity_id == KILL and action in ('turn_on', 'turn_off'):
        if action == 'turn_off' and role != 'configure':
            raise Rejected('Reluarea automatizarilor necesita drepturi de configurare.')
        return 'input_boolean', action, {'entity_id': entity_id}
    if domain == 'automation':
        if role != 'configure' or entity_id == 'automation.ha_global_automation_killswitch_controller' or action not in ('turn_on', 'turn_off'):
            raise Rejected('Comanda pentru automatizare nu este permisa.')
        if action == 'turn_on' and entity_id not in BACKUP_MAINTENANCE and states.get(KILL, {}).get('state') != 'off':
            raise Rejected('Pauza globala a automatizarilor este activa.', 409)
        return domain, action, {'entity_id': entity_id, **({'stop_actions': True} if action == 'turn_off' else {})}
    if entity_id in AUTO_FLAGS and action in ('turn_on', 'turn_off'):
        if role != 'configure':
            raise Rejected('Programul automat necesita drepturi Admin.')
        if action == 'turn_on' and states.get(KILL, {}).get('state') != 'off':
            raise Rejected('Pauza globala a automatizarilor este activa.', 409)
        return 'input_boolean', action, {'entity_id': entity_id}
    if entity_id in HELPERS:
        if role != 'configure' or action != 'set_value':
            raise Rejected('Parametrii necesita drepturi de configurare.')
        low, high = HELPERS[entity_id]
        low, high = max(low, attrs.get('min', low)), min(high, attrs.get('max', high))
        return domain, action, {'entity_id': entity_id, 'value': bounded(value, low, high)}
    if not visible(entity_id, registry):
        raise Rejected('Entitate tehnica protejata.')
    if domain == 'media_player':
        features = int(attrs.get('supported_features', 0))
        services = {'turn_on': (128, 'turn_on'), 'turn_off': (256, 'turn_off'), 'media_play': (16384, 'media_play'), 'media_pause': (1, 'media_pause'), 'media_stop': (4096, 'media_stop')}
        if action in services and features & services[action][0]:
            return domain, services[action][1], {'entity_id': entity_id}
        if action == 'set_volume' and features & 4:
            return domain, 'volume_set', {'entity_id': entity_id, 'volume_level': bounded(value, 0, 100) / 100}
        if action == 'set_mute' and features & 8 and value in ('on', 'off'):
            return domain, 'volume_mute', {'entity_id': entity_id, 'is_volume_muted': value == 'on'}
        raise Rejected('Control media nesuportat de acest dispozitiv.', 422)
    if domain == 'light' and action == 'set_brightness':
        modes = attrs.get('supported_color_modes') or []
        if not any(mode not in ('onoff', 'unknown') for mode in modes):
            raise Rejected('Luminozitatea nu este reglabila.', 409)
        return 'light', 'turn_on', {'entity_id': entity_id, 'brightness_pct': bounded(value, 1, 100)}
    if domain in ('light', 'switch', 'fan') and action in ('turn_on', 'turn_off'):
        if entity_id.startswith('switch.deye') or any(word in entity_id for word in ('polling', 'firmware', 'update', 'access_point')):
            raise Rejected('Control tehnic protejat.')
        return domain, action, {'entity_id': entity_id}
    if domain in ('climate', 'water_heater') and action == 'set_temperature':
        # The Tuya thermostats expose unscaled raw setpoints. Do not write those.
        if entity_id in ('climate.heat', 'climate.bedroom_heat'):
            raise Rejected('Termostat cu scalare specifica; modifica din HA.', 409)
        return domain, action, {'entity_id': entity_id, 'temperature': bounded(value, attrs.get('min_temp', 5), attrs.get('max_temp', 80))}
    if domain == 'climate' and action == 'set_hvac_mode' and value in attrs.get('hvac_modes', []):
        return domain, action, {'entity_id': entity_id, 'hvac_mode': value}
    if domain == 'climate' and action == 'set_fan_mode' and value in attrs.get('fan_modes', []):
        if entity_id in ('climate.heat', 'climate.bedroom_heat'):
            raise Rejected('Termostat protejat.', 409)
        return domain, action, {'entity_id': entity_id, 'fan_mode': value}
    if domain == 'water_heater' and action == 'set_operation_mode' and value in attrs.get('operation_list', []):
        return domain, action, {'entity_id': entity_id, 'operation_mode': value}
    raise Rejected('Actiune nepermisa pentru acest dispozitiv.')


def bounded(value, low, high):
    if isinstance(value, bool):
        raise Rejected('Valoare numerica invalida.', 422)
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise Rejected('Valoare numerica invalida.', 422)
    if not math.isfinite(number) or not low <= number <= high:
        raise Rejected(f'Valoarea trebuie sa fie intre {low} si {high}.', 422)
    return number


def build_rule(data, states, registry, rule_id):
    if not re.fullmatch(RULE_PREFIX + r'[a-f0-9]{16}', rule_id):
        raise Rejected('Identificator invalid.', 422)
    name = str(data.get('name', '')).strip()
    if not 1 <= len(name) <= 90:
        raise Rejected('Numele regulii este obligatoriu.', 422)
    domain, action, args = command('configure', data.get('entity_id', ''), data.get('action', ''), data.get('value'), states, registry)
    if domain in ('automation', 'input_boolean'):
        raise Rejected('Regulile nu pot activa alte automatizari sau killswitch-ul.', 422)
    kind = data.get('trigger')
    if kind == 'time':
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', data.get('at', '')):
            raise Rejected('Ora invalida.', 422)
        trigger = {'trigger': 'time', 'at': data['at'] + ':00'}
    elif kind == 'sun':
        if data.get('event') not in ('sunrise', 'sunset'):
            raise Rejected('Eveniment solar invalid.', 422)
        trigger = {'trigger': 'sun', 'event': data['event'], 'offset': int(bounded(data.get('offset', 0), -180, 180)) * 60}
    elif kind == 'numeric':
        source = data.get('source', '')
        if source not in states or source.split('.')[0] not in ('sensor', 'input_number'):
            raise Rejected('Senzor invalid.', 422)
        comparator = data.get('comparator')
        if comparator not in ('above', 'below'):
            raise Rejected('Comparator invalid.', 422)
        trigger = {'trigger': 'numeric_state', 'entity_id': source, comparator: bounded(data.get('threshold'), -100000, 100000), 'for': {'seconds': int(bounded(data.get('hold', 60), 0, 3600))}}
    else:
        raise Rejected('Declansator invalid.', 422)
    target = args.pop('entity_id')
    return {'id': rule_id, 'alias': name, 'description': 'Creata din Casa Salavat Web.', 'initial_state': False, 'mode': 'single', 'triggers': [trigger], 'conditions': [{'condition': 'state', 'entity_id': KILL, 'state': 'off'}], 'actions': [{'action': domain + '.' + action, 'target': {'entity_id': target}, **({'data': args} if args else {})}]}
