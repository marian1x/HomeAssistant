"""Final metadata/verification audit, run inside the Google Drive Backup app."""
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request


with urllib.request.urlopen('http://127.0.0.1:8099/getstatus',timeout=30) as response:
    status=json.load(response)
assert not status['syncing'] and status['last_error'] is None, 'Wait for upload/sync completion'
checks={}
for file in ('/data/retention-five-integrity.json','/data/retention-final-new-integrity.json'):
    for row in json.loads(Path(file).read_text()):checks[row['slug']]=row
drive=[b for b in status['backups'] if any(s['key']=='GoogleDrive' for s in b['sources'])]
local=[b for b in status['backups'] if any(s['key']=='HomeAssistant' for s in b['sources'])]
assert len(drive)==5 and len(local)==5
assert {b['slug'] for b in drive}=={b['slug'] for b in local}
final=[]
for backup in sorted(drive,key=lambda b:b['timestamp'],reverse=True):
    row=checks[backup['slug']]
    assert row['full'] and row['sqlite_quick_check']=='ok' and backup['status']=='Backed Up'
    size=next(s['size'] for s in backup['sources'] if s['key']=='GoogleDrive')
    assert size==row['size_bytes']==(Path('/backup')/(backup['slug']+'.tar')).stat().st_size
    final.append(row)
for file in ('/data/retention-five-integrity.json','/data/retention-five-final-audit.json'):
    path=Path(file)
    path.write_text(json.dumps(final,indent=2))
    path.chmod(0o600)
summary={'checked_at':datetime.now(timezone.utc).isoformat(),'full_backups_local':5,'full_backups_drive':5,
         'drive_bytes':sum(r['size_bytes'] for r in final),'sqlite_all_ok':True,
         'restored_on_spare_hardware':False,'backups':[{k:r[k] for k in ('slug','date','size_bytes')} for r in final]}
print(json.dumps(summary))
