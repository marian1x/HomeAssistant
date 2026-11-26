"""Device order per user (display preference only; never reaches HA)."""
import time

from fastapi.testclient import TestClient

from test_security import client, signin  # noqa: F401  (pytest fixture)
from test_local_accounts import connect_service, create_user, local_login
from server import app as module

LAYOUT = {'sort': 'manual', 'order': ['baby-spots', 'light.kitchen', '64f01c0359ebb3569a50e8eb51041183'], 'groups': ['climate', 'lights']}


def test_layout_is_saved_per_user_with_csrf_and_usage_from_the_audit_log(client):
    sid, headers = signin(client)
    assert client.get('/casa/api/layout').json() == {'sort': 'default', 'order': [], 'groups': [], 'favorites': [], 'views': [], 'usage': {}, 'usage_days': 30}
    assert client.post('/casa/api/layout', json=LAYOUT).status_code == 403, 'CSRF token and Origin are required'
    assert client.post('/casa/api/layout', json=LAYOUT, headers={'Origin': 'https://evil.example', 'X-CSRF-Token': headers['X-CSRF-Token']}).status_code == 403
    assert client.post('/casa/api/layout', json=LAYOUT, headers=headers).json() == {'saved': True}
    for bad in ({**LAYOUT, 'order': ['a', 'a']}, {**LAYOUT, 'groups': ['lights', 'lights']}, {**LAYOUT, 'order': ['../x y']},
                {**LAYOUT, 'sort': 'random'}, {**LAYOUT, 'groups': ['garage']}, {**LAYOUT, 'extra': 1}, {**LAYOUT, 'order': ['x'] * 501}):
        assert client.post('/casa/api/layout', json=bad, headers=headers).status_code == 422, bad
    module.store.log('owner', 'turn_on', 'light.kitchen', 'Acceptata de HA')
    module.store.log('owner', 'turn_off', 'light.kitchen', 'Acceptata de HA')
    module.store.log('owner', 'turn_on', 'switch.x', 'Fara confirmare')
    module.store.log('someone-else', 'turn_on', 'light.kitchen', 'Acceptata de HA')
    module.store.db.execute('INSERT INTO audit(at,actor,action,entity,result) VALUES (?,?,?,?,?)', (time.time() - 31 * 86400, 'owner', 'turn_on', 'light.old', 'Acceptata de HA'))
    body = client.get('/casa/api/layout').json()
    assert {k: body[k] for k in LAYOUT} == LAYOUT
    assert body['usage'] == {'light.kitchen': 2}, 'Only own, accepted commands of the last 30 days'
    # A command sent through the app counts; the layout endpoints never call HA.
    calls = len(module.peers[sid].calls)
    assert client.post('/casa/api/command', json={'entity_id': 'light.kitchen', 'action': 'turn_on'}, headers=headers).status_code == 200
    assert client.get('/casa/api/layout').json()['usage'] == {'light.kitchen': 3}
    assert len(module.peers[sid].calls) == calls + 1


def test_viewers_and_casa_accounts_arrange_their_own_view(client):
    _, headers = signin(client)
    connect_service()
    created = create_user(client, headers)
    viewer, _, viewer_headers = local_login('ana', created['password'])
    assert viewer.get('/casa/api/layout').json()['order'] == []
    mine = {'sort': 'usage', 'order': ['tcl'], 'groups': []}
    assert viewer.post('/casa/api/layout', json=mine, headers=viewer_headers).status_code == 200
    assert viewer.get('/casa/api/layout').json()['sort'] == 'usage'
    assert client.get('/casa/api/layout').json()['sort'] == 'default', 'Layouts are per user'
    assert client.post('/casa/api/local-users/' + created['id'] + '/delete', json={}, headers=headers).status_code == 200
    assert module.store.layout_get(created['id']) is None, 'Deleting a Casa account removes its layout'
    assert TestClient(module.app, base_url='https://salavat.home.ro').get('/casa/api/layout').status_code == 401
