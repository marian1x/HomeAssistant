"""Casa-only accounts (owner decision 2026-11-10): scrypt passwords and RFC 6238 TOTP.

Standard library only. Secrets never leave the server except the one-time temporary
password shown to the administrator and the TOTP secret shown once during enrollment.
"""
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

USERNAME = re.compile(r'^[a-z0-9][a-z0-9._-]{2,31}$')
ROLES = ('viewer', 'control', 'configure')
MIN_PASSWORD = 12
SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1}
MAXMEM = 64 * 1024 * 1024
STEP = 30
ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, maxmem=MAXMEM, **SCRYPT)
    return 'scrypt$%d$%d$%d$%s$%s' % (SCRYPT['n'], SCRYPT['r'], SCRYPT['p'],
                                      base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


# Unknown users are checked against this hash so the response time does not reveal them.
DUMMY = hash_password(secrets.token_urlsafe(16))


def check_password(password, stored):
    try:
        _, n, r, p, salt, digest = (stored or DUMMY).split('$')
        actual = hashlib.scrypt(str(password).encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=32, maxmem=MAXMEM)
        return hmac.compare_digest(actual, base64.b64decode(digest)) and stored is not None
    except (ValueError, TypeError):
        return False


def password_problem(password, username=''):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f'Parola trebuie sa aiba cel putin {MIN_PASSWORD} caractere.'
    if len(password) > 128:
        return 'Parola este prea lunga.'
    if username and username.lower() in password.lower():
        return 'Parola nu poate contine numele de utilizator.'
    return None


def temporary_password():
    raw = ''.join(secrets.choice(ALPHABET) for _ in range(16))
    return '-'.join(raw[i:i + 4] for i in range(0, 16, 4))


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def code_at(secret, counter):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = mac[-1] & 15
    return '%06d' % ((struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7fffffff) % 1_000_000)


def totp_step(secret, code, last_step=0, now=None):
    """Matched time step, or None. One step of clock drift; a used step is never accepted again."""
    code = re.sub(r'\s', '', str(code or ''))
    if not secret or not re.fullmatch(r'\d{6}', code):
        return None
    current = int((time.time() if now is None else now) // STEP)
    for step in (current - 1, current, current + 1):
        if step > last_step and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def otpauth(secret, username):
    label = quote('Casa Salavat:' + username)
    return f'otpauth://totp/{label}?secret={secret}&issuer=Casa%20Salavat&algorithm=SHA1&digits=6&period={STEP}'
