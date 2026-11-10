import asyncio
import json
import os
from pathlib import Path
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

os.environ['STATE_DIR'] = tempfile.mkdtemp(prefix='casa-test-')
from server import app as module
from server.policy import KILL, Rejected, build_rule, command
from server.store import Store
from server.ha import Peer

STATES = {
    'input_number.deye_battery_max_discharge_kw': {'entity_id': 'input_number.deye_battery_max_discharge_kw', 'state': '7', 'attributes': {'min': .5, 'max': 7}},
    'light.kitchen': {'entity_id': 'light.kitchen', 'state': 'off', 'attributes': {}},
    'switch.deye_battery_grid_charging': {'entity_id': 'switch.deye_battery_grid_charging', 'state': 'off', 'attributes': {}},
    'automation.deye_management_baterie_si_prognoza': {'entity_id': 'automation.deye_management_baterie_si_prognoza', 'state': 'off', 'attributes': {}},
    KILL: {'entity_id': KILL, 'state': 'on', 'attributes': {}},
}


def test_tcl_fan_commands_are_supported_and_bounded_by_actual_modes():
    entity='climate.tcl_test'
    states={entity:{'state':'heat','attributes':{'fan_modes':['Turbo','Auto','1','2','3','4','5','6']}}}
    domain,service,data=command('control',entity,'set_fan_mode','6',states,{})
    assert (domain,service,data)==('climate','set_fan_mode',{'entity_id':entity,'fan_mode':'6'})
    with pytest.raises(Rejected):command('control',entity,'set_fan_mode','7',states,{})
    with pytest.raises(Rejected):command('viewer',entity,'set_fan_mode','1',states,{})


def test_backup_maintenance_is_the_only_pause_exception_and_still_admin_only():
    backup='automation.ha_full_backup_morning_and_evening'
    household='automation.some_household_rule'
    states={KILL:{'state':'on'},backup:{'state':'off'},household:{'state':'off'}}
    assert command('configure',backup,'turn_on',None,states,{})[:2]==('automation','turn_on')
    with pytest.raises(Rejected):command('control',backup,'turn_on',None,states,{})
    with pytest.raises(Rejected):command('configure',household,'turn_on',None,states,{})


class FakePeer:
    def __init__(self, sid, store, *args):
        self.sid = sid
        self.store = store
        self.ready = asyncio.Event()
        self.ready.set()
        self.connected = True
        self.profile = {'id': 'owner', 'name': 'Cosmin', 'is_admin': True}
        self.states = STATES.copy()
        self.entities = {}
        self.devices = self.areas = []
        self.last_update = time.time()
        self.last_command = {}
        self.command_lock = asyncio.Lock()
        self.calls = []
        self.subscribers = {}
    def start(self): pass
    async def close(self): pass
    async def identity(self): return self.profile | {'role': self.store.user(self.profile)}
    async def call(self, data): self.calls.append(data); return {}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'store', Store(tmp_path))
    monkeypatch.setattr(module, 'Peer', FakePeer)
    monkeypatch.setattr(module, 'peers', {})
    monkeypatch.setattr(module, 'oauth_states', {})
    monkeypatch.setattr(module, 'rate_buckets', {})
    with TestClient(module.app, base_url='https://salavat.home.ro') as client:
        yield client


def signin(client):
    handle, sid = module.store.create({'access_token': 'TEST_ACCESS_SECRET', 'refresh_token': 'TEST_REFRESH_SECRET', 'expires_at': time.time() + 3600})
    client.cookies.set(module.COOKIE, handle, domain='salavat.home.ro', path='/casa/')
    session = client.get('/casa/api/session')
    assert session.status_code == 200
    return sid, {'Origin': module.ORIGIN, 'X-CSRF-Token': session.json()['csrf']}


