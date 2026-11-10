import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { Check, Copy, KeyRound, LoaderCircle, LogIn, X } from 'lucide-react';
import Qr from './Qr';

const BASE = import.meta.env.BASE_URL;

type Challenge = { must_change: boolean; name: string; enroll?: { secret: string; uri: string } };

async function send(path: string, body: unknown) {
  const response = await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(result.error || 'Conectarea a fost refuzata.');
  return result;
}

const trap = (event: KeyboardEvent<HTMLDivElement>) => {
  if (event.key !== 'Tab') return;
  const items = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input,a[href]')];
  if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus(); }
  else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); }
};

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="button copy-button" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 2000); } catch { setDone(false); }
    }}>{done ? <Check size={15} /> : <Copy size={15} />}{done ? 'Copiat' : label}</button>
  );
}

export default function LocalLogin({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [code, setCode] = useState(''), [fresh, setFresh] = useState(''), [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (challenge?.must_change && (fresh.length < 12 || fresh !== repeat)) {
      setError(fresh.length < 12 ? 'Parola noua trebuie sa aiba cel putin 12 caractere.' : 'Cele doua parole noi nu coincid.');
      return;
    }
    setBusy(true);
    try {
      if (!challenge) {
        setChallenge(await send('auth/local', { username, password }));
        setPassword('');
      } else {
        await send('auth/local/verify', { code, ...(challenge.must_change ? { new_password: fresh } : {}) });
        location.reload();
        return;
      }
    } catch (e: any) {
      setError(e.message);
      if (/expirat/i.test(e.message)) { setChallenge(null); setCode(''); }
    } finally {
      setBusy(false);
    }
  };
  const key = challenge?.enroll?.secret.replace(/(.{4})/g, '$1 ').trim();
  return (
    <div className="modal-shade" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="local-login-title" className="modal local-login" onKeyDown={trap}>
        <header>
          <h2 id="local-login-title">{challenge ? (challenge.enroll ? 'Configureaza codul de conectare' : 'Cod de conectare') : 'Conectare cu cont Casa'}</h2>
          <button className="icon-button" title="Inchide" aria-label="Inchide" disabled={busy} onClick={onClose}><X size={20} /></button>
        </header>
        <form onSubmit={submit}>
          <div className="modal-body">
            {!challenge ? <>
              <p className="dialog-context">Cont creat de administrator in aplicatia Casa, fara cont Home Assistant.</p>
              <label className="field">Utilizator<input name="username" autoFocus autoComplete="username" autoCapitalize="none" spellCheck={false} required maxLength={32} value={username} onChange={(e) => setUsername(e.target.value)} /></label>
              <label className="field">Parola<input name="password" type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            </> : <>
              {challenge.enroll && <div className="enroll">
                <p>Instaleaza o aplicatie de autentificare (Google Authenticator, Microsoft Authenticator), apoi adauga contul: scaneaza codul QR sau introdu cheia manual.</p>
                <div className="enroll-grid">
                  <Qr text={challenge.enroll.uri} label="Cod QR pentru aplicatia de autentificare" />
                  <div>
                    <span className="eyebrow">CHEIE MANUALA</span>
                    <code className="secret-value">{key}</code>
                    <div className="enroll-actions">
                      <CopyButton text={challenge.enroll.secret} label="Copiaza cheia" />
                      <a className="text-button" href={challenge.enroll.uri}>Deschide in aplicatie</a>
                    </div>
                    <p className="field-hint">Tip: bazat pe timp, 6 cifre, 30 secunde. Cheia se afiseaza doar acum.</p>
                  </div>
                </div>
              </div>}
              {challenge.must_change && <>
                <p className="dialog-context">Bun venit, {challenge.name}. Alege o parola noua in locul celei temporare.</p>
                <label className="field">Parola noua<input type="password" autoFocus autoComplete="new-password" required minLength={12} maxLength={128} value={fresh} onChange={(e) => setFresh(e.target.value)} /></label>
                <label className="field">Repeta parola noua<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={repeat} onChange={(e) => setRepeat(e.target.value)} /></label>
                <p className="field-hint">Minimum 12 caractere, fara numele de utilizator.</p>
              </>}
              <label className="field">Cod din aplicatie<input name="code" autoFocus={!challenge.must_change} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required maxLength={7} value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" /></label>
            </>}
            {error && <p className="form-error" role="alert">{error}</p>}
          </div>
          <footer>
            <button type="button" className="button" disabled={busy} onClick={onClose}>Anuleaza</button>
            <button type="submit" className="button primary" disabled={busy}>
              {busy ? <LoaderCircle size={16} className="spin" /> : challenge ? <KeyRound size={16} /> : <LogIn size={16} />}
              {challenge ? 'Conectare' : 'Continua'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
