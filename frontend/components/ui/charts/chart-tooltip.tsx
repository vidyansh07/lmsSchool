import type { NameType, ValueType } from 'recharts/types/component/DefaultTooltipContent';
import type { TooltipContentProps } from 'recharts';

/**
 * The one tooltip every wrapper in this directory uses.
 *
 * Follows this session's own dataviz guidance: one readout listing every
 * series at the hovered point (never gated behind landing the pointer
 * exactly on a line), the value as the strong element and the series name
 * secondary, and a short stroke — not a filled swatch — keying each row to
 * its series, since a tooltip is dense enough that a filled box reads as
 * data-weight ink doing a label's job. Series/category names come straight
 * from JSX interpolation (React's own escaping), never `innerHTML`.
 */
export function ChartTooltipContent({
  active,
  payload,
  label,
  valueFormatter,
}: TooltipContentProps<ValueType, NameType> & {
  valueFormatter?: (value: number) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="min-w-[9rem] rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-overlay">
      {label !== undefined && label !== null && label !== '' ? (
        <p className="mb-1.5 font-medium text-ink">{label}</p>
      ) : null}
      <dl className="space-y-1">
        {payload.map((entry) => {
          const numeric = typeof entry.value === 'number' ? entry.value : Number(entry.value);
          const display = Number.isFinite(numeric) && valueFormatter ? valueFormatter(numeric) : String(entry.value ?? '—');
          return (
            <div key={`${entry.dataKey ?? entry.name}`} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="h-0.5 w-3 shrink-0 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <dt className="text-ink-muted">{entry.name}</dt>
              <dd className="ml-auto font-semibold tabular-nums text-ink">{display}</dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
