"""Bind the confirmed downstairs TCL through HA APIs, preserving existing settings."""
import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import aiohttp

ENTITY = 'climate.living_living_air_cxbwrbfaaae_climate'
DEVICE = '64f01c0359ebb3569a50e8eb51041183'


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    headers = {'Authorization': 'Bearer ' + os.environ['CONTROL_TOKEN']}
    async with aiohttp.ClientSession(headers=headers) as session:
        async def state():
            async with session.get('http://supervisor/core/api/states/' + ENTITY) as response:
                response.raise_for_status()
                value = await response.json()
            return {k: value['attributes'].get(k) for k in ('temperature', 'fan_mode')} | {'state': value['state']}

        async with session.ws_connect('http://supervisor/core/websocket') as socket:
            assert (await socket.receive_json())['type'] == 'auth_required'
            await socket.send_json({'type': 'auth', 'access_token': os.environ['CONTROL_TOKEN']})
            assert (await socket.receive_json())['type'] == 'auth_ok'
            sequence = 0

            async def call(message):
                nonlocal sequence
                sequence += 1
                await socket.send_json({'id': sequence, **message})
                while True:
                    packet = await socket.receive_json()
                    if packet.get('id') == sequence:
                        if not packet.get('success'):
                            raise RuntimeError(packet.get('error'))
                        return packet.get('result')

            policy = await call({'type': 'home_energy_policy/get'})
            entities = await call({'type': 'config/entity_registry/list'})
            registered = next(e for e in entities if e['entity_id'] == ENTITY)
            assert registered['platform'] == 'tcl_home_unofficial' and registered['device_id'] == DEVICE
            before = await state()
            assert before['state'] not in ('unknown', 'unavailable')
            if not args.apply:
                print(json.dumps({'entity': ENTITY, 'existing': before, 'revision': policy['revision'], 'apply': False}))
                return
            backup = Path('/config/control_center/backups') / ('tcl-binding-' + datetime.now(ZoneInfo('Europe/Bucharest')).strftime('%Y%m%d-%H%M%S'))
            backup.mkdir(mode=0o700)
            (backup / 'policy-before.json').write_text(json.dumps(policy), encoding='utf-8')
            (backup / 'entity-before.json').write_text(json.dumps(registered), encoding='utf-8')
            (backup / 'device-before.json').write_text(json.dumps(next(d for d in await call({'type': 'config/device_registry/list'}) if d['id'] == DEVICE)), encoding='utf-8')
            for file in backup.iterdir(): file.chmod(0o600)
            device = next(d for d in await call({'type': 'config/device_registry/list'}) if d['id'] == DEVICE)
            areas = await call({'type': 'config/area_registry/list'})
            assert any(a['area_id'] == 'living_room' for a in areas)
            if device.get('area_id') != 'living_room':
                await call({'type': 'config/device_registry/update', 'device_id': DEVICE, 'area_id': 'living_room'})
            if registered.get('area_id') not in (None, 'living_room'):
                await call({'type': 'config/entity_registry/update', 'entity_id': ENTITY, 'area_id': 'living_room'})
            if not registered.get('name'):
                await call({'type': 'config/entity_registry/update', 'entity_id': ENTITY, 'name': 'TCL FreshIN'})
            result = await call({'type': 'call_service', 'domain': 'home_energy_policy', 'service': 'configure',
                                 'service_data': {'revision': policy['revision'], 'values': {'tcl_entity': ENTITY, 'tcl_enabled': True,
                                                  'tcl_fan1': '1', 'tcl_fan2': '2', 'tcl_fan3': '3', 'tcl_fan_boost': '6'}},
                                 'return_response': True})
            after = result['response']
            assert after['config']['ev_enabled'] == policy['config']['ev_enabled']
            hold = after['status']['devices']['tcl']['manual_until']
            if before['state'] != 'off':
                assert hold > time.time(), 'Existing manual AC settings were not protected'
                assert await state() == before, 'AC settings changed during binding'
            print(json.dumps({'entity': ENTITY, 'revision': after['revision'], 'existing_settings': before,
                              'manual_until': datetime.fromtimestamp(hold, ZoneInfo('Europe/Bucharest')).isoformat() if hold else None,
                              'policy_state': after['status']['devices']['tcl'], 'backup': str(backup), 'direct_ac_commands': 0}))


asyncio.run(main())
