"""Offline tests of the Fleet Telemetry parsing, assembly, budget and journal integration (no HA)."""
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'ha/custom_components/home_energy_policy'


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


telemetry, triplog, quota = load('telemetry'), load('triplog'), load('quota')
HOME = (45.7183, 21.2652)


def test_parse_converts_units_and_rejects_garbage():
    assert telemetry.parse('VehicleSpeed', '31.07') == ('kmh', 50.0)
    assert telemetry.parse('VehicleSpeed', 62.137) == ('kmh', 100.0)
    assert telemetry.parse('Odometer', '1000') == ('odo', 1609.34)
    assert telemetry.parse('Gear', '"ShiftStateD"') == ('shift', 'D')
    assert telemetry.parse('Gear', '"ShiftStateSNA"') == ('shift', None)
    assert telemetry.parse('Gear', 'null') == ('shift', None)
    assert telemetry.parse('Location', json.dumps({'latitude': 45.71831234, 'longitude': 21.2652})) == ('loc', (45.718312, 21.2652))
    assert telemetry.parse('Location', json.dumps({'latitude': 0, 'longitude': 0})) == ('loc', None)
    assert telemetry.parse('Location', json.dumps({'latitude': 120, 'longitude': 1})) == ('loc', None)
    assert telemetry.parse('Soc', '101') == ('soc', None)
    assert telemetry.parse('EnergyRemaining', '"55.25"') == ('energy', 55.25)
    assert telemetry.parse('DetailedChargeState', '"DetailedChargeStateCharging"') == ('charge_state', 'Charging')
    assert telemetry.parse('VehicleSpeed', 'not json') is None
    assert telemetry.parse('SomethingNew', '1') is None
    assert telemetry.charging('Charging') == (True, True)
    assert telemetry.charging('Disconnected') == (False, False)
    assert telemetry.charging('Complete') == (False, True)
    assert telemetry.charging(None) == (None, None)


def test_assembler_merges_one_record_and_carries_the_gear_forward():
    a = telemetry.Assembler()
    a.add('shift', 'D', 100.0)
    a.add('loc', (45.0, 21.0), 100.1)
    a.add('kmh', 40.0, 100.2)
    assert not a.due(100.5) and a.due(101.0)
    p = a.flush(101.0)
    assert p['t'] == 100.0 and p['shift'] == 'D' and (p['lat'], p['lon']) == (45.0, 21.0) and p['src'] == 'telemetry'
    a.add('loc', (45.001, 21.001), 106.0)  # next record: only the position changed
    p = a.flush(107.0)
    assert p['shift'] == 'D' and p['kmh'] == 40.0 and p['lat'] == 45.001
    a.add('shift', None, 110.0)  # invalid gear is not carried forward
    assert a.flush(111.0)['shift'] is None
    assert a.flush(112.0) is None


def dense(t, **kw):
    return {'t': t, 'src': 'telemetry', 'nocharge': True, 'soc': None, 'odo': None, 'shift': None, 'lat': None, 'lon': None,
            'home': None, 'charging': None, 'plugged': None, 'added': None, 'power': None, 'outside': None} | kw


def test_dense_stream_gives_exact_start_speed_trail_and_pack_energy():
    s = triplog.Sessions()
    s.feed(dense(0, shift='P', odo=1000.0, soc=80, energy=60.0, lat=HOME[0], lon=HOME[1], home=True))
    # parked for 20 minutes, then leaves: the drive must start at 1200, not at the parked reading
    t, lat = 1200, HOME[0]
    for i in range(120):  # 10 minutes at 5 s
        lat += .0005
        s.feed(dense(t + i * 5, shift='D', odo=1000.0 + i * .07, soc=80 - i * .02, energy=60.0 - i * .012,
                     lat=round(lat, 6), lon=HOME[1], kmh=50.0 + (i % 10), outside=3.0))
    s.feed(dense(t + 600, shift='P', odo=1008.4, soc=77.5, energy=58.5, lat=round(lat, 6), lon=HOME[1], kmh=0))
    kind, d = s.done[0]
    assert kind == 'drive' and d['start'] == 1200 and not d['approx_start'] and d['end'] == 1800
    assert d['km'] == 8.4 and d['source'] == 'telemetry' and d['max_kmh'] == 59
    assert d['energy_basis'] == 'energy' and d['kwh'] == 1.5 and d['wh_km'] == round(1500 / 8.4)
    assert d['avg_kmh'] == round(8.4 / (600 / 3600), 1)
    assert len(d['points']) > 100 and len(d['points'][1]) == 4, 'points carry the speed'
    assert d['points'][0][1:3] == list(HOME)


