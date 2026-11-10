import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode, urlparse
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .accounts import ROLES, USERNAME, check_password, hash_password, new_secret, otpauth, password_problem, temporary_password, totp_step
from .ha import Peer
from .policy import BASE, BINDINGS, HELPERS, HISTORY_ENERGY, HISTORY_POWER, KILL, LEVEL, RULE_PREFIX, Rejected, build_rule, command
from .store import SESSION_IDLE, Store
from . import energy
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
HOUSE = json.loads((ROOT / 'server/house.json').read_text(encoding='utf-8'))
HA_URL = os.environ.get('HA_URL', 'http://192.168.50.107:8123').rstrip('/')
PUBLIC_URL = os.environ.get('PUBLIC_URL', 'https://salavat.home.ro/casa').rstrip('/')
HA_AUTH_URL = os.environ.get('HA_AUTH_URL', 'https://salavat.home.ro/home-assistant/auth/authorize')
CLIENT_ID = PUBLIC_URL + '/'
ORIGIN = urlparse(PUBLIC_URL).scheme + '://' + urlparse(PUBLIC_URL).netloc
SECURE = PUBLIC_URL.startswith('https://')
if not SECURE and urlparse(PUBLIC_URL).hostname not in ('localhost', '127.0.0.1'):
    raise RuntimeError('HTTPS is required outside local development')
COOKIE = '__Secure-casa_session' if SECURE else 'casa_session'
STATE_COOKIE = '__Secure-casa_oauth' if SECURE else 'casa_oauth'
store = Store(os.environ.get('STATE_DIR', str(ROOT / '.state')))
peers, oauth_states, rate_buckets = {}, {}, {}
# Sessions now last weeks: close an unused HA WebSocket after 10 minutes without
# requests or open event streams; the next request reconnects it.
PEER_IDLE = 600
# Casa-only accounts (owner decision 2026-11-10) reach HA through one technical HA
# account connected by the HA administrator. Its tokens are a server-side row in the
# encrypted session store; roles are enforced here, never by the browser.
SERVICE = 'service'
SERVICE_EXPIRES = 4102444800.0  # 2100-01-01: ends only on disconnect or HA revocation
CHALLENGE_COOKIE = '__Secure-casa_local' if SECURE else 'casa_local'
login_challenges, login_failures = {}, {}


def publish(peer, entity=None):
    for queue, changed in peer.subscribers.items():
        changed.add(entity or '*')
        if queue.empty():
            queue.put_nowait(True)


async def sweep():
    for sid, payload in store.expired():
        if not payload.get('refresh_token'):
            store.remove(sid)  # Casa-only session: no HA token to revoke
            continue
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(HA_URL + '/auth/token', data={'action': 'revoke', 'token': payload['refresh_token']})
            if response.status_code < 500:
                store.remove(sid)
        except httpx.HTTPError:
            pass
    for sid in list(peers):
        peer = peers[sid]
        if not store.get(sid) or (not peer.subscribers and time.time() - getattr(peer, 'last_access', 0) > PEER_IDLE):
            await peers.pop(sid).close()
    for state in list(oauth_states):
        if oauth_states[state][1] < time.time():
            oauth_states.pop(state, None)
    for key in list(login_challenges):
        if login_challenges[key]['expires'] < time.time():
            login_challenges.pop(key, None)
    for ip in list(login_failures):
        login_failures[ip] = [stamp for stamp in login_failures[ip] if time.time() - stamp < 900]
        if not login_failures[ip]:
            login_failures.pop(ip, None)
    rate_buckets.clear()


@asynccontextmanager
async def lifespan(_):
    async def cleanup():
        while True:
            await asyncio.sleep(60)
            await sweep()
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    for peer in list(peers.values()):
        await peer.close()


app = FastAPI(title='Casa Salavat', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(PUBLIC_URL).hostname, '127.0.0.1', 'localhost'])


@app.exception_handler(Rejected)
async def rejected(_, error):
    return JSONResponse({'error': error.message}, status_code=error.status)


@app.middleware('http')
async def protection(request, call_next):
    if request.url.path.startswith(BASE + '/api'):
        origin = request.headers.get('origin')
        site = request.headers.get('sec-fetch-site')
        if (origin and origin != ORIGIN) or (site and site != 'same-origin'):
            return JSONResponse({'error': 'Origine nepermisa.'}, 403)
    response = await call_next(request)
    if request.url.path.startswith(BASE + '/api') and response.status_code < 400:
        handle = request.cookies.get(COOKIE)
        if handle and store.renew(handle):
            response.set_cookie(COOKIE, handle, httponly=True, secure=SECURE, samesite='lax', path=BASE + '/', max_age=SESSION_IDLE)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=(), usb=()'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"
    if '/assets/' not in request.url.path:
        response.headers['Cache-Control'] = 'no-store'
    return response