def test_unauthenticated_cannot_read_or_control(client):
    assert client.get('/casa/api/session').status_code == 401
    assert client.post('/casa/api/command', json={'entity_id': 'light.kitchen', 'action': 'turn_on'}).status_code == 401
    assert client.get('/casa/api/v1/energy-policy').status_code == 401
    assert client.post('/casa/api/v1/energy-policy', json={'revision': 0, 'values': {}}).status_code == 401


def test_policy_configuration_requires_admin_and_csrf(client):
    sid, headers = signin(client)
    assert client.post('/casa/api/v1/energy-policy', json={'revision':0, 'values':{}}).status_code == 403
    peer = module.peers[sid]
    peer.profile.update(is_admin=False)
    module.store.db.execute('UPDATE users SET role=? WHERE id=?', ('control', peer.profile['id']))
    module.store.db.commit()
    assert client.post('/casa/api/v1/energy-policy', headers=headers, json={'revision':0, 'values':{}}).status_code == 403
    assert not peer.calls


def test_policy_uses_narrow_native_services_not_generic_proxy(client):
    sid, headers = signin(client)
    assert client.post('/casa/api/v1/energy-policy', headers=headers, json={'revision':0, 'values':{'winter_cold_c':-15}}).status_code == 200
    call = module.peers[sid].calls[-1]
    assert call['domain'] == 'home_energy_policy' and call['service'] == 'configure' and call['return_response'] is True
    assert client.post('/casa/api/v1/energy-policy/resume', headers=headers, json={'device':'switch.deye_grid_charge'}).status_code == 422
    assert client.post('/casa/api/v1/energy-policy', headers=headers, json={'revision':True, 'values':{}}).status_code == 422


def test_legacy_actors_cannot_be_enabled_with_policy_installed():
    states = {KILL:{'state':'off'}, 'sensor.home_energy_policy_status':{'state':'Confort'},
              'automation.hvac_solar_climate_control':{'state':'off','attributes':{}}}
    with pytest.raises(Rejected):
        command('configure', 'automation.hvac_solar_climate_control', 'turn_on', None, states, {})


def test_host_header_and_permissions_policy(client):
    assert client.get('/casa/', headers={'Host':'evil.example'}).status_code == 400
    assert 'camera=()' in client.get('/casa/api/session').headers['permissions-policy']


def test_energy_finance_requires_auth_and_bounds_queries_before_ha(client):
    url='/casa/api/v1/energy-dashboard?start=2026-11-01&end=2026-11-08'
    assert client.get(url).status_code==401
    sid,_=signin(client)
    assert client.get('/casa/api/v1/energy-dashboard?start=1900-01-01&end=2026-11-08').status_code==422
    assert client.get(url+'&mode=arbitrary').status_code==422
    assert module.peers[sid].calls==[]


def test_energy_prices_cannot_be_written_by_control_users(client):
    sid,headers=signin(client)
    module.peers[sid].profile['is_admin']=False
    module.store.db.execute('UPDATE users SET role=? WHERE id=?',('control','owner'))
    module.store.db.commit()
    body={'revision':1,'values':{'energy_import_price':1.11,'energy_export_price':.45}}
    assert client.post('/casa/api/v1/energy-policy',headers=headers,json=body).status_code==403
    assert module.peers[sid].calls==[]


def test_oauth_requires_state_cookie_and_has_secure_cookies(client):
    response = client.get('/casa/auth/login', follow_redirects=False)
    assert response.status_code == 302
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
    assert client.get('/casa/auth/callback?state=forged&code=forged').status_code == 400


def test_session_never_exposes_ha_tokens(client):
    sid, _ = signin(client)
    response = client.get('/casa/api/session')
    assert 'TEST_ACCESS_SECRET' not in response.text and 'TEST_REFRESH_SECRET' not in response.text
    raw = module.store.db.execute('SELECT payload FROM sessions WHERE id=?', (sid,)).fetchone()[0]
    assert b'TEST_REFRESH_SECRET' not in raw
    assert not module.peers[sid].calls


