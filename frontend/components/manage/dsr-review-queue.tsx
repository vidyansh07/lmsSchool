'use client';

/**
 * The batch page's inline "reports awaiting review" queue.
 *
 * Approving is optimistic: the row leaves the list the moment the button is
 * pressed, because waiting on the network for a queue to shrink by one reads
 * as lag, not correctness. If the request then fails, the row is put back —
 * visibly, with the reason — rather than left removed while the report is
 * still sitting there unreviewed on the server. That rollback *is* this
 * screen's "undo": `APPROVED` is a terminal status server-side (no
 * transition leads out of it, see `lib/manage.ts#reviewDsr`), so a literal
 * "undo my approval" button would always fail with a conflict. Rolling back
 * on failure is the honest version of the same promise — this action is safe
 * to try, because it cannot silently half-succeed.
 */
import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { formatDate } from '@/lib/format';
import {
  DSR_STATUS_LABEL,
  DSR_STATUS_VARIANT,
  listBatchDsr,
  reviewDsr,
  type ManageDsrRow,
} from '@/lib/manage';

export function DsrReviewQueue({ batchId, onReviewed }: { batchId: string; onReviewed?: () => void }) {
  const { can } = useAuth();
  const [rows, setRows] = useState<ManageDsrRow[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    setError(null);
    listBatchDsr(batchId, { status: 'submitted', ordering: '-report_date', page_size: 10 })
      .then((page) => setRows(page.results))
      .catch((cause: unknown) => setError(cause instanceof ApiError ? cause : null));
  }, [batchId]);

  useEffect(() => {
    setRows(null);
    load();
  }, [load]);

  async function approve(row: ManageDsrRow) {
    setBusyId(row.id);
    setRowError((current) => ({ ...current, [row.id]: '' }));
    setRows((current) => (current ? current.filter((entry) => entry.id !== row.id) : current));
    try {
      await reviewDsr(row.id, 'approved');
      onReviewed?.();
    } catch (cause) {
      setRows((current) => (current ? [row, ...current] : [row]));
      setRowError((current) => ({
        ...current,
        [row.id]: cause instanceof ApiError ? cause.message : 'Could not approve this report. Please try again.',
      }));
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load reports awaiting review"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }
  if (rows === null) return <LoadingState label="Loading reports awaiting review…" rows={2} />;
  if (rows.length === 0) {
    return (
      <EmptyState
        title="Nothing awaiting review"
        description="Every submitted daily status report on this batch has been reviewed."
      />
    );
  }

  return (
    <ul className="stagger divide-y divide-border rounded-[var(--radius-card)] border border-border">
      {rows.map((row) => (
        <li
          key={row.id}
          className="animate-fade-in space-y-1.5 px-4 py-3 transition-colors hover:bg-muted/40"
          data-testid="dsr-queue-row"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {row.trainer_name || 'Unknown trainer'} — {formatDate(row.report_date)}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {row.actual_topic || 'No topic recorded'}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge variant={DSR_STATUS_VARIANT[row.status]}>{DSR_STATUS_LABEL[row.status]}</Badge>
              {can(Capability.dsrReview) ? (
                <Button size="sm" disabled={busyId === row.id} onClick={() => void approve(row)}>
                  {busyId === row.id ? 'Approving…' : 'Approve'}
                </Button>
              ) : null}
            </div>
          </div>
          {rowError[row.id] ? (
            <Alert variant="error" className="text-xs">
              {rowError[row.id]}
            </Alert>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
