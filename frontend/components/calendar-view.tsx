'use client';

import { useEffect, useState } from 'react';
import { CalendarDays, Clock, MapPin } from 'lucide-react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { getCalendar } from '@/lib/batches';
import {
  EVENT_KIND_LABEL,
  formatEventDay,
  formatEventTime,
  isoDaysFromNow,
  isoToday,
} from '@/lib/batch-labels';
import type { CalendarEvent } from '@/types/api';

/**
 * The one calendar.
 *
 * It renders whatever the API returns without knowing what produced it, so when
 * assignment deadlines or exams are registered as event sources they appear
 * here with no change to this component.
 */
export function CalendarView({ days = 28 }: { days?: number }) {
  const [range, setRange] = useState({ start: isoToday(), end: isoDaysFromNow(days) });
  const [state, setState] = useState<{
    events: CalendarEvent[];
    error: ApiError | null;
    isLoading: boolean;
    key: string;
  }>({ events: [], error: null, isLoading: true, key: `${range.start}#${range.end}` });

  const key = `${range.start}#${range.end}`;
  if (state.key !== key) {
    setState({ events: [], error: null, isLoading: true, key });
  }

  useEffect(() => {
    let cancelled = false;
    getCalendar(range.start, range.end)
      .then((response) => {
        if (!cancelled) {
          setState({ events: response.events, error: null, isLoading: false, key });
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            events: [],
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            key,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [range.start, range.end, key]);

  function shift(offset: number) {
    const start = new Date(range.start);
    start.setDate(start.getDate() + offset);
    const end = new Date(start);
    end.setDate(end.getDate() + days);
    setRange({ start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) });
  }

  if (state.isLoading) return <LoadingState label="Loading your calendar…" rows={5} />;
  if (state.error) {
    return (
      <ErrorState
        title="Could not load the calendar"
        message={state.error.message}
        requestId={state.error.requestId || undefined}
      />
    );
  }

  // Grouped by day so the list reads as a diary rather than a flat feed.
  const byDay = new Map<string, CalendarEvent[]>();
  for (const event of state.events) {
    const day = event.start.slice(0, 10);
    byDay.set(day, [...(byDay.get(day) ?? []), event]);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {formatEventDay(range.start)} – {formatEventDay(range.end)}
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => shift(-days)}>
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRange({ start: isoToday(), end: isoDaysFromNow(days) })}
          >
            Today
          </Button>
          <Button variant="outline" size="sm" onClick={() => shift(days)}>
            Next
          </Button>
        </div>
      </div>

      {byDay.size === 0 ? (
        <EmptyState
          title="Nothing scheduled"
          description="No classes or milestones fall in this period."
        />
      ) : (
        <ol className="space-y-4">
          {[...byDay.entries()].map(([day, events]) => (
            <li key={day} className="space-y-2">
              <h3 className="flex items-center gap-2 text-sm font-medium">
                <CalendarDays className="size-4 text-muted-foreground" aria-hidden="true" />
                {formatEventDay(day)}
              </h3>
              <ul className="divide-y divide-border rounded-[var(--radius-card)] border border-border">
                {events.map((event, index) => (
                  <li
                    key={`${event.kind}-${event.start}-${index}`}
                    className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm"
                  >
                    <Badge variant={event.kind === 'class' ? 'success' : 'neutral'}>
                      {EVENT_KIND_LABEL[event.kind] ?? event.kind}
                    </Badge>
                    <span className="min-w-0 flex-1 truncate font-medium">{event.title}</span>
                    {event.all_day ? (
                      <span className="text-xs text-muted-foreground">All day</span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Clock className="size-3.5" aria-hidden="true" />
                        {formatEventTime(event.start)}
                        {event.end ? `–${formatEventTime(event.end)}` : ''}
                      </span>
                    )}
                    {event.location ? (
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <MapPin className="size-3.5" aria-hidden="true" />
                        {event.location}
                      </span>
                    ) : null}
                    {event.batch_code ? (
                      <span className="font-mono text-xs text-muted-foreground">
                        {event.batch_code}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