def test_sparse_snapshot_during_a_live_stream_does_not_touch_the_drive():
    s = triplog.Sessions()
    s.feed(dense(0, shift='P', odo=500.0, soc=60, lat=HOME[0], lon=HOME[1]))
    s.feed(dense(10, shift='D', odo=500.0, soc=60, lat=45.72, lon=21.27, kmh=20))
    # an integration read arriving now still says P with an older odometer: ignored for drives
    s.feed({'t': 12, 'nodrive': True, 'shift': 'P', 'odo': 499.0, 'soc': 60, 'lat': HOME[0], 'lon': HOME[1],
            'charging': False, 'plugged': False})
    assert s.state['drive'] is not None and s.state['last']['odo'] == 500.0 and s.state['last']['shift'] == 'D'
    s.feed(dense(300, shift='D', odo=503.0, soc=59, lat=45.74, lon=21.29, kmh=45))
    s.feed(dense(320, shift='P', odo=503.2, soc=59, lat=45.741, lon=21.291, kmh=0))
    assert s.done[0][1]['km'] == 3.2


def test_telemetry_points_do_not_open_or_close_charges():
    s = triplog.Sessions()
    s.feed({'t': 0, 'charging': True, 'plugged': True, 'added': 0.0, 'home': True, 'soc': 40})
    s.feed(dense(30, shift='P', charging=False, plugged=False))  # nocharge: cannot close it
    assert s.state['charge'] is not None
    s.feed({'t': 3600, 'charging': False, 'plugged': True, 'added': 9.0, 'soc': 55})
    assert s.done[0][0] == 'charge' and s.done[0][1]['kwh'] == 9.0


def test_budget_trial_and_monthly_reserve():
    now = datetime(2026, 12, 3, 12).timestamp()
    b = telemetry.Budget()
    b.count(now, 100000)
    q = {'reads_month': 50, 'commands_month': 5, 'reads_cap': 900, 'commands_cap': 900}
    assert b.over(now, **q) == '', '100k signals ~ $0.80 with safety margin'
    b.count(now, 200000)  # total 300k -> $2.40 estimated inside the first two weeks
    assert b.over(now, **q) == 'trial'
    later = now + 20 * 86400  # after the trial, the month allowance applies
    b2 = telemetry.Budget({'since': now - 20 * 86400})
    b2.count(later, 600000)  # $4.80 estimated
    c = b2.costs(later, **q)
    assert not c['trial'] and c['api_reserve_usd'] > 3 and b2.over(later, **q) == ''
    b2.count(later, 120000)  # $5.76 + used + reserve > $10
    assert b2.over(later, **q) == 'month'


def test_budget_counters_roll_over_by_month():
    b = telemetry.Budget()
    nov, dec = datetime(2026, 11, 30, 12).timestamp(), datetime(2026, 12, 1, 12).timestamp()
    b.count(nov, 10)
    b.count(dec, 3)
    assert b.state['signals_month'] == 3 and b.state['signals_total'] == 13 and b.state['signals_day'] == 3


def test_rate_gate_drops_floods():
    g = telemetry.RateGate()
    assert sum(g.allow(1000.5) for _ in range(100)) == telemetry.MAX_RATE and g.dropped == 100 - telemetry.MAX_RATE
    assert g.allow(1001.0)


def test_config_claims_have_the_owner_fields():
    cfg = telemetry.config('salavat.home.ro', 4443, 'PEM', 1830000000)
    assert cfg['hostname'] == 'salavat.home.ro' and cfg['port'] == 4443 and cfg['exp'] == 1830000000
    for name in ('Location', 'VehicleSpeed', 'Soc', 'Odometer', 'Gear', 'EnergyRemaining'):
        assert name in cfg['fields']
    assert all(f['interval_seconds'] >= 1 for f in cfg['fields'].values())


def test_live_stream_skips_only_the_driving_read():
    c = {'enabled': True, 'ev_monitor_enabled': True, 'ev_reads_daily': 60, 'ev_reads_monthly': 900, 'ev_active_seconds': 120,
         'ev_step_enabled': True, 'ev_step_daily': 12, 'ev_driving_minutes': 10, 'ev_charging_minutes': 10,
         'ev_night_check_at': '00:00', 'solar_min_kw': .3, 'ev_plugged_minutes': 30, 'ev_away_minutes': 120,
         'ev_target_soc': 80, 'ev_idle_minutes': 90}
    now = datetime(2026, 11, 25, 13, 0)
    q = {'reads_day': 0, 'reads_month': 0, 'last_poll': now.timestamp() - 3600}
    o = {'ev_mode': 'driving', 'sun_up': True, 'pv': 2}
    assert quota.due(c, q, o, now) == 'driving'
    assert quota.due(c, q, o | {'telemetry_live': True}, now) == ''
    assert quota.due(c, q, {'ev_mode': 'charging', 'sun_up': True, 'pv': 2, 'telemetry_live': True}, now) == 'charging'
