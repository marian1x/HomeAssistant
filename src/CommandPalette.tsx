import { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search } from 'lucide-react';

/* Command palette (Ctrl/Cmd+K): pages, devices and actions from one field. Device
   actions behave like the switches on the page: lights act directly (owner decision
   2026-11-10), everything else opens the confirmation dialog. */

export type PaletteItem = { id: string; group: string; title: string; hint?: string; icon: any; keywords?: string; run: () => void; always?: boolean };

const plain = (text: string) => text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

function score(item: PaletteItem, query: string) {
  const title = plain(item.title), rest = plain((item.hint || '') + ' ' + (item.keywords || ''));
  if (title.startsWith(query)) return 100;
  if (title.split(/[\s/·-]+/).some((word) => word.startsWith(query))) return 80;
  if (title.includes(query)) return 60;
  if (rest.includes(query)) return 40;
  let at = 0;
  for (const letter of query) { at = title.indexOf(letter, at) + 1; if (!at) return 0; }
  return 20;
}

export default function CommandPalette({ items, onClose }: { items: PaletteItem[]; onClose: () => void }) {
  const [query, setQuery] = useState(''), [active, setActive] = useState(0);
  const list = useRef<HTMLUListElement>(null);
  const shown = useMemo(() => {
    const q = plain(query.trim());
    if (!q) return items.filter((item) => item.always);
    return items.map((item) => ({ item, rank: score(item, q) })).filter((row) => row.rank > 0)
      .sort((a, b) => b.rank - a.rank).slice(0, 14).map((row) => row.item);
  }, [items, query]);
  const grouped = useMemo(() => {
    const order: string[] = [];
    for (const item of shown) if (!order.includes(item.group)) order.push(item.group);
    return order.flatMap((group) => shown.filter((item) => item.group === group));
  }, [shown]);
  useEffect(() => { setActive(0); }, [query]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    // The Android shell closes dialogs by dispatching Escape on window.
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } };
    window.addEventListener('keydown', escape, true);
    return () => { window.removeEventListener('keydown', escape, true); previous?.focus?.(); };
  }, []);
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }); }, [active, grouped]);
  const choose = (item?: PaletteItem) => { if (!item) return; onClose(); item.run(); };
  const keys = (event: React.KeyboardEvent) => {
    const last = grouped.length - 1;
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive((n) => (n >= last ? 0 : n + 1)); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive((n) => (n <= 0 ? last : n - 1)); }
    else if (event.key === 'Home') { event.preventDefault(); setActive(0); }
    else if (event.key === 'End') { event.preventDefault(); setActive(last); }
    else if (event.key === 'Enter') { event.preventDefault(); choose(grouped[active]); }
    else if (event.key === 'Tab') event.preventDefault();
  };
  return (
    <div className="palette-layer" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Comenzi rapide">
        <div className="palette-field">
          <Search size={18} />
          <input autoFocus type="text" role="combobox" aria-label="Cauta pagini, dispozitive si actiuni" aria-expanded="true" aria-controls="palette-list"
            aria-activedescendant={grouped[active] ? 'palette-' + grouped[active].id : undefined} autoComplete="off" spellCheck={false}
            placeholder="Cauta o pagina, un dispozitiv sau o actiune" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={keys} />
          <button className="palette-close" onClick={onClose} aria-label="Inchide comenzile rapide"><kbd>Esc</kbd></button>
        </div>
        <ul id="palette-list" role="listbox" aria-label="Rezultate" ref={list}>
          {grouped.map((item, index) => (
            <li key={item.id} role="presentation">
              {(index === 0 || grouped[index - 1].group !== item.group) && <span className="palette-group">{item.group}</span>}
              <div id={'palette-' + item.id} role="option" aria-selected={index === active} className="palette-item"
                onMouseMove={() => setActive(index)} onClick={() => choose(item)}>
                <span className="palette-icon"><item.icon size={17} /></span>
                <span className="palette-title">{item.title}</span>
                {item.hint && <small>{item.hint}</small>}
                <CornerDownLeft size={14} className="palette-enter" />
              </div>
            </li>
          ))}
          {!grouped.length && <li className="palette-empty" role="presentation">Niciun rezultat pentru „{query.trim()}”.</li>}
        </ul>
        <footer className="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> navigheaza</span><span><kbd>Enter</kbd> alege</span><span>Luminile se comuta direct; restul cer confirmare</span></footer>
      </div>
    </div>
  );
}
