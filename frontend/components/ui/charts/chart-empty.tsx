import { BarChart3 } from 'lucide-react';

import { Empty, EmptyDescription, EmptyIcon, EmptyTitle } from '@/components/ui/empty';

/**
 * "No data yet" for a chart — the same `Empty` primitive every other empty
 * state in the app uses (see `components/ui/empty.tsx`), not a blank axis
 * frame with nothing plotted on it. A chart with zero points drawn still
 * *looks* like a chart (axes, gridlines) unless something says otherwise.
 */
export function ChartEmpty({
  message = 'No data yet',
  height,
}: {
  message?: string;
  height?: number;
}) {
  return (
    <Empty style={height ? { minHeight: height } : undefined} className="justify-center border-none bg-muted/40 py-8">
      <EmptyIcon>
        <BarChart3 aria-hidden="true" />
      </EmptyIcon>
      <EmptyTitle>{message}</EmptyTitle>
      <EmptyDescription>Figures will appear here once there is something to plot.</EmptyDescription>
    </Empty>
  );
}
