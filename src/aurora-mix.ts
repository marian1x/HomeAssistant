/* What the aurora background shows: shares of the live power flows. */
export type AuroraMix = { solar: number; grid: number; battery: number; load: number; energy: number };
export const CALM: AuroraMix = { solar: 0.16, grid: 0.3, battery: 0.14, load: 0.55, energy: 0.12 };

/** Shares of the live power flows, plus overall activity (0..1, 8 kW = full). */
export function auroraMix(flow: { live: boolean; pv: number | null; house: number | null; gridImport: number | null; gridExport: number | null; charge: number | null; discharge: number | null }): AuroraMix {
  if (!flow.live) return CALM;
  const solar = flow.pv ?? 0, grid = (flow.gridImport ?? 0) + (flow.gridExport ?? 0), battery = (flow.charge ?? 0) + (flow.discharge ?? 0), load = flow.house ?? 0;
  const top = Math.max(solar, grid, battery, load, 0.4);
  const share = (kw: number) => 0.06 + 0.94 * Math.min(1, kw / top);
  return { solar: share(solar), grid: share(grid), battery: share(battery), load: share(load), energy: Math.min(1, (solar + grid + battery + load) / 8) };
}
