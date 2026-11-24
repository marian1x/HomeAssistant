"""Tesla journal, owner charge limit and station prices: roles, CSRF, validation, audit."""
from test_security import client, signin  # noqa: F401  (pytest fixture)
from server import app as module


def control(peer):
    peer.profile.update(is_admin=False)
    module.store.db.execute('UPDATE users SET role=? WHERE id=?', ('control', peer.profile['id']))
    module.store.db.commit()


def test_journal_needs_control_role_and_is_cached(client):
    sid, _ = signin(client)
    peer = module.peers[sid]
    module.store.db.execute("UPDATE users SET role='viewer' WHERE id=?", (peer.profile['id'],))
    module.store.db.commit()
    peer.profile.update(is_admin=False)
    assert client.get('/casa/api/tesla/log').status_code == 403, 'Location history is not for viewers'
    control(peer)

    async def call(data):
        peer.calls.append(data)
        if data['type'] == 'recorder/statistics_during_period':
            return {'sensor.salavat_t3_odometer': [{'start': 1, 'min': 100.0, 'max': 350.25}, {'start': 2, 'min': None, 'max': 9}]}
        return {'charges': [], 'drives': []}
    peer.call = call
    assert client.get('/casa/api/tesla/log?days=900').status_code == 422
    body = client.get('/casa/api/tesla/log?days=30').json()
    assert body['monthly_km'] == [{'start': 1, 'km': 250.2}]
    client.get('/casa/api/tesla/log?days=30')
    assert [c['type'] for c in peer.calls] == ['home_energy_policy/tesla_log', 'recorder/statistics_during_period']
    assert peer.calls[0]['days'] == 30


def test_owner_limit_is_validated_audited_and_needs_csrf(client):
    sid, headers = signin(client)
    peer = module.peers[sid]
    control(peer)
    assert client.post('/casa/api/tesla/limit', json={'soc': 35}).status_code == 403, 'CSRF required'
    assert client.post('/casa/api/tesla/limit', json={'soc': 19}, headers=headers).status_code == 422
    assert client.post('/casa/api/tesla/limit', json={'soc': '35'}, headers=headers).status_code == 422
    assert client.post('/casa/api/tesla/limit', json={'soc': 35}, headers=headers).status_code == 200
    call = peer.calls[-1]
    assert call['domain'] == 'home_energy_policy' and call['service'] == 'set_ev_limit' and call['service_data'] == {'soc': 35}
    assert module.store.db.execute("SELECT count(*) FROM audit WHERE action='tesla_limit'").fetchone()[0] == 1


def test_station_price_set_and_clear(client):
    sid, headers = signin(client)
    peer = module.peers[sid]
    control(peer)
    assert client.post('/casa/api/tesla/charge-price', json={'id': 4, 'price_kwh': 2.35, 'note': 'Kaufland'}, headers=headers).status_code == 200
    assert peer.calls[-1]['service_data'] == {'id': 4, 'note': 'Kaufland', 'price_kwh': 2.35}
    assert client.post('/casa/api/tesla/charge-price', json={'id': 4, 'price_kwh': None}, headers=headers).status_code == 200
    assert 'price_kwh' not in peer.calls[-1]['service_data']
    assert client.post('/casa/api/tesla/charge-price', json={'id': 4, 'price_kwh': 50}, headers=headers).status_code == 422


def test_battery_bms_is_read_only_viewer_and_cached(client):
    sid, _ = signin(client)
    peer = module.peers[sid]
    calls = []

    async def call(data):
        calls.append(data)
        return {'available': True, 'status': 'Citire reusita', 'latest': {'pack': {'cells': [3.3] * 16}}, 'history': []}
    peer.call = call
    assert client.get('/casa/api/battery/bms?days=99').status_code == 422
    body = client.get('/casa/api/battery/bms').json()
    assert body['available'] and len(body['latest']['pack']['cells']) == 16
    client.get('/casa/api/battery/bms')
    assert [c['type'] for c in calls] == ['home_energy_policy/bms'], 'Cached; one read only'
    assert calls[0]['days'] == 2
