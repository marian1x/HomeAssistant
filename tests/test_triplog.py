"""Offline tests of the drive/charge session logic (no HA)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('triplog', Path(__file__).resolve().parents[1] / 'ha/custom_components/home_energy_policy/triplog.py')
triplog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triplog)

HOME = (45.7183, 21.2652)


def snap(t, **kw):
    base = {'t': t, 'soc': None, 'odo': None, 'shift': None, 'lat': None, 'lon': None, 'home': None,
            'charging': None, 'plugged': None, 'added': None, 'power': None, 'outside': None}
    return base | kw


def test_sparse_reads_make_one_drive_from_the_last_parked_reading():
    s = triplog.Sessions()
    s.feed(snap(0, soc=80, odo=1000.0, shift='P', lat=HOME[0], lon=HOME[1], home=True))
    s.feed(snap(600, soc=78, odo=1008.0, shift='D', lat=45.75, lon=21.23, outside=4))
    s.feed(snap(1200, soc=76, odo=1016.0, shift='D', lat=45.80, lon=21.30, outside=5))
    assert not s.done
    s.feed(snap(1800, soc=75, odo=1020.5, shift='P', lat=45.84, lon=21.43, home=False))
    kind, d = s.done[0]
    assert kind == 'drive' and d['km'] == 20.5 and d['start'] == 0 and d['end'] == 1800
    assert d['kwh'] == round(5 / 100 * 57.5, 2) and d['wh_km'] == round(5 / 100 * 57500 / 20.5)
    assert d['avg_kmh'] == 41.0 and d['outside'] == 4.5 and d['start_home'] is True
    assert [p[1:] for p in d['points']] == [list(HOME), [45.75, 21.23], [45.80, 21.30], [45.84, 21.43]]


def test_drive_seen_only_by_odometer_and_noise_is_ignored():
    s = triplog.Sessions()
    s.feed(snap(0, soc=50, odo=500.0, shift='P'))
    s.feed(snap(3600, soc=50, odo=500.02, shift='P'))
    assert not s.done and s.state['drive'] is None, 'GPS/odometer jitter is not a drive'
    s.feed(snap(7200, soc=45, odo=512.0, shift='P', lat=45.8, lon=21.4))
    d = s.done[0][1]
    assert d['km'] == 11.98 and d['approx_start'] and d['start'] == 3600 and s.state['drive'] is None


def test_charge_session_with_counter_and_home_split():
    s = triplog.Sessions()
    s.feed(snap(0, soc=30, charging=True, plugged=True, added=0.0, power=11.0, home=True, lat=HOME[0], lon=HOME[1]))
    for i in range(1, 121):  # one hour, 30 s samples
        s.add_split(30, triplog.split(load=12.0, ev=11.0, pv=0, battery=7.0, grid=5.0))
    s.feed(snap(3600, soc=48, charging=True, plugged=True, added=10.4, power=11.0))
    s.feed(snap(3700, soc=48, charging=False, plugged=True, added=10.5, power=0))
    kind, c = s.done[0]
    assert kind == 'charge' and c['kwh'] == 10.5 and c['start_soc'] == 30 and c['end_soc'] == 48 and c['max_kw'] == 11.0
    assert c['solar_kwh'] == 0 and round(c['battery_kwh'] + c['grid_kwh'], 2) == 11.0
    assert round(c['battery_kwh'], 2) == round(11 * 7 / 12, 2)
    cost = triplog.charge_cost(c, {'import': 1.11, 'export': .45})
    assert cost == round((c['battery_kwh'] * .45 / .9 + c['grid_kwh'] * 1.11) / (3600 / 3700), 2)
    c['price_kwh'] = 2.5
    assert triplog.charge_cost(c, {'import': 1.11, 'export': .45}) == 26.25


def test_marginal_split_gives_the_car_the_solar_surplus_first():
    solar, battery, grid = triplog.split(load=8.0, ev=5.0, pv=9.0, battery=0, grid=0)
    assert (solar, battery, grid) == (5.0, 0, 0)
    solar, battery, grid = triplog.split(load=8.0, ev=5.0, pv=6.0, battery=0, grid=2.0)
    assert (solar, battery, grid) == (3.0, 0, 2.0), 'House takes solar first; the car the rest'
    assert triplog.split(load=1, ev=0, pv=0, battery=0, grid=1) is None


def test_away_charge_without_price_has_no_cost_and_tiny_sessions_are_dropped():
    s = triplog.Sessions()
    s.feed(snap(0, charging=True, plugged=True, added=0.0, home=False))
    s.feed(snap(60, charging=False, plugged=False, added=.05))
    assert s.done == []
    s.feed(snap(100, charging=True, plugged=True, added=0.0, home=False, soc=20))
    s.feed(snap(2000, charging=False, plugged=False, added=30.0, soc=70))
    c = s.done[0][1]
    assert triplog.charge_cost(c, {'import': 1.11, 'export': .45}) is None
    assert c['home'] is False and c['kwh'] == 30.0


def test_out_of_order_readings_are_ignored():
    s = triplog.Sessions()
    s.feed(snap(100, odo=1.0, shift='P'))
    s.feed(snap(50, odo=99.0, shift='D'))
    assert s.state['drive'] is None and s.state['last']['t'] == 100
