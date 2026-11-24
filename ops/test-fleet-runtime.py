"""Run inside HA's Python environment: python3 test-fleet-runtime.py <dir containing custom_components>.
Fake hass/MQTT/Tesla objects; never touches the HA API, the broker or the car."""
import asyncio
import json
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '/config')
from homeassistant.components import mqtt as ha_mqtt  # noqa: E402
from custom_components.home_energy_policy import fleet as fleet_mod  # noqa: E402
from custom_components.home_energy_policy.schema import DEFAULTS  # noqa: E402

HOME = {'latitude': 45.7183, 'longitude': 21.2652, 'radius': 100}


class Calls:
    def __init__(self):
        self.calls = []

    async def async_call(self, *args, **kwargs):
        self.calls.append(args)


class Conn:
    def __init__(self):
        self.calls = []

    async def post(self, path, method='post', data=None):
        self.calls.append((path, method, data))
        if path.endswith('fleet_telemetry_config_jws'):
            return {'response': {'updated_vehicles': 1, 'skipped_vehicles': {}}}
        return {'response': {}}


class Coordinator:
    refreshed = 0

    async def async_refresh(self):
        Coordinator.refreshed += 1


class Journal:
    def __init__(self):
        self.points, self.saved = [], []

    def telemetry_point(self, p):
        self.points.append(p)

    async def save_telemetry(self, data):
        self.saved.append(json.loads(json.dumps(data)))


async def main():
    loop = asyncio.get_running_loop()

    def later(_hass, delay, action):
        handle = loop.call_later(delay, action)
        return handle.cancel
    fleet_mod.async_call_later = later
    fleet_mod.async_track_time_interval = lambda *a: (lambda: None)

    subs = []
    async def wait(_hass):
        return True
    async def subscribe(_hass, topic, handler, qos=0):
        subs.append(topic)
        return lambda: None
    ha_mqtt.async_wait_for_mqtt_client, ha_mqtt.async_subscribe = wait, subscribe

    conn, services = Conn(), Calls()
    controller = SimpleNamespace(_Controller__connection=conn)
    entry = SimpleNamespace(entry_id='e1')
    hass = SimpleNamespace(
        config=SimpleNamespace(components={'mqtt'}), services=services,
        config_entries=SimpleNamespace(async_entries=lambda d: [entry] if d in ('tesla_custom', 'mqtt') else []),
        data={'tesla_custom': {'e1': {'cars': {'VIN1': object()}, 'controller': controller, 'coordinators': {'VIN1': Coordinator()}}}},
        async_create_task=lambda coro: loop.create_task(coro))
    journal = Journal()
    zone = SimpleNamespace(state='0', attributes=HOME)
    manager = SimpleNamespace(config=dict(DEFAULTS), memory={'tesla_quota': {}}, journal=journal,
                              state=lambda e: zone if e == DEFAULTS['ev_home_zone'] else None)

    f = fleet_mod.Fleet(hass, manager)
    await f.start({'budget': {'signals_total': 5}, 'meta': {}})
    assert f.mqtt and len(subs) == 4 and f.budget.state['signals_total'] == 5, subs

    msg = lambda field, value, vin='VIN1': SimpleNamespace(topic=f'tesla/{vin}/v/{field}', payload=json.dumps(value))
    f.on_field(msg('Gear', 'ShiftStateD'))
    f.on_field(msg('Location', {'latitude': 45.71831, 'longitude': 21.26521}))
    f.on_field(msg('VehicleSpeed', 31.07))
    f.on_field(msg('DetailedChargeState', 'DetailedChargeStateDisconnected'))
    f.on_field(msg('Gear', 'ShiftStateP', vin='OTHER'))  # another car: ignored, not counted
    await asyncio.sleep(1.3)
    assert len(journal.points) == 1, journal.points
    p = journal.points[0]
    assert p['shift'] == 'D' and p['kmh'] == 50.0 and p['home'] is True and p['nocharge'] is True
    assert p['charging'] is False and p['plugged'] is False and p['src'] == 'telemetry'
    assert f.budget.state['signals_total'] == 9 and f.live() and f.gear() == 'D'

    f.on_connectivity(SimpleNamespace(topic='tesla/VIN1/connectivity', payload=json.dumps({'Status': 'DISCONNECTED'})))
    assert not f.live(), 'a disconnect after the last message ends the live stream'
    f.on_field(msg('Gear', 'ShiftStateP'))
    assert f.live()
    await asyncio.sleep(1.2)

    f.on_update(SimpleNamespace(topic='ops/fleet-telemetry/update', payload=json.dumps(
        {'checked': 1, 'fleet_telemetry': {'latest': 'v0.10.1', 'update': True}, 'mosquitto': {'latest': '2.0.23', 'update': False}})))
    f.on_update(SimpleNamespace(topic='ops/fleet-telemetry/update', payload=json.dumps(
        {'checked': 2, 'fleet_telemetry': {'latest': 'v0.10.1', 'update': True}})))
    await asyncio.sleep(0)
    assert sum(1 for c in services.calls if c[0] == 'persistent_notification') == 1, services.calls

    r = await f.push('x' * 40, 1830000000)
    assert r['updated_vehicles'] == 1 and f.meta['pushed_at'] and f.meta['config_exp'] == 1830000000
    assert conn.calls[-1] == ('vehicles/fleet_telemetry_config_jws', 'post', {'vins': ['VIN1'], 'token': 'x' * 40})

    f.budget.state.update(signals_total=400000, since=time.time() - 86400)  # $3.2 estimated in the trial
    await f.housekeeping()
    assert f.meta['stopped']['reason'] == 'trial', f.meta
    assert conn.calls[-1] == ('vehicles/VIN1/fleet_telemetry_config', 'delete', None)
    assert Coordinator.refreshed >= 2 and journal.saved and journal.saved[-1]['meta']['stopped']['reason'] == 'trial'
    calls = len(conn.calls)
    await f.housekeeping()
    assert len(conn.calls) == calls, 'stopped once, no repeated API calls'
    snap = f.snapshot()
    assert snap['stopped'] and snap['costs']['trial'] and snap['signals_total'] == 400000

    flood = fleet_mod.Fleet(hass, manager)
    flood.mqtt = True
    for _ in range(200):
        flood.on_field(msg('VehicleSpeed', 10))
    assert flood.gate.dropped == 160, flood.gate.dropped  # 40 messages/s accepted
    await asyncio.sleep(1.2)
    print('fleet runtime: ok')


asyncio.run(main())
