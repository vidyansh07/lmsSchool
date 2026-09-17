'use client';

/**
 * A trainer's own activities due today, shown alongside the register/DSR on
 * `/teaching/today` (ERP Phase 16). Fetched from `GET /me/activities/`
 * (`lib/work.ts`'s `listMyActivities`) rather than the dashboard's new
 * `today_activities` field, because this page never fetches the trainer
 * dashboard payload in the first place — pulling it in just for this one
 * field would add a whole second dashboard round trip in place of the one
 * dedicated request the Phase 9 endpoint already offers.
 *
 * Row click opens the caller's existing detail drawer
 * (`components/work/activity-drawer.tsx`) — this panel never owns a second
 * one, only the selected id, via `onSelect`.
 */

import { useEffect, useState } from 'react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { ACTIVITY_STATUS_LABEL, ACTIVITY_STATUS_VARIANT } from '@/lib/labels';
import { listMyActivities } from '@/lib/work';
import type { Activity } from '@/types/api';

function endOfTodayIso(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999).toISOString();
}

interface State {
  attempt: number;
  data: Activity[] | null;
  error: ApiError | null;
  isLoading: boolean;
}

export function TodayActivitiesPanel({
  onSelect,
  reloadToken = 0,
}: {
  onSelect: (activityId: string) => void;
  /** Bumped by the caller after a drawer mutation (a transition, a
   *  completion) so this list reflects it without owning that logic itself. */
  reloadToken?: number;
}) {
  const [retryCount, setRetryCount] = useState(0);
  const attempt = reloadToken * 1000 + retryCount;
  const [state, setState] = useState<State>({ attempt, data: null, error: null, isLoading: true });
  if (state.attempt !== attempt) {
    setState({ attempt, data: null, error: null, isLoading: true });
  }

  useEffect(() => {
    let cancelled = false;
    listMyActivities({ due_before: endOfTodayIso(), ordering: 'due_at', page_size: 50 })
      .then((page) => {
        if (!cancelled) setState({ attempt, data: page.results, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            attempt,
            data: null,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your activities due today</CardTitle>
        <CardDescription>Interviews, mentoring and reviews due before the day ends.</CardDescription>
      </CardHeader>
      <CardContent>
        {state.isLoading ? (
          <LoadingState label="Loading your activities…" rows={3} />
        ) : state.error ? (
          <ErrorState
            title="Could not load your activities"
            message={state.error.message}
            requestId={state.error.requestId || undefined}
            onRetry={() => setRetryCount((value) => value + 1)}
          />
        ) : !state.data || state.data.length === 0 ? (
          <EmptyState
            title="Nothing due today"
            description="None of your activities are due before the day ends."
          />
        ) : (
          <ul className="divide-y divide-border">
            {state.data.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="flex w-full flex-wrap items-center gap-3 py-2 text-left text-sm hover:text-primary"
                  onClick={() => onSelect(row.id)}
                >
                  <span className="min-w-0 flex-1 truncate font-medium">{row.title}</span>
                  <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>
                    {ACTIVITY_STATUS_LABEL[row.status]}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{row.student.name}</span>
                  <span className="whitespace-nowrap text-xs text-muted-foreground">
                    {formatDateTime(row.due_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
