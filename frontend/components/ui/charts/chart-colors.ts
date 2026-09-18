/**
 * The chart's own color assignment, drawn only from tokens `app/globals.css`
 * already defines — never a hardcoded hex here or in a caller.
 *
 * Two palettes, because the token file defines two for two different jobs
 * (see `globals.css`'s own comments above each block):
 *
 * - `CHART_PALETTE` — the 5 `--color-chart-N` tokens, chosen for maximum
 *   perceptual separation from each other and from `--color-primary`. The
 *   default for any chart whose categories are not already tied to a
 *   specific dashboard-tile accent.
 * - `ACCENT_PALETTE` — the 6 dashboard-tile accent hues (amber/violet/rose/
 *   sky/emerald/fuchsia). For a chart whose categories mirror the stat tiles
 *   above it (e.g. a donut of the same six figures `StatCard` already tints),
 *   picking from this palette instead keeps the color meaning the same
 *   figure has everywhere else on the page.
 *
 * Both are read as CSS custom properties, never resolved to a static hex at
 * build time — the whole point is that a token change in `globals.css`
 * repaints every chart without touching this file.
 */

export const CHART_PALETTE = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
] as const;

export const ACCENT_PALETTE = [
  'var(--color-amber)',
  'var(--color-violet)',
  'var(--color-rose)',
  'var(--color-sky)',
  'var(--color-emerald)',
  'var(--color-fuchsia)',
] as const;

/**
 * The category count past which a donut/pie reads as noise rather than
 * composition — kept as a soft warning (a dev-console note), not a hard
 * runtime check, per this codebase's own preference for "narrow, specific"
 * fixes over invented validation. A caller with 6+ categories almost always
 * means the underlying comparison, not the composition, is the real question
 * — the fix is `BarChart`, not a `DonutChart` prop to suppress the warning.
 */
export const DONUT_CATEGORY_WARNING_THRESHOLD = 5;

/** The next color in a palette, in the fixed order above — never a hash or a
 *  random assignment, so the same series always gets the same color across
 *  re-renders and re-fetches. */
export function paletteColor(index: number, palette: readonly string[] = CHART_PALETTE): string {
  return palette[index % palette.length] as string;
}

/** Low-contrast, "recessive" per the design system's own muted/border tokens
 *  — gridlines and axis lines should read as structure, not data. */
export const CHART_GRID_COLOR = 'var(--color-border)';
export const CHART_AXIS_TEXT_COLOR = 'var(--color-muted-foreground)';

/** Entrance-animation timing shared by every wrapper: within the 400–700ms
 *  band, and short enough it never reads as blocking the chart's own
 *  interactivity (hover/focus handlers are live from the first frame —
 *  Recharts' animation only tweens the drawn shape, not event wiring). */
export const CHART_ANIMATION_MS = 550;