def local_profile(session):
    account = store.local_get(session['local'])
    if not account or account['disabled']:
        return None
    return {'id': account['id'], 'name': account['name'], 'is_admin': False, 'local': True,
            'role': account['role'] if account['role'] in ROLES else 'viewer'}


def service_peer():
    if not store.get(SERVICE):
        raise Rejected('Contul tehnic HA nu este conectat. Administratorul il poate conecta din Setari.', 503)
    if SERVICE not in peers:
        peers[SERVICE] = Peer(SERVICE, store, HA_URL, CLIENT_ID, publish)
    return peers[SERVICE]


def require_admin(profile):
    # Mod Admin and the Casa "Parametri" role are not HA administration rights.
    if profile.get('local') or profile.get('is_admin') is not True:
        raise Rejected('Doar administratorul Home Assistant poate face asta.', 403)


async def access(request, level='viewer', mutation=False):
    sid, session = store.identify(request.cookies.get(COOKIE, ''))
    if not session:
        raise Rejected('Autentificare necesara.', 401)
    request.state.sid = sid
    if mutation:
        if request.headers.get('origin') != ORIGIN or not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
            raise Rejected('Cerere neautorizata.', 403)
        bucket = rate_buckets.setdefault(sid, [])
        bucket[:] = [stamp for stamp in bucket if time.time() - stamp < 60]
        if len(bucket) >= 30:
            raise Rejected('Prea multe comenzi. Asteapta un minut.', 429)
        bucket.append(time.time())
    profile = None
    if session.get('local'):
        profile = local_profile(session)
        if not profile:
            store.expire(sid)
            raise Rejected('Autentificare necesara.', 401)
        peer = service_peer()
    else:
        if sid not in peers:
            peers[sid] = Peer(sid, store, HA_URL, CLIENT_ID, publish)
        peer = peers[sid]
    peer.last_access = time.time()
    peer.start()
    if not peer.ready.is_set():
        try:
            await asyncio.wait_for(peer.ready.wait(), 15)
        except asyncio.TimeoutError:
            if profile:
                raise Rejected('Contul tehnic HA nu raspunde momentan.', 503)
            if not store.get(sid):
                raise Rejected('Autentificarea HA a expirat.', 401)
            raise Rejected('HA nu raspunde momentan.', 503)
    if mutation and not peer.connected:
        raise Rejected('HA este deconectat. Comanda nu a fost pusa in asteptare.', 409)
    if profile is None:
        profile = await peer.identity() if mutation or level == 'configure' else peer.profile | {'role': store.user(peer.profile)}
    if LEVEL.get(profile['role'], -1) < LEVEL[level]:
        raise Rejected('Nivel de acces insuficient.')
    return peer, session, profile


def person(peer, session):
    if session.get('local'):
        profile = local_profile(session)
        return profile and {'id': profile['id'], 'name': profile['name'], 'role': profile['role'], 'local': True, 'admin': False}
    profile = peer.profile or {}
    return {'id': profile.get('id'), 'name': profile.get('name'), 'role': store.user(profile), 'local': False,
            'admin': profile.get('is_admin') is True} if profile else None


def snapshot(peer, session):
    return {'user': person(peer, session),
            'connected': peer.connected, 'last_update': peer.last_update, 'csrf': session['csrf'],
            'states': peer.states, 'entities': list(peer.entities.values()), 'devices': peer.devices, 'areas': peer.areas,
            'floors': getattr(peer, 'floors', []), 'house': HOUSE,
            'bindings': BINDINGS, 'helpers': HELPERS}


@app.get(BASE + '/auth/login')
async def login():
    # Bound pending logins; no login identifiers or credentials are accepted here.
    if len(oauth_states) > 200:
        raise Rejected('Prea multe autentificari in asteptare.', 429)
    return oauth_start(RedirectResponse, None)


def oauth_start(kind, service_admin):
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    # service_admin: HA admin id when this flow connects the technical account.
    oauth_states[state] = (hashlib.sha256(verifier.encode()).hexdigest(), time.time() + 300, service_admin)
    url = HA_AUTH_URL + '?' + urlencode({'client_id': CLIENT_ID, 'redirect_uri': PUBLIC_URL + '/auth/callback', 'state': state})
    response = kind({'url': url}) if kind is JSONResponse else kind(url, 302)
    response.set_cookie(STATE_COOKIE, verifier, httponly=True, secure=SECURE, samesite='lax', path=BASE + '/auth', max_age=300)
    return response


