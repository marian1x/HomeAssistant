"""One token exchange at Tesla's documented endpoint. No vehicle API calls."""
import asyncio
import json
import os
from pathlib import Path
import time
import aiohttp


async def main():
    entries = json.loads(Path('/config/.storage/core.config_entries').read_text())['data']['entries']
    entry = next(e for e in entries if e['domain'] == 'tesla_custom')
    data = entry['data']
    folder = Path('/config/control_center/private')
    folder.mkdir(mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    result_file = folder/'tesla-oauth-recovery.json'
    if result_file.exists():
        print(json.dumps({'test_skipped':'A successful exchange was already saved. No repeated rotation.'}))
        return
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
        async with session.post('https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token', data={'grant_type':'refresh_token','client_id':data['client_id'],'refresh_token':data['token']}) as response:
            result = await response.json(content_type=None)
            output = {'http_status':response.status, 'authenticated':bool(result.get('access_token') and result.get('refresh_token')), 'vehicle_calls':0}
            if output['authenticated']:
                fd = os.open(result_file, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
                with os.fdopen(fd,'w') as file:
                    json.dump({'entry_id':entry['entry_id'],'tested_at':time.time(),'result':result},file)
                output['token_saved_locally'] = True
            else:
                error = result.get('error')
                output['error'] = error if error in ('invalid_grant','invalid_client','login_required','invalid_request','invalid_token','unauthorized_client') else 'OAuth exchange rejected'
                description = result.get('error_description','').lower()
                for phrase in ('expired','revoked','client_id','client id','invalid refresh token','invalid token','login required','not found'):
                    if phrase in description: output.setdefault('diagnostic_keywords',[]).append(phrase)
            print(json.dumps(output))


asyncio.run(main())
