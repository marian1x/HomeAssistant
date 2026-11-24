import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { format } from './model';

/* Motion primitives of the Nova layer. Everything here is progressive enhancement:
   without View Transitions, with reduced motion or in a hidden tab the update is applied
   at once and the interface works exactly the same. */

const calm = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return true; } };

/** A live number that glides from the previous real reading to the new one. */
export function Num({ value, digits = 2 }: { value: number | null | undefined; digits?: number }) {
  const goal = value ?? null;
  const [shown, setShown] = useState(goal);
  const from = useRef(goal);
  useEffect(() => {
    const start = from.current;
    if (start === null || goal === null || start === goal || calm() || document.hidden) { from.current = goal; setShown(goal); return; }
    let frame = 0;
    const began = performance.now();
    const step = (time: number) => {
      const k = Math.min(1, (time - began) / 650), current = start + (goal - start) * (1 - Math.pow(1 - k, 3));
      from.current = k === 1 ? goal : current;
      setShown(from.current);
      if (k < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [goal]);
  return <span className="num">{format(shown, digits)}</span>;
}

type Transition = { ready: Promise<void>; finished: Promise<void> };
type TransitionDocument = Document & { startViewTransition?: (update: () => void) => Transition };

/** Applies a state change inside a View Transition (page change, theme change). */
export function morph(update: () => void, kind = 'page'): Transition | null {
  const doc = document as TransitionDocument;
  if (!doc.startViewTransition || calm() || document.hidden) { update(); return null; }
  const root = document.documentElement;
  root.dataset.vt = kind;
  const transition = doc.startViewTransition(() => flushSync(update));
  const done = () => { if (root.dataset.vt === kind) delete root.dataset.vt; };
  transition.finished.then(done, done);
  transition.ready.catch(() => {});
  return transition;
}

/** Theme change that opens as a circle from the control that was pressed. */
export function reveal(origin: { clientX: number; clientY: number } | null, update: () => void) {
  const transition = morph(update, 'theme');
  if (!transition) return;
  const x = origin?.clientX || innerWidth / 2, y = origin?.clientY || 0;
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  transition.ready.then(() => document.documentElement.animate(
    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
    { duration: 640, easing: 'cubic-bezier(.22,.8,.2,1)', pseudoElement: '::view-transition-new(root)' },
  )).catch(() => {});
}

const LIT = '.home-device, .flow-load, .flow-node, .device-card, .metric, .live-power-strip > button, .rule-row, .brief-card, .palette-item';

/** Cards catch a soft light under a fine pointer (desktop only). */
export function useSpotlight() {
  useEffect(() => {
    let fine = false;
    try { fine = matchMedia('(hover: hover) and (pointer: fine)').matches; } catch { /* no spotlight */ }
    if (!fine || calm()) return;
    let frame = 0, last: PointerEvent | null = null;
    const apply = () => {
      frame = 0;
      const card = (last?.target as Element | null)?.closest?.<HTMLElement>(LIT);
      if (!card || !last) return;
      const box = card.getBoundingClientRect();
      card.style.setProperty('--mx', last.clientX - box.left + 'px');
      card.style.setProperty('--my', last.clientY - box.top + 'px');
    };
    const move = (event: PointerEvent) => { last = event; if (!frame) frame = requestAnimationFrame(apply); };
    window.addEventListener('pointermove', move, { passive: true });
    return () => { window.removeEventListener('pointermove', move); cancelAnimationFrame(frame); };
  }, []);
}
