"""Offline model tests: no HA services, tokens, network, or hardware."""
from datetime import datetime
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / 'ha/custom_components/home_energy_policy'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema, model = load('schema'), load('model')
quota = load('quota')
NOW = datetime(2026, 11, 9, 12)


def config(**values):
    return schema.validate({'enabled': True, **values})


def observed(**values):
    return {'power_ok': True, 'kill': False, 'conflict': False, 'outside': 1, 'soc': 100, 'pv': 8,
            'load': 1, 'export': 7, 'import': 0, 'discharge': 0, 'sun_up': True, 'daylight_hours': 4,
            'forecast_remaining': 30, 'recharge_lock': False, 'ev_connected': True, 'ev_soc': 60,
            'ev_on': False, 'ev_confirmed': False, 'ev_actual_amps': 5, 'owned_optional_kw': 0,
            'tcl_available': True, 'whirlpool_available': True, 'boiler_available': True, 'tesla_available': True,
            'boiler_done': False, 'bms_discharge_kw': 7, 'ev_home':True, 'ev_control_ready':True, **values}


@pytest.mark.parametrize('profile,outside,expected,fan', [('Low', 0, 23, '1'), ('Low', -5, 23, '2'), ('Low', -10, 23, '3'), ('Low', -15, 24, '3'), ('Med', 14, 24, '1'), ('Med', -15, 25, '3'), ('High', 14, 25, '3'), ('High', -15, 27, '3')])
def test_winter_profiles(profile, outside, expected, fan):
    d = model.plan(config(winter_profile=profile), observed(outside=outside, export=0), NOW)['devices']['tcl']
    assert (d['temperature'], d['fan']) == (expected, fan)


@pytest.mark.parametrize('profile,normal,hot', [('Low',22,21), ('Med',21,20), ('High',20,19)])
def test_summer_profiles(profile, normal, hot):
    c = config(season='Summer', summer_profile=profile)
    assert model.plan(c, observed(outside=31, export=0), NOW)['devices']['whirlpool']['temperature'] == normal
    assert model.plan(c, observed(outside=36, export=0), NOW)['devices']['whirlpool']['temperature'] == hot


def test_next_day_resume_is_not_same_day_even_before_six():
    assert model.next_resume(datetime(2026,11,8,2), '06:00') == datetime(2026,11,9,6)


def test_manual_devices_never_receive_targets():
    for key in ('tesla','tcl','whirlpool','boiler'):
        p = model.plan(config(ev_enabled=True), observed(**{key+'_manual': True}), NOW)
        assert p['devices'][key]['mode'] == 'manual'
        assert 'temperature' not in p['devices'][key] and 'amps' not in p['devices'][key]


@pytest.mark.parametrize('override', [{'kill': True}, {'conflict': True}])
def test_pause_has_no_commands(override):
    p = model.plan(config(), observed(**override), NOW)
    assert p['phase'] == 'Pauza'
    assert all(d['mode'] == 'idle' for d in p['devices'].values())


def test_master_off_has_no_commands():
    assert model.plan(config(enabled=False), observed(), NOW)['phase'] == 'Pauza'


def test_no_night_ev_or_solar_boost():
    p = model.plan(config(ev_enabled=True), observed(pv=0, sun_up=False, export=10), NOW)
    assert all(d['mode'] != 'solar' for d in p['devices'].values())
    assert p['devices']['boiler']['temperature'] == 47


def test_battery_charge_is_not_counted_as_ev_surplus():
    # 8 kW PV, 1 kW house and 7 kW absorbed by battery leaves no export.
    p = model.plan(config(ev_enabled=True), observed(export=0, soc=60, recharge_lock=True), NOW)
    assert p['devices']['tesla']['mode'] == 'idle'
    assert p['devices']['boiler']['mode'] == 'normal'


def test_exact_ev_amps_do_not_jump_to_maximum():
    p = model.plan(config(ev_enabled=True, export_buffer_kw=0), observed(export=3, owned_optional_kw=3.3, ev_on=True, ev_confirmed=True, ev_actual_amps=5), NOW)
    assert p['devices']['tesla']['amps'] == 9


