import type { Props as DefaultLegendContentProps } from 'recharts/types/component/DefaultLegendContent';

/**
 * The shared legend, shown whenever a chart carries more than one series —
 * color is never the only way to tell two series apart. The mark mirrors
 * what is actually drawn (a short line for `Line`/`Area` series, a rounded
 * rect for `Bar`/`Pie` slices) per this session's own dataviz guidance.
 */
export function ChartLegendContent({
  payload,
  markShape = 'line',
}: DefaultLegendContentProps & { markShape?: 'line' | 'rect' }) {
  if (!payload || payload.length === 0) return null;

  return (
    <ul className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 text-xs text-ink-muted">
      {payload.map((entry) => (
        // `value` first, not `dataKey`. For a line or an area `dataKey` is
        // the series key and is unique, but for a pie Recharts reports the
        // *same* `dataKey` on every slice (the one field the pie reads), so
        // keying on it gave four legend items the identical key `value` and
        // React logged a duplicate-key error for every donut on the page.
        // `value` is the visible label in both cases, which is unique by
        // definition -- two legend entries reading the same word would be a
        // legend bug of its own.
        <li key={`${entry.value ?? entry.dataKey}`} className="flex items-center gap-1.5">
          {markShape === 'rect' ? (
            <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[2px]" style={{ backgroundColor: entry.color }} />
          ) : (
            <span aria-hidden="true" className="h-0.5 w-3 shrink-0 rounded-full" style={{ backgroundColor: entry.color }} />
          )}
          {entry.value}
        </li>
      ))}
    </ul>
  );
}
