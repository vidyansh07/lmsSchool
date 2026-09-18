/**
 * A time-of-day greeting for a signed-in viewer — "Good morning, Priya."
 *
 * Deliberately the cheapest possible real per-viewer data: the viewer's own
 * `full_name` (already the exact field `HeaderAccount`/`AccountCard` read in
 * `components/app-shell.tsx`, falling back to `email` the same way those do)
 * and the browser's own clock. No fetch, no new field, no invented copy.
 */
export function timeOfDayGreeting(hour: number = new Date().getHours()): string {
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** `name` is the same `full_name || email` fallback used elsewhere; when
 *  neither is available (should not happen behind `RequireAuth`, but the
 *  type allows it), the greeting degrades to a plain one rather than
 *  rendering "undefined". */
export function greeting(name: string | null | undefined, hour?: number): string {
  const base = timeOfDayGreeting(hour);
  return name ? `${base}, ${name}` : base;
}
