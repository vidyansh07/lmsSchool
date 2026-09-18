import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading placeholder for a chart, built from the same `Skeleton` primitive
 * as the rest of the app (`components/ui/skeleton.tsx`) rather than a
 * chart-specific loader — a few bars of decreasing height read as "a chart
 * is coming" without pretending to be a real preview of the data.
 */
export function ChartSkeleton({ height = 240 }: { height?: number }) {
  const bars = [58, 82, 46, 94, 64, 100, 72];
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="flex items-end gap-2 px-1"
      style={{ height }}
    >
      <span className="sr-only">Loading chart…</span>
      {bars.map((percent, index) => (
        <Skeleton
          key={index}
          className="flex-1 rounded-t-md rounded-b-none"
          style={{ height: `${percent}%` }}
        />
      ))}
    </div>
  );
}
