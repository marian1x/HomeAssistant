"""Owner request 2026-11-25: one server truth for browser and app (favorites, views,
energy profiles), and full Tesla control through explicit, narrow commands."""
import asyncio

import pytest

from test_security import client, signin  # noqa: F401  (pytest fixture)
from test_local_accounts import connect_service, create_user, local_login
from server import app as module
from server.policy import Rejected, build_rule, command

CAR = {
    'switch.salavat_t3_charger': {'state': 'off', 'attributes': {}},
    'switch.salavat_t3_polling': {'state': 'off', 'attributes': {}},
    'switch.salavat_t3_valet_mode': {'state': 'off', 'attributes': {}},
    'number.salavat_t3_charging_amps': {'state': '10', 'attributes': {'min': 0, 'max': 16, 'step': 1}},
    'number.salavat_t3_charge_limit': {'state': '80', 'attributes': {'min': 50, 'max': 100}},
    'lock.salavat_t3_doors': {'state': 'locked', 'attributes': {}},
    'cover.salavat_t3_trunk': {'state': 'closed', 'attributes': {}},
    'button.salavat_t3_horn': {'state': 'unknown', 'attributes': {}},
    'button.salavat_t3_force_data_update': {'state': '2026-11-25T10:00:00', 'attributes': {}},
    'button.salavat_t3_wake_up': {'state': '2026-11-25T10:00:00', 'attributes': {}},
    'select.salavat_t3_heated_seat_left': {'state': 'Off', 'attributes': {'options': ['Off', 'Low', 'Medium', 'High']}},
    'time.salavat_t3_scheduled_charging': {'state': '23:00:00', 'attributes': {}},
    'climate.salavat_t3_hvac_climate_system': {'state': 'off', 'attributes': {'min_temp': 15, 'max_temp': 28, 'hvac_modes': ['off', 'heat_cool'], 'preset_modes': ['normal', 'defrost']}},
}


def test_tesla_commands_are_explicit_per_domain_and_bounded():
    assert command('control', 'switch.salavat_t3_charger', 'turn_on', None, CAR, {}) == ('switch', 'turn_on', {'entity_id': 'switch.salavat_t3_charger'})
    assert command('control', 'number.salavat_t3_charging_amps', 'set_value', 12, CAR, {})[2]['value'] == 12
    assert command('control', 'lock.salavat_t3_doors', 'unlock', None, CAR, {})[:2] == ('lock', 'unlock')
    assert command('control', 'cover.salavat_t3_trunk', 'open_cover', None, CAR, {})[:2] == ('cover', 'open_cover')
    assert command('control', 'select.salavat_t3_heated_seat_left', 'select_option', 'High', CAR, {})[2]['option'] == 'High'
    assert command('control', 'time.salavat_t3_scheduled_charging', 'set_value', '01:30', CAR, {})[2]['time'] == '01:30:00'
    assert command('control', 'climate.salavat_t3_hvac_climate_system', 'set_temperature', 21.5, CAR, {})[2]['temperature'] == 21.5
    assert command('control', 'climate.salavat_t3_hvac_climate_system', 'set_preset_mode', 'defrost', CAR, {})[2]['preset_mode'] == 'defrost'
    assert command('control', 'button.salavat_t3_horn', 'press', None, CAR, {})[:2] == ('button', 'press')
    assert command('control', 'button.salavat_t3_wake_up', 'press', None, CAR, {})[:2] == ('button', 'press')
    rejected = [
        ('viewer', 'switch.salavat_t3_charger', 'turn_on', None),            # viewers never command
        ('control', 'switch.salavat_t3_polling', 'turn_on', None),           # native polling stays off
        ('control', 'switch.salavat_t3_valet_mode', 'turn_on', None),
        ('control', 'number.salavat_t3_charge_limit', 'set_value', 60),      # owner limit goes through the policy
        ('control', 'number.salavat_t3_charging_amps', 'set_value', 40),     # above the entity max
        ('control', 'number.salavat_t3_charging_amps', 'set_value', True),
        ('control', 'button.salavat_t3_force_data_update', 'press', None),
        ('control', 'select.salavat_t3_heated_seat_left', 'select_option', 'Max'),
        ('control', 'time.salavat_t3_scheduled_charging', 'set_value', '25:00'),
        ('control', 'climate.salavat_t3_hvac_climate_system', 'set_temperature', 35),
        ('control', 'lock.salavat_t3_doors', 'open', None),
        ('control', 'cover.salavat_t3_trunk', 'set_cover_position', 50),
    ]
    for role, entity, action, value in rejected:
        with pytest.raises(Rejected):
            command(role, entity, action, value, CAR, {})


def test_tesla_commands_are_never_rule_actions():
    with pytest.raises(Rejected):
        build_rule({'name': 'x', 'entity_id': 'lock.salavat_t3_doors', 'action': 'unlock', 'trigger': 'time', 'at': '08:00'},
                   CAR, {}, 'web_casa_0123456789abcdef')


def test_tesla_command_through_the_api_is_audited(client):
    sid, headers = signin(client)
    peer = module.peers[sid]
    peer.states.update({k: {'entity_id': k, **v} for k, v in CAR.items()})
    assert client.post('/casa/api/command', json={'entity_id': 'number.salavat_t3_charging_amps', 'action': 'set_value', 'value': 8}, headers=headers).status_code == 200
    assert peer.calls[-1] == {'type': 'call_service', 'domain': 'number', 'service': 'set_value', 'service_data': {'entity_id': 'number.salavat_t3_charging_amps', 'value': 8}}
    assert client.post('/casa/api/command', json={'entity_id': 'switch.salavat_t3_polling', 'action': 'turn_on'}, headers=headers).status_code == 403
    assert module.store.db.execute("SELECT count(*) FROM audit WHERE entity='number.salavat_t3_charging_amps'").fetchone()[0] == 1


