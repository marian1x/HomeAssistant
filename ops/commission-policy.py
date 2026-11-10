"""On-host commissioning. Never sends Tesla commands or writes inverter registers."""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import aiohttp

LEGACY = [
    'automation.hvac_solar_climate_control', 'automation.ariston_solar_boiler_boost_from_surplus',
    'automation.ariston_solar_boiler_stop_when_surplus_drops', 'automation.ariston_solar_boiler_restore_after_tesla',
    'automation.ariston_summer_default_temperature_manager',
]


async def main():
    token = os.environ['CONTROL_TOKEN']
    async with aiohttp.ClientSession(headers={'Authorization': 'Bearer ' + token}) as session:
        async def api(method, path, data=None):
            async with session.request(method, 'http://supervisor/core/api/' + path, json=data) as response:
                if response.status >= 400:
                    raise RuntimeError('HA response ' + str(response.status) + ' for ' + path.split('?')[0])
                return await response.json()
        action = sys.argv[1]
        if action == 'prepare':
            states = {s['entity_id']:s for s in await api('GET','states')}
            assert states['input_boolean.ha_automation_killswitch']['state'] == 'off'
            assert states['input_boolean.tesla_solar_charging_enabled']['state'] == 'off'
            backup = Path('/config/control_center/backups') / ('energy-policy-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            backup.mkdir(mode=0o700)
            (backup/'states.json').write_text(json.dumps({k:v for k,v in states.items() if k.startswith(('automation.','input_boolean.','input_number.deye_')) or k in ('water_heater.boiler','climate.air')}, indent=2))
            for filename in ('ariston_solar_boiler.yaml','hvac_solar_climate.yaml','deye_battery_management.yaml'):
                source = Path('/config/packages') / filename
                if source.exists(): (backup/filename).write_bytes(source.read_bytes())
            targets = [e for e in LEGACY if e in states]
            await api('POST','services/automation/turn_off',{'entity_id':targets,'stop_actions':True})
            await api('POST','services/input_boolean/turn_off',{'entity_id':['input_boolean.ariston_solar_boost_enabled','input_boolean.hvac_solar_climate_enabled']})
            await api('POST','services/homeassistant/save_persistent_states',{})
            print(json.dumps({'backup':str(backup),'disabled_legacy':targets,'tesla':'untouched/off'}))
        elif action == 'create':
            flow = await api('POST','config/config_entries/flow',{'handler':'home_energy_policy','show_advanced_options':False})
            if flow['type'] == 'form':
                flow = await api('POST','config/config_entries/flow/'+flow['flow_id'],{})
            print(json.dumps({'type':flow['type'],'reason':flow.get('reason'),'result':flow.get('result',{}).get('entry_id') if isinstance(flow.get('result'),dict) else None}))
        else:
            async with session.ws_connect('http://supervisor/core/websocket') as ws:
                hello = await ws.receive_json()
                if hello['type'] == 'auth_required':
                    await ws.send_json({'type':'auth','access_token':token})
                    assert (await ws.receive_json())['type'] == 'auth_ok'
                await ws.send_json({'id':1,'type':'home_energy_policy/get'})
                packet = await ws.receive_json()
                assert packet.get('success'), packet.get('error')
                current = packet['result']
                if action == 'enable':
                    states = {s['entity_id']:s for s in await api('GET','states')}
                    assert all(states.get(e,{}).get('state') != 'on' for e in LEGACY)
                    assert states['input_boolean.tesla_solar_charging_enabled']['state'] == 'off'
                    assert current['config']['ev_enabled'] is False
                    assert current['status']['power_valid'] is True
                    response = await api('POST','services/home_energy_policy/configure?return_response',{'revision':current['revision'],'values':{'enabled':True}})
                    current = response['service_response']
                print(json.dumps(current, ensure_ascii=True))


asyncio.run(main())
