"""One authenticated HA WebSocket per browser session, no device polling."""
import asyncio
import contextlib
import json
import time
from urllib.parse import urlparse

import httpx
import websockets

from .policy import Rejected, clean_state


class Peer:
    def __init__(self, sid, store, ha_url, client_id, publish):
        self.sid, self.store, self.ha_url, self.client_id = sid, store, ha_url, client_id
        self.publish = publish
        self.states, self.entities, self.devices, self.areas, self.floors = {}, {}, [], [], []
        self.profile = None
        self.connected = False
        self.last_update = None
        self.pending = {}
        self.sequence = 0
        self.socket = None
        self.task = None
        self.ready = asyncio.Event()
        self.subscribers = {}
        self.last_command = {}
        self.command_lock = asyncio.Lock()
        self.metadata_task = None
        self.metadata_dirty = False
        self.event_revision = 0
        self.state_revisions = {}

    def start(self):
        if not self.task:
            self.task = asyncio.create_task(self.run())

    async def token(self):
        session = self.store.get(self.sid)
        if not session:
            raise Rejected('Sesiunea a expirat.', 401)
        if session['expires_at'] < time.time() + 60:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.post(self.ha_url + '/auth/token', data={'grant_type': 'refresh_token', 'refresh_token': session['refresh_token'], 'client_id': self.client_id})
                if response.status_code in (400, 401, 403):
                    self.store.remove(self.sid)
                    raise Rejected('Autentificarea HA a expirat.', 401)
                response.raise_for_status()
                data = response.json()
            session.update(access_token=data['access_token'], expires_at=time.time() + data['expires_in'])
            self.store.save(self.sid, session)
        return session['access_token']

    async def reader(self):
        async for raw in self.socket:
            packet = json.loads(raw)
            if packet.get('type') == 'result' and packet['id'] in self.pending:
                future = self.pending.pop(packet['id'])
                if not future.done():
                    if packet.get('success'):
                        future.set_result(packet.get('result'))
                    else:
                        future.set_exception(Rejected(packet.get('error', {}).get('message', 'HA a refuzat comanda.')[:200], 502))
            elif packet.get('type') == 'event':
                event = packet.get('event', {})
                data = event.get('data', {})
                entity = data.get('entity_id')
                if event.get('event_type') in ('area_registry_updated', 'floor_registry_updated', 'device_registry_updated', 'entity_registry_updated'):
                    self.metadata_dirty = True
                    if not self.metadata_task or self.metadata_task.done():
                        self.metadata_task = asyncio.create_task(self.metadata_updates())
                # Keep the initial readable entity set: do not broaden permissions from events.
                if entity in self.states:
                    self.event_revision += 1
                    self.state_revisions[entity] = self.event_revision
                    if data.get('new_state') is None:
                        self.states.pop(entity, None)
                    else:
                        self.states[entity] = clean_state(data['new_state'])
                    self.last_update = time.time()
                    self.publish(self, entity)

    async def registries(self, setup=False):
        for attr, kind in (('entities', 'entity_registry'), ('devices', 'device_registry'), ('areas', 'area_registry'), ('floors', 'floor_registry')):
            try:
                data = await self.call({'type': f'config/{kind}/list'}, setup=setup)
            except Rejected:
                data = []
            if attr == 'entities':
                data = {e['entity_id']: {k: e.get(k) for k in ('entity_id', 'device_id', 'area_id', 'hidden_by', 'disabled_by', 'entity_category')} for e in data}
            elif attr == 'devices':
                data = [{k: e.get(k) for k in ('id', 'name', 'name_by_user', 'manufacturer', 'model', 'area_id')} for e in data]
            elif attr == 'floors':
                data = [{k: e.get(k) for k in ('floor_id', 'name', 'level', 'icon')} for e in data]
            setattr(self, attr, data)

    async def metadata_updates(self):
        while self.metadata_dirty and self.connected:
            self.metadata_dirty = False
            await asyncio.sleep(.3)
            await self.registries()
            revision = self.event_revision
            states = await self.call({'type': 'get_states'})
            incoming = {s['entity_id']: clean_state(s) for s in states}
            # Preserve newer events received while HA prepared the full state snapshot.
            for entity, changed in self.state_revisions.items():
                if changed > revision:
                    if entity in self.states:
                        incoming[entity] = self.states[entity]
                    else:
                        incoming.pop(entity, None)
            self.states = incoming
            self.publish(self)

    async def call(self, data, setup=False):
        if not self.socket or (not setup and not self.connected):
            raise Rejected('Home Assistant este deconectat. Comanda nu a fost pusa in asteptare.', 409)
        self.sequence += 1
        request_id = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.socket.send(json.dumps({'id': request_id, **data}))
            return await asyncio.wait_for(future, 12)
        except asyncio.TimeoutError:
            raise Rejected('Confirmarea HA nu a sosit. Verifica starea inainte de a retrimite comanda.', 504)
        finally:
            self.pending.pop(request_id, None)

    async def run(self):
        retry = 1
        while self.store.get(self.sid):
            reader = None
            try:
                token = await self.token()
                parts = urlparse(self.ha_url)
                url = ('wss' if parts.scheme == 'https' else 'ws') + '://' + parts.netloc + parts.path.rstrip('/') + '/api/websocket'
                async with websockets.connect(url, open_timeout=10, ping_interval=20, ping_timeout=15, max_size=16 * 1024 * 1024) as socket:
                    self.socket = socket
                    first = json.loads(await socket.recv())
                    if first.get('type') != 'auth_required':
                        raise RuntimeError('Unexpected HA authentication response')
                    await socket.send(json.dumps({'type': 'auth', 'access_token': token}))
                    if json.loads(await socket.recv()).get('type') != 'auth_ok':
                        self.store.remove(self.sid)
                        raise RuntimeError('HA rejected authentication')
                    reader = asyncio.create_task(self.reader())
                    self.profile = await self.call({'type': 'auth/current_user'}, setup=True)
                    self.store.user(self.profile)
                    self.store.bind(self.sid, self.profile['id'])
                    states = await self.call({'type': 'get_states'}, setup=True)
                    self.states = {s['entity_id']: clean_state(s) for s in states}
                    self.state_revisions.clear()
                    self.event_revision = 0
                    await self.registries(setup=True)
                    await self.call({'type': 'subscribe_events', 'event_type': 'state_changed'}, setup=True)
                    for event in ('area_registry_updated', 'floor_registry_updated', 'device_registry_updated', 'entity_registry_updated'):
                        await self.call({'type': 'subscribe_events', 'event_type': event}, setup=True)
                    self.connected, self.last_update = True, time.time()
                    if self.metadata_dirty and (not self.metadata_task or self.metadata_task.done()):
                        self.metadata_task = asyncio.create_task(self.metadata_updates())
                    self.ready.set()
                    retry = 1
                    self.publish(self)
                    await reader
            except asyncio.CancelledError:
                break
            except Exception:
                # Never log access/refresh tokens, request URLs, or HA credentials.
                pass
            finally:
                self.connected = False
                self.socket = None
                if self.metadata_task:
                    self.metadata_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await self.metadata_task
                    self.metadata_task = None
                if reader:
                    reader.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await reader
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(Rejected('Conexiunea cu HA s-a intrerupt.', 502))
                self.pending.clear()
                self.publish(self)
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    async def identity(self):
        if self.connected:
            self.profile = await self.call({'type': 'auth/current_user'})
        if not self.profile:
            raise Rejected('Autentificarea HA nu este disponibila.', 503)
        return self.profile | {'role': self.store.user(self.profile)}
