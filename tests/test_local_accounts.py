"""Casa-only accounts: passwords, TOTP, roles, lockout and the technical HA account."""
import asyncio
import base64
import time

import pytest
from fastapi.testclient import TestClient

from test_security import FakePeer, client, signin  # noqa: F401 (fixture re-export)
from server import app as module
from server.accounts import check_password, code_at, hash_password, password_problem, temporary_password, totp_step

ORIGIN = {'Origin': 'https://salavat.home.ro'}


def code(secret, offset=0):
    return code_at(secret, int(time.time() // 30) + offset)


def connect_service():
    module.store.save(module.SERVICE, {'access_token': 's', 'refresh_token': 'service-refresh', 'expires_at': time.time() + 3600, 'csrf': ''}, module.SERVICE_EXPIRES)


def create_user(admin, headers, username='ana', role='viewer'):
    response = admin.post('/casa/api/local-users', json={'username': username, 'name': 'Ana Pop', 'role': role}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def local_login(username, password, new_password='o parola noua lunga', offset=0, secret=None):
    """Full login in a separate browser; returns (client, secret, csrf headers)."""
    browser = TestClient(module.app, base_url='https://salavat.home.ro')
    first = browser.post('/casa/auth/local', json={'username': username, 'password': password}, headers=ORIGIN)
    assert first.status_code == 200, first.text
    body = first.json()
    if 'enroll' in body:
        secret = body['enroll']['secret']
        assert body['enroll']['uri'].startswith('otpauth://totp/Casa%20Salavat%3A' + username)
    answer = {'code': code(secret, offset), **({'new_password': new_password} if body['must_change'] else {})}
    done = browser.post('/casa/auth/local/verify', json=answer, headers=ORIGIN)
    assert done.status_code == 200, done.text
    session = browser.get('/casa/api/session')
    assert session.status_code == 200, session.text
    return browser, secret, {**ORIGIN, 'X-CSRF-Token': session.json()['csrf']}


def test_totp_matches_rfc6238_and_never_accepts_a_used_code():
    secret = base64.b32encode(b'12345678901234567890').decode()
    assert code_at(secret, 59 // 30) == '287082' and code_at(secret, 1111111109 // 30) == '081804'
    assert totp_step(secret, '287 082', now=59) == 1
    assert totp_step(secret, '287082', last_step=1, now=59) is None
    assert totp_step(secret, '000000', now=59) is None and totp_step(secret, 'abcdef', now=59) is None


def test_passwords_are_salted_scrypt_and_policy_is_enforced():
    stored = hash_password('o parola destul de lunga')
    assert stored.startswith('scrypt$') and 'parola' not in stored and stored != hash_password('o parola destul de lunga')
    assert check_password('o parola destul de lunga', stored) and not check_password('alta parola lunga', stored)
    assert not check_password('orice', None)
    assert password_problem('scurta') and password_problem('ana-are-mere-123', 'ana') and password_problem('x' * 129)
    assert password_problem('o parola destul de lunga', 'ana') is None
    assert len(temporary_password()) == 19 and password_problem(temporary_password()) is None


def test_first_login_requires_new_password_and_valid_code(client):
    _, headers = signin(client)
    created = create_user(client, headers)
    connect_service()
    browser = TestClient(module.app, base_url='https://salavat.home.ro')
    assert browser.post('/casa/auth/local', json={'username': 'ana', 'password': created['password']}).status_code == 403, 'Origin is required'
    assert browser.post('/casa/auth/local', json={'username': 'ana', 'password': 'gresita gresita'}, headers=ORIGIN).status_code == 401
    assert browser.post('/casa/auth/local', json={'username': 'nimeni', 'password': 'gresita gresita'}, headers=ORIGIN).json()['error'] == 'Utilizator sau parola gresita.'
    secret = browser.post('/casa/auth/local', json={'username': 'ANA ', 'password': created['password']}, headers=ORIGIN).json()['enroll']['secret']
    assert browser.get('/casa/api/session').status_code == 401, 'Password alone never creates a session'
    assert browser.post('/casa/auth/local/verify', json={'code': code(secret)}, headers=ORIGIN).status_code == 422
    assert browser.post('/casa/auth/local/verify', json={'code': code(secret), 'new_password': created['password']}, headers=ORIGIN).status_code == 422
    assert browser.post('/casa/auth/local/verify', json={'code': '000000' if code(secret) != '000000' else '111111', 'new_password': 'o parola noua lunga'}, headers=ORIGIN).status_code == 401
    done = browser.post('/casa/auth/local/verify', json={'code': code(secret), 'new_password': 'o parola noua lunga'}, headers=ORIGIN)
    assert done.status_code == 200
    assert 'HttpOnly' in done.headers['set-cookie'] and 'Secure' in done.headers['set-cookie']
    user = browser.get('/casa/api/session').json()['user']
    assert user == {'id': created['id'], 'name': 'Ana Pop', 'role': 'viewer', 'local': True, 'admin': False}
    account = module.store.local_get(created['id'])
    assert account['must_change'] == 0 and account['totp'] == secret
    raw = module.store.db.execute('SELECT totp,password FROM local_users WHERE id=?', (created['id'],)).fetchone()
    assert secret.encode() not in raw[0] and 'o parola noua lunga' not in raw[1]
    again = browser.post('/casa/auth/local', json={'username': 'ana', 'password': 'o parola noua lunga'}, headers=ORIGIN).json()
    assert 'enroll' not in again and again['must_change'] is False
    used = module.store.local_get(created['id'])['totp_step']
    assert browser.post('/casa/auth/local/verify', json={'code': code_at(secret, used)}, headers=ORIGIN).status_code == 401, 'Used code is rejected'
    assert browser.post('/casa/auth/local/verify', json={'code': code_at(secret, used + 1)}, headers=ORIGIN).status_code == 200


def test_local_roles_are_enforced_server_side(client):
    _, headers = signin(client)
    connect_service()
    viewer, _, viewer_headers = local_login('ana', create_user(client, headers)['password'])
    light = {'entity_id': 'light.kitchen', 'action': 'turn_on'}
    assert viewer.get('/casa/api/history?period=day').status_code == 200
    assert viewer.post('/casa/api/command', json=light, headers=viewer_headers).status_code == 403
    control, _, control_headers = local_login('ion', create_user(client, headers, 'ion', 'control')['password'])
    assert control.post('/casa/api/command', json=light, headers=control_headers).status_code == 200
    assert control.post('/casa/api/v1/energy-policy', json={'revision': 0, 'values': {}}, headers=control_headers).status_code == 403
    assert control.post('/casa/api/command', json={'entity_id': 'input_number.deye_battery_max_discharge_kw', 'action': 'set_value', 'value': 6}, headers=control_headers).status_code == 403
    params, _, params_headers = local_login('maria', create_user(client, headers, 'maria', 'configure')['password'])
    assert params.post('/casa/api/v1/energy-policy', json={'revision': 0, 'values': {}}, headers=params_headers).status_code == 200
    assert params.post('/casa/api/command', json={'entity_id': 'input_number.deye_battery_max_discharge_kw', 'action': 'set_value', 'value': 16}, headers=params_headers).status_code == 422, 'Battery limits still apply'
    for method, url in (('get', '/casa/api/users'), ('get', '/casa/api/audit'), ('get', '/casa/api/local-users'),
                        ('post', '/casa/api/local-users'), ('post', '/casa/api/service/login'), ('post', '/casa/api/service/disconnect'),
                        ('post', '/casa/api/rules'), ('post', '/casa/api/users/owner')):
        response = getattr(params, method)(url, **({'json': {}, 'headers': params_headers} if method == 'post' else {}))
        assert response.status_code in (403, 422), (url, response.status_code)
        assert response.status_code == 403 or url in ('/casa/api/local-users', '/casa/api/users/owner')
    assert params.post('/casa/api/local-users', json={'username': 'x1x', 'name': 'X', 'role': 'configure'}, headers=params_headers).status_code == 403
    calls = module.peers[module.SERVICE].calls
    assert [c.get('service') for c in calls if c.get('type') == 'call_service'] == ['turn_on', 'configure']


def test_lockout_disable_reset_and_delete_end_sessions(client):
    _, headers = signin(client)
    connect_service()
    created = create_user(client, headers)
    browser, _, _ = local_login('ana', created['password'])
    other = TestClient(module.app, base_url='https://salavat.home.ro', headers={'X-Real-IP': '203.0.113.9'})
    for _ in range(5):
        assert other.post('/casa/auth/local', json={'username': 'ana', 'password': 'gresita gresita'}, headers=ORIGIN).status_code == 401
    assert other.post('/casa/auth/local', json={'username': 'ana', 'password': 'o parola noua lunga'}, headers=ORIGIN).status_code == 429, 'Account locked'
    module.store.local_update(created['id'], locked_until=0)
    module.login_failures.clear()
    assert client.post('/casa/api/local-users/' + created['id'], json={'disabled': True}, headers=headers).status_code == 200
    assert browser.get('/casa/api/session').status_code == 401
    assert browser.post('/casa/auth/local', json={'username': 'ana', 'password': 'o parola noua lunga'}, headers=ORIGIN).status_code == 401
    assert client.post('/casa/api/local-users/' + created['id'], json={'disabled': False, 'role': 'control'}, headers=headers).status_code == 200
    reset = client.post('/casa/api/local-users/' + created['id'] + '/reset', headers=headers).json()['password']
    assert browser.post('/casa/auth/local', json={'username': 'ana', 'password': 'o parola noua lunga'}, headers=ORIGIN).status_code == 401
    browser, _, _ = local_login('ana', reset, new_password='a treia parola lunga', offset=1)
    assert browser.get('/casa/api/session').json()['user']['role'] == 'control'
    listed = client.get('/casa/api/local-users').json()
    assert listed['service']['connected'] is True and listed['users'][0]['enrolled'] is True
    assert 'password' not in str(listed['users']) and 'totp' not in str(listed['users'])
    assert client.post('/casa/api/local-users/' + created['id'] + '/delete', headers=headers).status_code == 200
    assert browser.get('/casa/api/session').status_code == 401 and module.store.local_get(created['id']) is None
    actions = {r[0] for r in module.store.db.execute('SELECT action FROM audit')}
    assert {'local_user_create', 'local_user_edit', 'local_user_reset', 'local_user_delete', 'local_login'} <= actions


def test_ip_throttle_and_password_change(client):
    _, headers = signin(client)
    connect_service()
    browser, secret, local_headers = local_login('ana', create_user(client, headers)['password'])
    second, _, _ = local_login('ana', 'o parola noua lunga', offset=1, secret=secret)
    assert browser.post('/casa/api/me/password', json={'current': 'gresita gresita', 'new': 'alta parola lunga'}, headers=local_headers).status_code == 403
    assert browser.post('/casa/api/me/password', json={'current': 'o parola noua lunga', 'new': 'scurta'}, headers=local_headers).status_code == 422
    assert browser.post('/casa/api/me/password', json={'current': 'o parola noua lunga', 'new': 'alta parola lunga'}, headers=ORIGIN).status_code == 403
    changed = browser.post('/casa/api/me/password', json={'current': 'o parola noua lunga', 'new': 'alta parola lunga'}, headers=local_headers)
    assert changed.status_code == 200 and changed.json()['closed'] == 1
    assert browser.get('/casa/api/session').status_code == 200 and second.get('/casa/api/session').status_code == 401
    _, admin_csrf = signin(client)
    assert client.post('/casa/api/me/password', json={'current': 'x', 'new': 'alta parola lunga'}, headers=admin_csrf).status_code == 403, 'HA accounts change passwords in HA'
    module.login_failures.clear()
    attacker = TestClient(module.app, base_url='https://salavat.home.ro', headers={'X-Real-IP': '198.51.100.7'})
    for index in range(10):
        attacker.post('/casa/auth/local', json={'username': f'u{index}x', 'password': 'gresita gresita'}, headers=ORIGIN)
    assert attacker.post('/casa/auth/local', json={'username': 'ana', 'password': 'alta parola lunga'}, headers=ORIGIN).status_code == 429


def test_missing_service_account_and_local_logout(client):
    _, headers = signin(client)
    created = create_user(client, headers)
    connect_service()
    browser, _, local_headers = local_login('ana', created['password'])
    module.store.expire(module.SERVICE)
    module.peers.pop(module.SERVICE, None)
    response = browser.get('/casa/api/session')
    assert response.status_code == 503 and 'Contul tehnic' in response.json()['error']
    connect_service()
    assert browser.post('/casa/api/logout-all', json={}, headers=local_headers).json()['closed'] == 1
    assert browser.get('/casa/api/session').status_code == 401
    assert module.store.get(module.SERVICE) is not None, 'A Casa user cannot end the technical account'
    asyncio.run(module.sweep())
    assert not [sid for sid, _ in module.store.expired()], 'Expired Casa sessions are removed without an HA revoke'


def test_technical_account_is_connected_only_by_ha_admin(client, monkeypatch):
    sid, headers = signin(client)
    module.peers[sid].profile['is_admin'] = False
    assert client.post('/casa/api/service/login', headers=headers).status_code == 403
    module.peers[sid].profile['is_admin'] = True
    start = client.post('/casa/api/service/login', headers=headers)
    assert start.status_code == 200 and start.json()['url'].startswith(module.HA_AUTH_URL + '?')
    state = start.json()['url'].split('state=')[1]

    class Token:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'access_token': 'svc-access', 'refresh_token': 'svc-refresh', 'expires_in': 1800}

    class Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return Token()

    monkeypatch.setattr(module.httpx, 'AsyncClient', Client)
    admin_cookie = client.cookies.get(module.COOKIE)
    done = client.get('/casa/auth/callback?state=' + state + '&code=one-use', follow_redirects=False)
    assert done.status_code == 303 and done.headers['location'] == '/casa/#setari'
    assert module.COOKIE not in done.headers.get('set-cookie', ''), 'The admin session is not replaced'
    assert client.cookies.get(module.COOKIE) == admin_cookie
    assert module.store.get(module.SERVICE)['refresh_token'] == 'svc-refresh'
    assert client.get('/casa/auth/callback?state=' + state + '&code=one-use').status_code == 400, 'State is single use'
    assert client.post('/casa/api/service/disconnect', headers=headers).status_code == 200
    assert module.store.get(module.SERVICE) is None and module.SERVICE not in module.peers
