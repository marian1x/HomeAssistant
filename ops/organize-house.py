"""Organize HA registries through supported APIs; never operate physical devices."""
import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path

import aiohttp


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--plan', default='/config/control_center/house-layout.json')
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    token = os.environ['CONTROL_TOKEN']
    base = 'http://supervisor/core/api'
    async with aiohttp.ClientSession(headers={'Authorization': 'Bearer ' + token}) as session:
        async def api(method, path, data=None):
            async with session.request(method, base + path, json=data) as response:
                response.raise_for_status()
                return await response.json()

        async with session.ws_connect(base + '/websocket') as ws:
            assert (await ws.receive_json())['type'] == 'auth_required'
            await ws.send_json({'type': 'auth', 'access_token': token})
            assert (await ws.receive_json())['type'] == 'auth_ok'
            sequence = 0

            async def call(message):
                nonlocal sequence
                sequence += 1
                await ws.send_json({'id': sequence, **message})
                while True:
                    packet = await ws.receive_json()
                    if packet.get('id') == sequence:
                        if not packet.get('success'):
                            raise RuntimeError(packet.get('error'))
                        return packet.get('result')

            async def registries():
                return {kind: await call({'type': f'config/{kind}_registry/list'}) for kind in ('floor', 'area', 'device', 'entity')}

            before = await registries()
            states_before = {s['entity_id']: s for s in await api('GET', '/states')}
            controls_before = {id: s['state'] for id, s in states_before.items() if id.startswith('automation.') or id == 'input_boolean.ha_automation_killswitch'}
            if not args.apply:
                print(json.dumps({'floors': before['floor'], 'areas': before['area'], 'declared_items': len(plan['items']), 'apply': False}))
                return
            backup = Path('/config/control_center/backups') / ('house-layout-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            backup.mkdir(parents=True, exist_ok=False)
            (backup / 'registries.json').write_text(json.dumps(before, ensure_ascii=True, indent=2))
            (backup / 'control-states.json').write_text(json.dumps(controls_before, indent=2))
            floors = {f['name']: f for f in before['floor']}
            changes = []
            for spec in plan['floors']:
                if spec['name'] not in floors:
                    floors[spec['name']] = await call({'type': 'config/floor_registry/create', **spec})
                    changes.append('floor:' + spec['name'])
            areas = {a['area_id']: a for a in before['area']}
            rooms = {}
            for spec in plan['rooms']:
                area = areas.get(spec.get('ha_area_id')) or next((a for a in areas.values() if a['name'] == spec['name']), None)
                desired = {'name': spec['name'], 'floor_id': floors[spec['floor']]['floor_id'], 'icon': spec.get('icon')}
                if area is None:
                    area = await call({'type': 'config/area_registry/create', **desired})
                    areas[area['area_id']] = area
                    changes.append('area:create:' + spec['name'])
                else:
                    update = {key: val for key, val in desired.items() if area.get(key) != val}
                    if area['name'] != spec['name']:
                        update['aliases'] = sorted(set(area.get('aliases', [])) | {area['name']})
                    if update:
                        area = await call({'type': 'config/area_registry/update', 'area_id': area['area_id'], **update})
                        changes.append('area:update:' + spec['name'])
                rooms[spec['key']] = area['area_id']
            devices = {d['id']: d for d in before['device']}
            assignments = {}
            for item in plan['items']:
                for device_id in item.get('device_ids', []):
                    if device_id in devices:
                        target = rooms[item['room']]
                        if device_id in assignments and assignments[device_id] != target:
                            raise ValueError('Conflicting room for device ' + device_id)
                        assignments[device_id] = target
            for device_id, area_id in assignments.items():
                if devices[device_id].get('area_id') != area_id:
                    await call({'type': 'config/device_registry/update', 'device_id': device_id, 'area_id': area_id})
                    changes.append('device:' + device_id)
            for entry in before['entity']:
                area_id = assignments.get(entry.get('device_id'))
                if area_id and entry.get('area_id') and entry['area_id'] != area_id:
                    await call({'type': 'config/entity_registry/update', 'entity_id': entry['entity_id'], 'area_id': area_id})
                    changes.append('entity-area:' + entry['entity_id'])
            for room, entity in (('bedroom-main', 'sensor.hvac_upstairs_temperature'), ('living', 'sensor.hvac_downstairs_temperature')):
                if entity in states_before:
                    await call({'type': 'config/area_registry/update', 'area_id': rooms[room], 'temperature_entity_id': entity})
            helper = 'input_text.ariston_boiler_entity_id'
            if 'water_heater.boiler' in states_before and states_before.get(helper, {}).get('state') != 'water_heater.boiler':
                # This changes a lookup helper, never the boiler's operating state.
                await api('POST', '/services/input_text/set_value', {'entity_id': helper, 'value': 'water_heater.boiler'})
                changes.append('helper:boiler-reference')
            after = await registries()
            actual = {d['id']: d.get('area_id') for d in after['device']}
            assert all(actual.get(id) == area for id, area in assignments.items())
            states_after = {s['entity_id']: s for s in await api('GET', '/states')}
            assert all(states_after.get(id, {}).get('state') == state for id, state in controls_before.items()), 'Automation states changed; inspect before proceeding'
            if 'water_heater.boiler' in states_before:
                assert states_after['water_heater.boiler']['attributes'].get('temperature') == states_before['water_heater.boiler']['attributes'].get('temperature'), 'Boiler target changed unexpectedly'
            (backup / 'changes.json').write_text(json.dumps(changes, indent=2))
            print(json.dumps({'backup': str(backup), 'changes': changes, 'assigned_devices': len(assignments), 'rooms': rooms, 'automation_states_preserved': True, 'physical_commands': 0}, ensure_ascii=True))


asyncio.run(main())
