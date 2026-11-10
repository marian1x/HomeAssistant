"""Owner-approved activation of reviewed automations, excluding Tesla and street lighting."""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path

import aiohttp


ALLOW = {
    'automation.ariston_solar_boiler_discover_entities',
    'automation.ariston_solar_boiler_boost_from_surplus',
    'automation.ariston_solar_boiler_stop_when_surplus_drops',
    'automation.ariston_summer_default_temperature_manager',
    'automation.ariston_stop_internal_state_when_automation_disabled',
    'automation.ha_full_backup_morning_and_evening',
    'automation.ha_prune_backups_older_than_14_days',
    'automation.deye_management_baterie_si_prognoza',
    'automation.energy_initialize_unknown_utility_meters',
    'automation.xiaomi_scale_route_family_weight',
    'automation.hvac_discover_known_entities',
    'automation.hvac_solar_climate_control',
}
CONTROLLER = 'automation.ha_global_automation_killswitch_controller'


async def main():
    token = os.environ['CONTROL_TOKEN']
    async with aiohttp.ClientSession(headers={'Authorization': 'Bearer ' + token}) as session:
        async def api(method, path, data=None):
            async with session.request(method, 'http://supervisor/core/api' + path, json=data) as response:
                response.raise_for_status()
                return await response.json()

        async def read():
            return {s['entity_id']: s for s in await api('GET', '/states')}

        async def service(domain, action, ids):
            return await api('POST', f'/services/{domain}/{action}', {'entity_id': ids})

        before = await read()
        assert before['input_boolean.ha_automation_killswitch']['state'] == 'on', 'Global pause changed: review before activating'
        assert not (ALLOW - before.keys()), 'Missing expected automations'
        assert 20 <= float(before['input_number.deye_battery_min_soc']['state']) <= 80
        assert .5 <= float(before['input_number.deye_battery_max_discharge_kw']['state']) <= 7
        assert before['input_select.hvac_season_mode']['state'] == 'Auto'
        for id in ('sensor.hvac_upstairs_temperature', 'sensor.hvac_downstairs_temperature'):
            assert 10 <= float(before[id]['state']) <= 35, 'Implausible temperature: do not activate HVAC'
        assert before['water_heater.boiler']['state'] not in ('unavailable', 'unknown')
        backup = Path('/config/control_center/backups') / ('activation-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True, exist_ok=False)
        relevant = {id: {'state': s['state']} for id, s in before.items() if id.startswith(('automation.', 'input_boolean.', 'input_select.hvac_'))}
        (backup / 'before.json').write_text(json.dumps(relevant, indent=2))
        # All currently paused rules stay off during the transition, preventing a stale scene restore.
        automations = [id for id in before if id.startswith('automation.') and id != CONTROLLER]
        await api('POST', '/services/automation/turn_off', {'entity_id': automations, 'stop_actions': True})
        await service('input_boolean', 'turn_off', 'input_boolean.tesla_solar_charging_enabled')
        if 'scene.ha_automations_before_killswitch' in before:
            await service('scene', 'delete', 'scene.ha_automations_before_killswitch')
        await service('input_boolean', 'turn_off', 'input_boolean.ha_automation_killswitch')
        await asyncio.sleep(2)
        await service('automation', 'turn_on', sorted(ALLOW))
        await service('input_boolean', 'turn_on', ['input_boolean.ariston_solar_boost_enabled', 'input_boolean.hvac_solar_climate_enabled'])
        await asyncio.sleep(2)
        after = await read()
        assert after['input_boolean.ha_automation_killswitch']['state'] == 'off'
        assert all(after[id]['state'] == 'on' for id in ALLOW | {CONTROLLER})
        excluded = [id for id in after if id.startswith('automation.') and id not in ALLOW | {CONTROLLER}]
        assert all(after[id]['state'] == 'off' for id in excluded)
        assert after['input_boolean.tesla_solar_charging_enabled']['state'] == 'off'
        await api('POST', '/services/persistent_notification/dismiss', {'notification_id': 'ha_automation_restore_missing'})
        await api('POST', '/services/homeassistant/save_persistent_states', {})
        summary = {'backup': str(backup), 'enabled': sorted(ALLOW), 'kept_off': excluded, 'tesla_solar': 'off', 'global_pause': 'off', 'hvac_season': after['sensor.hvac_effective_season']['state']}
        (backup / 'after.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary))


asyncio.run(main())