def test_unconfirmed_ev_cannot_ramp_up():
    p = model.plan(config(ev_enabled=True), observed(export=10, ev_on=True, ev_actual_amps=5), NOW)
    assert p['devices']['tesla']['amps'] == 5


def test_minimum_ev_supported_by_battery_only_in_good_solar_window():
    p = model.plan(config(ev_enabled=True), observed(export=1, soc=90), NOW)
    assert p['devices']['tesla']['amps'] == 5
    assert p['battery_support_kw'] == pytest.approx(2.3)


@pytest.mark.parametrize('values', [{'soc':70}, {'recharge_lock':True, 'soc':85}, {'forecast_remaining':None}, {'forecast_remaining':1}, {'daylight_hours':.1}, {'bms_discharge_kw':0}])
def test_battery_assistance_safety(values):
    p = model.plan(config(ev_enabled=True), observed(export=1, **values), NOW)
    assert p['devices']['tesla']['mode'] != 'solar'


def test_ev_sheds_on_grid_import_and_battery_discharge():
    p = model.plan(config(ev_enabled=True), observed(export=0, owned_optional_kw=6.6, discharge=1, soc=70, **{'import': 3}), NOW)
    assert p['devices']['tesla']['mode'] == 'idle'


def test_thermal_storage_order_and_soc():
    c = config()
    assert model.plan(c, observed(boiler_done=False), NOW)['devices']['tcl']['mode'] != 'solar'
    assert model.plan(c, observed(boiler_done=True, soc=99), NOW)['devices']['tcl']['mode'] != 'solar'
    p = model.plan(c, observed(boiler_done=True), NOW)
    assert p['devices']['tcl']['temperature'] == 26
    assert p['devices']['whirlpool']['temperature'] == 27


def test_no_bad_sensor_becomes_zero_and_starts_boost():
    p = model.plan(config(ev_enabled=True), observed(power_ok=False, pv=None, soc=None), NOW)
    assert all(d['mode'] != 'solar' for d in p['devices'].values())


@pytest.mark.parametrize('hour,minute,active', [(19,59,False),(20,0,True),(20,59,True),(21,0,False)])
def test_whirlpool_winter_window(hour,minute,active):
    p = model.plan(config(), observed(export=0, whirlpool_normal=hour == 20 and minute > 0), NOW.replace(hour=hour,minute=minute))
    assert (p['devices']['whirlpool']['mode'] == 'normal') is active


def test_missed_winter_window_does_not_start_ac_late():
    assert model.plan(config(), observed(export=0), NOW.replace(hour=20,minute=50))['devices']['whirlpool']['mode'] == 'idle'


def test_solar_charging_never_controls_car_away_from_the_panels():
    p = model.plan(config(ev_enabled=True), observed(ev_home=False), NOW)
    assert p['devices']['tesla']['mode'] != 'solar'


def test_budget_or_sleep_blocks_automatic_charge():
    assert model.plan(config(ev_enabled=True), observed(ev_control_ready=False), NOW)['devices']['tesla']['mode'] != 'solar'


def test_lower_manual_car_limit_and_complete_are_respected():
    assert model.plan(config(ev_enabled=True), observed(ev_soc=70,ev_effective_target=65), NOW)['devices']['tesla']['mode'] != 'solar'
    assert model.plan(config(ev_enabled=True), observed(ev_soc=79,ev_complete=True), NOW)['devices']['tesla']['mode'] != 'solar'


def test_no_night_poll_except_one_midnight_slot():
    c, q = config(), quota.counters({}, NOW)
    o = observed(sun_up=False)
    assert not quota.due(c, q, o, NOW.replace(hour=2))
    assert quota.due(c, q, o, NOW.replace(hour=0,minute=1))
    q['night_day'] = NOW.strftime('%Y-%m-%d')
    assert not quota.due(c, q, o, NOW.replace(hour=0,minute=2))