@app.get(BASE + '/auth/callback')
async def callback(request: Request, state: str = '', code: str = ''):
    expected = oauth_states.pop(state, None)
    cookie = request.cookies.get(STATE_COOKIE, '')
    if not code or not expected or expected[1] < time.time() or not hmac.compare_digest(expected[0], hashlib.sha256(cookie.encode()).hexdigest()):
        raise Rejected('Autentificare expirata sau invalida.', 400)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(HA_URL + '/auth/token', data={'grant_type': 'authorization_code', 'code': code, 'client_id': CLIENT_ID})
            response.raise_for_status()
            tokens = response.json()
    except (httpx.HTTPError, ValueError):
        raise Rejected('Home Assistant a refuzat autentificarea.', 401)
    if expected[2]:
        old = store.get(SERVICE)
        store.save(SERVICE, {'access_token': tokens['access_token'], 'refresh_token': tokens['refresh_token'],
                             'expires_at': time.time() + tokens['expires_in'], 'csrf': ''}, SERVICE_EXPIRES)
        peer = peers.pop(SERVICE, None)
        if peer:
            await peer.close()
        peers[SERVICE] = Peer(SERVICE, store, HA_URL, CLIENT_ID, publish)
        peers[SERVICE].last_access = time.time()
        peers[SERVICE].start()
        if old and old.get('refresh_token') and old['refresh_token'] != tokens['refresh_token']:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(HA_URL + '/auth/token', data={'action': 'revoke', 'token': old['refresh_token']})
            except httpx.HTTPError:
                pass
        store.log(expected[2], 'service_connect', 'cont tehnic HA', 'Conectat')
        response = RedirectResponse(BASE + '/#setari', 303)
        response.delete_cookie(STATE_COOKIE, path=BASE + '/auth', secure=SECURE, samesite='lax')
        return response
    handle, sid = store.create({'access_token': tokens['access_token'], 'refresh_token': tokens['refresh_token'], 'expires_at': time.time() + tokens['expires_in']})
    peer = peers[sid] = Peer(sid, store, HA_URL, CLIENT_ID, publish)
    peer.last_access = time.time()
    peer.start()
    response = RedirectResponse(BASE + '/', 303)
    response.set_cookie(COOKIE, handle, httponly=True, secure=SECURE, samesite='lax', path=BASE + '/', max_age=SESSION_IDLE)
    response.delete_cookie(STATE_COOKIE, path=BASE + '/auth', secure=SECURE, samesite='lax')
    return response


@app.get(BASE + '/api/session')
async def session(request: Request):
    peer, session, _ = await access(request)
    return snapshot(peer, session)


@app.get(BASE + '/api/events')
async def events(request: Request):
    peer, session, _ = await access(request)
    async def stream():
        queue = asyncio.Queue(maxsize=1)
        changed = set()
        peer.subscribers[queue] = changed
        try:
            yield 'data: ' + json.dumps(snapshot(peer, session)) + '\n\n'
            while not await request.is_disconnected() and store.get(request.state.sid):
                try:
                    await asyncio.wait_for(queue.get(), 20)
                    await asyncio.sleep(.3)
                    packet = snapshot(peer, session) if '*' in changed else {'type': 'delta', 'connected': peer.connected, 'last_update': peer.last_update, 'states': {entity: peer.states.get(entity) for entity in changed}}
                    changed.clear()
                    yield 'data: ' + json.dumps(packet) + '\n\n'
                except asyncio.TimeoutError:
                    yield ': heartbeat\n\n'
        finally:
            peer.subscribers.pop(queue, None)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    entity_id: str
    action: str
    value: float | str | None = None


class EnergyConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int
    values: dict