def test_house_inventory_requires_authentication(client):
    assert client.get('/casa/api/session').status_code == 401
    signin(client)
    body = client.get('/casa/api/session').json()
    assert [floor['name'] for floor in body['house']['floors']] == ['Parter', 'Etaj', 'Exterior']
    assert any(item['id'] == 'boiler' and item['rated_power_kw'] == 1.8 for item in body['house']['items'])


def test_csrf_and_cross_origin_read_protection(client):
    signin(client)
    args = {'entity_id': 'light.kitchen', 'action': 'turn_on'}
    assert client.post('/casa/api/command', json=args, headers={'Origin': module.ORIGIN}).status_code == 403
    assert client.get('/casa/api/session', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/casa/api/session', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403


def test_rbac_and_explicit_command_allowlist(client):
    sid, headers = signin(client)
    peer = module.peers[sid]
    peer.profile['is_admin'] = False
    args = {'entity_id': 'light.kitchen', 'action': 'turn_on'}
    assert client.post('/casa/api/command', json=args, headers=headers).status_code == 403
    module.store.db.execute("UPDATE users SET role='control' WHERE id='owner'")
    module.store.db.commit()
    assert client.post('/casa/api/command', json=args, headers=headers).status_code == 200
    assert client.post('/casa/api/command', json={'entity_id': 'input_number.deye_battery_max_discharge_kw', 'action': 'set_value', 'value': 6}, headers=headers).status_code == 403
    assert client.post('/casa/api/command', json={'entity_id': 'switch.deye_battery_grid_charging', 'action': 'turn_on'}, headers=headers).status_code == 403


def test_battery_limits_killswitch_and_disconnected_commands(client):
    sid, headers = signin(client)
    args = {'entity_id': 'input_number.deye_battery_max_discharge_kw', 'action': 'set_value', 'value': 16}
    assert client.post('/casa/api/command', json=args, headers=headers).status_code == 422
    args = {'entity_id': 'automation.deye_management_baterie_si_prognoza', 'action': 'turn_on'}
    assert client.post('/casa/api/command', json=args, headers=headers).status_code == 409
    module.peers[sid].connected = False
    assert client.post('/casa/api/command', json={'entity_id': 'light.kitchen', 'action': 'turn_on'}, headers=headers).status_code == 409
    assert not module.peers[sid].calls


def test_state_expiry_is_immediate_and_keeps_encrypted_revocation_material(tmp_path):
    store = Store(tmp_path)
    handle, sid = store.create({'access_token': 'access', 'refresh_token': 'refresh', 'expires_at': time.time() + 3600})
    assert store.identify(handle)[1] is not None
    store.expire(sid)
    assert store.identify(handle)[1] is None
    assert store.expired()[0][1]['refresh_token'] == 'refresh'


def test_session_lasts_30_days_from_last_use_and_only_bound_sessions_renew(tmp_path):
    from server.store import SESSION_IDLE
    store = Store(tmp_path)
    handle, sid = store.create({'access_token': 'a', 'refresh_token': 'r', 'expires_at': time.time() + 3600})
    expiry = lambda: store.db.execute('SELECT expires FROM sessions WHERE id=?', (sid,)).fetchone()[0]
    assert abs(expiry() - (time.time() + SESSION_IDLE)) < 5
    store.db.execute('UPDATE sessions SET expires=? WHERE id=?', (time.time() + 86400, sid))
    store.db.commit()
    assert store.renew(handle) is False, 'A session not yet bound to an HA user is not extended'
    store.bind(sid, 'owner')
    assert store.owner(sid) == 'owner'
    assert store.renew(handle) is True and abs(expiry() - (time.time() + SESSION_IDLE)) < 5
    assert store.renew(handle) is False, 'Renewal is written at most once per hour'
    store.save(sid, {'access_token': 'b', 'refresh_token': 'r', 'expires_at': 0, 'csrf': 'x'})
    assert store.owner(sid) == 'owner', 'Token refresh keeps the session owner'
    store.expire(sid)
    assert store.renew(handle) is False and store.identify(handle)[1] is None, 'Logged-out sessions are never revived'


def test_legacy_session_table_is_migrated(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / 'app.sqlite')
    db.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, payload BLOB, expires REAL)')
    db.commit()
    db.close()
    store = Store(tmp_path)
    assert 'user' in {r[1] for r in store.db.execute('PRAGMA table_info(sessions)')}
    _, sid = store.create({'access_token': 'a', 'refresh_token': 'r', 'expires_at': 0})
    assert store.owner(sid) is None


