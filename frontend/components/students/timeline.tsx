'use client';

/**
 * A reusable, presentational timeline for one student (Phase 10, ADR-09).
 *
 * Purely a read model: it renders whatever `GET /students/{id}/timeline/`
 * returns and does no authorization work of its own — the endpoint already
 * scopes to "can this caller see this student". `kind` is open-ended (a
 * later phase can register a new source without touching this file), so
 * every entry renders through `timelineKindMeta`'s icon/label map with a
 * generic fallback rather than an exhaustive switch that would break on an
 * unrecognized kind.
 *
 * Not wired into a page of its own scope beyond the minimal host this phase
 * adds (`app/students/[id]/timeline/page.tsx`) — Phase 11 (Student 360)
 * embeds this component for real, the same way Phase 9 left
 * `field-renderer.tsx` ready without being that phase's whole deliverable.
 *
 * Pagination is "load more" over the API's `(occurred_at, id)` cursor,
 * matching this codebase's other cursor-shaped feeds rather than page
 * numbers (`app/activities/page.tsx`'s `Pagination` fits a `count`/`page`
 * envelope, which this endpoint does not return).
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { fallback, formatDate, formatRelative, NOT_AVAILABLE } from '@/lib/format';
import { timelineKindMeta } from '@/lib/labels';
import { getStudentTimeline } from '@/lib/timeline';
import type { TimelineEntry } from '@/types/api';

/** Shown as filter chips even before any entry of that kind has loaded —
 *  the point of a filter is to narrow a page you have not seen yet. New
 *  kinds outside this list are still rendered (see `timelineKindMeta`);
 *  they just do not get a chip of their own here. */
const FILTERABLE_KINDS = [
  'enrollment_started',
  'attendance_day',
  'dsr_submitted',
  'assessment_result',
  'assignment_submitted',
  'project_state_changed',
  'certificate_issued',
] as const;

const DEFAULT_PAGE_SIZE = 25;

interface TimelineState {
  key: string;
  entries: TimelineEntry[];
  nextCursor: string | null;
  isLoading: boolean;
  isLoadingMore: boolean;
  error: ApiError | null;
}

function toApiError(cause: unknown): ApiError {
  return cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The request failed.', '');
}

/** Groups already-sorted entries by calendar day, using the same locale
 *  formatting as the rest of the app so the group headings and each row's
 *  own timestamp never disagree. */
function groupByDay(entries: TimelineEntry[]): { label: string; entries: TimelineEntry[] }[] {
  const groups: { label: string; entries: TimelineEntry[] }[] = [];
  for (const entry of entries) {
    const label = formatDate(entry.occurred_at, NOT_AVAILABLE);
    const current = groups[groups.length - 1];
    if (current && current.label === label) {
      current.entries.push(entry);
    } else {
      groups.push({ label, entries: [entry] });
    }
  }
  return groups;
}

