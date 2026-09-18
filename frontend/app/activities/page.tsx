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
 *
 * Saved filters (ERP Phase 11, DATA_MODEL.md `SavedFilter`,
 * DESIGN_DECISIONS.md "Search and saved filters"): this is the one screen
 * that wires the server-side saved-filter API to a real filter bar, and the
 * one place `useUnsavedChanges` (DESIGN_DECISIONS.md "Unsaved-changes
 * guard") guards a genuine uncommitted edit — the name typed into the "Save
 * this filter" popover before Save is clicked. Applying a saved filter is a
 * safe, reversible read (it only ever sets local filter state, matching
 * "Caching UX and optimistic UI"'s bar for what may update without a round
 * trip), so recall does not go through the guard; only losing an
 * *unsubmitted name* does.
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Bookmark } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { RequireAuth } from "@/components/require-auth";
import { ActivityDrawer } from "@/components/work/activity-drawer";
import { Confirm } from "@/components/confirm";
import { LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Pagination } from "@/components/pagination";
import { Popover, PopoverContent, PopoverHeading, PopoverTrigger } from "@/components/ui/popover";
import { ApiError } from "@/lib/api";
import { categoryVariant } from "@/components/ui/badge";
import { Capability } from "@/lib/capabilities";
import { formatDateTime, NOT_ASSIGNED } from "@/lib/format";
import {
  ACTIVITY_PRIORITY_LABEL,
  ACTIVITY_STATUS_LABEL,
  ACTIVITY_STATUS_VARIANT,
} from "@/lib/labels";
import { createSavedFilter, deleteSavedFilter, listSavedFilters } from "@/lib/saved-filters";
import { useUnsavedChanges } from "@/hooks/use-unsaved-changes";
import { listActivities, listActivityTypes } from "@/lib/work";
import type { Activity, ActivityStatus, ActivityType, Paginated, SavedFilter } from "@/types/api";

const SAVED_FILTER_SCREEN = "activities";

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

/** `SavedFilter.filters` round-trips opaquely (`lib/saved-filters.ts`) — a
 *  preset saved before a filter was added, or edited by hand through the
 *  API, is untrusted input here, so every field is re-validated against this
 *  screen's own vocabulary rather than cast straight to `Filters`. Anything
 *  unrecognised falls back to its default instead of reaching the UI as
 *  `undefined`. */
function parseSavedActivityFilters(raw: Record<string, unknown>): Filters {
  const status = typeof raw.status === "string" && (STATUSES as string[]).includes(raw.status) ? (raw.status as ActivityStatus) : "";
  return {
    status,
    type: typeof raw.type === "string" ? raw.type : "",
    assignedTo: typeof raw.assignedTo === "string" ? raw.assignedTo : "",
    mine: raw.mine === true,
    overdue: raw.overdue === true,
    page: 1,
  };
}

interface ListState {
  key: string;
  data: Paginated<Activity> | null;
  error: ApiError | null;
  isLoading: boolean;
}

/**
 * The dashboard's `activities.under_review` tile (and any other future
 * link into this screen) opens `/activities?status=under_review` — a plain
 * status filter is the one URL entry point this screen supports on load,
 * matching `?attention=…` on the batches/trainers hubs
 * (`app/manage/trainers/page.tsx`). Anything not in this screen's own
 * `STATUSES` vocabulary is ignored rather than reaching `listActivities` as
 * an unvalidated string, the same rule `parseSavedActivityFilters` already
 * applies to a saved filter's `status`.
 */
function initialFiltersFromParams(params: URLSearchParams): Filters {
  const status = params.get("status");
  return {
    ...DEFAULT_FILTERS,
    status: status && (STATUSES as string[]).includes(status) ? (status as ActivityStatus) : "",
  };
}