def test_session_cookie_is_renewed_on_use_with_secure_flags(client):
    from server.store import SESSION_IDLE
    sid, _ = signin(client)
    module.store.bind(sid, 'owner')
    module.store.db.execute('UPDATE sessions SET expires=? WHERE id=?', (time.time() + 3600, sid))
    module.store.db.commit()
    response = client.get('/casa/api/session')
    cookie = response.headers.get('set-cookie', '')
    assert response.status_code == 200 and module.COOKIE in cookie
    assert f'Max-Age={SESSION_IDLE}' in cookie and 'HttpOnly' in cookie and 'Secure' in cookie and 'samesite=lax' in cookie.lower() and 'Path=/casa/' in cookie
    assert 'set-cookie' not in client.get('/casa/api/session').headers, 'No cookie rewrite on every request'


def test_logout_everywhere_requires_csrf_and_only_closes_own_sessions(client):
    sid, headers = signin(client)
    module.store.bind(sid, 'owner')
    phone_handle, phone = module.store.create({'access_token': 'p', 'refresh_token': 'phone-refresh', 'expires_at': time.time() + 3600})
    module.store.bind(phone, 'owner')
    module.peers[phone] = FakePeer(phone, module.store)
    _, family = module.store.create({'access_token': 'f', 'refresh_token': 'family-refresh', 'expires_at': time.time() + 3600})
    module.store.bind(family, 'family')
    assert client.post('/casa/api/logout-all', json={}, headers={'Origin': module.ORIGIN}).status_code == 403
    assert client.post('/casa/api/logout-all', json={}, headers={'Origin': 'https://evil.example', 'X-CSRF-Token': headers['X-CSRF-Token']}).status_code == 403
    assert module.store.get(sid) and module.store.get(phone)
    response = client.post('/casa/api/logout-all', json={}, headers=headers)
    assert response.status_code == 200 and response.json()['closed'] == 2
    assert module.COOKIE in response.headers['set-cookie'] and 'Max-Age=0' in response.headers['set-cookie']
    assert module.store.get(sid) is None and module.store.get(phone) is None and module.store.get(family) is not None
    assert phone not in module.peers and sid not in module.peers
    revocable = {payload['refresh_token'] for _, payload in module.store.expired()}
    assert {'TEST_REFRESH_SECRET', 'phone-refresh'} <= revocable and 'family-refresh' not in revocable
    assert module.store.db.execute("SELECT count(*) FROM audit WHERE action='logout_all'").fetchone()[0] == 1
    assert client.get('/casa/api/session').status_code == 401
    assert client.post('/casa/api/logout-all', json={}, headers=headers).status_code == 401


def test_idle_ha_connections_close_but_sessions_and_open_streams_stay(client):
    sid, _ = signin(client)
    assert module.peers[sid].last_access > time.time() - 5
    _, streaming = module.store.create({'access_token': 's', 'refresh_token': 's', 'expires_at': time.time() + 3600})
    module.peers[streaming] = FakePeer(streaming, module.store)
    module.peers[streaming].subscribers['stream'] = set()
    for peer in module.peers.values():
        peer.last_access = time.time() - module.PEER_IDLE - 1
    asyncio.run(module.sweep())
    assert sid not in module.peers and streaming in module.peers
    assert module.store.get(sid) is not None, 'Closing an idle HA connection keeps the Casa session'
    assert client.get('/casa/api/session').status_code == 200 and sid in module.peers


