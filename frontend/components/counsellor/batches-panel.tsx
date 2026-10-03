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
 *
 * "Starting soon" has one subtlety worth stating, because getting it wrong is
 * what the list did until now: a batch's status is set by a person, not by the
 * calendar, so `upcoming` with a start date two weeks in the past is a real
 * state — somebody scheduled a cohort and never marked it active. Sorting
 * purely by start date put that batch at the top of a list headed "soonest
 * first", where it read as the next thing to start. It is still shown, because
 * it is the row most in need of attention, but it is shown as what it is:
 * overdue to start, said in words, above the ones that genuinely have not
 * started yet.
 */
import Link from 'next/link';

import { ErrorState, LoadingState } from '@/components/states';
import { formatCount, formatDate } from '@/lib/format';
import type { BatchListRow } from '@/types/api';

/** Below this many seats left (or this fraction of capacity, if larger), a batch counts as "filling up". */
const FEW_SEATS_LEFT = 3;
const FEW_SEATS_FRACTION = 0.15;

/** Whether an `upcoming` batch's start date has already gone by — its start
 *  is overdue, not soon. `today` is an ISO date (`YYYY-MM-DD`), compared as a
 *  string so no timezone is involved: both sides are plain dates. */
export function hasOverdueStart(batch: BatchListRow, today: string): boolean {
  return Boolean(batch.start_date) && batch.start_date < today;
}

/**
 * Batches not running yet, the most urgent first.
 *
 * Two groups, in this order: the ones whose start date has passed while they
 * are still `upcoming` (oldest first — the longest overdue is the worst), then
 * the ones still ahead (soonest first). An upcoming batch with no start date at
 * all sorts last rather than throwing.
 *
 * `today` is passed in rather than read from the clock so the order a test
 * pins down is the order a reader sees, and `formatDate`'s timezone cannot
 * change which group a batch lands in.
 */
export function startingSoonBatches(batches: BatchListRow[], today: string): BatchListRow[] {
  const byDate = (a: BatchListRow, b: BatchListRow) =>
    (a.start_date ?? '￿').localeCompare(b.start_date ?? '￿');
  const upcoming = batches.filter((batch) => batch.status === 'upcoming');
  return [
    ...upcoming.filter((batch) => hasOverdueStart(batch, today)).sort(byDate),
    ...upcoming.filter((batch) => !hasOverdueStart(batch, today)).sort(byDate),
  ];
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
        <Link href="/admissions/batches" className="truncate font-medium hover:text-action">
          {batch.name}
        </Link>
        <p className="truncate text-xs text-ink-muted">
          {batch.course_title} · {batch.code}
        </p>
      </div>
      <span className="shrink-0 text-xs text-ink-muted">{detail}</span>
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
  /** Today as an ISO date. Injected so a test — and a screen holding a frozen
   *  "as of" moment — does not depend on the clock. */
  today = new Date().toISOString().slice(0, 10),
}: {
  batches: BatchListRow[];
  kind: 'starting-soon' | 'filling-up';
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  limit?: number;
  today?: string;
}) {
  if (isLoading) return <LoadingState label="Loading batches…" rows={3} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  const full =
    kind === 'starting-soon' ? startingSoonBatches(batches, today) : fillingUpBatches(batches);
  const visible = full.slice(0, limit);

  if (visible.length === 0) {
    return (
      <p className="rounded-card border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted">
        {kind === 'starting-soon'
          ? 'No upcoming batch is scheduled yet.'
          : 'No batch is close to full right now.'}
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <ul className="divide-y divide-line">
        {visible.map((batch) => (
          <BatchRow
            key={batch.id}
            batch={batch}
            detail={
              kind === 'starting-soon'
                ? // Never "Starts 12 Sep" about a date that has gone: the
                  // reader is told the batch was due to start and has not
                  // been marked active, which is the thing to act on.
                  hasOverdueStart(batch, today)
                  ? `Was due to start ${formatDate(batch.start_date)} — not marked active`
                  : `Starts ${formatDate(batch.start_date)}`
                : formatCount(batch.seats_available, 'seat left', 'seats left')
            }
          />
        ))}
      </ul>
      {full.length > visible.length ? (
        <p className="text-xs text-ink-muted">and {full.length - visible.length} more</p>
      ) : null}
    </div>
  );
}
