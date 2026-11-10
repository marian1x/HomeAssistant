import { useEffect, useState, type FormEvent } from 'react';
import { KeyRound, Link2, LoaderCircle, RotateCcw, Trash2, Unlink, UserPlus, UserRound } from 'lucide-react';
import { CopyButton } from './LocalLogin';

const BASE = import.meta.env.BASE_URL;
export const LOCAL_ROLES: Record<string, string> = { viewer: 'Vizualizare', control: 'Control dispozitive', configure: 'Parametri si control' };

type Post = (path: string, body: any) => Promise<any>;
type Account = { id: string; username: string; name: string; role: string; enrolled: boolean; must_change: boolean; disabled: boolean; locked: boolean; last_login: number | null };
type Service = { connected: boolean; online: boolean; name: string | null; admin: boolean };

const when = (time: number | null) => time ? new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(time * 1000)) : 'niciodata';

export function LocalUsers({ post, notify, enabled }: { post: Post; notify: (text: string) => void; enabled: boolean }) {
  const [state, setState] = useState<{ service: Service; users: Account[] } | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState('');
  const [form, setForm] = useState({ username: '', name: '', role: 'viewer' });
  const [secret, setSecret] = useState<{ username: string; password: string } | null>(null);
  const [confirm, setConfirm] = useState('');
  const load = () => fetch(BASE + 'api/local-users').then(async (r) => {
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(body.error || 'Lista conturilor nu este disponibila.');
    setState(body); setError('');
  }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!confirm) return; const timer = setTimeout(() => setConfirm(''), 6000); return () => clearTimeout(timer); }, [confirm]);
  const run = async (key: string, action: () => Promise<any>, message?: string) => {
    setBusy(key);
    try { await action(); if (message) notify(message); await load(); }
    catch (e: any) { notify(e.message); }
    finally { setBusy(''); setConfirm(''); }
  };
  const ask = (key: string, action: () => Promise<any>, message: string) => confirm === key ? run(key, action, message) : setConfirm(key);
  const create = (event: FormEvent) => {
    event.preventDefault();
    run('create', async () => {
      const result = await post('local-users', form);
      setSecret({ username: result.username, password: result.password });
      setForm({ username: '', name: '', role: form.role });
    }, 'Cont creat. Transmite parola temporara utilizatorului.');
  };
  const service = state?.service;
  return (
    <section className="local-accounts" aria-labelledby="local-accounts-title">
      <h2 className="users-title" id="local-accounts-title">Conturi Casa</h2>
      <p className="field-hint">Conturi doar pentru aplicatia Casa, fara acces in Home Assistant. Conectare cu parola si cod din aplicatia de autentificare. Rolurile sunt verificate pe server.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      {state && <>
        <div className="setting-row service-row">
          <span>Cont tehnic HA<small>{service?.connected ? `${service.name || 'Cont conectat'} · ${service.admin ? 'administrator HA' : 'fara drepturi de administrator'}${service.online ? '' : ' · se conecteaza la prima folosire'}` : 'Neconectat: conturile Casa nu pot citi sau comanda casa'}</small></span>
          <div className="row-actions">
            <button className="button" disabled={!enabled || !!busy} onClick={() => run('service', async () => { location.href = (await post('service/login', {})).url; })}>
              {busy === 'service' ? <LoaderCircle size={15} className="spin" /> : <Link2 size={15} />}{service?.connected ? 'Schimba' : 'Conecteaza'}
            </button>
            {service?.connected && <button className="button" disabled={!enabled || !!busy} onClick={() => ask('service-off', () => post('service/disconnect', {}), 'Contul tehnic a fost deconectat.')}>
              <Unlink size={15} />{confirm === 'service-off' ? 'Confirma deconectarea' : 'Deconecteaza'}</button>}
          </div>
        </div>
        {!service?.connected && <p className="field-hint">Creeaza intai in Home Assistant un utilizator dedicat (de exemplu „Casa servicii”), administrator, cu parola puternica. Apasa Conecteaza si, in pagina HA, autentifica-te cu acel cont, nu cu al tau.</p>}
        {service?.connected && !service.admin && <p className="form-error">Contul tehnic nu este administrator HA: rolul Parametri nu poate salva Politica Energie.</p>}
        {secret && <div className="secret-panel" role="status">
          <span>Parola temporara pentru <strong>{secret.username}</strong>, afisata o singura data:</span>
          <code className="secret-value">{secret.password}</code>
          <div className="row-actions"><CopyButton text={secret.password} label="Copiaza parola" /><button className="button" onClick={() => setSecret(null)}>Am notat-o</button></div>
          <small>La prima conectare utilizatorul alege o parola noua si configureaza codul din aplicatia de autentificare.</small>
        </div>}
        {state.users.length === 0 && <p className="field-hint">Nu exista inca niciun cont Casa.</p>}
        {state.users.map((user) => (
          <div className="setting-row local-user" key={user.id}>
            <span><UserRound size={15} /> {user.name}<small>{user.username} · ultima conectare {when(user.last_login)}</small>
              <span className="user-flags">
                {user.disabled && <i className="warn">Dezactivat</i>}
                {user.locked && <i className="warn">Blocat temporar</i>}
                {!user.enrolled && <i>Asteapta prima conectare</i>}
              </span>
            </span>
            <div className="row-actions">
              <select aria-label={'Rol ' + user.name} value={user.role} disabled={!enabled || !!busy} onChange={(e) => run(user.id, () => post('local-users/' + user.id, { role: e.target.value }), 'Rol actualizat.')}>
                {Object.entries(LOCAL_ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button className="button" disabled={!enabled || !!busy} onClick={() => ask('reset-' + user.id, async () => {
                const result = await post('local-users/' + user.id + '/reset', {});
                setSecret({ username: user.username, password: result.password });
              }, 'Parola si codul au fost resetate.')}><RotateCcw size={15} />{confirm === 'reset-' + user.id ? 'Confirma resetarea' : 'Reseteaza'}</button>
              <button className="button" disabled={!enabled || !!busy} onClick={() => user.disabled ? run(user.id, () => post('local-users/' + user.id, { disabled: false }), 'Cont activat.') : ask('off-' + user.id, () => post('local-users/' + user.id, { disabled: true }), 'Cont dezactivat; sesiunile lui s-au inchis.')}>
                {user.disabled ? 'Activeaza' : confirm === 'off-' + user.id ? 'Confirma' : 'Dezactiveaza'}</button>
              <button className="button danger" aria-label={'Sterge ' + user.name} disabled={!enabled || !!busy} onClick={() => ask('del-' + user.id, () => post('local-users/' + user.id + '/delete', {}), 'Cont sters.')}>
                <Trash2 size={15} />{confirm === 'del-' + user.id ? 'Confirma stergerea' : ''}</button>
            </div>
          </div>
        ))}
        <form className="local-user-form" onSubmit={create}>
          <label className="field">Utilizator<input required pattern="[a-z0-9][a-z0-9._\-]{2,31}" maxLength={32} autoCapitalize="none" spellCheck={false} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })} placeholder="ana" /></label>
          <label className="field">Nume afisat<input required maxLength={60} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ana" /></label>
          <label className="field">Rol<select aria-label="Rol cont nou" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{Object.entries(LOCAL_ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <button className="button primary" type="submit" disabled={!enabled || !!busy}>{busy === 'create' ? <LoaderCircle size={15} className="spin" /> : <UserPlus size={15} />}Adauga cont</button>
        </form>
        <p className="field-hint">Vizualizare: stari, grafice si costuri. Control: si comenzi pentru dispozitive. Parametri: si setarile bateriei, programele si Politica Energie. Conturile, regulile si jurnalul raman la administratorul HA.</p>
      </>}
    </section>
  );
}

export function PasswordChange({ post, notify }: { post: Post; notify: (text: string) => void }) {
  const [current, setCurrent] = useState(''), [fresh, setFresh] = useState(''), [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (fresh !== repeat) { setError('Cele doua parole noi nu coincid.'); return; }
    setBusy(true); setError('');
    try {
      const result = await post('me/password', { current, new: fresh });
      setCurrent(''); setFresh(''); setRepeat('');
      notify(result.closed ? `Parola a fost schimbata. Alte ${result.closed} sesiuni au fost inchise.` : 'Parola a fost schimbata.');
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };
  return (
    <form className="password-change" onSubmit={submit}>
      <h2 className="users-title">Schimba parola</h2>
      <label className="field">Parola actuala<input type="password" autoComplete="current-password" required maxLength={128} value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
      <label className="field">Parola noua<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={fresh} onChange={(e) => setFresh(e.target.value)} /></label>
      <label className="field">Repeta parola noua<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={repeat} onChange={(e) => setRepeat(e.target.value)} /></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="button" type="submit" disabled={busy}>{busy ? <LoaderCircle size={15} className="spin" /> : <KeyRound size={15} />}Schimba parola</button>
    </form>
  );
}