def test_nan_and_raw_inverter_settings_are_rejected():
    for value in (float('nan'), float('inf'), -1, 8):
        with pytest.raises(Rejected):
            command('configure', 'input_number.deye_battery_max_discharge_kw', 'set_value', value, STATES, {})
    with pytest.raises(Rejected):
        command('configure', 'switch.deye_battery_grid_charging', 'turn_on', None, STATES, {})


def test_rule_creation_is_disabled_and_guarded():
    config = build_rule({'name': 'Lumina seara', 'entity_id': 'light.kitchen', 'action': 'turn_on', 'trigger': 'sun', 'event': 'sunset', 'offset': 15}, STATES, {}, 'web_casa_' + 'a'*16)
    assert config['initial_state'] is False
    assert config['conditions'] == [{'condition': 'state', 'entity_id': KILL, 'state': 'off'}]
    assert config['triggers'][0]['offset'] == 900
    with pytest.raises(Rejected):
        build_rule({'name': 'Bad', 'entity_id': KILL, 'action': 'turn_off', 'trigger': 'time', 'at': '18:00'}, STATES, {}, 'web_casa_' + 'b'*16)


def test_brightness_requires_supported_light_and_bounded_value():
    states = STATES | {'light.dimmer': {'entity_id': 'light.dimmer', 'state': 'on', 'attributes': {'supported_color_modes': ['brightness']}}}
    assert command('control', 'light.dimmer', 'set_brightness', 67, states, {}) == ('light', 'turn_on', {'entity_id': 'light.dimmer', 'brightness_pct': 67})
    for value in (0, 101, float('nan'), float('inf'), True):
        with pytest.raises(Rejected):
            command('configure', 'light.dimmer', 'set_brightness', value, states, {})
    with pytest.raises(Rejected):
        command('viewer', 'light.dimmer', 'set_brightness', 67, states, {})
    with pytest.raises(Rejected):
        command('control', 'light.kitchen', 'set_brightness', 67, states, {})
    with pytest.raises(Rejected):
        command('control', 'light.dimmer', 'set_brightness', 67, states, {'light.dimmer': {'hidden_by': 'user'}})


def test_supported_media_controls_and_limits():
    states = {'media_player.speaker': {'entity_id':'media_player.speaker', 'state':'off', 'attributes':{'supported_features':152461}}}
    assert command('control','media_player.speaker','media_play',None,states,{}) == ('media_player','media_play',{'entity_id':'media_player.speaker'})
    assert command('control','media_player.speaker','set_volume',25,states,{}) == ('media_player','volume_set',{'entity_id':'media_player.speaker','volume_level':.25})
    assert command('control','media_player.speaker','set_mute','on',states,{})[2]['is_volume_muted'] is True
    for value in (-1,101,float('nan'),True):
        with pytest.raises(Rejected): command('control','media_player.speaker','set_volume',value,states,{})
    with pytest.raises(Rejected): command('viewer','media_player.speaker','media_play',None,states,{})
    with pytest.raises(Rejected): command('control','media_player.speaker','play_media','https://untrusted.example',states,{})
    states['media_player.speaker']['attributes']['supported_features'] = 0
    with pytest.raises(Rejected): command('control','media_player.speaker','media_play',None,states,{})


def test_boiler_operation_modes_are_exactly_validated():
    states = {'water_heater.boiler': {'entity_id':'water_heater.boiler','state':'MANUAL','attributes':{'operation_list':['MANUAL','PROGRAM','BOOST']}}}
    assert command('control','water_heater.boiler','set_operation_mode','BOOST',states,{}) == ('water_heater','set_operation_mode',{'entity_id':'water_heater.boiler','operation_mode':'BOOST'})
    with pytest.raises(Rejected): command('control','water_heater.boiler','set_operation_mode','INVENTED',states,{})
    with pytest.raises(Rejected): command('viewer','water_heater.boiler','set_operation_mode','BOOST',states,{})


