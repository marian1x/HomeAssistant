"""HA-native policy, independent of the web server and Tesla polling."""
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_register_admin_service
from .const import DOMAIN, DEVICES
from .runtime import Policy
from .outlook import snapshot as outlook_snapshot


async def async_setup(hass, config):
    @websocket_api.websocket_command({vol.Required('type'): DOMAIN + '/get'})
    @websocket_api.async_response
    async def get_policy(hass, connection, msg):
        manager = hass.data.get(DOMAIN)
        if manager is None:
            connection.send_error(msg['id'], 'not_ready', 'Controlul energetic nu este configurat.')
            return
        if not connection.user.permissions.check_entity('sensor.home_energy_policy_status', 'read'):
            connection.send_error(msg['id'], 'unauthorized', 'Acces nepermis.')
            return
        connection.send_result(msg['id'], manager.snapshot())
    websocket_api.async_register_command(hass, get_policy)

    @websocket_api.websocket_command({vol.Required('type'): DOMAIN + '/outlook'})
    @websocket_api.async_response
    async def outlook(hass, connection, msg):
        manager = hass.data.get(DOMAIN)
        if manager is None:
            connection.send_error(msg['id'], 'not_ready', 'Controlul energetic nu este configurat.')
            return
        if not connection.user.permissions.check_entity('sensor.home_energy_policy_status', 'read') or not connection.user.permissions.check_entity('weather.forecast_home', 'read'):
            connection.send_error(msg['id'], 'unauthorized', 'Acces nepermis.')
            return
        connection.send_result(msg['id'], await outlook_snapshot(manager))
    websocket_api.async_register_command(hass, outlook)
    return True


async def async_setup_entry(hass, entry):
    manager = Policy(hass, entry)
    await manager.load()
    hass.data[DOMAIN] = manager

    async def configure(call):
        try:
            await manager.configure(call.data['values'], call.data['revision'])
        except ValueError as error:
            raise ServiceValidationError(str(error)) from error
        return manager.snapshot()

    async def resume(call):
        key = call.data['device']
        # The app role is not a substitute for HA's native entity permission.
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            entity = manager.entity(key)
            if not user or not entity or not user.permissions.check_entity(entity, 'control'):
                raise HomeAssistantError('Control nepermis pentru acest dispozitiv.')
        await manager.resume(key)
        return manager.snapshot()

    async_register_admin_service(hass, DOMAIN, 'configure', configure,
        vol.Schema({vol.Required('values'): dict, vol.Required('revision'): vol.All(int, vol.Range(min=0))}), SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, 'resume_device', resume,
        vol.Schema({vol.Required('device'): vol.In(DEVICES)}), SupportsResponse.ONLY)
    await hass.config_entries.async_forward_entry_setups(entry, ['sensor'])
    await manager.start()
    return True


async def async_unload_entry(hass, entry):
    manager = hass.data[DOMAIN]
    await manager.stop()
    hass.services.async_remove(DOMAIN, 'configure')
    hass.services.async_remove(DOMAIN, 'resume_device')
    unloaded = await hass.config_entries.async_unload_platforms(entry, ['sensor'])
    hass.data.pop(DOMAIN, None)
    return unloaded
