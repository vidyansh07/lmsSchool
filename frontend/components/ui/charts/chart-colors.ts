/**
 * The chart's own colour assignment, drawn only from tokens
 * `app/globals.css` already defines -- never a hardcoded hex here or in a
 * caller.
 *
 * One palette now. `--color-chart-1..5` is anchored on the action orange and
 * walked around the wheel for perceptual separation at roughly equal
 * lightness, and `theme-contrast.test.ts` checks each step against the card
 * it is drawn on at 3:1 -- the threshold for a graphical object rather than
 * for text.
 *
 * There used to be a second, `ACCENT_PALETTE`, holding the six
 * dashboard-tile accent hues so that a donut of the same six figures could
 * match the tiles above it. Those tiles no longer carry a hue each, so the
 * palette had nothing left to mirror and nothing outside this file read it.
 *
 * Read as CSS custom properties, never resolved to a static hex at build
 * time -- the whole point is that a token change in `globals.css` repaints
 * every chart without touching this file.
 */

export const CHART_PALETTE = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
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
export const CHART_GRID_COLOR = 'var(--color-line)';
export const CHART_AXIS_TEXT_COLOR = 'var(--color-ink-faint)';

/** Entrance-animation timing shared by every wrapper: within the 400–700ms
 *  band, and short enough it never reads as blocking the chart's own
 *  interactivity (hover/focus handlers are live from the first frame —
 *  Recharts' animation only tweens the drawn shape, not event wiring). */
export const CHART_ANIMATION_MS = 550;