class EnergyResume(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    device: Literal['tesla', 'boiler', 'tcl', 'whirlpool']


@app.get(BASE + '/api/v1/energy-policy')
async def energy_policy(request: Request):
    peer, _, _ = await access(request)
    return await peer.call({'type': 'home_energy_policy/get'})


@app.post(BASE + '/api/v1/energy-policy')
async def energy_config(data: EnergyConfig, request: Request):
    peer, _, profile = await access(request, 'configure', True)
    if len(data.values) > 160 or data.revision < 0:
        raise Rejected('Configuratie invalida.', 422)
    async with peer.command_lock:
        result = await peer.call({'type': 'call_service', 'domain': 'home_energy_policy', 'service': 'configure',
                                 'service_data': data.model_dump(), 'return_response': True})
    store.log(profile['id'], 'energy_policy_configure', 'home_energy_policy', 'Configuratie validata de HA')
    return result.get('response', result)


@app.post(BASE + '/api/v1/energy-policy/resume')
async def energy_resume(data: EnergyResume, request: Request):
    peer, _, profile = await access(request, 'control', True)
    async with peer.command_lock:
        result = await peer.call({'type': 'call_service', 'domain': 'home_energy_policy', 'service': 'resume_device',
                                 'service_data': data.model_dump(), 'return_response': True})
    store.log(profile['id'], 'energy_policy_resume', data.device, 'Control automat reluat')
    return result.get('response', result)


@app.post(BASE + '/api/command')
async def execute(data: Command, request: Request):
    peer, _, profile = await access(request, 'control', True)
    if not peer.connected:
        raise Rejected('HA este deconectat; comanda nu a fost salvata pentru mai tarziu.', 409)
    async with peer.command_lock:
        if time.time() - peer.last_command.get(data.entity_id, 0) < 1:
            raise Rejected('Asteapta confirmarea comenzii anterioare.', 429)
        domain, service, args = command(profile['role'], data.entity_id, data.action, data.value, peer.states, peer.entities)
        peer.last_command[data.entity_id] = time.time()
        try:
            rule_id = peer.states[data.entity_id].get('attributes', {}).get('id', '')
            if domain == 'automation' and rule_id.startswith(RULE_PREFIX):
                # Persist the chosen state for app-created rules across HA restarts.
                token = await peer.token()
                async with httpx.AsyncClient(timeout=15) as client:
                    url = HA_URL + '/api/config/automation/config/' + rule_id
                    stored = await client.get(url, headers={'Authorization': 'Bearer ' + token})
                    if stored.status_code >= 400:
                        raise Rejected('Regula nu a putut fi citita din HA.', 502)
                    config = stored.json()
                    config['initial_state'] = service == 'turn_on'
                    saved = await client.post(url, headers={'Authorization': 'Bearer ' + token}, json=config)
                    if saved.status_code >= 400:
                        raise Rejected('Starea regulii nu a putut fi salvata.', 502)
            await peer.call({'type': 'call_service', 'domain': domain, 'service': service, 'service_data': args})
        except Rejected:
            store.log(profile['id'], service, data.entity_id, 'Fara confirmare')
            raise
        store.log(profile['id'], service, data.entity_id, 'Acceptata de HA')
    return {'accepted': True}


@app.get(BASE + '/api/history')
async def history(request: Request, period: str = 'day'):
    peer, _, _ = await access(request)
    if period not in ('day', 'week', 'month', 'year'):
        raise Rejected('Perioada invalida.', 422)
    days, interval = {'day': (1, '5minute'), 'week': (7, 'hour'), 'month': (30, 'day'), 'year': (365, 'month')}[period]
    ids, metric = (HISTORY_POWER, 'mean') if period == 'day' else (HISTORY_ENERGY, 'change')
    end = datetime.now(timezone.utc)
    result = await peer.call({'type': 'recorder/statistics_during_period', 'start_time': (end - timedelta(days=days)).isoformat(), 'end_time': end.isoformat(), 'statistic_ids': ids, 'period': interval, 'types': [metric]})
    rows = {}
    for index, entity in enumerate(ids):
        for item in result.get(entity, []):
            timestamp = item['start']
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp).timestamp() * 1000
            if timestamp < end.timestamp() * 1000 and item.get(metric) is not None:
                rows.setdefault(timestamp, {'time': timestamp})[['solar', 'load', 'battery', 'grid'][index]] = item[metric]
    return {'period': period, 'unit': 'kW' if period == 'day' else 'kWh', 'points': [rows[k] for k in sorted(rows)][-400:]}


