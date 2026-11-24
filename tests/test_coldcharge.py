"""Cold-morning grid-charge decision: window, hysteresis, stop conditions. No HA, no I/O."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('coldcharge', Path(__file__).resolve().parents[1] / 'ha/custom_components/home_energy_policy/coldcharge.py')
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

CFG = {'cold_charge_enabled': True, 'cold_charge_temp_c': 3, 'cold_charge_recover_c': 6,
       'cold_charge_hours_before_sunrise': 3, 'solar_min_kw': 0.5}
SUNRISE = 100000.0
IN = SUNRISE - 3600          # 1h before sunrise, inside the window
EARLY = SUNRISE - 4 * 3600   # 4h before sunrise, outside the window


def test_window_open_is_the_three_hours_before_sunrise():
    assert cc.window_open(IN, SUNRISE, 3)
    assert not cc.window_open(EARLY, SUNRISE, 3)
    assert not cc.window_open(SUNRISE + 1, SUNRISE, 3), 'After sunrise is closed'
    assert not cc.window_open(IN, None, 3), 'No sunrise known'


def test_starts_only_cold_and_in_window():
    assert cc.decide(False, 1.0, IN, SUNRISE, 0.0, CFG)[0] is True
    assert cc.decide(False, 4.0, IN, SUNRISE, 0.0, CFG)[0] is False, 'Above 3 C does not start'
    assert cc.decide(False, 1.0, EARLY, SUNRISE, 0.0, CFG)[0] is False, 'Outside the window'
    assert cc.decide(False, 1.0, IN, SUNRISE, 2.0, CFG)[0] is False, 'Solar already producing'


def test_hysteresis_keeps_it_on_between_3_and_6():
    # Once active, stays on from 3 up to just under the 6 C recovery point.
    assert cc.decide(True, 4.5, IN, SUNRISE, 0.0, CFG)[0] is True
    assert cc.decide(True, 5.9, IN, SUNRISE, 0.0, CFG)[0] is True
    assert cc.decide(True, 6.0, IN, SUNRISE, 0.0, CFG)[0] is False, 'Stops at 6 C'


def test_stop_conditions_recovery_solar_and_window_end():
    assert cc.decide(True, 6.5, IN, SUNRISE, 0.0, CFG) == (False, 'bateria a ajuns la 6 C')
    assert cc.decide(True, 2.0, IN, SUNRISE, 0.8, CFG) == (False, 'a inceput surplusul din panouri, raman doar panourile')
    assert cc.decide(True, 2.0, SUNRISE + 10, SUNRISE, 0.0, CFG)[0] is False, 'Window ended at sunrise'


def test_disabled_or_unknown_temp_never_injects():
    assert cc.decide(True, 1.0, IN, SUNRISE, 0.0, {**CFG, 'cold_charge_enabled': False}) == (False, 'dezactivat')
    assert cc.decide(True, None, IN, SUNRISE, 0.0, CFG) == (False, 'temperatura bateriei indisponibila')
