DOMAIN = 'home_energy_policy'
STATUS_ENTITY = 'sensor.home_energy_policy_status'
KILL = 'input_boolean.ha_automation_killswitch'
DEVICES = ('tcl', 'whirlpool', 'boiler', 'tesla')
LEGACY = (
    'automation.hvac_solar_climate_control',
    'automation.ariston_solar_boiler_boost_from_surplus',
    'automation.ariston_solar_boiler_stop_when_surplus_drops',
    'automation.ariston_solar_boiler_restore_after_tesla',
    'automation.ariston_summer_default_temperature_manager',
)