def test_quota_caps_and_reserved_stop_commands():
    c, q = config(), quota.counters({}, NOW)
    q['reads_day'] = c['ev_reads_daily']
    assert not quota.read_allowed(c, q)
    q['commands_day'] = c['ev_commands_daily']-2
    assert not quota.command_allowed(c, q)
    assert quota.command_allowed(c, q, emergency=True)
    q['emergency_day'] = 2
    assert not quota.command_allowed(c, q, emergency=True)


def test_quota_counts_do_not_reset_on_same_day_restart():
    q = quota.counters({}, NOW)
    q.update(reads_day=15, reads_month=25)
    assert quota.counters(dict(q),NOW)['reads_day'] == 15
    tomorrow = quota.counters(dict(q), NOW.replace(day=10))
    assert tomorrow['reads_day'] == 0 and tomorrow['reads_month'] == 25


def test_home_zone_requires_actual_coordinates():
    assert quota.at_home({'latitude':45,'longitude':21}, {'latitude':45,'longitude':21,'radius':100})
    assert not quota.at_home({'latitude':46,'longitude':21}, {'latitude':45,'longitude':21,'radius':100})
    assert not quota.at_home({}, {'latitude':45,'longitude':21,'radius':100})


@pytest.mark.parametrize('values', [{'winter_cold_c':15}, {'ev_max_amps':17}, {'max_discharge_kw':8}, {'base_reserve_soc':10}, {'enabled':1}, {'boiler_solar_c':float('nan')}, {'manual_resume_at':'25:00'}, {'winter_months':'13'}, {'secret':'x'}])
def test_configuration_bounds(values):
    with pytest.raises(ValueError): schema.validate(values)


def series(levels, now=1000.0, step=30):
    """levels: list of (seconds_ago, l1, l2, l3) in kW."""
    return [(now - ago, a, b, c) for ago, a, b, c in levels]


def test_balanced_three_phase_rise_is_a_car_but_single_phase_is_not():
    now = 1000.0
    before = [(ago, .5, .4, .6) for ago in range(600, 119, -30)]
    car = series(before + [(60, 4.2, 4.1, 4.3), (30, 4.2, 4.1, 4.3), (0, 4.2, 4.1, 4.3)], now)
    assert quota.load_step(car, now) == 1
    boiler = series(before + [(60, 3.5, .4, .6), (30, 3.5, .4, .6), (0, 3.5, .4, .6)], now)
    assert quota.load_step(boiler, now) == 0, 'Single-phase load is not a charger'
    blip = series(before + [(30, 4.2, 4.1, 4.3), (0, .5, .4, .6)], now)
    assert quota.load_step(blip, now) == 0, 'Must be sustained'
    stop = series([(ago, 4.2, 4.1, 4.3) for ago in range(600, 119, -30)] + [(60, .5, .4, .6), (0, .5, .4, .6)], now)
    assert quota.load_step(stop, now) == -1
    assert quota.load_step(car[-3:], now) == 0, 'Needs a baseline'


def test_ev_mode_from_last_known_state():
    assert quota.ev_mode(True, 'D', False, False, False, True) == 'driving'
    assert quota.ev_mode(False, 'D', False, False, False, True) == 'away', 'Offline car is not driving'
    assert quota.ev_mode(True, 'P', True, True, True, True) == 'charging'
    assert quota.ev_mode(False, 'P', False, True, True, True) == 'plugged'
    assert quota.ev_mode(False, 'P', False, False, True, True) == 'home'
    assert quota.ev_mode(False, None, False, False, False, False) == 'unknown'


def test_load_step_triggers_a_read_at_night_with_cooldown_and_cap():
    c, q = config(), quota.counters({}, NOW)
    night = NOW.replace(hour=20)
    q['last_poll'] = night.timestamp() - 3600
    o = observed(sun_up=False, ev_mode='away', load_step=1)
    assert quota.due(c, q, o, night) == 'step_up'
    q['step_at'] = night.timestamp() - 60
    assert not quota.due(c, q, o, night), 'Cooldown after a step read'
    q['step_at'] = 0
    q['steps_day'] = c['ev_step_daily']
    assert not quota.due(c, q, o, night), 'Daily cap on step reads'
    q['steps_day'] = 0
    q['last_poll'] = night.timestamp() - 360
    assert not quota.due(c, q, observed(sun_up=False, ev_mode='charging', load_step=1), night), 'Already known charging'
    assert quota.due(c, q, observed(sun_up=False, ev_mode='charging', load_step=-1), night) == 'step_down'
    assert not quota.due(config(ev_step_enabled=False), q, o, night)
    q['last_poll'] = night.timestamp() - 120
    assert not quota.due(c, q, o, night), 'At least 5 minutes between reads'