function ActivitiesWorkspace() {
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => initialFiltersFromParams(searchParams));
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

  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [selectedSavedFilterId, setSelectedSavedFilterId] = useState("");

  useEffect(() => {
    let cancelled = false;
    listSavedFilters(SAVED_FILTER_SCREEN)
      .then((rows) => {
        if (!cancelled) setSavedFilters(rows);
      })
      .catch(() => {
        // The saved-filters list is a convenience; its own failure does not
        // block the activity list below.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function applySavedFilter(id: string) {
    setSelectedSavedFilterId(id);
    if (!id) {
      setFilters(DEFAULT_FILTERS);
      return;
    }
    const saved = savedFilters.find((row) => row.id === id);
    if (saved) setFilters(parseSavedActivityFilters(saved.filters));
  }

  async function removeSavedFilter(id: string) {
    setSavedFilters((current) => current.filter((row) => row.id !== id));
    if (selectedSavedFilterId === id) setSelectedSavedFilterId("");
    try {
      await deleteSavedFilter(id);
    } catch {
      // Best-effort: a failed delete leaves the preset usable again on the
      // next load, which is a safer failure than an error banner over a
      // screen whose primary purpose is the activity list, not this row.
    }
  }

  // "Save this filter" — the one uncommitted edit on this screen worth
  // guarding: a name typed but not yet saved (DESIGN_DECISIONS.md
  // "Unsaved-changes guard"). Recalling or clearing a filter is always safe
  // and reversible, so nothing else here goes through the guard.
  const [savePopoverOpen, setSavePopoverOpen] = useState(false);
  const [filterName, setFilterName] = useState("");
  const [isSavingFilter, setIsSavingFilter] = useState(false);
  const [saveFilterError, setSaveFilterError] = useState("");
  const { isPrompting, guard, confirmDiscard, cancelDiscard } = useUnsavedChanges(
    savePopoverOpen && filterName.trim().length > 0,
  );

  function resetSaveFilterPopover() {
    setSavePopoverOpen(false);
    setFilterName("");
    setSaveFilterError("");
  }

  function requestCloseSaveFilterPopover() {
    guard(resetSaveFilterPopover);
  }

  async function saveCurrentFilter() {
    const name = filterName.trim();
    if (!name) return;
    setIsSavingFilter(true);
    setSaveFilterError("");
    try {
      const created = await createSavedFilter({
        screen: SAVED_FILTER_SCREEN,
        name,
        filters: filters as unknown as Record<string, unknown>,
      });
      setSavedFilters((current) => [...current.filter((row) => row.name !== created.name), created]);
      setSelectedSavedFilterId(created.id);
      resetSaveFilterPopover();
    } catch (cause: unknown) {
      setSaveFilterError(cause instanceof ApiError ? cause.message : "Could not save this filter.");
    } finally {
      setIsSavingFilter(false);
    }
  }

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

  const columns: DataTableColumn<Activity>[] = [
    {
      key: "title",
      header: "Title",
      sticky: "start",
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
      key: "student",
      header: "Student",
      render: (row) => (
        <>
          {row.student.name}
          <span className="block text-xs text-muted-foreground">{row.student.student_id}</span>
        </>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (row) => (
        <Badge variant={categoryVariant(row.type.category)}>{row.type.name}</Badge>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>
          {ACTIVITY_STATUS_LABEL[row.status]}
        </Badge>
      ),
    },
    { key: "priority", header: "Priority", render: (row) => ACTIVITY_PRIORITY_LABEL[row.priority] },
    {
      key: "assigned_to",
      header: "Assigned to",
      render: (row) => (row.assigned_to ? row.assigned_to.name : NOT_ASSIGNED),
    },
    {
      key: "due_at",
      header: "Due",
      render: (row) => <span className="whitespace-nowrap">{formatDateTime(row.due_at)}</span>,
    },
  ];

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

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Select
          aria-label="Saved filters"
          value={selectedSavedFilterId}
          onChange={(event) => applySavedFilter(event.target.value)}
          className="w-56"
        >
          <option value="">Saved filters…</option>
          {savedFilters.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </Select>
        {selectedSavedFilterId ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => removeSavedFilter(selectedSavedFilterId)}>
            Remove
          </Button>
        ) : null}
        <Popover
          open={savePopoverOpen}
          onOpenChange={(open) => (open ? setSavePopoverOpen(true) : requestCloseSaveFilterPopover())}
        >
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" size="sm">
              <Bookmark className="size-3.5" aria-hidden="true" />
              Save this filter
            </Button>
          </PopoverTrigger>
          <PopoverContent>
            <PopoverHeading>Save this filter</PopoverHeading>
            <Field label="Name" htmlFor="save-activity-filter-name" error={saveFilterError || undefined}>
              <Input
                id="save-activity-filter-name"
                autoFocus
                value={filterName}
                onChange={(event) => setFilterName(event.target.value)}
                placeholder="e.g. My overdue reviews"
              />
            </Field>
            <div className="mt-3 flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={requestCloseSaveFilterPopover}>
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={saveCurrentFilter}
                disabled={!filterName.trim() || isSavingFilter}
              >
                {isSavingFilter ? "Saving…" : "Save"}
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <Confirm
        open={isPrompting}
        title="Discard this filter name?"
        description="You typed a name for a saved filter but have not saved it yet."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={confirmDiscard}
        onCancel={cancelDiscard}
      />

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        isLoading={state.isLoading}
        loadingLabel="Loading activities…"
        error={state.error ? { message: state.error.message, requestId: state.error.requestId } : null}
        errorTitle="Could not load activities"
        onRetry={reload}
        emptyTitle="No activities match these filters"
        emptyDescription="Widen the filters, or check back once work is assigned."
        onRowActivate={(row) => setSelectedId(row.id)}
        caption="Activities"
        densityStorageKey="grras.activities-density"
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

export default function ActivitiesPage() {
  return (
    <RequireAuth capability={Capability.activityViewAny} roles={["trainer"]}>
      <Suspense fallback={<LoadingState label="Loading activities…" rows={6} />}>
        <ActivitiesWorkspace />
      </Suspense>
    </RequireAuth>
  );
}
