'use client';

/**
 * Choosing a class — today's, or a backdated catch-up.
 *
 * This is the one picker for both cases, on purpose. The brief is explicit
 * that a trainer completing an old paper register "must not fight [the
 * screen] about the date" — the surest way to honour that is to make
 * "pick a different day" a plain field at the top of the same list a trainer
 * already sees for today, not a separate flow buried behind a link. Changing
 * the date re-queries `listSessions` for that day; the initial `today`
 * value never re-fetches, since the caller already has it.
 */
import { useEffect, useState } from 'react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { listSessions } from '@/lib/academics';
import { ApiError } from '@/lib/api';
import { SESSION_STATUS_LABEL, SESSION_STATUS_VARIANT } from '@/lib/academic-labels';
import { formatClassTime } from '@/lib/dsr';
import { fallback, NO_DATA } from '@/lib/format';
import type { ClassSession } from '@/types/api';

function SessionOption({ session, onSelect }: { session: ClassSession; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className="w-full rounded-[var(--radius-card)] border border-border bg-surface p-4 text-left transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={SESSION_STATUS_VARIANT[session.status]}>
            {SESSION_STATUS_LABEL[session.status]}
          </Badge>
          {session.attendance_taken_at ? <Badge variant="success">Register taken</Badge> : null}
          <span className="font-mono text-xs text-muted-foreground">{fallback(session.batch_code)}</span>
        </div>
        <p className="mt-1 font-medium">{fallback(session.topic || session.course_title, NO_DATA)}</p>
        <p className="text-sm text-muted-foreground">
          {formatClassTime(session.start_time)}–{formatClassTime(session.end_time)} ·{' '}
          {fallback(session.batch_name)}
        </p>
      </button>
    </li>
  );
}

export interface ClassPickerProps {
  todayIso: string;
  todaySessions: ClassSession[];
  isLoadingToday: boolean;
  todayError: ApiError | null;
  onRetryToday: () => void;
  onSelect: (session: ClassSession) => void;
}

export function ClassPicker({
  todayIso,
  todaySessions,
  isLoadingToday,
  todayError,
  onRetryToday,
  onSelect,
}: ClassPickerProps) {
  const [date, setDate] = useState(todayIso);
  const [attempt, setAttempt] = useState(0);
  const [customSessions, setCustomSessions] = useState<ClassSession[] | null>(null);
  const [isLoadingCustom, setIsLoadingCustom] = useState(false);
  const [customError, setCustomError] = useState<ApiError | null>(null);

  const onTodayDate = date === todayIso;

  // The loading/error reset happens in the two event handlers below (the
  // date field changing, or the retry button), not synchronously at the top
  // of this effect — the same "adjust state in response to an event, not
  // inside the effect" shape `hooks/use-api.ts` uses for its own fetch.
  useEffect(() => {
    if (onTodayDate) return;
    let cancelled = false;
    listSessions({ date_from: date, date_to: date, ordering: 'start_time' })
      .then((page) => {
        if (!cancelled) setCustomSessions(page.results);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setCustomError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingCustom(false);
      });
    return () => {
      cancelled = true;
    };
  }, [date, onTodayDate, attempt]);

  function changeDate(value: string) {
    const next = value || todayIso;
    setDate(next);
    if (next !== todayIso) {
      setIsLoadingCustom(true);
      setCustomError(null);
    }
  }

  const sessions = onTodayDate ? todaySessions : (customSessions ?? []);
  const isLoading = onTodayDate ? isLoadingToday : isLoadingCustom;
  const error = onTodayDate ? todayError : customError;
  const retry = onTodayDate
    ? onRetryToday
    : () => {
        setIsLoadingCustom(true);
        setCustomError(null);
        setAttempt((value) => value + 1);
      };

  return (
    <div className="space-y-4">
      <Field label="Date" htmlFor="class-picker-date" hint="Today by default — pick another day to catch up on an earlier class.">
        <Input type="date" value={date} max={todayIso} onChange={(event) => changeDate(event.target.value)} />
      </Field>

      {isLoading ? (
        <LoadingState label="Loading classes…" rows={3} />
      ) : error ? (
        <ErrorState
          title="Could not load classes"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={retry}
        />
      ) : sessions.length === 0 ? (
        <EmptyState
          title={onTodayDate ? 'No classes today' : 'No classes on this date'}
          description="Nothing is scheduled on the batches you teach for this day."
        />
      ) : (
        <ul className="space-y-2">
          {sessions.map((session) => (
            <SessionOption key={session.id} session={session} onSelect={() => onSelect(session)} />
          ))}
        </ul>
      )}
    </div>
  );
}
