'use client';

/**
 * A manager's oversight view of one trainer's own activity queue — the
 * "Work" tab on the trainer detail page.
 *
 * Reuses Phase 9's real activity list shape and `ActivityDrawer` wholesale
 * (`components/students/student-activities-tab.tsx` is the closest existing
 * example of this exact pattern, narrowed to one person's activities); this
 * is not a second, simplified activity view; the drawer a manager opens here
 * is the same one a trainer opens on their own queue, review panel included
 * — Phase 9's `activity.review` capability check inside the drawer already
 * decides who sees that panel, and the drawer's own self-review guard
 * already hides it from the performer, so nothing about "manager oversight"
 * needs its own logic here.
 *
 * `apps.work.access` has no trainer-id filter — activities are scoped by
 * `assigned_to` (a user), not by trainer profile — so this first resolves
 * the trainer's own user id (`getTrainer`, `TrainerProfile.user.id`) and
 * then reads `GET /activities/?assigned_to=<user id>`, the same endpoint and
 * filter `/activities` (Phase 9) already exposes; no new backend surface.
 */
import { useEffect, useState } from 'react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ActivityDrawer } from '@/components/work/activity-drawer';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/input';
import { Pagination } from '@/components/pagination';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { ACTIVITY_PRIORITY_LABEL, ACTIVITY_STATUS_LABEL, ACTIVITY_STATUS_VARIANT } from '@/lib/labels';
import { getTrainer } from '@/lib/people';
import { listActivities } from '@/lib/work';
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

interface ListState {
  key: string;
  userId: string | null;
  data: Paginated<Activity> | null;
  error: ApiError | null;
  isLoading: boolean;
}

export function TrainerWorkTab({ trainerId }: { trainerId: string }) {
  const [status, setStatus] = useState<'' | ActivityStatus>('');
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const key = `${trainerId}#${status}#${page}#${reloadToken}`;
  const [state, setState] = useState<ListState>({
    key,
    userId: null,
    data: null,
    error: null,
    isLoading: true,
  });
  if (state.key !== key) {
    setState({ key, userId: null, data: null, error: null, isLoading: true });
  }

  useEffect(() => {
    let cancelled = false;
    getTrainer(trainerId)
      .then((trainer) =>
        listActivities({ assigned_to: trainer.user.id, status: status || undefined, page }).then((data) => ({
          userId: trainer.user.id,
          data,
        })),
      )
      .then(({ userId, data }) => {
        if (!cancelled) setState({ key, userId, data, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error = cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The request failed.', '');
        setState({ key, userId: null, data: null, error, isLoading: false });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function reload() {
    setReloadToken((value) => value + 1);
  }

  if (state.isLoading) return <LoadingState label="Loading this trainer's activities…" rows={4} />;
  if (state.error) {
    return (
      <ErrorState
        title="Could not load this trainer's activities"
        message={state.error.message}
        requestId={state.error.requestId || undefined}
        onRetry={reload}
      />
    );
  }

  const rows = state.data?.results ?? [];

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
        <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>{ACTIVITY_STATUS_LABEL[row.status]}</Badge>
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <Select
          aria-label="Status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as '' | ActivityStatus);
            setPage(1);
          }}
          className="w-48"
        >
          <option value="">Every status</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {ACTIVITY_STATUS_LABEL[value]}
            </option>
          ))}
        </Select>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        emptyTitle="No activities match these filters"
        emptyDescription="Widen the filters, or check back once work is assigned to this trainer."
        onRowActivate={(row) => setSelectedId(row.id)}
        caption="Trainer activities"
        densityStorageKey="grras.trainer-work-density"
      />
      {state.data ? (
        <Pagination
          page={state.data.page}
          totalPages={state.data.total_pages}
          count={state.data.count}
          pageSize={state.data.page_size}
          onPageChange={setPage}
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
