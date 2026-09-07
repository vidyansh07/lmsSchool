'use client';

/**
 * The manager's review queue — `/dsr`, fixing the "Daily reports" 404 in the
 * Review group of the sidebar.
 *
 * One table, not two screens for "what's waiting" and "everything else"
 * -------------------------------------------------------------------------
 * `components/manage/dsr-review-queue.tsx` already owns "a batch's reports
 * awaiting review, approved inline with a visible rollback" — it is reused
 * as-is on the batch detail page and is not rebuilt here, because it cannot
 * be: it is hard-wired to one `batchId` (`listBatchDsr`), with no filters, a
 * ten-row cap and no reject or revision path, which is exactly right for a
 * widget inside one batch's page and exactly wrong for an institution-wide
 * queue. Rather than bolt a second, parallel "awaiting review" widget on top
 * of a full filterable table underneath — two components fetching
 * overlapping data, two empty states to keep in sync — this page is *one*
 * `DataTable` + `useList`, exactly the `BatchesHub` pairing, defaulted to
 * `status=submitted`. That default *is* "lead with what awaits review": it
 * is the same definition of "awaiting review" `DsrReviewQueue` itself uses,
 * just answered at full institution scale with the extra filters and the
 * reject/revision path that scale requires. Widening the status filter is
 * how "the rest is filterable history" stops being a separate screen.
 *
 * Why there is no search box and no sortable column headers
 * ------------------------------------------------------------
 * `DSRListView` (`GET /api/v1/dsr/`) declares only `DjangoFilterBackend` with
 * `batch`, `trainer`, `status`, `date_after` and `date_before` — no search
 * filter, no ordering filter. `ListToolbar` and a sortable `Th` both exist
 * elsewhere in this app for endpoints that support them; wiring either up
 * here would be a control that visibly does nothing when used, which is a
 * worse failure than not offering it. Results come back newest-first because
 * that is `DSR`'s own model ordering, not because this page asked for it.
 *
 * Approve is inline; reject and revision are not
 * ------------------------------------------------
 * Approving calls `reviewDsr` (from `lib/manage.ts`, the same function and
 * the same optimistic-hide-then-roll-back-on-failure behaviour
 * `DsrReviewQueue` established) the moment the button is pressed. Rejecting
 * or asking for a revision needs a reason server-side
 * (`apps.dsr.services.review_dsr` refuses either with a blank comment), so
 * clicking either one opens a small comment field in place rather than
 * firing immediately — the "fuller control" the brief asks for, sized to
 * what actually differs (one required field), not a second page.
 */
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { DateRangePicker, type DateRange } from '@/components/date-range-picker';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, Textarea } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { listBatches } from '@/lib/batches';
import { Capability } from '@/lib/capabilities';
import { listDsr, type DSRListItem } from '@/lib/dsr';
import { fallback, formatDate, formatNumber, NO_DATA, UNKNOWN } from '@/lib/format';
import { DSR_STATUS_LABEL, DSR_STATUS_VARIANT, reviewDsr, type DsrReviewDecision } from '@/lib/manage';
import { listTrainers } from '@/lib/people';
import type { BatchListRow, TrainerListRow } from '@/types/api';

const DSR_STATUS_OPTIONS = Object.entries(DSR_STATUS_LABEL).map(([value, label]) => ({ value, label }));

/** A row's in-progress reject/revision comment. Approve carries none, so it
 *  never needs this — it fires straight from `decide`. */
interface PendingDecision {
  id: string;
  kind: Extract<DsrReviewDecision, 'rejected' | 'revision_required'>;
  comment: string;
}

const REVIEWABLE_STATUSES = new Set<DSRListItem['status']>(['submitted', 'under_review']);

