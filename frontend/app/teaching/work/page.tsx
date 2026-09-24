'use client';

/**
 * A trainer's own "my work" queue (ERP Phase 16): every one of their own
 * activities, filterable by status and overdue, reusing Phase 9's activity
 * engine end to end — `lib/work.ts`'s `listMyActivities` (already scoped
 * server-side to the caller by `GET /me/activities/`) for the list and
 * `components/work/activity-drawer.tsx` for detail.
 *
 * Deliberately a separate, lighter page rather than the shared `/activities`
 * screen (`app/activities/page.tsx`) with `mine=1` pinned: that screen's
 * saved filters, "assigned to" field and type filter all exist for a
 * cross-role reviewer working someone else's queue, and every one of them
 * would have exactly one useful value once every row is already the
 * caller's own — reusing it would mean carrying that dead UI along, or
 * threading new "hide this control" props through an already-dense
 * component for a single caller. The two screens share everything that
 * *is* reusable instead: the query and mutation functions in `lib/work.ts`,
 * `ActivityDrawer`, and the same table/badge/pagination primitives.
 */

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Select } from '@/components/ui/input';
import { ActivityDrawer } from '@/components/work/activity-drawer';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import {
  ACTIVITY_PRIORITY_LABEL,
  ACTIVITY_STATUS_LABEL,
  ACTIVITY_STATUS_VARIANT,
} from '@/lib/labels';
import { listMyActivities } from '@/lib/work';
import type { Activity, ActivityStatus, Paginated } from '@/types/api';

const STATUSES: ActivityStatus[] = [
  'draft',
  'planned',
  'assigned',
  'in_progress',
  'completed',
  'missed',
  'overdue',
  'cancelled',
  'reopened',
  'under_review',
  'approved',
  'requires_action',
];

interface Filters {
  status: '' | ActivityStatus;
  overdue: boolean;
  page: number;
}

interface ListState {
  key: string;
  data: Paginated<Activity> | null;
  error: ApiError | null;
  isLoading: boolean;
}

function MyWorkWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Read once, at mount — this only seeds the initial filter from a link
  // like the dashboard's "Overdue" tile (`/teaching/work?overdue=1`); after
  // that the checkbox below is the source of truth, same as the toggles on
  // `/activities`.
  const [filters, setFilters] = useState<Filters>(() => ({
    status: '',
    overdue: searchParams.get('overdue') === '1',
    page: 1,
  }));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const key = `${JSON.stringify(filters)}#${reloadToken}`;
  const [state, setState] = useState<ListState>({ key, data: null, error: null, isLoading: true });
  if (state.key !== key) {
    setState({ key, data: null, error: null, isLoading: true });
  }

  useEffect(() => {
    let cancelled = false;
    listMyActivities({
      status: filters.status || undefined,
      overdue: filters.overdue ? 1 : undefined,
      ordering: 'due_at',
      page: filters.page,
    })
      .then((data) => {
        if (!cancelled) setState({ key, data, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error =
          cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The request failed.', '');
        setState({ key, data: null, error, isLoading: false });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function reload() {
    setReloadToken((value) => value + 1);
  }

  function updateFilters(patch: Partial<Filters>) {
    const next = { ...filters, ...patch, page: patch.page ?? 1 };
    setFilters(next);
    // Keeps the URL in sync with the "overdue" toggle so this screen stays
    // bookmarkable/shareable the same way the dashboard tile links to it —
    // without making the filter bar itself re-read the URL on every render.
    const query = next.overdue ? '?overdue=1' : '';
    router.replace(`/teaching/work${query}`);
  }

  const rows = state.data?.results ?? [];
  const hasFilters = Boolean(filters.status) || filters.overdue;

  const columns: DataTableColumn<Activity>[] = [
    {
      key: 'title',
      header: 'Title',
      sticky: 'start',
      render: (row) => (
        <button
          type="button"
          className="text-left font-medium underline-offset-2 hover:underline"
          onClick={() => setSelectedId(row.id)}
        >
          {row.title}
        </button>
      ),
    },
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <>
          {row.student.name}
          <span className="block text-xs text-ink-muted">{row.student.student_id}</span>
        </>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      render: (row) => <Badge>{row.type.name}</Badge>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>
          {ACTIVITY_STATUS_LABEL[row.status]}
        </Badge>
      ),
    },
    { key: 'priority', header: 'Priority', render: (row) => ACTIVITY_PRIORITY_LABEL[row.priority] },
    {
      key: 'due_at',
      header: 'Due',
      render: (row) => <span className="whitespace-nowrap">{formatDateTime(row.due_at)}</span>,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My work</h1>
        <p className="text-sm text-ink-muted">
          Every activity assigned to you — interviews, mentoring, reviews and the rest.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <Select
          aria-label="Status"
          value={filters.status}
          onChange={(event) => updateFilters({ status: event.target.value as '' | ActivityStatus })}
          className="w-44"
        >
          <option value="">Every status</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {ACTIVITY_STATUS_LABEL[status]}
            </option>
          ))}
        </Select>
        <div className="flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
          <Checkbox
            aria-label="Overdue"
            checked={filters.overdue}
            onCheckedChange={(checked) => updateFilters({ overdue: Boolean(checked) })}
          />
          <span>Overdue only</span>
        </div>
        {hasFilters ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => updateFilters({ status: '', overdue: false })}
          >
            Clear filters
          </Button>
        ) : null}
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        isLoading={state.isLoading}
        loadingLabel="Loading your work…"
        error={
          state.error ? { message: state.error.message, requestId: state.error.requestId } : null
        }
        errorTitle="Could not load your work"
        onRetry={reload}
        emptyTitle="Nothing here"
        emptyDescription="No activities match these filters."
        onRowActivate={(row) => setSelectedId(row.id)}
        caption="My work"
        densityStorageKey="grras.teaching-work-density"
      />
      {state.data ? (
        <Pagination
          page={state.data.page}
          totalPages={state.data.total_pages}
          count={state.data.count}
          pageSize={state.data.page_size}
          onPageChange={(page) => updateFilters({ page })}
        />
      ) : null}

      <ActivityDrawer
        activityId={selectedId}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
        onChanged={reload}
      />
    </div>
  );
}

export default function TeachingWorkPage() {
  return (
    <RequireAuth>
      <Suspense fallback={<LoadingState label="Loading your work…" rows={6} />}>
        <MyWorkWorkspace />
      </Suspense>
    </RequireAuth>
  );
}
