from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN]
    async_add_entities([PolicySensor(manager), ReadingSensor(manager, 'import_price', 'Home Energy Import Price', 'RON/kWh'),
                       ReadingSensor(manager, 'export_price', 'Home Energy Export Price', 'RON/kWh'),
                       ReadingSensor(manager, 'temperature', 'Home Energy Outdoor Temperature', '°C', SensorDeviceClass.TEMPERATURE),
                       ReadingSensor(manager, 'cloud_coverage', 'Home Energy Cloud Coverage', '%')])


class ReadingSensor(SensorEntity):
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, manager, key, name, unit, device_class=None):
        self.manager, self.key = manager, key
        self._attr_name = name
        self._attr_unique_id = 'casa_salavat_' + key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, DOMAIN, self.async_write_ha_state))

    @property
    def native_value(self):
        if self.key in ('import_price', 'export_price'):
            return self.manager.rate()[self.key]
        if not self.manager.available('weather.forecast_home'):
            return None
        value = self.manager.number('weather.forecast_home', self.manager.config['weather_stale_seconds'], attribute=self.key)
        state = self.manager.state('weather.forecast_home')
        if value is not None and self.key == 'temperature' and state.attributes.get('temperature_unit') == '°F':
            return round((value-32)*5/9, 2)
        return value


class PolicySensor(SensorEntity):
    _attr_name = 'Home Energy Policy Status'
    _attr_unique_id = 'casa_salavat_energy_policy_status'
    _attr_icon = 'mdi:home-lightning-bolt-outline'
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({'devices', 'reason', 'updated_at', 'last_error', 'season', 'solar_budget_kw', 'battery_support_kw', 'recharge_lock', 'power_valid', 'outside_c', 'battery_soc', 'pv_kw', 'import_kw', 'export_kw', 'forecast_remaining_kwh', 'ac_power_estimated', 'tesla_quota', 'ev_limit', 'cold_charge'})

    def __init__(self, manager):
        self.manager = manager

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, DOMAIN, self.async_write_ha_state))

    @property
    def native_value(self):
        return self.manager.status.get('phase', 'Initializare')

    @property
    def extra_state_attributes(self):
        return self.manager.status
