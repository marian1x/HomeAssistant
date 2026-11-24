import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

/* OpenStreetMap through Leaflet. Tiles are the only outside request: coordinates stay in the
   page (tile URLs reveal only the viewed area, like any map). No marker images are loaded.
   A track with speeds (Fleet Telemetry) is drawn as segments coloured by speed band. */

export type Track = { path: [number, number][]; speeds?: (number | null)[]; start?: [number, number] | null; end?: [number, number] | null; live?: boolean };

/* Speed bands, km/h. Colours are theme tokens (--speed-1..5) so light/dark stay legible. */
export const SPEED_BANDS = [
  { max: 30, label: '< 30', token: '--speed-1', fallback: '#2a8f6a' },
  { max: 60, label: '30–60', token: '--speed-2', fallback: '#7aa23a' },
  { max: 90, label: '60–90', token: '--speed-3', fallback: '#d69a1c' },
  { max: 130, label: '90–130', token: '--speed-4', fallback: '#d9622b' },
  { max: Infinity, label: '> 130', token: '--speed-5', fallback: '#b03a5b' },
];
export const band = (kmh: number) => SPEED_BANDS.findIndex((b) => kmh < b.max);

const color = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

function speedSegments(path: [number, number][], speeds: (number | null)[]) {
  // consecutive points in the same band become one polyline (fewer layers, smoother lines)
  const out: { band: number; pts: [number, number][] }[] = [];
  for (let i = 1; i < path.length; i++) {
    const a = speeds[i - 1], b = speeds[i];
    const v = a !== null && a !== undefined && b !== null && b !== undefined ? (a + b) / 2 : (b ?? a);
    const k = v === null || v === undefined ? -1 : band(v);
    const last = out[out.length - 1];
    if (last && last.band === k) last.pts.push(path[i]);
    else out.push({ band: k, pts: [path[i - 1], path[i]] });
  }
  return out;
}

export default function TeslaMap({ tracks, focus, label, compact }: { tracks: Track[]; focus?: number; label: string; compact?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!box.current || map.current) return;
    map.current = L.map(box.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>',
    } as L.TileLayerOptions).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    map.current.setView([45.7183, 21.2652], 11);
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const line = color('--energy-load', '#2f9e6b'), dim = color('--muted', '#888'), start = color('--energy-solar', '#d99a1e'), end = color('--energy-grid', '#3b6fd8');
    const casing = color('--surface', '#ffffff');
    const bands = SPEED_BANDS.map((b) => color(b.token, b.fallback));
    const bounds: L.LatLngExpression[] = [];
    tracks.forEach((t, i) => {
      const selected = focus === undefined || focus === i;
      if (t.path.length > 1) {
        const speeds = t.speeds && t.speeds.length === t.path.length && t.speeds.some((v) => v !== null) ? t.speeds : null;
        if (selected && speeds) {
          L.polyline(t.path, { color: casing, weight: 8, opacity: .85, interactive: false }).addTo(g);
          for (const s of speedSegments(t.path, speeds)) {
            L.polyline(s.pts, { color: s.band < 0 ? line : bands[s.band], weight: 5, opacity: .95, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(g);
          }
        } else {
          L.polyline(t.path, { color: selected ? line : dim, weight: selected ? 4 : 2, opacity: selected ? .95 : .45, dashArray: t.live ? '6 6' : undefined }).addTo(g);
        }
      }
      if (selected) {
        bounds.push(...t.path);
        const a = t.start ?? t.path[0], b = t.end ?? t.path[t.path.length - 1];
        if (a) L.circleMarker(a, { radius: 7, color: '#fff', weight: 2, fillColor: start, fillOpacity: 1 }).bindTooltip('Plecare').addTo(g);
        if (b) L.circleMarker(b, { radius: t.live ? 9 : 7, color: '#fff', weight: 2, fillColor: t.live ? line : end, fillOpacity: 1 }).bindTooltip(t.live ? 'Acum' : 'Sosire').addTo(g);
      }
    });
    if (bounds.length) m.fitBounds(L.latLngBounds(bounds as L.LatLngTuple[]).pad(.15), { maxZoom: 15 });
    setTimeout(() => m.invalidateSize(), 50);
  }, [tracks, focus]);

  return <div className={'tesla-map' + (compact ? ' compact' : '')} ref={box} role="img" aria-label={label} />;
}
