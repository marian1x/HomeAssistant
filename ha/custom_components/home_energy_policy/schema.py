"""Bounded configuration shared by the HA runtime and the web editor."""
import math
import re
from datetime import date

FIELDS = []


def field(key, label, group, default, kind='number', low=None, high=None, step=1, unit='', choices=None):
    FIELDS.append({'key': key, 'label': label, 'group': group, 'default': default, 'kind': kind,
                   'min': low, 'max': high, 'step': step, 'unit': unit, 'choices': choices})


field('enabled', 'Control energetic automat', 'general', False, 'boolean')
field('energy_import_price', 'Cumparare din retea', 'prices', 1.11, low=0, high=5, step=.01, unit='RON/kWh')
field('energy_export_price', 'Vanzare in retea', 'prices', .45, low=0, high=5, step=.01, unit='RON/kWh')
field('energy_tariff_from', 'Tarif valabil din', 'prices', '2026-11-09', 'date')
field('planning_base_kwh', 'Consum zilnic de baza, estimare initiala', 'planning', 16.8, low=1, high=150, step=.1, unit='kWh')
field('planning_auto_calibration', 'Calibrare termica din istoric', 'planning', True, 'boolean')
field('planning_heat_kwh_degree', 'Sensibilitate estimata la frig', 'planning', 1, low=0, high=8, step=.1, unit='kWh/C/zi')
field('planning_cool_kwh_degree', 'Sensibilitate estimata la caldura', 'planning', .6, low=0, high=8, step=.1, unit='kWh/C/zi')
field('planning_heat_base_c', 'Prag necesar incalzire', 'planning', 18, low=5, high=25, step=.5, unit='C')
field('planning_cool_base_c', 'Prag necesar racire', 'planning', 24, low=18, high=35, step=.5, unit='C')
field('planning_battery_efficiency', 'Randament estimat baterie, ciclu complet', 'planning', 90, low=70, high=100, unit='%')
field('season', 'Sezon', 'general', 'Auto', 'select', choices=['Auto', 'Winter', 'Summer'])
field('winter_months', 'Luni pentru iarna in modul Auto', 'general', '10,11,12,1,2,3,4', 'months')
field('winter_profile', 'Profil iarna', 'general', 'Low', 'select', choices=['Low', 'Med', 'High'])
field('summer_profile', 'Profil vara', 'general', 'Low', 'select', choices=['Low', 'Med', 'High'])
field('manual_resume_at', 'Reluare dupa control manual, a doua zi', 'general', '06:00', 'time')
field('control_seconds', 'Interval evaluare', 'general', 30, low=10, high=300, unit='s')
field('command_seconds', 'Interval minim comenzi climatizare', 'general', 60, low=15, high=900, unit='s')
field('echo_seconds', 'Timp pentru confirmarea comenzilor cloud', 'general', 90, low=15, high=300, unit='s')
field('power_stale_seconds', 'Vechime maxima date electrice', 'safety', 120, low=30, high=300, unit='s')
field('weather_stale_seconds', 'Vechime maxima meteo', 'safety', 7200, low=900, high=21600, unit='s')
field('import_tolerance_kw', 'Import tolerat in regim optional', 'safety', .25, low=0, high=1, step=.05, unit='kW')
field('export_buffer_kw', 'Marja surplus solar', 'safety', .2, low=0, high=1, step=.05, unit='kW')
field('optional_start_seconds', 'Surplus stabil pentru pornire', 'safety', 120, low=30, high=900, unit='s')
field('optional_stop_seconds', 'Deficit stabil pentru reducere', 'safety', 30, low=0, high=180, unit='s')
field('solar_min_kw', 'Productie minima pentru consum optional', 'safety', .3, low=.1, high=3, step=.1, unit='kW')
field('base_reserve_soc', 'Rezerva minima pentru casa', 'battery', 20, low=20, high=80, unit='%')
field('max_discharge_kw', 'Limita descarcare baterie', 'battery', 7, low=.5, high=7, step=.1, unit='kW')
field('battery_capacity_kwh', 'Capacitate utilizata in estimari', 'battery', 16, low=5, high=100, step=.1, unit='kWh')
field('battery_optional_floor_soc', 'Oprire consumatori optionali la', 'battery', 70, low=20, high=95, unit='%')
field('battery_resume_soc', 'Reluare optionali dupa reincarcare la', 'battery', 100, low=50, high=100, unit='%')
field('battery_support_enabled', 'Sprijin din baterie pentru Tesla', 'battery', True, 'boolean')
field('battery_support_kw', 'Sprijin maxim pentru Tesla', 'battery', 3.3, low=0, high=7, step=.1, unit='kW')
field('forecast_confidence_pct', 'Procent utilizabil din prognoza', 'battery', 65, low=20, high=90, unit='%')
field('forecast_margin_kwh', 'Marja energie dupa reincarcarea bateriei', 'battery', 1, low=0, high=20, step=.1, unit='kWh')
field('forecast_max_age_seconds', 'Vechime maxima prognoza', 'battery', 10800, low=1800, high=21600, unit='s')
field('support_daylight_hours', 'Lumina ramasa minima pentru sprijin', 'battery', 1, low=.25, high=6, step=.25, unit='h')
field('forecast_base_kw', 'Consum de baza estimat pana la apus', 'battery', .7, low=.1, high=5, step=.1, unit='kW')
field('ev_enabled', 'Tesla automata, dupa reinrolare', 'tesla', False, 'boolean')
field('ev_monitor_enabled', 'Monitorizare Tesla economica', 'quota', True, 'boolean')
field('ev_idle_minutes', 'Verificare zi, fara incarcare solara', 'quota', 90, low=30, high=360, unit='min')
field('ev_active_seconds', 'Citire in timpul incarcarii solare', 'quota', 120, low=120, high=900, unit='s')
field('ev_night_check_at', 'Singura verificare de noapte', 'quota', '00:00', 'time')
field('ev_reads_daily', 'Buget cicluri citire pe zi', 'quota', 60, low=1, high=150, unit='cicluri')
field('ev_reads_monthly', 'Buget cicluri citire pe luna', 'quota', 900, low=10, high=2500, unit='cicluri')
field('ev_commands_daily', 'Buget comenzi automate pe zi', 'quota', 60, low=5, high=150, unit='comenzi')
field('ev_commands_monthly', 'Buget comenzi automate pe luna', 'quota', 900, low=20, high=2500, unit='comenzi')
field('ev_error_backoff_minutes', 'Pauza dupa eroare Tesla', 'quota', 60, low=15, high=360, unit='min')
field('ev_switch', 'Comanda incarcare Tesla', 'bindings', 'switch.salavat_t3_charger', 'entity')
field('ev_amps', 'Curent incarcare Tesla', 'bindings', 'number.salavat_t3_charging_amps', 'entity')
field('ev_limit', 'Limita incarcare Tesla', 'bindings', 'number.salavat_t3_charge_limit', 'entity')
field('ev_soc', 'Nivel baterie Tesla', 'bindings', 'sensor.salavat_t3_battery', 'entity')
field('ev_connected', 'Cablu conectat Tesla', 'bindings', 'binary_sensor.salavat_t3_charger', 'entity')
field('ev_charging', 'Incarcare efectiva Tesla', 'bindings', 'binary_sensor.salavat_t3_charging', 'entity')
field('ev_power', 'Putere incarcare Tesla', 'bindings', 'sensor.tesla_charging_power', 'entity')
field('ev_voltage', 'Tensiune masurata Tesla, optional', 'bindings', '', 'entity')
field('ev_tracker', 'Localizare Tesla', 'bindings', 'device_tracker.salavat_t3_location_tracker', 'entity')
field('ev_home_zone', 'Zona fizica a casei cu panouri', 'bindings', 'zone.home', 'entity')
field('ev_target_soc', 'Limita baterie Tesla', 'tesla', 80, low=50, high=100, unit='%')
field('ev_min_amps', 'Curent minim', 'tesla', 5, low=5, high=16, unit='A')
field('ev_max_amps', 'Curent maxim', 'tesla', 16, low=5, high=16, unit='A')
field('ev_nominal_voltage', 'Tensiune nominala pe faza', 'tesla', 220, low=200, high=250, unit='V')
field('ev_phases', 'Numar faze', 'tesla', 3, low=1, high=3)
field('ev_max_kw', 'Plafon putere incarcare', 'tesla', 11.1, low=1, high=12, step=.1, unit='kW')
field('ev_command_seconds', 'Interval ajustari amperaj', 'tesla', 120, low=60, high=900, unit='s')
field('ev_data_age_seconds', 'Vechime maxima date Tesla', 'tesla', 900, low=120, high=1800, unit='s')
field('boiler_enabled', 'Program automat boiler', 'boiler', True, 'boolean')
field('boiler_entity', 'Boiler', 'bindings', 'water_heater.boiler', 'entity')
field('boiler_power', 'Pornire boiler', 'bindings', 'switch.boiler_ariston_power', 'entity')
field('boiler_winter_c', 'Temperatura normala iarna', 'boiler', 47, low=40, high=80, unit='C')
field('boiler_summer_c', 'Temperatura normala vara', 'boiler', 43, low=40, high=80, unit='C')
field('boiler_solar_c', 'Temperatura la surplus solar', 'boiler', 80, low=45, high=80, unit='C')
field('boiler_kw', 'Putere rezistenta', 'boiler', 1.8, low=.5, high=4, step=.1, unit='kW')
field('boiler_done_delta_c', 'Histerezis boiler incarcat termic', 'boiler', 1, low=.5, high=3, step=.5, unit='C')
field('boiler_while_ev_waits', 'Boiler solar daca Tesla asteapta surplus minim', 'boiler', False, 'boolean')
field('tcl_enabled', 'Program TCL, dupa integrare', 'tcl', True, 'boolean')
field('tcl_entity', 'AC parter TCL', 'bindings', '', 'entity')
field('whirlpool_enabled', 'Program Whirlpool', 'whirlpool', True, 'boolean')
field('whirlpool_entity', 'AC etaj Whirlpool', 'bindings', 'climate.air', 'entity')
field('ac_min_on_minutes', 'Durata minima functionare AC', 'comfort', 10, low=1, high=30, unit='min')
field('ac_min_off_minutes', 'Pauza minima AC', 'comfort', 5, low=1, high=30, unit='min')
field('winter_cold_c', 'Prag frig sever', 'winter', -15, low=-30, high=0, unit='C')
field('winter_fan2_c', 'Prag ventilator treapta 2', 'winter', -5, low=-20, high=10, unit='C')
field('winter_fan3_c', 'Prag ventilator treapta 3', 'winter', -10, low=-25, high=5, unit='C')
for profile, base, cold in [('low', 23, 24), ('med', 24, 25), ('high', 25, 27)]:
    field(f'winter_{profile}_c', f'Iarna {profile.title()} - normal', 'winter', base, low=18, high=24 if profile == 'low' else 30, step=.5, unit='C')
    field(f'winter_{profile}_cold_c', f'Iarna {profile.title()} - frig sever', 'winter', cold, low=18, high=24 if profile == 'low' else 30, step=.5, unit='C')