async def energy_data(peer, start, end, policy, mode, timezone_name):
    tz = ZoneInfo(timezone_name)
    begin, finish = energy.boundaries(start,end,tz,datetime.now(timezone.utc))
    key = (start,end,policy['revision'],mode)
    cache = getattr(peer, 'energy_cache', {})
    peer.energy_cache = cache
    if key in cache and time.time()-cache[key][0] < 180:
        return cache[key][1]
    bucket = getattr(peer,'energy_reads',[])
    bucket = [t for t in bucket if time.time()-t < 60]
    if len(bucket) >= 8:
        raise Rejected('Prea multe rapoarte diferite. Asteapta un minut.',429)
    bucket.append(time.time())
    peer.energy_reads = bucket
    period = 'hour' if (finish-begin).days <= 93 else 'day'
    raw = await energy.read_statistics(peer,begin,finish,period)
    result = energy.report(raw,begin,finish,policy['tariffs'],mode,policy['active_tariff'])
    # Existing weather history fills the initial gap before the new long-term
    # outdoor sensors were installed. Data gaps are never filled with zero.
    recent = max(begin,datetime.now(timezone.utc)-timedelta(days=30))
    if recent < finish and any(r['temperature'] is None for r in result['days']):
        weather = getattr(peer,'energy_weather_cache',None)
        if not weather or time.time()-weather[0] >= 900:
            try:
                token = await peer.token()
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(HA_URL+'/api/history/period/'+(datetime.now(timezone.utc)-timedelta(days=30)).isoformat(),
                        params={'filter_entity_id':'weather.forecast_home','end_time':datetime.now(timezone.utc).isoformat()}, headers={'Authorization':'Bearer '+token})
                    r.raise_for_status()
                    series = r.json()
                weather = (time.time(),series[0] if series else [])
                peer.energy_weather_cache = weather
            except (httpx.HTTPError,ValueError):
                weather = (time.time(),[])
                peer.energy_weather_cache = weather
        weather_days = energy.raw_weather_days(weather[1],tz,recent,finish)
        for row in result['days']:
            if row['date'] in weather_days:
                for field,value in weather_days[row['date']].items():
                    if row[field] is None: row[field] = value
    cache[key] = (time.time(),result)
    while len(cache) > 8: cache.pop(next(iter(cache)))
    return result


@app.get(BASE + '/api/v1/energy-dashboard')
async def energy_dashboard(request: Request, start: str, end: str, mode: Literal['historical','current']='historical'):
    peer, _, _ = await access(request)
    # Validate before any expensive native request; the authoritative timezone is
    # returned by HA and validated again below.
    energy.boundaries(start,end,ZoneInfo('Europe/Bucharest'),datetime.now(timezone.utc))
    policy = await peer.call({'type':'home_energy_policy/get'})
    if 'tariffs' not in policy:
        raise Rejected('Componenta de costuri este in curs de instalare.',503)
    feed = await peer.call({'type':'home_energy_policy/outlook'})
    tz = ZoneInfo(feed['timezone'])
    now = datetime.now(tz)
    result = await energy_data(peer,start,end,policy,mode,feed['timezone'])
    month = await energy_data(peer,now.replace(day=1).date().isoformat(),now.date().isoformat(),policy,'historical',feed['timezone'])
    training = await energy_data(peer,(now.date()-timedelta(days=28)).isoformat(),now.date().isoformat(),policy,'historical',feed['timezone'])
    return {'report':result,'month':month,'outlook':energy.forecast(feed,training,policy['config'],policy['tariffs']),
            'pricing':{'revision':policy['revision'],'config':{k:v for k,v in policy['config'].items() if k.startswith('energy_')},
                       'active':policy['active_tariff'],'history':policy['tariffs']},'timezone':feed['timezone']}


@app.post(BASE + '/api/rules')
async def create_rule(data: dict, request: Request):
    peer, _, profile = await access(request, 'configure', True)
    if profile.get('local') or not profile.get('is_admin'):
        raise Rejected('Configurarea regulilor necesita administrator HA.')
    rule_id = RULE_PREFIX + secrets.token_hex(8)
    config = build_rule(data, peer.states, peer.entities, rule_id)
    token = await peer.token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(HA_URL + '/api/config/automation/config/' + rule_id, headers={'Authorization': 'Bearer ' + token}, json=config)
        if response.status_code >= 400:
            raise Rejected('HA nu a putut salva regula.', 502)
    store.log(profile['id'], 'create_rule', rule_id, 'Salvata oprita')
    return {'id': rule_id, 'enabled': False}


@app.get(BASE + '/api/audit')
async def audit(request: Request):
    _, _, profile = await access(request, 'configure')
    require_admin(profile)
    rows = store.db.execute("SELECT audit.at,COALESCE(users.name,local_users.name || ' (cont Casa)'),audit.action,audit.entity,audit.result FROM audit "
                            'LEFT JOIN users ON users.id=audit.actor LEFT JOIN local_users ON local_users.id=audit.actor ORDER BY audit.id DESC LIMIT 100').fetchall()
    return [{'at': r[0], 'name': r[1], 'action': r[2], 'entity': r[3], 'result': r[4]} for r in rows]