def test_cadence_follows_the_car():
    c, q = config(), quota.counters({}, NOW)
    def due_after(minutes, **o):
        q['last_poll'] = NOW.timestamp() - minutes * 60
        return quota.due(c, q, observed(**o), NOW)
    assert due_after(10, ev_mode='driving') == 'driving' and not due_after(9, ev_mode='driving')
    assert due_after(10, ev_mode='charging') == 'charging'
    assert due_after(10, ev_mode='driving', sun_up=False) == 'driving', 'Driving cadence also at night'
    assert due_after(30, ev_mode='plugged') == 'plugged' and not due_after(29, ev_mode='plugged')
    assert due_after(120, ev_mode='away') == 'away' and not due_after(119, ev_mode='away')
    assert not due_after(300, ev_mode='away', sun_up=False, pv=0), 'Parked away: no night reads'
    assert not due_after(60, ev_mode='home', export=0), 'Home idle keeps 90 min'
    assert due_after(90, ev_mode='home', export=0) == 'idle'
    q['reads_day'] = c['ev_reads_daily']
    assert not due_after(60, ev_mode='driving'), 'Budget still applies'


evlimit = load('evlimit')
HOME = {'ev_home': True, 'ev_connected': True}


def test_owner_limit_sets_native_once_then_enforces_below_the_floor():
    assert evlimit.valid(35) and not evlimit.valid(19) and not evlimit.valid(101) and not evlimit.valid(True) and not evlimit.valid(35.5)
    lim = {'soc': 35, 'pending_native': True}
    assert evlimit.decide(lim, HOME, 30, 80, True, True) == ('set_limit', 50)
    lim['pending_native'] = False
    assert evlimit.decide(lim, HOME, 34, 50, True, True) is None
    assert evlimit.decide(lim, HOME, 35, 50, True, True) == ('stop', None)
    assert evlimit.decide(lim, HOME, 35, 50, True, True) == ('stop', None), 'Also a charge the owner started in the car app'
    assert evlimit.decide(lim, {'ev_home': False, 'ev_connected': True}, 40, 50, True, True) is None, 'Only at home'
    lim['stopped'] = True
    assert evlimit.decide(lim, HOME, 34, 50, False, False) is None, 'Hysteresis'
    assert evlimit.decide(lim, HOME, 33, 50, False, False) == ('start', None)
    assert evlimit.decide(lim, HOME | {'ev_complete': True}, 33, 50, False, False) is None
    assert evlimit.decide({'soc': 35}, HOME, 20, 50, False, False) is None, 'Never starts a charge it did not stop'


def test_owner_limit_at_or_above_floor_is_left_to_the_car():
    lim = {'soc': 70, 'pending_native': True}
    assert evlimit.decide(lim, HOME, 60, 50, True, True) == ('set_limit', 70)
    lim['pending_native'] = False
    assert evlimit.decide(lim, HOME, 75, 70, True, True) is None
    assert evlimit.decide(lim | {'stopped': True}, HOME, 40, 70, False, False) == ('start', None), 'Raised target resumes a charge the limit stopped'


def test_near_owner_limit_reads_at_the_active_cadence():
    lim = {'soc': 35}
    assert evlimit.near(lim, HOME, 31) and not evlimit.near(lim, HOME, 30) and not evlimit.near({'soc': 70}, HOME, 69)
    c, q = config(), quota.counters({}, NOW)
    q['last_poll'] = NOW.timestamp() - c['ev_active_seconds']
    assert quota.due(c, q, observed(ev_mode='charging', ev_limit_near=True), NOW) == 'limit'
