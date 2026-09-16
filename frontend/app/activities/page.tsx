"use client";

/**
 * The activity work list: every trainer's, counsellor's and manager's own
 * queue of interviews, mentoring, reviews and the rest, filterable by
 * status, type, assignee, "mine" and overdue.
 *
 * Route `/activities`, top-level rather than under `/admin` or `/manage`:
 * this app already keeps a cross-role working screen there when several
 * roles share it with the server doing the scoping (`/dsr`, `/calendar`),
 * reserving `/admin/*` for administrator-only configuration. `activity
 * .view_any` is held by every staff role in `PERMISSION_CATALOG.md`
 * (trainer/counsellor scoped to "assigned"), so the same route serves all of
 * them; the backend's queryset — not this route — decides what each of them
 * actually sees.
 */

import { useEffect, useState } from "react";

import { RequireAuth } from "@/components/require-auth";
import { ActivityDrawer } from "@/components/work/activity-drawer";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, Select } from "@/components/ui/input";
import { Pagination } from "@/components/pagination";
import { Table, TableWrapper, Td, Th, Tr } from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { categoryVariant } from "@/components/ui/badge";
import { Capability } from "@/lib/capabilities";
import { formatDateTime, NOT_ASSIGNED } from "@/lib/format";
import {
  ACTIVITY_PRIORITY_LABEL,
  ACTIVITY_STATUS_LABEL,
  ACTIVITY_STATUS_VARIANT,
} from "@/lib/labels";
import { listActivities, listActivityTypes } from "@/lib/work";
import type { Activity, ActivityStatus, ActivityType, Paginated } from "@/types/api";

const STATUSES: ActivityStatus[] = [
  "draft",
  "planned",
  "assigned",
  "in_progress",
  "completed",
  "missed",
  "overdue",
  "cancelled",
  "reopened",
  "under_review",
  "approved",
  "requires_action",
];

interface Filters {
  status: "" | ActivityStatus;
  type: string;
  assignedTo: string;
  mine: boolean;
  overdue: boolean;
  page: number;
}

const DEFAULT_FILTERS: Filters = {
  status: "",
  type: "",
  assignedTo: "",
  mine: false,
  overdue: false,
  page: 1,
};

interface ListState {
  key: string;
  data: Paginated<Activity> | null;
  error: ApiError | null;
  isLoading: boolean;
}

function ActivitiesWorkspace() {
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
        // the list below, which still works with `type` left blank.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [reloadToken, setReloadToken] = useState(0);
  // `reloadToken` is part of the request identity, not just an effect
  // dependency: a reload with unchanged filters must still reset `isLoading`
  // to true, which only happens when the key itself changes (mirrors
  // `hooks/use-api.ts`'s `requestKey`).
  const key = `${JSON.stringify(filters)}#${reloadToken}`;
  const [state, setState] = useState<ListState>({
    key,
    data: null,
    error: null,
    isLoading: true,
  });
  if (state.key !== key) {
    setState({ key, data: null, error: null, isLoading: true });
  }

  useEffect(() => {
    let cancelled = false;
    listActivities({
      status: filters.status || undefined,
      type: filters.type || undefined,
      assigned_to: filters.assignedTo.trim() || undefined,
      mine: filters.mine ? 1 : undefined,
      overdue: filters.overdue ? 1 : undefined,
      page: filters.page,
    })
      .then((data) => {
        if (!cancelled) setState({ key, data, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const error =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, "unknown_error", "The request failed.", "");
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
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Activities</h1>
        <p className="text-sm text-muted-foreground">
          Interviews, mentoring, reviews, placement calls and the rest of the work assigned
          across the institution.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <Select
          aria-label="Status"
          value={filters.status}
          onChange={(event) =>
            updateFilters({ status: event.target.value as "" | ActivityStatus })
          }
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
        <Input
          aria-label="Assigned to (user id)"
          placeholder="Assigned to (user id)"
          value={filters.assignedTo}
          onChange={(event) => updateFilters({ assignedTo: event.target.value })}
          className="w-56"
        />
        {/* `Checkbox` renders its own wrapping `<label>`; a second `<label>`
            around it here would nest labels invalidly, so the visible text
            sits beside it as a sibling instead, and `aria-label` carries the
            accessible name. */}
        <div className="flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm">
          <Checkbox
            aria-label="Mine"
            checked={filters.mine}
            onCheckedChange={(checked) => updateFilters({ mine: Boolean(checked) })}
          />
          <span>Mine</span>
        </div>
        <div className="flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm">
          <Checkbox
            aria-label="Overdue"
            checked={filters.overdue}
            onCheckedChange={(checked) => updateFilters({ overdue: Boolean(checked) })}
          />
          <span>Overdue</span>
        </div>
        {filters.status || filters.type || filters.assignedTo || filters.mine || filters.overdue ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => setFilters(DEFAULT_FILTERS)}>
            Clear filters
          </Button>
        ) : null}
      </div>

      {state.isLoading ? (
        <LoadingState label="Loading activities…" rows={6} />
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
          description="Widen the filters, or check back once work is assigned."
        />
      ) : (
        <>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Title</Th>
                  <Th>Student</Th>
                  <Th>Type</Th>
                  <Th>Status</Th>
                  <Th>Priority</Th>
                  <Th>Assigned to</Th>
                  <Th>Due</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <Tr
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedId(row.id)}
                  >
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
                      {row.student.name}
                      <span className="block text-xs text-muted-foreground">
                        {row.student.student_id}
                      </span>
                    </Td>
                    <Td>
                      <Badge variant={categoryVariant(row.type.category)}>
                        {row.type.name}
                      </Badge>
                    </Td>
                    <Td>
                      <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>
                        {ACTIVITY_STATUS_LABEL[row.status]}
                      </Badge>
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

export default function ActivitiesPage() {
  return (
    <RequireAuth capability={Capability.activityViewAny} roles={["trainer"]}>
      <ActivitiesWorkspace />
    </RequireAuth>
  );
}
