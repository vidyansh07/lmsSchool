/**
 * A student's own offers, on their dashboard.
 *
 * `GET /placements/` is scoped to the caller, so a student reads their own
 * offers and nobody else's — their classmate's package is somebody else's
 * salary, and the endpoint gives them a 404 for it
 * (`tests/test_placements.py`).
 *
 * Read-only: an offer is recorded by the placement desk, which is also who
 * can correct one. A student reading "declined" here is reading what the
 * desk wrote about a decision they made, which is the point of showing it —
 * the record should not be a thing only staff can see.
 *
 * The card renders nothing at all when there are no offers. Most students at
 * any moment have none, and a permanent "no offers yet" tile on the
 * dashboard is a daily reminder of nothing.
 */
import { Briefcase } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatDate, NOT_AVAILABLE } from '@/lib/format';
import { PLACEMENT_STATUS_LABEL, PLACEMENT_STATUS_VARIANT } from '@/lib/placement-labels';
import type { Placement } from '@/types/api';

export function PlacementsPanel({
  placements,
  isLoading,
  error,
  onRetry,
}: {
  placements: Placement[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading your offers…" rows={2} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }
  if (placements.length === 0) return null;

  return (
    <ul className="space-y-3">
      {placements.map((offer) => (
        <li
          key={offer.id}
          className="flex flex-wrap items-start justify-between gap-3 rounded-card border border-line p-3"
        >
          <div className="flex min-w-0 items-start gap-2.5">
            <Briefcase className="mt-0.5 size-4 shrink-0 text-action" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{offer.company}</p>
              <p className="truncate text-xs text-ink-muted">
                {offer.role_title}
                {offer.location ? ` · ${offer.location}` : ''}
              </p>
              <p className="text-xs text-ink-muted">
                <Badge variant={PLACEMENT_STATUS_VARIANT[offer.status]}>
                  {PLACEMENT_STATUS_LABEL[offer.status]}
                </Badge>
                <span className="ml-2">Offered {formatDate(offer.offered_on)}</span>
              </p>
            </div>
          </div>
          <p className="shrink-0 text-sm tabular-nums">
            {offer.annual_package ? formatCurrency(offer.annual_package) : NOT_AVAILABLE}
          </p>
        </li>
      ))}
    </ul>
  );
}
