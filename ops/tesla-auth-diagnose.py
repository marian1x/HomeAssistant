"""Read-only local Tesla diagnostics; never prints tokens, account IDs or VINs."""
import base64
import json
from pathlib import Path
import re
import sys


def redact(text):
    text = re.sub(r'[\w.+-]+@[\w.-]+', '[account]', text)
    text = re.sub(r'\b[A-HJ-NPR-Z0-9]{17}\b', '[VIN]', text)
    text = re.sub(r'\b(?:EU_|NA_)?[A-Za-z0-9_./+=-]{45,}\b', '[redacted]', text)
    text = re.sub(r'(?i)(bearer|refresh_token|access_token|client_secret|password)[\s\":=]+[^\s,}\"]+', r'\1=[redacted]', text)
    return text


if '--logs' in sys.argv:
    lines = sys.stdin.read().splitlines()
    selected = set()
    for i, line in enumerate(lines):
        if ('tesla_custom' in line or 'teslajsonpy' in line) and any(k in line.lower() for k in ('error','warning','auth','exception')):
            selected.update(range(max(0,i-1), min(len(lines),i+35)))
    print(redact('\n'.join(lines[i] for i in sorted(selected)))[-16000:])
    sys.exit(0)

entries = json.loads(Path('/config/.storage/core.config_entries').read_text())['data']['entries']
for entry in entries:
    if entry['domain'] not in ('tesla_custom','tesla_fleet'):
        continue
    data = entry['data']
    info = {'domain':entry['domain'], 'modified_at':entry.get('modified_at'), 'keys':sorted(data),
            'proxy':data.get('api_proxy_url'), 'auth_domain':data.get('domain'),
            'has_client_id':bool(data.get('client_id')), 'initial_setup':data.get('initial_setup'),
            'options':entry.get('options')}
    token = data.get('access_token') or ''
    info['has_access_token'] = bool(token)
    info['has_refresh_token'] = bool(data.get('token'))
    if token.count('.') == 2:
        try:
            part = token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
            info['unverified_access_claims'] = {k:claims[k] for k in ('aud','scope','scp','exp','iss') if k in claims}
        except (ValueError, TypeError):
            pass
    cert = data.get('api_proxy_cert')
    info['proxy_cert_exists'] = bool(cert and Path(cert).is_file())
    print(json.dumps(info))

for filename in ('home-assistant.log','home-assistant.log.1'):
    log = Path('/config')/filename
    if not log.exists(): continue
    lines = log.read_text(errors='replace').splitlines()[-5000:]
    for i,line in enumerate(lines):
        if any(key in line.lower() for key in ('tesla_custom','teslajsonpy','tesla api')) and any(key in line.lower() for key in ('error','warning','exception','traceback','auth')):
            print(redact('\n'.join(lines[max(0,i-1):min(len(lines),i+18)]))[:3000])
