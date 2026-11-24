"""Run inside HA's Python environment. Fake states/services; never touches HA API."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '/config')
from custom_components.home_energy_policy.runtime import Policy, SOURCE
from custom_components.home_energy_policy import runtime
from custom_components.home_energy_policy import tesla
from custom_components.home_energy_policy.schema import DEFAULTS
from custom_components.home_energy_policy.const import DEVICES, KILL


class States:
    def __init__(self): self.items = {}
    def get(self, key): return self.items.get(key)
    def put(self, key, value, attrs=None):
        self.items[key] = SimpleNamespace(state=str(value), attributes=attrs or {}, last_reported=datetime.now(timezone.utc))


class Services:
    def __init__(self): self.calls = []
    async def async_call(self, *args, **kwargs): self.calls.append((args, kwargs))


async def main():
    p = Policy.__new__(Policy)
    p.lock = asyncio.Lock()
    states, services = States(), Services()
    p.hass = SimpleNamespace(states=states, services=services, is_running=True, config_entries=SimpleNamespace(async_get_entry=lambda _:None))
    runtime.er.async_get = lambda _:SimpleNamespace(async_get=lambda _:None)
    p.config = dict(DEFAULTS, enabled=True)
    p.memory = {'devices': {key: {} for key in DEVICES}}
    p.contexts, p.before, p.load_samples = {}, {}, []
    p.save = lambda: asyncio.sleep(0)
    states.put(KILL, 'off')
    states.put('water_heater.boiler', 'MANUAL', {'temperature':47, 'current_temperature':46})
    states.put('switch.boiler_ariston_power', 'on')
    states.put('binary_sensor.deye_connection', 'on', {'timestamp':datetime.now(timezone.utc).timestamp()})
    for key, val in [('pv',8),('load',1),('grid',-2),('battery',-5)]:
        states.put(SOURCE[key], val, {'unit_of_measurement':'kW'})
    states.put(SOURCE['soc'], 95, {'BMS Discharging Current':140})
    states.put(SOURCE['outside'], 'sunny', {'temperature':4})
    states.put('sensor.deye_battery_voltage', 52)
    states.put('input_number.deye_battery_max_discharge_kw', 7)
    o = p.observe()
    assert o['power_ok'] and o['export'] == 2 and o['discharge'] == 0
    assert o['bms_discharge_kw'] == 7
    # Manual change from native application: no context propagation required.
    p.before['boiler'] = p.fingerprint('boiler')
    old = states.get('water_heater.boiler')
    states.put('water_heater.boiler', 'MANUAL', {'temperature':80,'current_temperature':46})
    event = SimpleNamespace(data={'entity_id':'water_heater.boiler','old_state':old,'new_state':states.get('water_heater.boiler')}, context=SimpleNamespace(id='external', user_id=None))
    await p.on_state(event)
    assert p.until('boiler') and not p.memory['devices']['boiler']['owned']
    assert not await p.call('water_heater','set_temperature','water_heater.boiler',{'temperature':47},'boiler')
    assert services.calls == []
    # An exact pending temperature echo is accepted; a different manual target is not.
    m = p.memory['devices']['boiler']
    import time
    m.update(manual_until=0, owned=True, expected={'temperature':47}, echo_until=time.time()+60)
    p.before['boiler'] = p.fingerprint('boiler')
    old = states.get('water_heater.boiler')
    states.put('water_heater.boiler','MANUAL',{'temperature':47,'current_temperature':46})
    event.data.update(old_state=old,new_state=states.get('water_heater.boiler'))
    await p.on_state(event)
    assert not p.until('boiler')
    old = states.get('water_heater.boiler')
    states.put('water_heater.boiler','MANUAL',{'temperature':65,'current_temperature':46})
    event.data.update(old_state=old,new_state=states.get('water_heater.boiler'))
    await p.on_state(event)
    assert p.until('boiler')
    m.update(manual_until=0)
    states.put(KILL,'on')
    assert not await p.call('water_heater','set_temperature','water_heater.boiler',{'temperature':47},'boiler')
    assert services.calls == []
    # The refresh adapter must never wake a vehicle and must honor its persisted cap.
    p.hass.config_entries = SimpleNamespace(async_get_entry=lambda _:SimpleNamespace(domain='tesla_custom',pref_disable_polling=True,entry_id='test'))
    runtime.er.async_get = lambda _:SimpleNamespace(async_get=lambda _:SimpleNamespace(config_entry_id='test'))
    class Controller:
        def __init__(self): self.calls = []; self.flag = False
        def get_last_update_time(self, **kw): return 1
        def set_updates(self, **kw): self.flag = kw['value']
        def is_car_online(self, **kw): return False
        async def update(self, **kw):
            assert kw['wake_if_asleep'] is False
            self.calls.append(kw)
    controller = Controller()
    coordinator = SimpleNamespace(async_refresh=lambda:asyncio.sleep(0))
    p.hass.data = {'tesla_custom':{'test':{'cars':{'private-vin':{}},'controller':controller,'coordinators':{'private-vin':coordinator}}}}
    original_due = tesla.due
    tesla.due = lambda *args:'idle'
    await tesla.refresh(p, {'sun_up':True,'ev_on':False})
    assert len(controller.calls) == 1 and controller.flag is False
    assert p.memory['tesla_quota']['reads_day'] == 1
    tesla.due = original_due
    # Binding an already running AC must not overwrite its settings before tomorrow.
    from custom_components.home_energy_policy import pricing
    p.revision = 0
    p.memory['tariffs'] = pricing.initial(p.config)
    p.tick = lambda **kwargs:asyncio.sleep(0)
    runtime.er.async_get = lambda _:SimpleNamespace(async_get=lambda _:None)
    states.put('climate.tcl_test', 'heat', {'temperature':23, 'fan_mode':'3', 'fan_modes':['1','2','3','6']})
    await p.configure({'tcl_entity':'climate.tcl_test'},0)
    assert p.until('tcl') and not p.memory['devices']['tcl']['owned']
    assert p.before['tcl'] == p.fingerprint('tcl')
    preserved = p.memory['devices']['tcl']['manual_until']
    await p.configure({'winter_profile':'Med'},1)
    assert p.memory['devices']['tcl']['manual_until'] == preserved
    await p.configure({'tcl_entity':''},2)
    assert p.memory['devices']['tcl'] == {}
    states.put('climate.tcl_test','off',{'temperature':23,'fan_mode':'3','fan_modes':['1','2','3','6']})
    await p.configure({'tcl_entity':'climate.tcl_test'},3)
    assert not p.until('tcl')
    assert services.calls == []
    print('Runtime: telemetry/BMS, manual override, binding holds, exact echoes, global kill and no-wake polling passed; zero physical calls.')


asyncio.run(main())