export function StudentTimeline({
  studentId,
  pageSize = DEFAULT_PAGE_SIZE,
}: {
  studentId: string;
  pageSize?: number;
}) {
  const [selectedKinds, setSelectedKinds] = useState<string[]>([]);
  const [reloadToken, setReloadToken] = useState(0);
  const key = `${studentId}#${selectedKinds.join(',')}#${reloadToken}`;

  const [state, setState] = useState<TimelineState>({
    key,
    entries: [],
    nextCursor: null,
    isLoading: true,
    isLoadingMore: false,
    error: null,
  });
  // A change in `key` (student, kind filter, or an explicit retry) starts a
  // fresh page from scratch; only `loadMore` appends to the current one.
  if (state.key !== key) {
    setState({ key, entries: [], nextCursor: null, isLoading: true, isLoadingMore: false, error: null });
  }

  useEffect(() => {
    let cancelled = false;
    getStudentTimeline(studentId, {
      kinds: selectedKinds.length > 0 ? selectedKinds : undefined,
      pageSize,
    })
      .then((response) => {
        if (cancelled) return;
        setState({
          key,
          entries: response.results,
          nextCursor: response.next_cursor,
          isLoading: false,
          isLoadingMore: false,
          error: null,
        });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setState({
          key,
          entries: [],
          nextCursor: null,
          isLoading: false,
          isLoadingMore: false,
          error: toApiError(cause),
        });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function toggleKind(kind: string) {
    setSelectedKinds((current) =>
      current.includes(kind) ? current.filter((value) => value !== kind) : [...current, kind],
    );
  }

  function retry() {
    setReloadToken((value) => value + 1);
  }

  function loadMore() {
    const cursor = state.nextCursor;
    if (!cursor || state.isLoadingMore) return;
    setState((current) => ({ ...current, isLoadingMore: true }));
    getStudentTimeline(studentId, {
      kinds: selectedKinds.length > 0 ? selectedKinds : undefined,
      pageSize,
      cursor,
    })
      .then((response) => {
        setState((current) => {
          if (current.key !== key) return current; // filters changed mid-flight
          const seen = new Set(current.entries.map((entry) => entry.id));
          const appended = response.results.filter((entry) => !seen.has(entry.id));
          return {
            ...current,
            entries: [...current.entries, ...appended],
            nextCursor: response.next_cursor,
            isLoadingMore: false,
          };
        });
      })
      .catch((cause: unknown) => {
        setState((current) => (current.key === key ? { ...current, isLoadingMore: false, error: toApiError(cause) } : current));
      });
  }

  const groups = groupByDay(state.entries);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by kind">
        {FILTERABLE_KINDS.map((kind) => {
          const meta = timelineKindMeta(kind);
          const Icon = meta.icon;
          const active = selectedKinds.includes(kind);
          return (
            <Button
              key={kind}
              type="button"
              size="sm"
              variant={active ? 'primary' : 'outline'}
              aria-pressed={active}
              onClick={() => toggleKind(kind)}
            >
              <Icon className="size-3.5" aria-hidden="true" />
              {meta.label}
            </Button>
          );
        })}
        {selectedKinds.length > 0 ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedKinds([])}>
            Clear filters
          </Button>
        ) : null}
      </div>

      {state.isLoading ? (
        <LoadingState label="Loading timeline…" rows={6} />
      ) : state.error ? (
        <ErrorState
          title="Could not load the timeline"
          message={state.error.message}
          requestId={state.error.requestId || undefined}
          onRetry={retry}
        />
      ) : state.entries.length === 0 ? (
        <EmptyState
          title="Nothing recorded yet"
          description={
            selectedKinds.length > 0
              ? 'No events of the selected kinds yet. Try clearing the filters.'
              : 'Once something happens for this student, it will show up here.'
          }
        />
      ) : (
        <>
          <ol className="space-y-6">
            {groups.map((group) => (
              <li key={group.label}>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {group.label}
                </p>
                <ul className="space-y-3 border-l border-border pl-4">
                  {group.entries.map((entry) => {
                    const meta = timelineKindMeta(entry.kind);
                    const Icon = meta.icon;
                    const title = fallback(entry.title, NOT_AVAILABLE);
                    return (
                      <li key={entry.id} className="relative" data-testid="timeline-entry">
                        <span className="absolute -left-[1.4rem] top-1 flex size-6 items-center justify-center rounded-full bg-muted text-muted-foreground">
                          <Icon className="size-3.5" aria-hidden="true" />
                        </span>
                        <div className="rounded-card border border-border p-3">
                          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                            <p className="font-medium">
                              {entry.href ? (
                                <Link href={entry.href} className="hover:underline">
                                  {title}
                                </Link>
                              ) : (
                                title
                              )}
                            </p>
                            <time
                              className="whitespace-nowrap text-xs text-muted-foreground"
                              dateTime={entry.occurred_at}
                              title={formatDate(entry.occurred_at)}
                            >
                              {formatRelative(entry.occurred_at)}
                            </time>
                          </div>
                          {entry.summary ? (
                            <p className="mt-1 text-sm text-muted-foreground">{entry.summary}</p>
                          ) : null}
                          <p className="mt-2 text-xs text-muted-foreground">
                            {meta.label}
                            {entry.actor ? ` · ${entry.actor.name}` : ''}
                          </p>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ol>
          {state.nextCursor ? (
            <div className="flex justify-center">
              <Button type="button" variant="outline" size="sm" onClick={loadMore} disabled={state.isLoadingMore}>
                {state.isLoadingMore ? 'Loading…' : 'Load more'}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
