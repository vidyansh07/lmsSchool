/**
 * Two watchlists built from one fetch of live batches: the ones about to
 * start, and the ones with few seats left. Both read `BatchListRow.status`,
 * `.start_date` and `.seats_available`/`.capacity` — figures the batch list
 * already carries, so this is filtering and sorting, not a second source of
 * truth for seat counts.
 *
 * "Filling up" needs a threshold, and there is no institution setting for
 * one (unlike, say, the risk percentages in `apps.performance.risk`, which
 * are configurable policy). Three seats or 15% of capacity, whichever is
 * larger, is a judgement call fixed here rather than invented as a fake
 * "backend setting" — it is written down once, in `FEW_SEATS_LEFT`, so it is
 * easy to find and revisit rather than buried in a filter expression.
 */
import Link from 'next/link';

import { ErrorState, LoadingState } from '@/components/states';
import { formatCount, formatDate } from '@/lib/format';
import type { BatchListRow } from '@/types/api';

/** Below this many seats left (or this fraction of capacity, if larger), a batch counts as "filling up". */
const FEW_SEATS_LEFT = 3;
const FEW_SEATS_FRACTION = 0.15;

export function startingSoonBatches(batches: BatchListRow[]): BatchListRow[] {
  return batches
    .filter((batch) => batch.status === 'upcoming')
    .slice()
    .sort((a, b) => a.start_date.localeCompare(b.start_date));
}

export function fillingUpBatches(batches: BatchListRow[]): BatchListRow[] {
  return batches
    .filter((batch) => {
      if (batch.status !== 'upcoming' && batch.status !== 'active') return false;
      if (batch.capacity <= 0 || batch.seats_available <= 0) return false;
      const threshold = Math.max(FEW_SEATS_LEFT, Math.ceil(batch.capacity * FEW_SEATS_FRACTION));
      return batch.seats_available <= threshold;
    })
    .slice()
    .sort((a, b) => a.seats_available - b.seats_available);
}

function BatchRow({ batch, detail }: { batch: BatchListRow; detail: string }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
      <div className="min-w-0">
        <Link href="/admissions/batches" className="truncate font-medium hover:text-primary">
          {batch.name}
        </Link>
        <p className="truncate text-xs text-muted-foreground">
          {batch.course_title} · {batch.code}
        </p>
      </div>
      <span className="shrink-0 text-xs text-muted-foreground">{detail}</span>
    </li>
  );
}

export function BatchWatchlist({
  batches,
  kind,
  isLoading,
  error,
  onRetry,
  limit = 5,
}: {
  batches: BatchListRow[];
  kind: 'starting-soon' | 'filling-up';
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  limit?: number;
}) {
  if (isLoading) return <LoadingState label="Loading batches…" rows={3} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  const full = kind === 'starting-soon' ? startingSoonBatches(batches) : fillingUpBatches(batches);
  const visible = full.slice(0, limit);

  if (visible.length === 0) {
    return (
      <p className="rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        {kind === 'starting-soon'
          ? 'No upcoming batch is scheduled yet.'
          : 'No batch is close to full right now.'}
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <ul className="divide-y divide-border">
        {visible.map((batch) => (
          <BatchRow
            key={batch.id}
            batch={batch}
            detail={
              kind === 'starting-soon'
                ? `Starts ${formatDate(batch.start_date)}`
                : formatCount(batch.seats_available, 'seat left', 'seats left')
            }
          />
        ))}
      </ul>
      {full.length > visible.length ? (
        <p className="text-xs text-muted-foreground">and {full.length - visible.length} more</p>
      ) : null}
    </div>
  );
}