@app.get(BASE + '/api/users')
async def users(request: Request):
    _, _, profile = await access(request, 'configure')
    require_admin(profile)
    return [{'id': r[0], 'name': r[1], 'role': 'configure' if r[3] else r[2] if r[2] in ('viewer', 'control') else 'viewer', 'is_admin': bool(r[3])} for r in store.db.execute('SELECT id,name,role,is_admin FROM users ORDER BY name COLLATE NOCASE')]


class UserRole(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['viewer', 'control']


@app.post(BASE + '/api/users/{user_id}')
async def user_role(user_id: str, data: UserRole, request: Request):
    _, _, profile = await access(request, 'configure', True)
    require_admin(profile)
    if user_id == profile['id']:
        raise Rejected('Nu iti poti modifica propriul rol.', 403)
    target = store.db.execute('SELECT is_admin FROM users WHERE id=?', (user_id,)).fetchone()
    if target is None:
        raise Rejected('Utilizatorul nu a accesat inca aplicatia.', 404)
    if target[0]:
        raise Rejected('Rolul Admin este administrat din Home Assistant.', 403)
    store.db.execute('UPDATE users SET role=? WHERE id=?', (data.role, user_id))
    store.db.commit()
    store.log(profile['id'], 'set_role', user_id, data.role)
    for peer in peers.values():
        if peer.profile and peer.profile.get('id') == user_id:
            publish(peer)
    return {'saved': True}


@app.post(BASE + '/api/logout')
async def logout(request: Request):
    sid, session = store.identify(request.cookies.get(COOKIE, ''))
    if request.headers.get('origin') != ORIGIN or (session and not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf'])):
        raise Rejected('Cerere neautorizata.', 403)
    store.expire(sid)
    peer = peers.pop(sid, None)
    if peer:
        await peer.close()
    if session and session.get('refresh_token'):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(HA_URL + '/auth/token', data={'action': 'revoke', 'token': session['refresh_token']})
                if response.status_code < 500:
                    store.remove(sid)
        except httpx.HTTPError:
            pass
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE, path=BASE + '/', secure=SECURE, samesite='lax')
    return response


@app.post(BASE + '/api/logout-all')
async def logout_all(request: Request):
    # Ends every Casa session of this HA user (phone, tablet, browsers), this one included.
    # HA refresh tokens are revoked by the cleanup task; HA's own sessions are not touched.
    sid, session = store.identify(request.cookies.get(COOKIE, ''))
    if not session:
        raise Rejected('Autentificare necesara.', 401)
    if request.headers.get('origin') != ORIGIN or not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
        raise Rejected('Cerere neautorizata.', 403)
    user_id = store.owner(sid)
    closed = store.expire_user(user_id) if user_id else []
    if sid not in closed:
        store.expire(sid)
        closed.append(sid)
    for item in closed:
        peer = peers.pop(item, None)
        if peer:
            await peer.close()
    store.log(user_id or '', 'logout_all', 'sesiuni', f'{len(closed)} sesiuni inchise')
    response = JSONResponse({'ok': True, 'closed': len(closed)})
    response.delete_cookie(COOKIE, path=BASE + '/', secure=SECURE, samesite='lax')
    return response


class LocalLogin(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class LocalVerify(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    code: str = Field(max_length=12)
    new_password: str | None = Field(default=None, max_length=256)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


class LocalUserNew(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(max_length=32)
    name: str = Field(max_length=60)
    role: Literal['viewer', 'control', 'configure']


class LocalUserEdit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str | None = Field(default=None, max_length=60)
    role: Literal['viewer', 'control', 'configure'] | None = None
    disabled: bool | None = None


def login_guard(request):
    # The Casa login endpoints are outside /casa/api: require our exact Origin here.
    if request.headers.get('origin') != ORIGIN:
        raise Rejected('Cerere neautorizata.', 403)
    # uvicorn listens only on 127.0.0.1; nginx sets X-Real-IP from the TCP peer.
    ip = request.headers.get('x-real-ip') or (request.client.host if request.client else '')
    failures = login_failures.setdefault(ip, [])
    failures[:] = [stamp for stamp in failures if time.time() - stamp < 900]
    if len(failures) >= 10:
        raise Rejected('Prea multe incercari. Incearca din nou in 15 minute.', 429)
    return failures


def session_cookie(response, handle):
    response.set_cookie(COOKIE, handle, httponly=True, secure=SECURE, samesite='lax', path=BASE + '/', max_age=SESSION_IDLE)


@app.post(BASE + '/auth/local')
async def local_login(data: LocalLogin, request: Request):
    failures = login_guard(request)
    account = store.local_get(username=data.username.strip().lower())
    now = time.time()
    locked = bool(account and account['locked_until'] > now)
    valid = check_password(data.password, account['password'] if account and not locked else None)
    if locked or not valid or account['disabled']:
        failures.append(now)
        if account and not locked:
            store.local_failed(account['id'])
        if locked:
            raise Rejected('Prea multe incercari. Incearca din nou in 15 minute.', 429)
        raise Rejected('Utilizator sau parola gresita.', 401)
    if len(login_challenges) > 200:
        raise Rejected('Prea multe autentificari in asteptare.', 429)
    token = secrets.token_urlsafe(32)
    enroll = None if account['totp'] else new_secret()
    login_challenges[hashlib.sha256(token.encode()).hexdigest()] = {'id': account['id'], 'expires': now + 300, 'enroll': enroll, 'tries': 0}
    body = {'next': 'code', 'must_change': bool(account['must_change']), 'name': account['name']}
    if enroll:
        body['enroll'] = {'secret': enroll, 'uri': otpauth(enroll, account['username'])}
    response = JSONResponse(body)
    response.set_cookie(CHALLENGE_COOKIE, token, httponly=True, secure=SECURE, samesite='strict', path=BASE + '/auth', max_age=300)
    return response


@app.post(BASE + '/auth/local/verify')
async def local_verify(data: LocalVerify, request: Request):
    failures = login_guard(request)
    key = hashlib.sha256(request.cookies.get(CHALLENGE_COOKIE, '').encode()).hexdigest()
    challenge = login_challenges.get(key)
    account = challenge and challenge['expires'] > time.time() and store.local_get(challenge['id'])
    if not account or account['disabled']:
        login_challenges.pop(key, None)
        raise Rejected('Autentificarea a expirat. Reia conectarea.', 400)
    if account['must_change']:
        problem = password_problem(data.new_password, account['username'])
        if problem:
            raise Rejected(problem, 422)
        if check_password(data.new_password, account['password']):
            raise Rejected('Alege o parola noua, diferita de cea temporara.', 422)
    secret = challenge['enroll'] or account['totp']
    step = totp_step(secret, data.code, 0 if challenge['enroll'] else account['totp_step'])
    if step is None:
        failures.append(time.time())
        store.local_failed(account['id'])
        challenge['tries'] += 1
        if challenge['tries'] >= 5:
            login_challenges.pop(key, None)
        raise Rejected('Cod incorect sau expirat.', 401)
    login_challenges.pop(key, None)
    changes = {'totp_step': step, 'failures': 0, 'locked_until': 0, 'last_login': time.time()}
    if challenge['enroll']:
        changes['totp'] = challenge['enroll']
    if account['must_change']:
        changes.update(password=hash_password(data.new_password), must_change=0)
    store.local_update(account['id'], **changes)
    handle, sid = store.create({'local': account['id']})
    store.bind(sid, account['id'])
    store.log(account['id'], 'local_login', 'sesiune', 'Parola si cod verificate')
    response = JSONResponse({'ok': True})
    session_cookie(response, handle)
    response.delete_cookie(CHALLENGE_COOKIE, path=BASE + '/auth', secure=SECURE, samesite='strict')
    return response


@app.post(BASE + '/api/me/password')
async def change_password(data: PasswordChange, request: Request):
    sid, session = store.identify(request.cookies.get(COOKIE, ''))
    if not session:
        raise Rejected('Autentificare necesara.', 401)
    if request.headers.get('origin') != ORIGIN or not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
        raise Rejected('Cerere neautorizata.', 403)
    account = session.get('local') and store.local_get(session['local'])
    if not account or account['disabled']:
        raise Rejected('Parola se schimba doar pentru conturile Casa.', 403)
    failures = login_guard(request)
    if not check_password(data.current, account['password']):
        failures.append(time.time())
        raise Rejected('Parola actuala este gresita.', 403)
    problem = password_problem(data.new, account['username'])
    if problem:
        raise Rejected(problem, 422)
    store.local_update(account['id'], password=hash_password(data.new))
    closed = store.expire_user(account['id'], keep=sid)
    store.log(account['id'], 'password_change', 'cont Casa', f'Parola schimbata, {len(closed)} alte sesiuni inchise')
    return {'saved': True, 'closed': len(closed)}


def service_status():
    user_id = store.owner(SERVICE)
    row = store.db.execute('SELECT name,is_admin FROM users WHERE id=?', (user_id,)).fetchone() if user_id else None
    peer = peers.get(SERVICE)
    return {'connected': bool(store.get(SERVICE)), 'online': bool(peer and peer.connected),
            'name': row[0] if row else None, 'admin': bool(row and row[1])}


@app.post(BASE + '/api/service/login')
async def service_login(request: Request):
    _, _, profile = await access(request, 'configure', True)
    require_admin(profile)
    if len(oauth_states) > 200:
        raise Rejected('Prea multe autentificari in asteptare.', 429)
    return oauth_start(JSONResponse, profile['id'])


@app.post(BASE + '/api/service/disconnect')
async def service_disconnect(request: Request):
    _, _, profile = await access(request, 'configure', True)
    require_admin(profile)
    store.expire(SERVICE)  # the cleanup task revokes the HA refresh token
    peer = peers.pop(SERVICE, None)
    if peer:
        await peer.close()
    store.log(profile['id'], 'service_disconnect', 'cont tehnic HA', 'Deconectat')
    return {'saved': True}


async def local_admin(request, mutation=True):
    _, _, profile = await access(request, 'configure', mutation)
    require_admin(profile)
    return profile


def local_target(user_id):
    account = store.local_get(user_id)
    if not account:
        raise Rejected('Contul nu exista.', 404)
    return account


@app.get(BASE + '/api/local-users')
async def local_users(request: Request):
    await local_admin(request, False)
    return {'service': service_status(), 'users': store.local_list()}


@app.post(BASE + '/api/local-users')
async def local_user_create(data: LocalUserNew, request: Request):
    profile = await local_admin(request)
    username, name = data.username.strip().lower(), ' '.join(data.name.split())
    if not USERNAME.fullmatch(username):
        raise Rejected('Utilizator: 3-32 caractere, litere mici, cifre, punct, minus sau underscore.', 422)
    if not name:
        raise Rejected('Numele este obligatoriu.', 422)
    if store.local_get(username=username):
        raise Rejected('Exista deja un cont cu acest utilizator.', 409)
    password = temporary_password()
    user_id = store.local_create(username, name, data.role, hash_password(password), profile['id'])
    store.log(profile['id'], 'local_user_create', user_id, data.role)
    return {'id': user_id, 'username': username, 'password': password}


@app.post(BASE + '/api/local-users/{user_id}')
async def local_user_edit(user_id: str, data: LocalUserEdit, request: Request):
    profile = await local_admin(request)
    local_target(user_id)
    changes = {k: v for k, v in {'name': ' '.join(data.name.split()) if data.name is not None else None,
                                  'role': data.role, 'disabled': int(data.disabled) if data.disabled is not None else None}.items() if v is not None}
    if not changes or changes.get('name') == '':
        raise Rejected('Nicio modificare valida.', 422)
    store.local_update(user_id, **changes)
    if changes.get('disabled'):
        store.expire_user(user_id)
    if SERVICE in peers:
        publish(peers[SERVICE])  # open pages of this account receive the new role at once
    store.log(profile['id'], 'local_user_edit', user_id, ', '.join(f'{k}={v}' for k, v in changes.items()))
    return {'saved': True}


@app.post(BASE + '/api/local-users/{user_id}/reset')
async def local_user_reset(user_id: str, request: Request):
    profile = await local_admin(request)
    local_target(user_id)
    password = temporary_password()
    store.local_update(user_id, password=hash_password(password), totp=None, totp_step=0, must_change=1, failures=0, locked_until=0)
    closed = store.expire_user(user_id)
    store.log(profile['id'], 'local_user_reset', user_id, f'Parola si cod resetate, {len(closed)} sesiuni inchise')
    return {'password': password}


@app.post(BASE + '/api/local-users/{user_id}/delete')
async def local_user_delete(user_id: str, request: Request):
    profile = await local_admin(request)
    local_target(user_id)
    closed = store.expire_user(user_id)
    store.local_delete(user_id)
    store.log(profile['id'], 'local_user_delete', user_id, f'{len(closed)} sesiuni inchise')
    return {'deleted': True}


@app.get(BASE + '/api/health')
async def health():
    return {'ok': True, 'version': '0.1.0'}


if (ROOT / 'dist/assets').exists():
    app.mount(BASE + '/assets', StaticFiles(directory=ROOT / 'dist/assets'), name='assets')


@app.get(BASE + '/')
@app.get(BASE + '/{path:path}')
async def index(path: str = ''):
    if path.startswith(('api/', 'auth/', 'assets/')):
        raise Rejected('Resursa inexistenta.', 404)
    return FileResponse(ROOT / 'dist/index.html')
