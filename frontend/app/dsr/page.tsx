'use client';

/**
 * Class reports across every batch the caller can see — `/dsr`.
 *
 * Submitted is done: no manager has to approve a class report (the owner's
 * call, 3 October 2026). So this page opens on every report, newest first,
 * not on a review queue, and its second tab is the list that does need
 * action — classes that ended without a report (`GET /dsr/missing/`).
 *
 * A manager may still read a report in full (the side sheet), mark it seen,
 * ask for changes, or reject it. Asking for changes or rejecting needs a
 * reason server-side (`apps.dsr.services.review_dsr` refuses either with a
 * blank comment), so both open a small comment field in place rather than
 * firing immediately. Marking seen fires at once, hiding the row until the
 * reload and rolling back visibly if the request fails.
 *
 * Why there is no search box and no sortable column headers
 * ------------------------------------------------------------
 * `DSRListView` (`GET /api/v1/dsr/`) declares only `DjangoFilterBackend` with
 * `batch`, `trainer`, `status`, `date_after` and `date_before` — no search
 * filter, no ordering filter. Wiring either up here would be a control that
 * visibly does nothing when used. Results come back newest-first because
 * that is `DSR`'s own model ordering.
 */
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { DsrReportSheet } from '@/components/manage/dsr-report-sheet';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { DateRangePicker, type DateRange } from '@/components/date-range-picker';
import { Pagination } from '@/components/pagination';
import { ExportMenu } from '@/components/export-menu';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, Textarea } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { listBatches } from '@/lib/batches';
import { Capability } from '@/lib/capabilities';
import {
  formatClassTime,
  listDsr,
  listMissingReports,
  type DSRListItem,
  type MissingReportRow,
} from '@/lib/dsr';
import { fallback, formatDate, formatDateTime, formatNumber, NO_DATA, UNKNOWN } from '@/lib/format';
import {
  DSR_STATUS_LABEL,
  DSR_STATUS_VARIANT,
  reviewDsr,
  type DsrReviewDecision,
} from '@/lib/manage';
import { listTrainers } from '@/lib/people';
import type { BatchListRow, TrainerListRow } from '@/types/api';

