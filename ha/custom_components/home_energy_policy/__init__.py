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

    def journal_for(connection, msg):
        manager = hass.data.get(DOMAIN)
        if manager is None or manager.journal is None:
            connection.send_error(msg['id'], 'not_ready', 'Jurnalul Tesla nu este pornit.')
            return None
        if not connection.user.permissions.check_entity('device_tracker.salavat_t3_location_tracker', 'read'):
            connection.send_error(msg['id'], 'unauthorized', 'Acces nepermis.')
            return None
        return manager.journal

    @websocket_api.websocket_command({vol.Required('type'): DOMAIN + '/tesla_log', vol.Optional('days', default=90): vol.All(int, vol.Range(min=1, max=800))})
    @websocket_api.async_response
    async def tesla_log(hass, connection, msg):
        journal = journal_for(connection, msg)
        if journal:
            connection.send_result(msg['id'], await journal.listing(msg['days']))
    websocket_api.async_register_command(hass, tesla_log)

    @websocket_api.websocket_command({vol.Required('type'): DOMAIN + '/tesla_drive', vol.Required('id'): vol.All(int, vol.Range(min=1))})
    @websocket_api.async_response
    async def tesla_drive(hass, connection, msg):
        journal = journal_for(connection, msg)
        if journal:
            drive = await journal.drive(msg['id'])
            if drive is None:
                connection.send_error(msg['id'], 'not_found', 'Deplasare inexistenta.')
            else:
                connection.send_result(msg['id'], drive)
    websocket_api.async_register_command(hass, tesla_drive)

    @websocket_api.websocket_command({vol.Required('type'): DOMAIN + '/bms', vol.Optional('days', default=2): vol.All(int, vol.Range(min=1, max=14))})
    @websocket_api.async_response
    async def bms(hass, connection, msg):
        manager = hass.data.get(DOMAIN)
        if manager is None:
            connection.send_error(msg['id'], 'not_ready', 'Controlul energetic nu este configurat.')
            return
        if not connection.user.permissions.check_entity('sensor.deye_battery', 'read'):
            connection.send_error(msg['id'], 'unauthorized', 'Acces nepermis.')
            return
        reader = getattr(manager, 'bms', None)
        if reader is None:
            connection.send_result(msg['id'], {'available': False, 'status': 'Cititorul Bluetooth nu este pornit', 'latest': None, 'history': []})
            return
        connection.send_result(msg['id'], await reader.snapshot(msg['days']))
    websocket_api.async_register_command(hass, bms)
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

    async def set_ev_limit(call):
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if not user or not user.permissions.check_entity(manager.config['ev_limit'], 'control'):
                raise HomeAssistantError('Control nepermis pentru masina.')
        try:
            await manager.set_ev_limit(call.data['soc'])
        except ValueError as error:
            raise ServiceValidationError(str(error)) from error
        await manager.tick(force=True)
        return manager.snapshot()

    async def set_charge_price(call):
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if not user or not user.permissions.check_entity(manager.config['ev_limit'], 'control'):
                raise HomeAssistantError('Control nepermis pentru masina.')
        if manager.journal is None or not await manager.journal.set_price(call.data['id'], call.data.get('price_kwh'), call.data.get('note', '')[:120]):
            raise ServiceValidationError('Incarcare inexistenta')
        return {'saved': True}

    async def fleet_telemetry(call):
        # Admin only (registered as an admin service). Push needs a config already signed in the
        # Tesla HTTP Proxy add-on with tesla-jws; the private key never leaves the add-on.
        fleet = manager.fleet
        if fleet is None:
            raise ServiceValidationError('Consumatorul Fleet Telemetry nu este pornit')
        action = call.data['action']
        try:
            if action == 'push':
                if not call.data.get('token'):
                    raise ServiceValidationError('Lipseste configul semnat (token)')
                result = await fleet.push(call.data['token'], call.data.get('exp'))
            elif action == 'stop':
                result = {'stopped': await fleet.stop_stream('owner')}
            elif action == 'remote':
                result = await fleet.remote_status()
            else:
                result = {}
        except ServiceValidationError:
            raise
        except Exception as error:
            raise HomeAssistantError('Fleet API: ' + type(error).__name__ + ' ' + str(getattr(error, 'code', '') or '')) from error
        return {'result': result, 'local': fleet.snapshot()}

    async_register_admin_service(hass, DOMAIN, 'fleet_telemetry', fleet_telemetry,
        vol.Schema({vol.Required('action'): vol.In(['status', 'remote', 'push', 'stop']),
                    vol.Optional('token'): vol.All(str, vol.Length(min=20, max=20000)),
                    vol.Optional('exp'): vol.All(int, vol.Range(min=0))}), SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, 'set_charge_price', set_charge_price,
        vol.Schema({vol.Required('id'): vol.All(int, vol.Range(min=1)), vol.Optional('price_kwh'): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=20))),
                    vol.Optional('note', default=''): str}), SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, 'set_ev_limit', set_ev_limit,
        vol.Schema({vol.Required('soc'): vol.All(int, vol.Range(min=20, max=100))}), SupportsResponse.ONLY)
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
    hass.services.async_remove(DOMAIN, 'set_ev_limit')
    hass.services.async_remove(DOMAIN, 'set_charge_price')
    hass.services.async_remove(DOMAIN, 'fleet_telemetry')
    unloaded = await hass.config_entries.async_unload_platforms(entry, ['sensor'])
    hass.data.pop(DOMAIN, None)
    return unloaded
