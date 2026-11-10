"""Small encrypted server-side session store. Cookies contain only random handles."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from cryptography.fernet import Fernet

# Owner decision 2026-11-10: a session ends after 30 days without use. Use renews
# the expiry (and the cookie) at most once per hour to avoid a write per request.
SESSION_IDLE = 30 * 24 * 3600
RENEW_AFTER = 3600


class Store:
    def __init__(self, path):
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        key_path = root / 'secret.key'
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as file:
                file.write(Fernet.generate_key())
        self.crypto = Fernet(key_path.read_bytes())
        self.db = sqlite3.connect(root / 'app.sqlite', check_same_thread=False)
        os.chmod(root / 'app.sqlite', 0o600)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload BLOB, expires REAL);
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT, role TEXT DEFAULT 'viewer');
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at REAL, actor TEXT, action TEXT, entity TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS local_users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer', password TEXT NOT NULL, totp BLOB, totp_step INTEGER NOT NULL DEFAULT 0,
                must_change INTEGER NOT NULL DEFAULT 1, failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
                disabled INTEGER NOT NULL DEFAULT 0, created REAL, created_by TEXT, last_login REAL);
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(users)')}
        if 'is_admin' not in columns:
            self.db.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
        # HA user id of the session (not secret), used for renewal and "log out everywhere".
        if 'user' not in {row[1] for row in self.db.execute('PRAGMA table_info(sessions)')}:
            self.db.execute('ALTER TABLE sessions ADD COLUMN user TEXT')
        self.db.commit()

    def create(self, data):
        handle = secrets.token_urlsafe(40)
        sid = hashlib.sha256(handle.encode()).hexdigest()
        data['csrf'] = secrets.token_urlsafe(32)
        self.save(sid, data, time.time() + SESSION_IDLE)
        return handle, sid

    def save(self, sid, data, expires=None):
        if expires is None:
            row = self.db.execute('SELECT expires FROM sessions WHERE id=?', (sid,)).fetchone()
            if not row:
                return
            expires = row[0]
        self.db.execute('INSERT INTO sessions(id,payload,expires) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, expires=excluded.expires',
                        (sid, self.crypto.encrypt(json.dumps(data).encode()), expires))
        self.db.commit()

    def bind(self, sid, user_id):
        self.db.execute('UPDATE sessions SET user=? WHERE id=? AND expires > ?', (user_id, sid, time.time()))
        self.db.commit()

    def owner(self, sid):
        row = self.db.execute('SELECT user FROM sessions WHERE id=? AND expires > ?', (sid, time.time())).fetchone()
        return row[0] if row else None

    def renew(self, handle):
        """Slide a live, user-bound session to SESSION_IDLE from now; True when renewed."""
        sid, now = hashlib.sha256(handle.encode()).hexdigest(), time.time()
        cursor = self.db.execute('UPDATE sessions SET expires=? WHERE id=? AND user IS NOT NULL AND expires > ? AND expires < ?',
                                 (now + SESSION_IDLE, sid, now, now + SESSION_IDLE - RENEW_AFTER))
        self.db.commit()
        return cursor.rowcount == 1

    def expire_user(self, user_id, keep=None):
        # The technical HA account row ('service') is never a user session.
        now = time.time()
        sids = [row[0] for row in self.db.execute('SELECT id FROM sessions WHERE user=? AND expires > ? AND id NOT IN (?, ?)',
                                                  (user_id, now, 'service', keep or ''))]
        self.db.executemany('UPDATE sessions SET expires=0 WHERE id=?', [(sid,) for sid in sids])
        self.db.commit()
        return sids

    LOCAL_FIELDS = ('id', 'username', 'name', 'role', 'password', 'totp', 'totp_step', 'must_change', 'failures',
                    'locked_until', 'disabled', 'created', 'created_by', 'last_login')

    def local_get(self, user_id=None, username=None):
        column, value = ('id', user_id) if user_id is not None else ('username', username)
        row = self.db.execute(f'SELECT {",".join(self.LOCAL_FIELDS)} FROM local_users WHERE {column}=?', (value,)).fetchone()
        if not row:
            return None
        account = dict(zip(self.LOCAL_FIELDS, row))
        account['totp'] = self.crypto.decrypt(account['totp']).decode() if account['totp'] else None
        return account

    def local_list(self):
        rows = self.db.execute('SELECT id,username,name,role,totp IS NOT NULL,must_change,disabled,locked_until,created,last_login '
                               'FROM local_users ORDER BY name COLLATE NOCASE').fetchall()
        return [{'id': r[0], 'username': r[1], 'name': r[2], 'role': r[3], 'enrolled': bool(r[4]), 'must_change': bool(r[5]),
                 'disabled': bool(r[6]), 'locked': r[7] > time.time(), 'created': r[8], 'last_login': r[9]} for r in rows]

    def local_create(self, username, name, role, password_hash, created_by):
        user_id = 'local:' + secrets.token_hex(8)
        self.db.execute('INSERT INTO local_users(id,username,name,role,password,created,created_by) VALUES (?,?,?,?,?,?,?)',
                        (user_id, username, name, role, password_hash, time.time(), created_by))
        self.db.commit()
        return user_id

    def local_update(self, user_id, **fields):
        allowed = {'name', 'role', 'password', 'totp', 'totp_step', 'must_change', 'failures', 'locked_until', 'disabled', 'last_login'}
        if not fields or not set(fields) <= allowed:
            raise ValueError('Unsupported local user field')
        if 'totp' in fields and fields['totp'] is not None:
            fields['totp'] = self.crypto.encrypt(fields['totp'].encode())
        self.db.execute(f'UPDATE local_users SET {",".join(k + "=?" for k in fields)} WHERE id=?', (*fields.values(), user_id))
        self.db.commit()

    def local_failed(self, user_id, limit=5, lock=900):
        self.db.execute('UPDATE local_users SET failures=failures+1 WHERE id=?', (user_id,))
        self.db.execute('UPDATE local_users SET failures=0, locked_until=? WHERE id=? AND failures>=?', (time.time() + lock, user_id, limit))
        self.db.commit()

    def local_delete(self, user_id):
        self.db.execute('DELETE FROM local_users WHERE id=?', (user_id,))
        self.db.commit()

    def get(self, sid):
        row = self.db.execute('SELECT payload,expires FROM sessions WHERE id=?', (sid,)).fetchone()
        if not row or row[1] <= time.time():
            return None
        return json.loads(self.crypto.decrypt(row[0]))

    def identify(self, handle):
        sid = hashlib.sha256(handle.encode()).hexdigest()
        return sid, self.get(sid)

    def remove(self, sid):
        self.db.execute('DELETE FROM sessions WHERE id=?', (sid,))
        self.db.commit()

    def expire(self, sid):
        self.db.execute('UPDATE sessions SET expires=0 WHERE id=?', (sid,))
        self.db.commit()

    def expired(self):
        return [(row[0], json.loads(self.crypto.decrypt(row[1]))) for row in self.db.execute('SELECT id,payload FROM sessions WHERE expires <= ?', (time.time(),))]

    def user(self, profile):
        self.db.execute('INSERT INTO users(id,name,is_admin) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,is_admin=excluded.is_admin', (profile['id'], profile.get('name', 'Utilizator'), int(profile.get('is_admin') is True)))
        self.db.commit()
        role = self.db.execute('SELECT role FROM users WHERE id=?', (profile['id'],)).fetchone()[0]
        return 'configure' if profile.get('is_admin') is True else role if role in ('viewer', 'control') else 'viewer'

    def log(self, actor, action, entity, result):
        self.db.execute('INSERT INTO audit(at,actor,action,entity,result) VALUES (?,?,?,?,?)', (time.time(), actor, action, entity, result))
        self.db.execute('DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 10000)')
        self.db.commit()

    def prune(self):
        self.db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        self.db.commit()