export function DsrQueue() {
  const { can } = useAuth();
  const list = useList<DSRListItem>(listDsr, { status: 'submitted', ordering: '-report_date', page_size: 20 });

  const [batchOptions, setBatchOptions] = useState<BatchListRow[]>([]);
  const [trainerOptions, setTrainerOptions] = useState<TrainerListRow[]>([]);
  const [dateRange, setDateRange] = useState<DateRange>({ start: '', end: '' });

  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingDecision | null>(null);

  useEffect(() => {
    let cancelled = false;
    // These two populate convenience filters. A batch or trainer list that
    // fails to load should not block the queue itself — the corresponding
    // filter just offers no options beyond "All", the same as if nobody had
    // touched it.
    listBatches({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setBatchOptions(page.results);
      })
      .catch(() => undefined);
    listTrainers({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setTrainerOptions(page.results);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // A fresh page from the server is the moment any locally-held optimism
  // (a row hidden pending its own request, an error left over from a
  // previous attempt) stops being needed — the server's own answer now
  // supersedes it.
  useEffect(() => {
    setHiddenIds(new Set());
    setRowErrors({});
  }, [list.data]);

  async function decide(row: DSRListItem, decision: DsrReviewDecision, comment: string) {
    setBusyId(row.id);
    setRowErrors((current) => ({ ...current, [row.id]: '' }));
    setHiddenIds((current) => new Set(current).add(row.id));
    try {
      await reviewDsr(row.id, decision, comment);
      setPending(null);
      list.reload();
    } catch (cause) {
      setHiddenIds((current) => {
        const next = new Set(current);
        next.delete(row.id);
        return next;
      });
      setRowErrors((current) => ({
        ...current,
        [row.id]: cause instanceof ApiError ? cause.message : 'Could not save this decision. Please try again.',
      }));
    } finally {
      setBusyId(null);
    }
  }

  function onDateRangeChange(range: DateRange) {
    setDateRange(range);
    list.setQuery({ date_after: range.start, date_before: range.end });
  }

  const columns: DataTableColumn<DSRListItem>[] = [
    { key: 'report_date', header: 'Date', width: '7rem', render: (row) => formatDate(row.report_date) },
    {
      key: 'batch_code',
      header: 'Batch',
      render: (row) => (
        <Link
          href={`/manage/batches/${row.batch}`}
          className="font-mono text-xs text-foreground hover:text-primary hover:underline"
        >
          {fallback(row.batch_code, NO_DATA)}
        </Link>
      ),
    },
    { key: 'trainer_name', header: 'Trainer', render: (row) => fallback(row.trainer_name, UNKNOWN) },
    {
      key: 'actual_topic',
      header: 'Topic',
      render: (row) => (
        <span className="block max-w-[16rem] truncate" title={row.actual_topic || undefined}>
          {fallback(row.actual_topic, NO_DATA)}
        </span>
      ),
    },
    {
      key: 'attendance',
      header: 'Present / absent',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">
          {formatNumber(row.present_count)} / {formatNumber(row.absent_count)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <Badge variant={DSR_STATUS_VARIANT[row.status]}>{DSR_STATUS_LABEL[row.status]}</Badge>,
    },
    {
      key: 'review',
      header: 'Review',
      render: (row) => {
        if (!can(Capability.dsrReview) || !REVIEWABLE_STATUSES.has(row.status)) return null;

        if (pending?.id === row.id) {
          const commentId = `dsr-comment-${row.id}`;
          return (
            <div className="w-56 space-y-1.5">
              <label htmlFor={commentId} className="block text-xs font-medium">
                {pending.kind === 'rejected' ? 'Why is this being rejected?' : 'What needs to change?'}
              </label>
              <Textarea
                id={commentId}
                rows={2}
                className="text-xs"
                autoFocus
                value={pending.comment}
                onChange={(event) =>
                  setPending((current) => (current ? { ...current, comment: event.target.value } : current))
                }
              />
              <div className="flex gap-1.5">
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={!pending.comment.trim() || busyId === row.id}
                  onClick={() => void decide(row, pending.kind, pending.comment.trim())}
                >
                  {busyId === row.id ? 'Saving…' : pending.kind === 'rejected' ? 'Reject' : 'Request revision'}
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setPending(null)}>
                  Cancel
                </Button>
              </div>
              {rowErrors[row.id] ? (
                <Alert variant="error" className="p-2 text-xs">
                  {rowErrors[row.id]}
                </Alert>
              ) : null}
            </div>
          );
        }

        return (
          <div className="space-y-1">
            <div className="flex flex-wrap gap-1.5">
              <Button type="button" size="sm" disabled={busyId === row.id} onClick={() => void decide(row, 'approved', '')}>
                {busyId === row.id ? 'Approving…' : 'Approve'}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPending({ id: row.id, kind: 'revision_required', comment: '' })}
              >
                Request revision
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPending({ id: row.id, kind: 'rejected', comment: '' })}
              >
                Reject
              </Button>
            </div>
            {rowErrors[row.id] ? (
              <Alert variant="error" className="w-56 p-2 text-xs">
                {rowErrors[row.id]}
              </Alert>
            ) : null}
          </div>
        );
      },
    },
  ];

  const visibleRows = (list.data?.results ?? []).filter((row) => !hiddenIds.has(row.id));
  const isAwaitingReviewView = (list.query.status ?? '') === 'submitted';

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Daily reports</h1>
        <p className="text-sm text-muted-foreground">
          Opens on what is waiting for your review, newest first. Approve inline; rejecting or asking for a
          revision needs a word about why. Change the filters below to browse the rest as history.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="dsr-filter-status" className="mb-1.5 block text-sm font-medium">
            Status
          </label>
          <Select
            id="dsr-filter-status"
            className="sm:w-48"
            value={String(list.query.status ?? '')}
            onChange={(event) => list.setQuery({ status: event.target.value })}
          >
            <option value="">All statuses</option>
            {DSR_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="dsr-filter-batch" className="mb-1.5 block text-sm font-medium">
            Batch
          </label>
          <Select
            id="dsr-filter-batch"
            className="sm:w-56"
            value={String(list.query.batch ?? '')}
            onChange={(event) => list.setQuery({ batch: event.target.value })}
          >
            <option value="">All batches</option>
            {batchOptions.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.code} · {batch.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="dsr-filter-trainer" className="mb-1.5 block text-sm font-medium">
            Trainer
          </label>
          <Select
            id="dsr-filter-trainer"
            className="sm:w-56"
            value={String(list.query.trainer ?? '')}
            onChange={(event) => list.setQuery({ trainer: event.target.value })}
          >
            <option value="">All trainers</option>
            {trainerOptions.map((trainer) => (
              <option key={trainer.id} value={trainer.id}>
                {trainer.full_name} ({trainer.trainer_id})
              </option>
            ))}
          </Select>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Report date</p>
          <DateRangePicker value={dateRange} onChange={onDateRangeChange} />
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={visibleRows}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        onRetry={list.reload}
        emptyTitle={isAwaitingReviewView ? 'Nothing awaiting review' : 'No reports match these filters'}
        emptyDescription={
          isAwaitingReviewView
            ? 'Every submitted daily status report has been reviewed.'
            : 'Try a different status, batch, trainer or date range.'
        }
        caption="Daily status reports"
        densityStorageKey="grras.dsr-queue-density"
      />

      {list.data ? (
        <Pagination
          page={list.data.page}
          totalPages={list.data.total_pages}
          count={list.data.count}
          pageSize={list.data.page_size}
          onPageChange={list.setPage}
        />
      ) : null}
    </div>
  );
}

export default function DsrPage() {
  return (
    <RequireAuth capability={Capability.dsrViewAny}>
      <DsrQueue />
    </RequireAuth>
  );
}
