"""Cold-morning heat assist decision: pure logic, no HA, no I/O.

Enables grid charging only (one switch) so the inverter is "waiting to charge" and the pack's
self-heater runs before sunrise when the battery is below freezing. The BMS still caps the real
charge current at low temperature, so little grid energy is actually used. Hysteresis
(start below `temp_c`, stop at `recover_c`) plus the window keep writes to a couple per morning.
"""


def window_open(now_ts, next_rising_ts, hours_before):
    """True when now is within the given hours before the next sunrise."""
    if next_rising_ts is None:
        return False
    return next_rising_ts - hours_before * 3600 <= now_ts < next_rising_ts


def decide(active, temp_c, now_ts, next_rising_ts, pv_kw, cfg):
    """Return (should_be_injecting, reason). `active` is whether we already turned grid charge on.

    cfg needs: cold_charge_enabled, cold_charge_temp_c, cold_charge_recover_c,
    cold_charge_hours_before_sunrise, solar_min_kw.
    """
    if not cfg['cold_charge_enabled']:
        return False, 'dezactivat'
    if temp_c is None:
        return False, 'temperatura bateriei indisponibila'
    win = window_open(now_ts, next_rising_ts, cfg['cold_charge_hours_before_sunrise'])
    solar = pv_kw is not None and pv_kw >= cfg['solar_min_kw']
    if active:
        if temp_c >= cfg['cold_charge_recover_c']:
            return False, 'bateria a ajuns la %g C' % cfg['cold_charge_recover_c']
        if solar:
            return False, 'a inceput surplusul din panouri, raman doar panourile'
        if not win:
            return False, 'in afara ferestrei de dinainte de rasarit'
        return True, 'injectie din retea pentru incalzire'
    if win and temp_c < cfg['cold_charge_temp_c'] and not solar:
        return True, 'injectie din retea, sub %g C inainte de rasarit' % cfg['cold_charge_temp_c']
    return False, 'conditii neindeplinite'
