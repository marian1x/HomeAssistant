import { format } from './model.ts';

/* "Casa acum": one sentence and a few facts derived only from live readings. Nothing is
   forecast or invented; without a recent inverter reading it says so. */

export type Flow = { live: boolean; pv: number | null; house: number | null; gridImport: number | null; gridExport: number | null;
  charge: number | null; discharge: number | null; solarHouse: number | null; soc: number | null;
  solarToday: number | null; loadToday: number | null; importToday: number | null };
export type Brief = { tone: 'solar' | 'battery' | 'grid' | 'calm' | 'idle'; headline: string; autarky: number | null };

const ON = 0.05; // kW below this is measurement noise, not a flow
const kw = (n: number) => format(n, 2) + ' kW';

/** Share of today's consumption that was not bought from the grid (0..100). */
export function autarky(flow: Pick<Flow, 'loadToday' | 'importToday'>): number | null {
  if (flow.loadToday === null || flow.importToday === null || flow.loadToday < 0.1) return null;
  return Math.round(Math.max(0, Math.min(1, 1 - flow.importToday / flow.loadToday)) * 100);
}

export function brief(flow: Flow): Brief {
  const today = autarky(flow);
  if (!flow.live || flow.house === null) return { tone: 'idle', headline: 'Astept o citire recenta de la invertor.', autarky: today };
  const pv = flow.pv ?? 0, house = flow.house, grid = flow.gridImport ?? 0, out = flow.gridExport ?? 0, charge = flow.charge ?? 0, discharge = flow.discharge ?? 0;
  const soc = flow.soc === null ? '' : ', la ' + format(flow.soc, 0) + '%';
  if (pv > ON) {
    if (out > ON) return { tone: 'solar', autarky: today, headline: `Soarele alimenteaza casa${charge > ON ? ', incarca bateria' : ''} si injecteaza ${kw(out)} in retea.` };
    if (charge > ON && grid <= ON) return { tone: 'solar', autarky: today, headline: `Soarele alimenteaza casa si incarca bateria cu ${kw(charge)}.` };
    const share = flow.solarHouse === null || house <= 0 ? null : Math.round(Math.min(1, flow.solarHouse / house) * 100);
    if (share !== null && share >= 98 && grid <= ON && discharge <= ON) return { tone: 'solar', autarky: today, headline: 'Casa merge integral pe energie solara.' };
    const rest = discharge > ON && discharge >= grid ? `; bateria completeaza cu ${kw(discharge)}` : grid > ON ? `; reteaua completeaza cu ${kw(grid)}` : '';
    return { tone: 'solar', autarky: today, headline: (share === null ? `Panourile produc ${kw(pv)}` : `Soarele acopera ${share}% din consum`) + rest + '.' };
  }
  if (discharge > ON && discharge >= grid) return { tone: 'battery', autarky: today, headline: `Casa merge pe baterie: ${kw(discharge)}${soc}.` };
  if (grid > ON) return { tone: 'grid', autarky: today, headline: `Casa consuma ${kw(grid)} din retea${charge > ON ? `; bateria se incarca cu ${kw(charge)}` : ''}.` };
  return { tone: 'calm', autarky: today, headline: `Consum redus: ${kw(house)}.` };
}
