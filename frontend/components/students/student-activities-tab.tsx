'use client';

/**
 * Purpose: one student's activity queue, embedded in the Student 360 page's
 * Activities tab. User: any staff role that can see the student. Primary
 * action: open an activity (`ActivityDrawer`, Phase 9). Secondary actions:
 * filter by status/type/overdue. API on load: `GET
 * /students/{id}/activities/` (`lib/work.ts::listStudentActivities`). State
 * model: loading, empty, error, success — no separate "denied", the tab only
 * renders once the 360 page itself already passed its own capability check.
 * Mobile: the table scrolls horizontally inside `TableWrapper`, same as
 * every other list in this app.
 *
 * There is no existing reusable "activities list" component to embed:
 * `app/activities/page.tsx` (Phase 9) is a whole page, not a component, and
 * its own filter bar has no student scope in its UI even though the API
 * (`listStudentActivities`) supports one. This is that same shape — the
 * table, `ActivityDrawer`, `lib/work.ts`, `lib/labels.ts` — narrowed to one
 * student and a shorter filter set (status, type, overdue; "assigned to" and
 * "mine" do not mean anything once the list is already scoped to a single
 * student's own record).
 */
import { useEffect, useState } from 'react';

import { ActivityDrawer } from '@/components/work/activity-drawer';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge, categoryVariant } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Select } from '@/components/ui/input';
import { Pagination } from '@/components/pagination';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import { formatDateTime, NOT_ASSIGNED } from '@/lib/format';
import { ACTIVITY_PRIORITY_LABEL, ACTIVITY_STATUS_LABEL, ACTIVITY_STATUS_VARIANT } from '@/lib/labels';
import { listActivityTypes, listStudentActivities } from '@/lib/work';
import type { Activity, ActivityStatus, ActivityType, Paginated } from '@/types/api';

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
  type: string;
  overdue: boolean;
  page: number;
}

const DEFAULT_FILTERS: Filters = { status: '', type: '', overdue: false, page: 1 };

interface ListState {
  key: string;
  data: Paginated<Activity> | null;
  error: ApiError | null;
  isLoading: boolean;
}

export function StudentActivitiesTab({ studentId }: { studentId: string }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [types, setTypes] = useState<ActivityType[]>([]);

  useEffect(() => {
    let cancelled = false;
    listActivityTypes()
      .then((response) => {
        if (!cancelled) setTypes(response.results);
      })
      .catch(() => {
        // The type filter is a convenience; its own failure does not block
        // the list below.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [reloadToken, setReloadToken] = useState(0);
  const key = `${studentId}#${JSON.stringify(filters)}#${reloadToken}`;
  const [state, setState] = useState<ListState>({ key, data: null, error: null, isLoading: true });
  if (state.key !== key) {
    setState({ key, data: null, error: null, isLoading: true });
  }

  useEffect(() => {
    let cancelled = false;
    listStudentActivities(studentId, {
      status: filters.status || undefined,
      type: filters.type || undefined,
      overdue: filters.overdue ? 1 : undefined,
      page: filters.page,
    })
      .then((data) => {
        if (!cancelled) setState({ key, data, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error = cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The request failed.', '');
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
    setFilters((current) => ({ ...current, ...patch, page: patch.page ?? 1 }));
  }

  const rows = state.data?.results ?? [];

  return (
    <div className="space-y-4">
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
        <Select
          aria-label="Type"
          value={filters.type}
          onChange={(event) => updateFilters({ type: event.target.value })}
          className="w-48"
        >
          <option value="">Every type</option>
          {types.map((type) => (
            <option key={type.slug} value={type.slug}>
              {type.name}
            </option>
          ))}
        </Select>
        <div className="flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm">
          <Checkbox
            aria-label="Overdue"
            checked={filters.overdue}
            onCheckedChange={(checked) => updateFilters({ overdue: Boolean(checked) })}
          />
          <span>Overdue</span>
        </div>
        {filters.status || filters.type || filters.overdue ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => setFilters(DEFAULT_FILTERS)}>
            Clear filters
          </Button>
        ) : null}
      </div>

      {state.isLoading ? (
        <LoadingState label="Loading activities…" rows={4} />
      ) : state.error ? (
        <ErrorState
          title="Could not load activities"
          message={state.error.message}
          requestId={state.error.requestId || undefined}
          onRetry={reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No activities match these filters"
          description="Widen the filters, or check back once work is assigned to this student."
        />
      ) : (
        <>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Title</Th>
                  <Th>Type</Th>
                  <Th>Status</Th>
                  <Th>Priority</Th>
                  <Th>Assigned to</Th>
                  <Th>Due</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <Tr key={row.id} className="cursor-pointer" onClick={() => setSelectedId(row.id)}>
                    <Td>
                      <button
                        type="button"
                        className="text-left font-medium underline-offset-2 hover:underline"
                        onClick={() => setSelectedId(row.id)}
                      >
                        {row.title}
                      </button>
                    </Td>
                    <Td>
                      <Badge variant={categoryVariant(row.type.category)}>{row.type.name}</Badge>
                    </Td>
                    <Td>
                      <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>{ACTIVITY_STATUS_LABEL[row.status]}</Badge>
                    </Td>
                    <Td>{ACTIVITY_PRIORITY_LABEL[row.priority]}</Td>
                    <Td>{row.assigned_to ? row.assigned_to.name : NOT_ASSIGNED}</Td>
                    <Td className="whitespace-nowrap">{formatDateTime(row.due_at)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
          {state.data ? (
            <Pagination
              page={state.data.page}
              totalPages={state.data.total_pages}
              count={state.data.count}
              pageSize={state.data.page_size}
              onPageChange={(page) => updateFilters({ page })}
            />
          ) : null}
        </>
      )}

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
