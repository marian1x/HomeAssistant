"""Normalize app UI settings without deprecated aliases or a retention change."""
import json
import urllib.request
import sys
sys.path.insert(0,'/app')
from backup.config.config import UPGRADE_OPTIONS


def api(path,data=None):
    request=urllib.request.Request('http://127.0.0.1:8099/'+path,
        data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)


settings=api('getconfig')
deprecated={setting.key() for setting in UPGRADE_OPTIONS}
config={k:v for k,v in settings['config'].items() if k not in deprecated}
config['call_backup_snapshot']=False
assert config['max_backups_in_ha']==config['max_backups_in_google_drive']==5
api('saveconfig',{'config':config,'backup_folder':settings['backup_folder']})
after=api('getconfig')['config']
assert not after['call_backup_snapshot'] and after['max_backups_in_google_drive']==5
print('Backup state reporting restored; five-copy retention unchanged.')
