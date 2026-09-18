/**
 * Shared shapes for the chart wrappers in this directory.
 *
 * Kept intentionally plain — a chart's caller should be able to hand it the
 * same array it already fetched (see `TrendPoint` in `types/api.ts`) without
 * a mapping step, and `series` is the one place multi-line/multi-bar charts
 * add structure on top of that.
 */

/** One labelled series drawn on a chart. `color` defaults to the next step
 *  in the chart palette (see `chart-colors.ts`) when omitted, in a fixed,
 *  never-cycled-per-render order. */
export interface ChartSeriesDef {
  key: string;
  label: string;
  color?: string;
}

/** A point on a trend-over-time chart (line/area). `date` is a pre-formatted
 *  label (a week, a day, a month) — these wrappers never parse or format
 *  dates themselves, matching `lib/format.ts` owning that job everywhere
 *  else in the app. Extra numeric fields are additional series. */
export type TrendDatum = Record<string, string | number | null | undefined> & {
  date: string;
};

/** One category on a comparison/composition chart (bar/donut). `label` is
 *  the category name; extra numeric fields let the bar chart's grouped
 *  variant plot more than one series per category. */
export type CategoryDatum = Record<string, string | number | null | undefined> & {
  label: string;
};

/** Common props every wrapper accepts beyond its data. */
export interface ChartBaseProps {
  /** Fixed plot height in px. Width is fluid (`ResponsiveContainer`). */
  height?: number;
  /** Shows the loading skeleton instead of the plot. */
  loading?: boolean;
  /** Shown in place of the plot when `data` has no usable points. */
  emptyMessage?: string;
  /** Formats a raw numeric value for the tooltip, legend and axis ticks. */
  valueFormatter?: (value: number) => string;
  /** Accessible name for the chart's `role="img"` summary and the caption
   *  read alongside the visually-hidden data table. */
  ariaLabel?: string;
  className?: string;
}
