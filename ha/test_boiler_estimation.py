"""Run inside HA's Python environment; renders actual YAML templates with test inputs."""
from decimal import Decimal
from pathlib import Path
import sys
import unittest

import jinja2
import yaml
from homeassistant.components.integration.sensor import _Left


PACKAGE = yaml.safe_load(Path(sys.argv.pop(1)).read_text())
SENSORS = {item['name']: item for group in PACKAGE['template'] for item in group.get('sensor', [])}
BINARY = next(item for group in PACKAGE['template'] for item in group.get('binary_sensor', []) if item['name'] == 'Ariston boiler consuming estimated')


def render(template, overrides=None):
    states = {
        'input_text.ariston_boiler_power_switch_entity_id': 'switch.boiler_ariston_power',
        'switch.boiler_ariston_power': 'on',
        'binary_sensor.boiler_ariston_is_heating': 'off',
        'input_boolean.ariston_solar_boost_active': 'on',
        'input_number.ariston_boiler_power_kw': '1.8',
    } | (overrides or {})
    env = jinja2.Environment()
    env.globals.update(states=lambda id: states.get(id, 'unknown'), is_state=lambda id, value: states.get(id, 'unknown') == value)
    return env.from_string(template).render().strip()


class BoilerTests(unittest.TestCase):
    def test_boost_is_not_a_measurement(self):
        self.assertEqual(render(BINARY['state']), 'False')

    def test_real_heating_signal_drives_consumption(self):
        self.assertEqual(render(BINARY['state'], {'binary_sensor.boiler_ariston_is_heating': 'on'}), 'True')

    def test_power_off_overrides_stale_heating(self):
        self.assertEqual(render(BINARY['state'], {'switch.boiler_ariston_power': 'off', 'binary_sensor.boiler_ariston_is_heating': 'on'}), 'False')

    def test_unknown_heating_is_not_assumed_idle(self):
        self.assertEqual(render(BINARY['availability'], {'binary_sensor.boiler_ariston_is_heating': 'unavailable'}), 'False')

    def test_confirmed_power_off_is_known_zero(self):
        self.assertEqual(render(BINARY['availability'], {'switch.boiler_ariston_power': 'off', 'binary_sensor.boiler_ariston_is_heating': 'unavailable'}), 'True')

    def test_nominal_power_only_during_heating(self):
        template = SENSORS['Ariston boiler power estimated']['state']
        self.assertEqual(float(render(template, {'binary_sensor.ariston_boiler_consuming_estimated': 'on'})), 1.8)
        self.assertEqual(float(render(template, {'binary_sensor.ariston_boiler_consuming_estimated': 'off'})), 0)

    def test_unknown_heater_state_hides_power(self):
        self.assertEqual(render(SENSORS['Ariston boiler power estimated']['availability']), 'False')

    def test_no_energy_ramp_before_switch_on(self):
        self.assertEqual(_Left().calculate_area_with_two_states(Decimal(3600), Decimal(0), Decimal('1.8')), Decimal(0))

    def test_one_hour_at_nominal_is_1_8_kwh(self):
        self.assertEqual(_Left().calculate_area_with_two_states(Decimal(3600), Decimal('1.8'), Decimal(0)) / 3600, Decimal('1.8'))

    def test_all_energy_integrators_use_left_and_tick(self):
        for sensor in PACKAGE['sensor']:
            self.assertEqual(sensor['method'], 'left')
            self.assertEqual(sensor['max_sub_interval'], {'minutes': 1})


unittest.main()