def stream_of(peer):
    queue = asyncio.Queue(maxsize=1)
    changed = set()
    peer.subscribers[queue] = changed
    return queue, changed


def test_favorites_and_views_merge_and_reach_the_users_other_sessions(client):
    sid, headers = signin(client)
    peer = module.peers[sid]
    queue, changed = stream_of(peer)
    view = {'id': 'seara', 'name': 'Seara', 'icon': 'moon', 'items': ['light.kitchen', 'tcl']}
    assert client.post('/casa/api/layout', json={'favorites': ['light.kitchen'], 'views': [view]}, headers=headers).status_code == 200
    assert '*' in changed and not queue.empty(), 'Open streams of this user get a fresh snapshot'
    # An older client posting only order fields keeps favorites and views.
    assert client.post('/casa/api/layout', json={'sort': 'manual', 'order': ['tcl'], 'groups': []}, headers=headers).status_code == 200
    body = client.get('/casa/api/layout').json()
    assert body['favorites'] == ['light.kitchen'] and body['views'] == [view] and body['order'] == ['tcl']
    assert client.get('/casa/api/session').json()['layout']['views'][0]['name'] == 'Seara', 'Snapshot carries the layout'
    for bad in ({'favorites': ['a', 'a']}, {'views': [view, view]}, {'views': [{**view, 'items': ['x', 'x']}]},
                {'views': [{**view, 'id': 'Has Space'}]}, {'views': [{**view, 'icon': 'skull'}]}, {'views': [{**view, 'name': ''}]},
                {'views': [{**view, 'id': f'v{i}'} for i in range(13)]}):
        assert client.post('/casa/api/layout', json=bad, headers=headers).status_code == 422, bad


def test_profiles_are_shared_admin_only_and_applied_through_ha(client):
    sid, headers = signin(client)
    peer = module.peers[sid]
    policy = {'revision': 7, 'config': {'season': 'Auto', 'winter_profile': 'Low', 'boiler_winter_c': 47},
              'schema': [{'key': 'season', 'group': 'general', 'kind': 'select'}, {'key': 'winter_profile', 'group': 'general', 'kind': 'select'},
                         {'key': 'boiler_winter_c', 'group': 'boiler', 'kind': 'number'}, {'key': 'ev_switch', 'group': 'bindings', 'kind': 'entity'}]}

    async def call(data):
        peer.calls.append(data)
        if data['type'] == 'home_energy_policy/get':
            return policy
        return {'response': {'revision': 8, 'config': {**policy['config'], **data['service_data']['values']}}}
    peer.call = call
    seeded = client.get('/casa/api/v1/energy-profiles').json()
    assert [p['id'] for p in seeded['profiles']] == ['iarna', 'vara', 'auto'] and seeded['active'] is None
    assert client.post('/casa/api/v1/energy-profiles', json={'name': 'Ger', 'values': {'season': 'Winter'}}).status_code == 403, 'CSRF'
    assert client.post('/casa/api/v1/energy-profiles', json={'name': 'Rau', 'values': {'ev_switch': 'switch.x'}}, headers=headers).status_code == 422, 'No bindings'
    assert client.post('/casa/api/v1/energy-profiles', json={'name': 'Rau', 'values': {'nope': 1}}, headers=headers).status_code == 422
    assert client.post('/casa/api/v1/energy-profiles', json={'name': 'Rau', 'values': {'season': ['x']}}, headers=headers).status_code == 422
    created = client.post('/casa/api/v1/energy-profiles', json={'name': 'Ger', 'icon': 'snow', 'values': {'season': 'Winter', 'winter_profile': 'High', 'boiler_winter_c': 47}}, headers=headers).json()
    queue, changed = stream_of(peer)
    applied = client.post(f"/casa/api/v1/energy-profiles/{created['id']}/activate", headers=headers).json()
    configure = peer.calls[-1]
    assert configure['service'] == 'configure' and configure['service_data'] == {'values': {'season': 'Winter', 'winter_profile': 'High'}, 'revision': 7}, 'Only differences, with the revision guard'
    assert applied['changed'] == ['season', 'winter_profile'] and applied['active']['id'] == created['id']
    session = client.get('/casa/api/session').json()
    assert session['active_profile']['id'] == created['id'] and session['policy_stamp'] >= 1 and not queue.empty()
    assert client.post(f"/casa/api/v1/energy-profiles/{created['id']}", json={'name': 'Ger mare', 'icon': 'snow', 'values': {'season': 'Winter'}}, headers=headers).json()['name'] == 'Ger mare'
    assert client.post(f"/casa/api/v1/energy-profiles/{created['id']}/delete", headers=headers).json() == {'deleted': True}
    assert client.get('/casa/api/v1/energy-profiles').json()['active'] is None
    assert client.post('/casa/api/v1/energy-profiles/missing/activate', headers=headers).status_code == 404
    audit = {r[0] for r in module.store.db.execute('SELECT action FROM audit')}
    assert {'energy_profile_save', 'energy_profile_apply', 'energy_profile_delete'} <= audit


def test_profiles_are_read_only_below_configure(client):
    _, headers = signin(client)
    connect_service()
    created = create_user(client, headers, role='control')
    user, _, user_headers = local_login('ana', created['password'])
    assert user.get('/casa/api/v1/energy-profiles').status_code == 200
    assert user.post('/casa/api/v1/energy-profiles/iarna/activate', headers=user_headers).status_code == 403
    assert user.post('/casa/api/v1/energy-profiles', json={'name': 'X', 'values': {}}, headers=user_headers).status_code == 403
