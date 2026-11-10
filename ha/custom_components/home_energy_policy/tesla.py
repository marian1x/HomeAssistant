"""Adapter to the installed Tesla Custom shared cache/coordinator, not a new client."""
import asyncio
import time
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from .quota import counters, due


async def refresh(manager, observations):
    c, hass = manager.config, manager.hass
    q = counters(manager.memory.setdefault('tesla_quota', {}), dt_util.now())
    owned = manager.memory['devices']['tesla']
    active = c['ev_enabled'] and owned.get('owned') and owned.get('mode') == 'solar' and observations.get('ev_on') and not observations.get('tesla_manual')
    if not due(c, q, observations, dt_util.now(), active):
        return
    registry = er.async_get(hass)
    entity = registry.async_get(c['ev_switch'])
    entry = hass.config_entries.async_get_entry(entity.config_entry_id) if entity else None
    if not entry or entry.domain != 'tesla_custom' or not entry.pref_disable_polling:
        q['status'] = 'Polling nativ neprotejat sau integrare lipsa; controlul automat este blocat'
        return
    data = hass.data.get('tesla_custom', {}).get(entry.entry_id)
    if not data:
        return
    cars = data.get('cars', {})
    if len(cars) != 1:
        q['status'] = 'Asociere auto ambigua'
        return
    vin = next(iter(cars))
    controller = data['controller']
    coordinator = data['coordinators'][vin]
    q.update(last_poll=time.time(), reads_day=q['reads_day']+1, reads_month=q['reads_month']+1, status='Verificare fara wake-up')
    if not observations.get('sun_up'):
        q['night_day'] = dt_util.now().strftime('%Y-%m-%d')
    await manager.save()
    old_update = controller.get_last_update_time(vin=vin)
    try:
        controller.set_updates(vin=vin, value=True)
        async with asyncio.timeout(30):
            await controller.update(vins={vin}, energy_site_ids=set(), update_vehicles=True, force=True, wake_if_asleep=False)
        q['status'] = 'Stare memorata; fara wake-up'
        if controller.is_car_online(vin=vin) and controller.get_last_update_time(vin=vin) == old_update:
            q.update(status='Date auto neactualizate; pauza de siguranta', backoff_until=time.time()+c['ev_error_backoff_minutes']*60)
    except Exception as error:
        q.update(status='Eroare Tesla: ' + type(error).__name__, backoff_until=time.time()+c['ev_error_backoff_minutes']*60)
    finally:
        controller.set_updates(vin=vin, value=False)
        # Native refresh saves rotated tokens and publishes the cache. With per-car
        # updates and integration polling disabled, it cannot issue another data poll.
        await coordinator.async_refresh()
