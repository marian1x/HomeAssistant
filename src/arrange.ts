/* Device order chosen by each user (owner request 2026-11-10). Display preference only:
   saved per account on the server (/casa/api/layout) so phone, browser and APK agree.
   "usage" ranks by the user's accepted commands of the last 30 days (audit log). */

export type Sort = 'manual' | 'usage' | 'default';
export type Layout = { sort: Sort; order: string[]; groups: string[]; usage: Record<string, number>; usage_days?: number };
export const EMPTY: Layout = { sort: 'default', order: [], groups: [], usage: {} };
export const GROUPS = ['lights', 'climate', 'water', 'power', 'media', 'mobility'];
type Item = { id: string; primary: { entity_id: string }; entries?: { entity_id: string }[] };

/** Commands this user sent to any entity of the device. */
export function uses(d: Item, usage: Record<string, number>) {
  const ids = new Set([d.primary.entity_id, ...(d.entries || []).map((e) => e.entity_id)]);
  let total = 0;
  ids.forEach((id) => { total += usage[id] || 0; });
  return total;
}

/** Items in the chosen order; unknown items keep their default order after the known ones. */
export function arrange<T extends Item>(items: T[], layout: Layout): T[] {
  if (layout.sort === 'default') return items;
  const rank = new Map(layout.order.map((id, i) => [id, i]));
  return items
    .map((d, i) => ({ d, place: rank.get(d.id) ?? layout.order.length + i, score: layout.sort === 'usage' ? uses(d, layout.usage) : 0 }))
    .sort((a, b) => b.score - a.score || a.place - b.place)
    .map((row) => row.d);
}

/** Moves one id to position `to` among the ids currently shown, keeping every other
    id (other rooms, other groups) where it was in the full order. */
export function move(order: string[], shown: string[], id: string, to: number): string[] {
  const visible = shown.filter((x) => x !== id);
  visible.splice(Math.max(0, Math.min(to, visible.length)), 0, id);
  const showing = new Set(shown);
  const base = [...order, ...shown.filter((x) => !order.includes(x))];
  let next = 0;
  return base.map((x) => (showing.has(x) ? visible[next++] : x));
}

/** Category groups in the user's order; new categories follow at the end. */
export function groupOrder(layout: Layout) {
  return [...layout.groups.filter((g) => GROUPS.includes(g)), ...GROUPS.filter((g) => !layout.groups.includes(g))];
}

export function moveGroup(layout: Layout, group: string, step: number): string[] {
  const groups = groupOrder(layout), from = groups.indexOf(group), to = from + step;
  if (from < 0 || to < 0 || to >= groups.length) return groups;
  groups.splice(from, 1);
  groups.splice(to, 0, group);
  return groups;
}
