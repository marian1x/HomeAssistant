"""Battery panel: BMS attributes reach the browser, history is read-only and bounded."""
import time

from test_security import client, signin  # noqa: F401  (pytest fixture)
from server import app as module
from server.ha import clean_state


def test_bms_attributes_pass_the_filter_and_unknown_ones_do_not():
    state = clean_state({'entity_id': 'sensor.deye_battery', 'state': '77', 'attributes': {
        'BMS Charging Current': 10, 'BMS Max Charging Current': 30, 'BMS Discharging Current': 200, 'Corrected Capacity': 317,
        'serial_number': 'SECRET-123', 'unit_of_measurement': '%'}})
    assert state['attributes'] == {'BMS Charging Current': 10, 'BMS Max Charging Current': 30, 'BMS Discharging Current': 200,
                                   'Corrected Capacity': 317, 'unit_of_measurement': '%'}


def test_battery_history_is_bucketed_cached_and_never_commands(client):
    sid, _ = signin(client)
    now = time.time()
    answer = {
        'sensor.deye_battery': [{'s': '20', 'a': {'BMS Charging Current': 157, 'BMS Discharging Current': 200}, 'lu': now - 7000},
                                {'s': '21', 'a': {'BMS Charging Current': 10, 'BMS Discharging Current': 200}, 'lu': now - 3600},
                                {'s': '22', 'lu': now - 1800}],
        'sensor.deye_battery_temperature': [{'s': '3.1', 'lu': now - 3600}, {'s': 'unavailable', 'lu': now - 1700}],
        'sensor.deye_battery_power': [{'s': '-400', 'lu': now - 3500}],
    }
    calls = []

    async def history(data):
        calls.append(data)
        return answer
    module.peers[sid].call = history
    assert client.get('/casa/api/battery/history?hours=12').status_code == 422
    body = client.get('/casa/api/battery/history').json()
    assert body['hours'] == 24 and body['step'] == 300 and len(body['points']) == 289
    last = body['points'][-1]
    assert last['soc'] == 22 and last['charge_limit'] == 10 and last['discharge_limit'] == 200, 'Attributes carry over unchanged rows'
    assert last['temp'] is None and last['power'] == -400, 'Unavailable is a gap, not zero'
    assert 'soc' not in body['points'][0] or body['points'][0]['soc'] is None or body['points'][0]['soc'] == 20
    client.get('/casa/api/battery/history')
    assert len(calls) == 1 and calls[0]['type'] == 'history/history_during_period', 'Cached for a minute; only a history read'
    assert set(calls[0]['entity_ids']) == {'sensor.deye_battery', 'sensor.deye_battery_temperature', 'sensor.deye_battery_power'}
    assert client.get('/casa/api/battery/history?hours=48').json()['step'] == 600


def test_battery_history_requires_a_session(client):
    assert client.get('/casa/api/battery/history').status_code == 401
