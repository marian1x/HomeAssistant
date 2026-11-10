"""Run inside the Drive app: scope deletion to its own verified backup inventory."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request
import sys
sys.path.insert(0,'/app')
from backup.config.config import UPGRADE_OPTIONS


def api(path,data=None):
    request=urllib.request.Request('http://127.0.0.1:8099/'+path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=180) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    report=json.loads(Path('/data/retention-five-integrity.json').read_text())
    assert len(report)==5 and all(r['full'] and r['sqlite_quick_check']=='ok' for r in report)
    keep={r['slug'] for r in report}
    status=api('getstatus')
    full=sorted((b for b in status['backups'] if b['type']=='full'),key=lambda b:b['timestamp'],reverse=True)
    assert keep=={b['slug'] for b in full[:5]}, 'Inventory changed: reverify the latest five full backups'
    for row in report:
        assert (datetime.now(timezone.utc)-datetime.fromisoformat(row['checked_at'])).total_seconds()<86400
        backup=next(b for b in full if b['slug']==row['slug'])
        assert backup['status']=='Backed Up', 'Wait for all five uploads to complete'
        remote=next(s for s in backup['sources'] if s['key']=='GoogleDrive')
        assert remote['size']==row['size_bytes'], 'Uploaded size differs from checked archive'
    partials=[b for b in status['backups'] if b['type']=='partial' and not any(s['retained'] for s in b['sources'])]
    print(json.dumps({'keep':sorted(keep),'partial_copies_to_remove':len(partials),'apply':args.apply}),flush=True)
    if not args.apply:return
    settings=api('getconfig')
    audit=Path('/data/retention-five-before.json')
    if not audit.exists():
        audit.write_text(json.dumps({'backups':status['backups'],'settings':settings},indent=2))
        audit.chmod(0o600)
    # Remove only upgrade/partial backup records already covered by the verified full copies.
    deleted=[]
    for backup in partials:
        api('deleteSnapshot',{'slug':backup['slug'],'sources':[s['key'] for s in backup['sources']]})
        deleted.append(backup['slug'])
        print(json.dumps({'removed_partial':backup['slug']}),flush=True)
    deprecated={setting.key() for setting in UPGRADE_OPTIONS}
    config={key:value for key,value in settings['config'].items() if key not in deprecated}
    config.update(max_backups_in_ha=5,max_backups_in_google_drive=5,days_between_backups=0,
        ignore_other_backups=False,ignore_upgrade_backups=True,delete_ignored_after_days=1,
        delete_before_new_backup=False,delete_after_upload=False,
        generational_days=0,generational_weeks=0,generational_months=0,generational_years=0,
        enable_drive_upload=True,confirm_multiple_deletes=True,exclude_ha_database=False,call_backup_snapshot=False)
    api('saveconfig',{'config':config,'backup_folder':settings['backup_folder']})
    pending=api('getstatus')
    deadline=time.monotonic()+300
    while pending['syncing'] and time.monotonic()<deadline:
        time.sleep(2)
        pending=api('getstatus')
    assert not pending['syncing'], 'Sync still running; inspect before another cleanup'
    remaining_drive={b['slug'] for b in pending['backups'] if any(s['key']=='GoogleDrive' for s in b['sources'])}
    # Owner authorized this one cleanup; retain the mass-deletion safeguard for future syncs.
    if remaining_drive!=keep:
        assert keep.issubset(remaining_drive)
        assert {b['slug'] for b in sorted((b for b in pending['backups'] if b['type']=='full'),key=lambda b:b['timestamp'],reverse=True)[:5]}==keep
        api('confirmdelete?always=false')
    after=api('getstatus')
    assert {b['slug'] for b in after['backups'] if any(s['key']=='GoogleDrive' for s in b['sources'])}==keep
    print(json.dumps({'removed_partials':deleted,'remaining':[{k:b[k] for k in ('slug','name','type','status')} for b in after['backups']],
                      'syncing':after['syncing'],'error_present':after['last_error'] is not None}),flush=True)


if __name__=='__main__':main()