const DSR_STATUS_OPTIONS = Object.entries(DSR_STATUS_LABEL)
  // `under_review` is a legacy state that reads as "Submitted"; one entry for it.
  .filter(([value]) => value !== 'under_review')
  .map(([value, label]) => ({ value, label }));

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
  const list = useList<DSRListItem>(listDsr, {
    ordering: '-report_date',
    page_size: 20,
  });
  const [readingId, setReadingId] = useState<string | null>(null);

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
        [row.id]:
          cause instanceof ApiError
            ? cause.message
            : 'Could not save this decision. Please try again.',
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
    {
      key: 'report_date',
      header: 'Date',
      width: '7rem',
      render: (row) => formatDate(row.report_date),
    },
    {
      key: 'batch_code',
      header: 'Batch',
      render: (row) => (
        <Link
          href={`/manage/batches/${row.batch}`}
          className="font-mono text-xs text-ink hover:text-action hover:underline"
        >
          {fallback(row.batch_code, NO_DATA)}
        </Link>
      ),
    },
    {
      key: 'trainer_name',
      header: 'Trainer',
      render: (row) => fallback(row.trainer_name, UNKNOWN),
    },
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
      render: (row) => (
        <Badge variant={DSR_STATUS_VARIANT[row.status]}>{DSR_STATUS_LABEL[row.status]}</Badge>
      ),
    },
    {
      key: 'read',
      header: 'Report',
      render: (row) => (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`Read the ${row.batch_code} report for ${formatDate(row.report_date)}`}
          onClick={() => setReadingId(row.id)}
        >
          Read
        </Button>
      ),
    },
    {
      key: 'review',
      header: 'Follow up',
      render: (row) => {
        if (!can(Capability.dsrReview) || !REVIEWABLE_STATUSES.has(row.status)) return null;

        if (pending?.id === row.id) {
          const commentId = `dsr-comment-${row.id}`;
          return (
            <div className="w-56 space-y-1.5">
              <label htmlFor={commentId} className="block text-xs font-medium">
                {pending.kind === 'rejected'
                  ? 'Why is this being rejected?'
                  : 'What should the trainer change?'}
              </label>
              <Textarea
                id={commentId}
                rows={2}
                className="text-xs"
                autoFocus
                value={pending.comment}
                onChange={(event) =>
                  setPending((current) =>
                    current ? { ...current, comment: event.target.value } : current,
                  )
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
                  {busyId === row.id
                    ? 'Saving…'
                    : pending.kind === 'rejected'
                      ? 'Reject'
                      : 'Ask for changes'}
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
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busyId === row.id}
                onClick={() => void decide(row, 'approved', '')}
              >
                {busyId === row.id ? 'Saving…' : 'Mark seen'}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPending({ id: row.id, kind: 'revision_required', comment: '' })}
              >
                Ask for changes
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
  const isUnfiltered = !list.query.status && !list.query.batch && !list.query.trainer && !dateRange.start;
  const reading = visibleRows.find((row) => row.id === readingId) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Class reports</h1>
          <p className="text-sm text-ink-muted">
            What each class covered, as its trainer reported it. A submitted report is done — no
            approval needed. Ask for changes if something is wrong.
          </p>
        </div>
        <ExportMenu reportKey="daily_reports" count={list.data?.count ?? null} size="md" />
      </div>

      <Tabs defaultValue="reports">
        <TabsList aria-label="Class reports">
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="missing">Missing</TabsTrigger>
        </TabsList>
        <TabsContent value="missing" className="pt-4">
          <MissingReports />
        </TabsContent>
        <TabsContent value="reports" className="space-y-6 pt-4">

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
            emptyTitle={isUnfiltered ? 'No class reports yet' : 'No reports match these filters'}
            emptyDescription={
              isUnfiltered
                ? 'Reports appear here as trainers submit them after class.'
                : 'Try a different status, batch, trainer or date range.'
            }
            caption="Class reports"
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
        </TabsContent>
      </Tabs>

      <DsrReportSheet
        dsrId={readingId}
        heading={
          reading
            ? {
                batchCode: reading.batch_code,
                date: reading.report_date,
                startTime: reading.start_time,
                trainerName: reading.trainer_name,
              }
            : undefined
        }
        onClose={() => setReadingId(null)}
      />
    </div>
  );
}

/** Classes that ended without a submitted report, in the caller's reach. */
function MissingReports() {
  const [rows, setRows] = useState<MissingReportRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listMissingReports()
      .then((result) => {
        if (!cancelled) {
          setRows(result);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : 'The request failed.');
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const columns: DataTableColumn<MissingReportRow>[] = [
    { key: 'date', header: 'Date', width: '7rem', render: (row) => formatDate(row.date) },
    {
      key: 'time',
      header: 'Class',
      render: (row) => `${formatClassTime(row.start_time)}–${formatClassTime(row.end_time)}`,
    },
    {
      key: 'batch_code',
      header: 'Batch',
      render: (row) => (
        <Link
          href={`/manage/batches/${row.batch}`}
          className="font-mono text-xs text-ink hover:text-action hover:underline"
        >
          {fallback(row.batch_code, NO_DATA)}
        </Link>
      ),
    },
    { key: 'trainer_name', header: 'Trainer', render: (row) => fallback(row.trainer_name, UNKNOWN) },
    {
      key: 'state',
      header: 'Report',
      render: (row) =>
        row.dsr_status === 'revision_required' ? (
          <Badge variant="warning">Changes asked for</Badge>
        ) : row.dsr ? (
          <Badge variant="neutral">Draft</Badge>
        ) : (
          <Badge variant="warning">Not started</Badge>
        ),
    },
    {
      key: 'due_at',
      header: 'Due',
      render: (row) => (row.due_at ? formatDateTime(row.due_at) : NO_DATA),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows ?? []}
      getRowId={(row) => row.session}
      isLoading={rows === null && error === null}
      error={error ? { message: error } : null}
      onRetry={() => {
        setError(null);
        setRows(null);
        setAttempt((value) => value + 1);
      }}
      emptyTitle="Nothing missing"
      emptyDescription="Every class in the last two weeks has its report."
      caption="Classes without a submitted report"
    />
  );
}

export default function DsrPage() {
  return (
    <RequireAuth capability={Capability.dsrViewAny}>
      <DsrQueue />
    </RequireAuth>
  );
}