def test_automatic_program_flags_respect_admin_and_global_pause():
    id = 'input_boolean.ariston_solar_boost_enabled'
    states = STATES | {id: {'entity_id': id, 'state': 'on', 'attributes': {}}}
    assert command('configure',id,'turn_off',None,states,{}) == ('input_boolean','turn_off',{'entity_id':id})
    with pytest.raises(Rejected): command('configure',id,'turn_on',None,states,{})
    with pytest.raises(Rejected): command('control',id,'turn_off',None,states,{})
    states[KILL] = STATES[KILL] | {'state':'off'}
    assert command('configure',id,'turn_on',None,states,{})[1] == 'turn_on'


def test_admin_can_assign_user_and_viewer_but_not_admin_or_self(client):
    sid, headers = signin(client)
    module.store.user({'id': 'family', 'name': 'Family', 'is_admin': False})
    module.store.user({'id': 'other-admin', 'name': 'Other admin', 'is_admin': True})
    users = client.get('/casa/api/users').json()
    assert next(u for u in users if u['id'] == 'owner')['role'] == 'configure'
    assert next(u for u in users if u['id'] == 'other-admin')['is_admin'] is True
    assert client.post('/casa/api/users/family', json={'role': 'control'}, headers=headers).status_code == 200
    assert module.store.user({'id': 'family', 'is_admin': False}) == 'control'
    assert client.post('/casa/api/users/family', json={'role': 'configure'}, headers=headers).status_code == 422
    assert client.post('/casa/api/users/owner', json={'role': 'viewer'}, headers=headers).status_code == 403
    assert client.post('/casa/api/users/other-admin', json={'role': 'viewer'}, headers=headers).status_code == 403
    assert client.post('/casa/api/users/missing', json={'role': 'control'}, headers=headers).status_code == 404
    assert client.post('/casa/api/users/family', json={'role': 'viewer'}, headers=headers).status_code == 200
    assert module.store.user({'id': 'family', 'is_admin': False}) == 'viewer'
    assert module.store.db.execute("SELECT count(*) FROM audit WHERE action='set_role'").fetchone()[0] == 2
    assert not module.peers[sid].calls


def test_user_cannot_access_admin_endpoints_or_elevate_itself(client):
    sid, headers = signin(client)
    module.peers[sid].profile['is_admin'] = False
    module.store.db.execute("UPDATE users SET role='control' WHERE id='owner'")
    module.store.db.commit()
    assert client.get('/casa/api/users').status_code == 403
    assert client.get('/casa/api/audit').status_code == 403
    assert client.post('/casa/api/users/owner', json={'role': 'control'}, headers=headers).status_code == 403
    assert client.post('/casa/api/rules', json={}, headers=headers).status_code == 403
    assert not module.peers[sid].calls


def test_role_change_publishes_new_snapshot_for_active_user(client):
    import queue
    _, headers = signin(client)
    peer = FakePeer('family-session', module.store)
    peer.profile = {'id': 'family', 'name': 'Family', 'is_admin': False}
    module.store.user(peer.profile)
    update_queue, changed = queue.Queue(maxsize=1), set()
    peer.subscribers[update_queue] = changed
    module.peers['family-session'] = peer
    assert client.post('/casa/api/users/family', json={'role': 'control'}, headers=headers).status_code == 200
    assert changed == {'*'} and not update_queue.empty()
    assert module.snapshot(peer, {'csrf': 'test'})['user']['role'] == 'control'
    assert client.post('/casa/api/users/family', json={'role': 'viewer'}, headers=headers).status_code == 200
    assert module.snapshot(peer, {'csrf': 'test'})['user']['role'] == 'viewer'


