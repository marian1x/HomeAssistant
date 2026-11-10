"""Pure decision model. Powers are kW, stored energy is kWh; no device I/O."""
from datetime import datetime, timedelta
import math


def next_resume(now, at):
    hour, minute = map(int, at.split(':'))
    return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def winter(c, now):
    return c['season'] == 'Winter' or c['season'] == 'Auto' and now.month in map(int, c['winter_months'].split(','))


def target(c, cold, outside):
    profile = c['winter_profile' if cold else 'summer_profile'].lower()
    extreme = outside <= c['winter_cold_c'] if cold else outside >= c['summer_hot_c']
    return c[('winter_' if cold else 'summer_') + profile + ('_cold_c' if cold and extreme else '_hot_c' if extreme else '_c')]


def plan(c, o, now):
    cold = winter(c, now)
    result = {'season': 'Winter' if cold else 'Summer', 'phase': 'Confort', 'reason': '', 'devices': {},
              'solar_budget_kw': 0, 'battery_support_kw': 0, 'recharge_lock': o.get('recharge_lock', True)}
    devices = result['devices']
    for key in ('tcl', 'whirlpool', 'boiler', 'tesla'):
        devices[key] = {'mode': 'idle', 'reason': 'Fara cerere automata'}
    if not c['enabled'] or o.get('kill', True) or o.get('conflict'):
        result.update(phase='Pauza', reason='Control oprit, pauza globala sau regula veche activa')
        return result
    # Weather is needed for comfort; missing power only blocks optional loads.
    outside = o.get('outside')
    weather_ok = outside is not None
    boiler = devices['boiler']
    if c['boiler_enabled']:
        boiler.update(mode='normal', temperature=c['boiler_winter_c' if cold else 'boiler_summer_c'], reason='Temperatura de baza')
    if c['tcl_enabled'] and weather_ok and cold:
        fan = c['tcl_fan3'] if outside <= c['winter_fan3_c'] or c['winter_profile'] == 'High' else c['tcl_fan2'] if outside <= c['winter_fan2_c'] else c['tcl_fan1']
        devices['tcl'].update(mode='normal', hvac='heat', temperature=target(c, True, outside), fan=fan, reason='Confort iarna')
    hour, minute = map(int, c['whirlpool_winter_start'].split(':'))
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if c['whirlpool_enabled'] and weather_ok:
        if cold and outside < c['whirlpool_winter_outside_c'] and start <= now < start + timedelta(minutes=c['whirlpool_winter_minutes']) and (o.get('whirlpool_normal') or now < start + timedelta(minutes=c['whirlpool_start_grace_minutes'])):
            devices['whirlpool'].update(mode='normal', hvac='heat', temperature=c['whirlpool_winter_c'], fan=c['whirlpool_medium'], reason='Program de seara')
        elif not cold and outside > c['summer_start_c'] - (c['summer_outside_hysteresis_c'] if o.get('whirlpool_normal') else 0):
            devices['whirlpool'].update(mode='normal', hvac='cool', temperature=target(c, False, outside), fan=c['whirlpool_low'], reason='Confort vara')
    for key, d in devices.items():
        if o.get(key + '_manual'):
            d.clear()
            d.update(mode='manual', reason='Setare manuala, reluare in ziua urmatoare')
        elif not o.get(key + '_available', False):
            d.clear()
            d.update(mode='unavailable', reason='Dispozitiv neintegrat sau date indisponibile')
    if not o.get('power_ok'):
        result.update(phase='Date incomplete', reason='Puteri lipsa sau vechi; consumatorii optionali nu primesc energie')
        return result
    soc = o['soc']
    support_floor = max(c['battery_optional_floor_soc'], o.get('reserve_soc', c['base_reserve_soc']))
    if soc <= support_floor:
        result['recharge_lock'] = True
    elif soc >= c['battery_resume_soc']:
        result['recharge_lock'] = False
    # Add back only measured engine-owned optional consumption. Never add requested amps.
    physical_surplus = max(0, o['export'] - max(0, o['import'] - c['import_tolerance_kw']) + o.get('owned_optional_kw', 0) - o['discharge'])
    budget = max(0, physical_surplus - c['export_buffer_kw'])
    solar = o['pv'] >= c['solar_min_kw'] and o.get('sun_up', False)
    if not solar:
        budget = 0
    result['solar_budget_kw'] = round(budget, 3)
    result.update(phase='Bateria are prioritate', reason='Surplusul real este masurat dupa consumul casei si incarcarea bateriei')
    if not solar:
        result.update(phase='Fara surplus solar', reason='Doar confort; Tesla nu porneste automat')
        return result
    ev = devices['tesla']
    ev_eligible = c['ev_enabled'] and ev['mode'] != 'unavailable' and o.get('ev_home', False) and o.get('ev_connected') and not o.get('ev_complete') and o.get('ev_soc', 100) < o.get('ev_effective_target', c['ev_target_soc']) and ev['mode'] != 'manual'
    ev_waiting = ev_eligible
    if ev_eligible:
        volts = o.get('ev_voltage') or c['ev_nominal_voltage']
        per_amp = volts * c['ev_phases'] / 1000
        min_kw = c['ev_min_amps'] * per_amp
        house_need = max(c['forecast_base_kw'], o['load'] - o.get('owned_optional_kw', 0))
        recharge_need = max(0, c['battery_resume_soc'] - soc) / 100 * c['battery_capacity_kwh']
        forecast = o.get('forecast_remaining')
        recoverable = forecast is not None and o.get('daylight_hours', 0) >= c['support_daylight_hours'] and forecast * c['forecast_confidence_pct'] / 100 >= recharge_need + house_need * o.get('daylight_hours', 0) + c['forecast_margin_kwh']
        support = 0
        if c['battery_support_enabled'] and not result['recharge_lock'] and soc > support_floor and recoverable and budget > 0:
            support = min(c['battery_support_kw'], max(0, min(c['max_discharge_kw'], o.get('bms_discharge_kw', 0)) - max(0, o['discharge'] - o.get('ev_owned_power', 0))), max(0, min_kw - physical_surplus))
            if support:
                budget = physical_surplus
        amps = min(c['ev_max_amps'], math.floor(min(c['ev_max_kw'], budget + support) / per_amp + 1e-8))
        if amps >= c['ev_min_amps'] and o.get('ev_control_ready', False):
            # Do not ramp until charging telemetry confirms the previous request.
            if o.get('ev_on') and not o.get('ev_confirmed'):
                amps = min(amps, max(c['ev_min_amps'], o.get('ev_actual_amps', c['ev_min_amps'])))
            ev.update(mode='solar', amps=amps, limit=c['ev_target_soc'], reason='Surplus rezidual' + (' + sprijin baterie' if support else ''))
            result['battery_support_kw'] = round(support, 3)
            budget = max(0, budget - amps * per_amp)
            result.update(phase='Tesla', reason=ev['reason'])
        else:
            ev.update(mode='idle', reason='Telemetrie veche, masina doarme sau buget API limitat; fara wake-up' if amps >= c['ev_min_amps'] else 'Surplus sub pragul minim trifazat; bateria ramane prioritara')
    # Manual charging is not stopped and blocks lower-priority discretionary loads.
    ev_blocks = ev_waiting and not c['boiler_while_ev_waits'] or ev['mode'] == 'manual' and o.get('ev_on')
    if not ev_blocks and boiler['mode'] == 'normal' and budget >= c['boiler_kw']:
        boiler.update(mode='solar', temperature=c['boiler_solar_c'], reason='Baterie/Tesla deservite, stocare termica')
        budget -= c['boiler_kw'] if not o.get('boiler_done') else 0
        result.update(phase='Boiler', reason=boiler['reason'])
    thermal_ready = c['climate_solar_enabled'] and soc >= c['boost_requires_full_soc'] and not ev_waiting and o.get('boiler_done') and weather_ok
    if thermal_ready:
        for key in ('tcl', 'whirlpool'):
            d = devices[key]
            if not c[key + '_enabled'] or d['mode'] in ('manual', 'unavailable'):
                continue
            if budget >= c[key + '_boost_kw']:
                d.update(mode='solar', hvac='heat' if cold else 'cool', temperature=c[key + '_boost_' + ('winter_c' if cold else 'summer_c')],
                         fan=c['tcl_fan_boost' if cold else 'tcl_fan3'] if key == 'tcl' else c['whirlpool_high' if cold else 'whirlpool_medium'], reason='Stocare termica din surplus')
                budget -= c[key + '_boost_kw']
                result.update(phase='Climatizare solar', reason='Baterie plina, Tesla indisponibila/finalizata si boiler cald')
    return result
