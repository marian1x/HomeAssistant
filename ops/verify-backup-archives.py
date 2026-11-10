"""Read backup archives and SQLite copies, never restore or modify live HA data."""
import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile


def verify(slug):
    if len(slug) != 8 or any(c not in '0123456789abcdef' for c in slug):
        raise ValueError('Invalid backup slug')
    path = Path('/backup') / (slug + '.tar')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            digest.update(chunk)
    with tarfile.open(path, 'r:') as archive:
        metadata_name=next(n for n in archive.getnames() if n.lstrip('./') in ('backup.json','snapshot.json'))
        metadata = json.load(archive.extractfile(metadata_name))
        assert metadata['type'] == 'full' and not metadata.get('protected'), 'Expected a readable full backup'
        inner_name = next(n for n in archive.getnames() if n.lstrip('./') == 'homeassistant.tar.gz')
        present = set()
        with tempfile.TemporaryDirectory(prefix='ha-backup-check-') as directory:
            root = Path(directory)
            with archive.extractfile(inner_name) as nested:
                with gzip.GzipFile(fileobj=nested,mode='rb') as decoded:
                    with tarfile.open(fileobj=decoded,mode='r|') as inner:
                        for member in inner:
                            if not member.isfile(): continue
                            name = member.name.lstrip('./')
                            present.add(name)
                            base = Path(name).name
                            with inner.extractfile(member) as stream:
                                if base in ('home-assistant_v2.db','home-assistant_v2.db-wal','home-assistant_v2.db-shm'):
                                    with (root/base).open('wb') as output: shutil.copyfileobj(stream,output)
                                else:
                                    for _ in iter(lambda: stream.read(1024*1024),b''): pass
                    # Reading the gzip trailer verifies its CRC, beyond tar's EOF.
                    while decoded.read(1024*1024): pass
            for item in archive.getmembers():
                if item.name != inner_name and item.name.endswith('.tar.gz'):
                    with archive.extractfile(item) as source, gzip.GzipFile(fileobj=source) as decoded:
                        while decoded.read(1024*1024): pass
            assert any(n.endswith('configuration.yaml') for n in present)
            assert any(n.endswith('.storage/core.config_entries') for n in present)
            db = root/'home-assistant_v2.db'
            assert db.is_file() and db.stat().st_size>0, 'History database missing'
            with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
                result = [r[0] for r in conn.execute('PRAGMA quick_check')]
                assert result == ['ok'], 'SQLite integrity check failed'
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                assert {'states','statistics'}.issubset(tables)
                states = conn.execute('SELECT COUNT(*) FROM states').fetchone()[0]
                statistics = conn.execute('SELECT COUNT(*) FROM statistics').fetchone()[0]
            return {'slug':slug,'date':metadata['date'],'size_bytes':path.stat().st_size,'sha256':digest.hexdigest(),
                    'full':True,'sqlite_quick_check':'ok','history_rows':states,'statistics_rows':statistics,
                    'checked_at':datetime.now(timezone.utc).isoformat(),'restored_on_spare_hardware':False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('slugs',nargs='+')
    parser.add_argument('--report',required=True)
    args=parser.parse_args()
    report=[]
    for slug in args.slugs:
        result=verify(slug)
        report.append(result)
        print(json.dumps(result),flush=True)
    target=Path(args.report)
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    target.chmod(0o600)


if __name__=='__main__': main()