for profile, base, hot in [('low', 22, 21), ('med', 21, 20), ('high', 20, 19)]:
    field(f'summer_{profile}_c', f'Vara {profile.title()} - normal', 'summer', base, low=18, high=28, step=.5, unit='C')
    field(f'summer_{profile}_hot_c', f'Vara {profile.title()} - canicula', 'summer', hot, low=18, high=28, step=.5, unit='C')
field('summer_hot_c', 'Prag canicula', 'summer', 35, low=30, high=45, unit='C')
field('summer_start_c', 'Pornire racire etaj peste', 'summer', 30, low=25, high=40, unit='C')
field('summer_outside_hysteresis_c', 'Histerezis temperatura exterioara', 'summer', 1, low=.5, high=3, step=.5, unit='C')
field('whirlpool_winter_outside_c', 'Seara iarna, exterior sub', 'whirlpool', 5, low=-15, high=15, unit='C')
field('whirlpool_winter_start', 'Pornire seara iarna', 'whirlpool', '20:00', 'time')
field('whirlpool_winter_minutes', 'Durata seara iarna', 'whirlpool', 60, low=15, high=180, unit='min')
field('whirlpool_start_grace_minutes', 'Fereastra de pornire dupa ora programata', 'whirlpool', 5, low=1, high=15, unit='min')
field('whirlpool_winter_c', 'Temperatura seara iarna', 'whirlpool', 27, low=18, high=30, unit='C')
for key, label, default in [('tcl_fan1','TCL treapta 1','1'), ('tcl_fan2','TCL treapta 2','2'), ('tcl_fan3','TCL treapta 3','3'), ('tcl_fan_boost','TCL treapta surplus iarna','6'), ('whirlpool_low','Whirlpool Low','low'), ('whirlpool_medium','Whirlpool Medium','medium'), ('whirlpool_high','Whirlpool High','high')]:
    field(key, label, 'fans', default, 'fan')