def test_legacy_user_database_migration_and_fail_closed_role(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / 'app.sqlite')
    db.execute("CREATE TABLE users (id TEXT PRIMARY KEY,name TEXT,role TEXT DEFAULT 'viewer')")
    db.execute("INSERT INTO users VALUES ('old','Old user','configure')")
    db.commit()
    db.close()
    store = Store(tmp_path)
    assert 'is_admin' in {r[1] for r in store.db.execute('PRAGMA table_info(users)')}
    assert store.user({'id': 'old', 'is_admin': False}) == 'viewer'
    assert store.user({'id': 'old', 'is_admin': True}) == 'configure'
    assert store.user({'id': 'old', 'is_admin': False}) == 'viewer'


@pytest.mark.asyncio
async def test_metadata_refresh_does_not_overwrite_newer_state_event(tmp_path):
    store = Store(tmp_path)
    _, sid = store.create({'access_token': 'test', 'refresh_token': 'test', 'expires_at': time.time() + 3600})
    peer = Peer(sid, store, 'http://localhost', module.CLIENT_ID, lambda *args: None)
    peer.connected, peer.metadata_dirty = True, True
    peer.states = STATES.copy()

    async def registries(): pass

    async def call(message):
        assert message == {'type': 'get_states'}
        peer.event_revision += 1
        peer.state_revisions['light.kitchen'] = peer.event_revision
        peer.states['light.kitchen'] = STATES['light.kitchen'] | {'state': 'on'}
        return list(STATES.values())

    peer.registries, peer.call = registries, call
    await peer.metadata_updates()
    assert peer.states['light.kitchen']['state'] == 'on'


@pytest.mark.asyncio
async def test_live_websocket_cache_and_no_initial_service_calls(tmp_path):
    import websockets
    calls = []
    area_name = 'Before'
    async def upstream(socket):
        nonlocal area_name
        await socket.send(json.dumps({'type': 'auth_required'}))
        auth = json.loads(await socket.recv())
        assert auth['type'] == 'auth'
        await socket.send(json.dumps({'type': 'auth_ok'}))
        async for raw in socket:
            message = json.loads(raw)
            calls.append(message)
            kind = message['type']
            result = {'id': 'owner', 'name': 'Cosmin', 'is_admin': True} if kind == 'auth/current_user' else list(STATES.values()) if kind == 'get_states' else [{'area_id': 'living', 'name': area_name, 'floor_id': 'parter'}] if kind == 'config/area_registry/list' else [{'floor_id': 'parter', 'name': 'Parter', 'level': 0}] if kind == 'config/floor_registry/list' else []
            await socket.send(json.dumps({'type': 'result', 'id': message['id'], 'success': True, 'result': result}))
            if kind == 'subscribe_events':
                await socket.send(json.dumps({'type': 'event', 'event': {'data': {'entity_id': 'light.kitchen', 'new_state': STATES['light.kitchen'] | {'state': 'on'}}}}))
                if message.get('event_type') == 'floor_registry_updated':
                    area_name = 'After'
                    await socket.send(json.dumps({'type': 'event', 'event': {'event_type': 'area_registry_updated', 'data': {'area_id': 'living'}}}))
    store = Store(tmp_path)
    _, sid = store.create({'access_token': 'test', 'refresh_token': 'test', 'expires_at': time.time() + 3600})
    async with websockets.serve(upstream, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        peer = Peer(sid, store, f'http://127.0.0.1:{port}', module.CLIENT_ID, lambda *args: None)
        peer.start()
        try:
            await asyncio.wait_for(peer.ready.wait(), 5)
            for _ in range(20):
                if peer.states['light.kitchen']['state'] == 'on': break
                await asyncio.sleep(.05)
            assert peer.connected and peer.states['light.kitchen']['state'] == 'on'
            for _ in range(40):
                if peer.areas and peer.areas[0]['name'] == 'After': break
                await asyncio.sleep(.05)
            assert peer.areas[0]['name'] == 'After'
            assert peer.floors[0]['name'] == 'Parter'
            assert not any(c['type'] == 'call_service' for c in calls)
        finally:
            await peer.close()
