"""Read-only weather and existing PV forecasts; no actuator or Tesla requests."""
import asyncio
from datetime import timedelta
import math
import time
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util


def numeric(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


async def snapshot(manager):
    if not hasattr(manager, 'weather_lock'):
        manager.weather_lock = asyncio.Lock()
        manager.weather_cache = {'hours': [], 'fetched_at': None, 'error': ''}
        manager.weather_next = 0
    async with manager.weather_lock:
        if time.time() >= manager.weather_next:
            manager.weather_next = time.time() + 900
            try:
                params = {'latitude': manager.hass.config.latitude, 'longitude': manager.hass.config.longitude,
                          'hourly': 'temperature_2m,cloud_cover,weather_code', 'forecast_days': 7,
                          'timezone': manager.hass.config.time_zone, 'timeformat': 'unixtime'}
                session = async_get_clientsession(manager.hass)
                async with session.get('https://api.open-meteo.com/v1/forecast', params=params, timeout=aiohttp.ClientTimeout(total=12)) as response:
                    response.raise_for_status()
                    if response.content_length and response.content_length > 512000:
                        raise ValueError('Forecast too large')
                    data = await response.json()
                hourly = data['hourly']
                hours = []
                for i, stamp in enumerate(hourly['time']):
                    temp, cloud = numeric(hourly['temperature_2m'][i]), numeric(hourly['cloud_cover'][i])
                    stamp = numeric(stamp)
                    if stamp is not None and temp is not None and -90 <= temp <= 70 and cloud is not None and 0 <= cloud <= 100:
                        hours.append({'time': stamp*1000, 'temperature': temp, 'clouds': cloud,
                                      'code': hourly['weather_code'][i]})
                manager.weather_cache = {'hours': hours, 'fetched_at': dt_util.now().isoformat(), 'error': ''}
                manager.weather_next = time.time() + 3600
            except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as error:
                manager.weather_cache = manager.weather_cache | {'error': 'Prognoza meteo indisponibila: ' + type(error).__name__}
    now = dt_util.now()
    days = { (now.date()+timedelta(days=i)).isoformat(): {'date':(now.date()+timedelta(days=i)).isoformat(), 'hours':[]} for i in range(6)}
    for state in manager.hass.states.async_all('sensor'):
        if not state.entity_id.startswith('sensor.prognoza_solar_energy_production_'):
            continue
        periods = state.attributes.get('wh_period')
        if state.state in ('unknown', 'unavailable') or not isinstance(periods, dict) or len(periods)>240:
            continue
        for stamp, wh in periods.items():
            try:
                parsed, energy = dt_util.parse_datetime(stamp), numeric(wh)
            except (TypeError, ValueError):
                continue
            if parsed is None or energy is None or energy < 0:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now.tzinfo)
            day = dt_util.as_local(parsed).date().isoformat()
            if day in days:
                row = {'time':parsed.timestamp()*1000, 'energy_kwh':energy/1000}
                if not any(h['time'] == row['time'] for h in days[day]['hours']):
                    days[day]['hours'].append(row)
    for day in days.values():
        day['hours'].sort(key=lambda h:h['time'])
        day['energy_kwh'] = sum(h['energy_kwh'] for h in day['hours']) if day['hours'] else None
    reserve = manager.number('sensor.deye_rezerva_recomandata')
    voltage = manager.number('sensor.deye_battery_voltage')
    amps = manager.number('number.deye_battery_max_charging_current')
    bms = manager.hass.states.get('sensor.deye_battery')
    bms_amps = numeric(bms.attributes.get('BMS Charging Current')) if bms else None
    discharge = manager.number('sensor.deye_putere_descarcare_recomandata')
    return {'weather': manager.weather_cache, 'solar': list(days.values()), 'now': now.isoformat(),
            'timezone':manager.hass.config.time_zone,
            'battery': {'soc':manager.number('sensor.deye_battery'), 'capacity_kwh': manager.config['battery_capacity_kwh'],
                        'reserve_soc':reserve if reserve is not None else manager.config['base_reserve_soc'],
                        'discharge_kw':min(manager.config['max_discharge_kw'], discharge) if discharge is not None else 0,
                        'charge_kw':max(0,min(7,voltage*min(amps,bms_amps)/1000)) if voltage is not None and amps is not None and bms_amps is not None else None},
            'today': {k: manager.number(e) for k,e in {
                'import_kwh':'sensor.deye_today_energy_import','export_kwh':'sensor.deye_today_energy_export',
                'load_kwh':'sensor.deye_today_load_consumption','solar_kwh':'sensor.deye_productie_solara_astazi'}.items()}}
