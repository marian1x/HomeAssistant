"""Owner charge limit for the car, including targets below the car's own 50 % floor.

>= 50 %: the car's native charge limit is set once and the car enforces it.
<  50 %: the native limit stays at 50 % and, only at home while plugged in, charging is
stopped at the target; a charge stopped this way restarts once the battery is 2 points
below it. Charging the owner starts above the target with the car app is stopped too: the
target is the owner's explicit limit, changed only from the Casa interface.
"""

NATIVE_FLOOR = 50
LOW, HIGH = 20, 100
RESTART_BELOW = 2


def valid(soc):
    return isinstance(soc, int) and not isinstance(soc, bool) and LOW <= soc <= HIGH


def near(lim, o, soc):
    """A charging car close to a sub-floor target is read at the active cadence."""
    target = (lim or {}).get('soc')
    return bool(target and target < NATIVE_FLOOR and o.get('ev_home') and o.get('ev_connected')
                and soc is not None and soc >= target - 4)


def decide(lim, o, soc, native, charging, switch_on):
    """Next single action as (service, value) or None. Caller checks freshness/budget."""
    target = (lim or {}).get('soc')
    if not target:
        return None
    want = max(NATIVE_FLOOR, target)
    if lim.get('pending_native') and native is not None and native != want:
        return ('set_limit', want)
    if not o.get('ev_home') or not o.get('ev_connected') or soc is None:
        return None
    if target < NATIVE_FLOOR and charging and soc >= target:
        return ('stop', None)
    # Only a charge this limit stopped is restarted (also after the owner raises the target).
    if lim.get('stopped') and not charging and not switch_on and not o.get('ev_complete') and soc <= target - RESTART_BELOW:
        return ('start', None)
    return None
