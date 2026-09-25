/**
 * The chart's own colour assignment, drawn only from tokens
 * `app/globals.css` already defines -- never a hardcoded hex here or in a
 * caller.
 *
 * One palette, eight steps. This is the single place in the product where
 * colour is categorical rather than semantic: a series' colour is its
 * identity, and identity is information. `theme-contrast.test.ts` checks
 * every step against the card it is drawn on at 3:1 -- the threshold for a
 * graphical object rather than for text, and what a 2px stroke has to clear.
 *
 * The hues are the reference product's; the lightness is not. Five of its
 * ten series colours fail that 3:1 check (amber-500 2.15:1, cyan-500 2.43,
 * teal-500 2.49, emerald-500 2.54, sky-500 2.77), so the 600/700 family is
 * used at the same hue. See `globals.css` for the measurements.
 *
 * There used to be a second palette, `ACCENT_PALETTE`, holding the six
 * dashboard-tile accent hues so that a donut of the same six figures could
 * match the tiles above it. Those tiles no longer carry a hue each, so it
 * had nothing left to mirror and nothing outside this file read it.
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
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
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

/**
 * The series count past which colour stops doing the job.
 *
 * Eight steps exist, but eight *lines on one plot* is not what they are for
 * -- past five the eye cannot hold the legend, and three of the eight are
 * blue-family. The fix for a seven-series chart is small multiples, not a
 * ninth colour. A soft dev-console warning, the same shape as
 * `DONUT_CATEGORY_WARNING_THRESHOLD`: a caller who genuinely needs seven
 * categories has a different chart, not a suppression prop.
 *
 * The overview strip is the deliberate exception -- seven dots there are
 * fine because each is paired with its own text label, so colour is never
 * the identifier.
 */
export const SERIES_COUNT_WARNING_THRESHOLD = 5;

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
