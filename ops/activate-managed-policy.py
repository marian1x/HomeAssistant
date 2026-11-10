"""Activate the owner-approved unified policy, never competing legacy writers."""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp


ENABLE = ['automation.ha_global_automation_killswitch_controller',
          'automation.deye_management_baterie_si_prognoza',
          'automation.ha_full_backup_morning_and_evening',
          'automation.ha_backup_integrity_monitor']
LEGACY = ['automation.hvac_solar_climate_control',
          'automation.ariston_solar_boiler_boost_from_surplus',
          'automation.ariston_solar_boiler_stop_when_surplus_drops',
          'automation.ariston_solar_boiler_restore_after_tesla',
          'automation.ariston_summer_default_temperature_manager']


async def main():
    async with aiohttp.ClientSession(headers={'Authorization':'Bearer '+os.environ['CONTROL_TOKEN']}) as session:
        async def api(method,path,data=None):
            async with session.request(method,'http://supervisor/core/api/'+path,json=data) as response:
                response.raise_for_status()
                return await response.json()
        async def states():
            return {s['entity_id']:s for s in await api('GET','states')}
        async with session.ws_connect('http://supervisor/core/websocket') as socket:
            assert (await socket.receive_json())['type']=='auth_required'
            await socket.send_json({'type':'auth','access_token':os.environ['CONTROL_TOKEN']})
            assert (await socket.receive_json())['type']=='auth_ok'
            seq=0
            async def call(message):
                nonlocal seq
                seq+=1
                await socket.send_json({'id':seq,**message})
                while True:
                    packet=await socket.receive_json()
                    if packet.get('id')==seq:
                        if not packet.get('success'):raise RuntimeError(packet.get('error'))
                        return packet.get('result')
            policy=await call({'type':'home_energy_policy/get'})
            entries=await call({'type':'config_entries/get'})
            tesla=next(e for e in entries if e['domain']=='tesla_custom')
            assert tesla['state']=='loaded' and tesla['pref_disable_polling'] is True
            before=await states()
            assert before['input_boolean.ha_automation_killswitch']['state']=='off', 'Pause changed; review activation'
            assert before['switch.deye_battery_grid_charging']['state']=='off'
            for id in ('binary_sensor.deye_battery_alarm','binary_sensor.deye_battery_fault'):
                assert before[id]['state']=='off', 'Battery alarm/fault: activation blocked'
            for key in ('tcl_entity','whirlpool_entity','boiler_entity'):
                assert before[policy['config'][key]]['state'] not in ('unknown','unavailable')
            assert 20<=float(before['input_number.deye_battery_min_soc']['state'])<=80
            assert float(before['input_number.deye_battery_max_discharge_kw']['state'])<=7
            now=datetime.now(ZoneInfo('Europe/Bucharest'))
            folder=Path('/config/control_center/backups')/('managed-activation-'+now.strftime('%Y%m%d-%H%M%S'))
            folder.mkdir(mode=0o700)
            (folder/'before-policy.json').write_text(json.dumps(policy,indent=2))
            relevant=[s for s in before.values() if s['entity_id'].startswith('automation.') or s['entity_id']=='input_boolean.ha_automation_killswitch']
            (folder/'before-automation-states.json').write_text(json.dumps([{k:s[k] for k in ('entity_id','state')} for s in relevant],indent=2))
            for path in folder.iterdir():path.chmod(0o600)
            conflicting=[id for id,s in before.items() if s['state']=='on' and (id in LEGACY or id.startswith('automation.tesla_'))]
            if conflicting:
                await api('POST','services/automation/turn_off',{'entity_id':conflicting,'stop_actions':True})
            for id in ENABLE:
                assert id in before
                if before[id]['state']!='on':
                    await api('POST','services/automation/turn_on',{'entity_id':id})
            result=await call({'type':'call_service','domain':'home_energy_policy','service':'configure',
                             'service_data':{'revision':policy['revision'],'values':{
                                 'enabled':True,'ev_enabled':True,'ev_monitor_enabled':True,
                                 'boiler_enabled':True,'tcl_enabled':True,'whirlpool_enabled':True,'climate_solar_enabled':True}},
                             'return_response':True})
            assert result['response']['config']['ev_enabled'] is True
            for device in ('tesla','boiler','tcl','whirlpool'):
                await call({'type':'call_service','domain':'home_energy_policy','service':'resume_device',
                            'service_data':{'device':device},'return_response':True})
            await api('POST','services/homeassistant/save_persistent_states',{})
            after=await call({'type':'home_energy_policy/get'})
            live=await states()
            assert all(live[id]['state']=='on' for id in ENABLE)
            assert not any(s['state']=='on' for id,s in live.items() if id in LEGACY or id.startswith('automation.tesla_'))
            assert live['switch.deye_battery_grid_charging']['state']=='off'
            assert not after['status']['last_error']
            summary={'at':now.isoformat(),'revision':after['revision'],'enabled':{k:after['config'][k] for k in
                     ('enabled','ev_enabled','ev_monitor_enabled','boiler_enabled','tcl_enabled','whirlpool_enabled','climate_solar_enabled')},
                     'state':after['status'],'legacy_writers_off':True,'backup':str(folder)}
            (folder/'after.json').write_text(json.dumps(summary,indent=2));(folder/'after.json').chmod(0o600)
            print(json.dumps(summary))


asyncio.run(main())