field('climate_solar_enabled', 'Stocare termica prin AC', 'boost', True, 'boolean')
field('boost_requires_full_soc', 'Baterie minima pentru boost AC', 'boost', 100, low=80, high=100, unit='%')
field('tcl_boost_winter_c', 'TCL surplus iarna', 'boost', 26, low=20, high=30, unit='C')
field('whirlpool_boost_winter_c', 'Whirlpool surplus iarna', 'boost', 27, low=20, high=30, unit='C')
field('tcl_boost_summer_c', 'TCL surplus vara', 'boost', 19, low=18, high=26, unit='C')
field('whirlpool_boost_summer_c', 'Whirlpool surplus vara', 'boost', 19, low=18, high=26, unit='C')
field('tcl_boost_kw', 'Putere suplimentara TCL estimata', 'boost', 1.2, low=.3, high=4, step=.1, unit='kW')
field('whirlpool_boost_kw', 'Putere suplimentara Whirlpool estimata', 'boost', 1.2, low=.3, high=4, step=.1, unit='kW')

DEFAULTS = {f['key']: f['default'] for f in FIELDS}


def validate(raw, base=None):
    if not isinstance(raw, dict) or set(raw) - DEFAULTS.keys():
        raise ValueError('Configuratie invalida sau parametri necunoscuti')
    result = dict(DEFAULTS if base is None else base)
    for spec in FIELDS:
        key = spec['key']
        if key not in raw:
            continue
        value, kind = raw[key], spec['kind']
        if kind == 'boolean':
            ok = isinstance(value, bool)
        elif kind == 'number':
            ok = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and spec['min'] <= value <= spec['max']
            if ok and spec['step'] == 1:
                ok = float(value).is_integer()
        elif kind == 'select':
            ok = isinstance(value, str) and value in spec['choices']
        elif kind == 'entity':
            ok = isinstance(value, str) and len(value) <= 150 and (not value or bool(re.fullmatch(r'(?:climate|water_heater|switch|number|sensor|binary_sensor|device_tracker|zone)\.[a-z0-9_]+', value)))
        elif kind == 'time':
            ok = isinstance(value, str) and bool(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value))
        elif kind == 'date':
            try:
                parsed = date.fromisoformat(value)
                ok = isinstance(value, str) and parsed.isoformat() == value and 2000 <= parsed.year <= 2100
            except (TypeError, ValueError):
                ok = False
        elif kind == 'months':
            ok = isinstance(value, str) and bool(re.fullmatch(r'\d{1,2}(?:,\d{1,2}){0,11}', value)) and all(1 <= int(v) <= 12 for v in value.split(',')) and len(set(value.split(','))) == len(value.split(','))
        else:
            ok = isinstance(value, str) and 1 <= len(value) <= 32 and not any(ord(c) < 32 for c in value)
        if not ok:
            raise ValueError('Valoare invalida: ' + spec['label'])
        result[key] = value
    if not result['base_reserve_soc'] <= result['battery_optional_floor_soc'] < result['battery_resume_soc']:
        raise ValueError('Rezerva de baza <= prag optional < prag de reluare')
    if not result['winter_cold_c'] <= result['winter_fan3_c'] <= result['winter_fan2_c']:
        raise ValueError('Pragurile de frig trebuie ordonate')
    if result['ev_min_amps'] > result['ev_max_amps'] or result['boiler_solar_c'] < max(result['boiler_winter_c'], result['boiler_summer_c']):
        raise ValueError('Limite minime/maxime incompatibile')
    if result['tcl_entity'] and result['tcl_entity'] == result['whirlpool_entity']:
        raise ValueError('Acelasi AC nu poate avea doua roluri')
    if result['planning_heat_base_c'] > result['planning_cool_base_c']:
        raise ValueError('Pragul de incalzire trebuie sa fie sub pragul de racire')
    return result
