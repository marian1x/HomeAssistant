"""Read-only HA activation and Tesla enrollment audit; never prints credentials."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import yaml


async def main():
    token = os.environ['CONTROL_TOKEN']
    async with aiohttp.ClientSession(headers={'Authorization': 'Bearer ' + token}) as session:
        async def get(url):
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()
        states = {s['entity_id']: s for s in await get('http://supervisor/core/api/states')}
        selected = []
        for id, s in states.items():
            if id.startswith('automation.') or id.startswith(('input_boolean.hvac_', 'input_select.hvac_', 'input_boolean.ariston_', 'input_boolean.tesla_', 'input_number.hvac_')) or id in ('input_boolean.ha_automation_killswitch', 'scene.ha_automations_before_killswitch') or id.split('.')[0] in ('water_heater', 'climate', 'media_player'):
                attrs = s['attributes']
                selected.append({'id': id, 'state': s['state'], 'attributes': {k: attrs[k] for k in ('friendly_name', 'id', 'current_temperature', 'temperature', 'hvac_modes', 'operation_list', 'supported_features', 'volume_level', 'is_volume_muted') if k in attrs}})
        print(json.dumps({'states': selected}))
        automations = []
        for path in Path('/config/packages').glob('*.yaml'):
            if path.name.startswith('tesla_'):
                continue
            data = yaml.safe_load(path.read_text()) or {}
            for rule in data.get('automation', []):
                automations.append({'file': path.name, 'id': rule.get('id'), 'alias': rule.get('alias'), 'triggers': rule.get('triggers', rule.get('trigger')), 'conditions': rule.get('conditions', rule.get('condition'))})
        print(json.dumps({'rules': automations}, default=str))
        entries = json.loads(Path('/config/.storage/core.config_entries').read_text())['data']['entries']
        tesla = next((e for e in entries if e['domain'] == 'tesla_custom'), None)
        if tesla:
            data, options = tesla.get('data', {}), tesla.get('options', {})
            proxy = urlparse(data.get('api_proxy_url', ''))
            print(json.dumps({'tesla': {'entry_id': tesla['entry_id'], 'has_refresh_token': bool(data.get('token')), 'has_access_token': bool(data.get('access_token')), 'has_client_id': bool(data.get('client_id')), 'proxy_url': proxy.scheme + '://' + proxy.netloc + proxy.path if proxy.netloc else None, 'custom_cert_exists': Path(data['api_proxy_cert']).exists() if data.get('api_proxy_cert') else None, 'options': {k: options[k] for k in ('scan_interval', 'polling_policy', 'enable_wake_on_start') if k in options}, 'data_keys': list(data)}}))
        addons = (await get('http://supervisor/addons'))['data']['addons']
        for addon in addons:
            if 'tesla' in addon['name'].lower():
                info = (await get('http://supervisor/addons/' + addon['slug'] + '/info'))['data']
                options = info.get('options', {})
                print(json.dumps({'tesla_addon': {'slug': addon['slug'], 'name': addon['name'], 'state': info.get('state'), 'version': info.get('version'), 'option_presence': {k: bool(v) for k, v in options.items()}, 'ports': info.get('network')}}))
        log = Path('/config/home-assistant.log')
        if log.exists():
            lines = [line.lower() for line in log.read_text(errors='replace').splitlines() if 'tesla' in line.lower()]
            flags = {word: sum(word in line for line in lines[-200:]) for word in ('invalid_grant', 'invalid_client', 'unauthorized', 'forbidden', 'too_many_requests', 'quota', 'expired', 'setup', 'auth', 'keyerror', 'cannot import', '401', '403', '429')}
            print(json.dumps({'tesla_log_flags': {k: v for k, v in flags.items() if v}}))


asyncio.run(main())
