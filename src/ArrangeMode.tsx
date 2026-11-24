import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, Check, GripVertical, History, ListOrdered, Undo2 } from 'lucide-react';
import { type Sort } from './arrange';

/* Arrange mode: drag a card by its handle (mouse, pen or touch) or use the arrow
   buttons / arrow keys. While arranging, the device controls are inert, so a drag can
   never switch a light (lights act on the first press since 2026-11-10). */

type Drag = { scope: string; id: string; ids: string[]; to: number };
export type Sorter = ReturnType<typeof useSortable>;

export function useSortable(drop: (ids: string[], id: string, to: number) => void) {
  const [drag, setDrag] = useState<Drag | null>(null);
  const live = useRef<Drag | null>(null);
  live.current = drag;
  const commit = useRef(drop);
  commit.current = drop;
  const preview = (scope: string, ids: string[]) => {
    if (!drag || drag.scope !== scope) return ids;
    const rest = ids.filter((x) => x !== drag.id);
    rest.splice(drag.to, 0, drag.id);
    return rest;
  };
  useEffect(() => {
    if (!drag) return;
    const moveTo = (event: PointerEvent) => {
      const now = live.current;
      if (!now) return;
      if (event.clientY < 90) scrollBy(0, -14);
      else if (event.clientY > innerHeight - 110) scrollBy(0, 14);
      // Inert cards are skipped by hit testing, so pick the card whose box is nearest.
      let key = '', best = Infinity;
      for (const card of document.querySelectorAll<HTMLElement>(`[data-sort-scope="${CSS.escape(now.scope)}"]`)) {
        const box = card.getBoundingClientRect();
        const dx = Math.max(box.left - event.clientX, 0, event.clientX - box.right), dy = Math.max(box.top - event.clientY, 0, event.clientY - box.bottom);
        if (dx * dx + dy * dy < best) { best = dx * dx + dy * dy; key = card.dataset.sortKey || ''; }
      }
      if (!key || best > 3600) return;
      // Positions as currently drawn (computed from the live drag, not a stale render).
      const order = now.ids.filter((x) => x !== now.id);
      order.splice(now.to, 0, now.id);
      const at = order.indexOf(key);
      if (at >= 0 && at !== now.to) { live.current = { ...now, to: at }; setDrag(live.current); }
    };
    const finish = () => {
      const now = live.current;
      setDrag(null);
      if (now && now.to !== now.ids.indexOf(now.id)) commit.current(now.ids, now.id, now.to);
    };
    const cancel = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.stopPropagation(); setDrag(null); } };
    window.addEventListener('pointermove', moveTo);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
    window.addEventListener('keydown', cancel, true);
    return () => {
      window.removeEventListener('pointermove', moveTo);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      window.removeEventListener('keydown', cancel, true);
    };
  }, [!!drag]);
  const start = (scope: string, ids: string[], id: string) => (event: React.PointerEvent) => {
    if (event.button !== 0) return;
    event.preventDefault();
    setDrag({ scope, id, ids, to: ids.indexOf(id) });
  };
  return { drag, preview, start, step: (ids: string[], id: string, by: number) => {
    const at = ids.indexOf(id) + by;
    if (at >= 0 && at < ids.length) commit.current(ids, id, at);
  } };
}

/** Card wrapper used only while arranging. */
export function Sortable({ sorter, scope, ids, id, name, uses, children }: { sorter: Sorter; scope: string; ids: string[]; id: string; name: string; uses: number | null; children: ReactNode }) {
  const index = ids.indexOf(id), dragging = sorter.drag?.id === id;
  const key = (event: React.KeyboardEvent) => {
    const by = ['ArrowUp', 'ArrowLeft'].includes(event.key) ? -1 : ['ArrowDown', 'ArrowRight'].includes(event.key) ? 1 : 0;
    if (!by) return;
    event.preventDefault();
    sorter.step(ids, id, by);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-sort-scope="${scope}"][data-sort-key="${CSS.escape(id)}"] .arrange-handle`)?.focus());
  };
  return (
    <div className={'sortable' + (dragging ? ' dragging' : '')} data-sort-scope={scope} data-sort-key={id}>
      <div className="sortable-card" inert>{children}</div>
      <div className="arrange-overlay">
        <button type="button" className="arrange-handle" aria-label={`Muta ${name}, pozitia ${index + 1} din ${ids.length}`} title="Trage sau foloseste sagetile"
          onPointerDown={sorter.start(scope, ids, id)} onKeyDown={key}><GripVertical size={18} /></button>
        <span className="arrange-place">{index + 1}</span>
        {uses !== null && <span className="arrange-uses" title="Comenzi trimise de tine in ultimele 30 de zile">{uses}×</span>}
        <span className="arrange-steps">
          <button type="button" aria-label={`Muta ${name} mai sus`} disabled={index === 0} onClick={() => sorter.step(ids, id, -1)}><ArrowUp size={16} /></button>
          <button type="button" aria-label={`Muta ${name} mai jos`} disabled={index === ids.length - 1} onClick={() => sorter.step(ids, id, 1)}><ArrowDown size={16} /></button>
        </span>
      </div>
    </div>
  );
}

export function ArrangeBar({ sort, days, onSort, onDone }: { sort: Sort; days: number; onSort: (sort: Sort) => void; onDone: () => void }) {
  return (
    <div className="arrange-bar" role="region" aria-label="Aranjare dispozitive">
      <span className="arrange-hint">Trage de maner sau foloseste sagetile. Ordinea se salveaza pentru contul tau, pe toate dispozitivele.</span>
      <div className="arrange-sorts" role="radiogroup" aria-label="Ordine">
        {([['manual', 'Ordinea mea', ListOrdered], ['usage', 'Cele mai folosite', History], ['default', 'Implicit', Undo2]] as const).map(([value, label, Icon]) => (
          <button key={value} type="button" role="radio" aria-checked={sort === value} title={value === 'usage' ? `Dupa comenzile tale din ultimele ${days} de zile` : undefined} onClick={() => onSort(value)}><Icon size={15} />{label}</button>
        ))}
      </div>
      <button type="button" className="button primary" onClick={onDone}><Check size={16} />Gata</button>
    </div>
  );
}
