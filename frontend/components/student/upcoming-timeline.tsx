/**
 * "What's coming" — the second half of the top-of-page priority pair (the
 * first half is `pending-work-panel.tsx`).
 *
 * The backend's `/api/v1/dashboard/student/` already returns a *mixed* feed
 * under the key `upcoming_classes` — despite the name, `StudentDashboardView`
 * builds it from every calendar source (`apps/dashboards/calendar.py`), so a
 * due assignment or an exam sits in the same list as an actual class. That is
 * reused as-is here rather than fetching `/api/v1/calendar/` separately: the
 * backend already curated it down to five items over the next week (see
 * `RECENT_LIMIT` in that view), and re-deriving a second, longer version would
 * fight the same "don't show a wall of everything" reasoning this dashboard
 * is built around.
 *
 * `CalendarEventKind` in `types/api.ts` is missing `'project_due'` — the
 * backend's own `EventKind.PROJECT_DUE` (`apps/dashboards/calendar.py`) is a
 * real value `project_events()` emits, just never folded into that union. The
 * icon/label lookup below is keyed by plain `string`, not that type, and
 * falls back to a generic marker for anything it does not recognise —
 * including that gap — rather than trusting the union is complete.
 */
import type { LucideIcon } from 'lucide-react';
import {
  CalendarDays,
  ClipboardList,
  FileQuestion,
  FlagTriangleRight,
  GraduationCap,
  Megaphone,
  PlayCircle,
  Rocket,
} from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { formatEventDay, formatEventTime } from '@/lib/batch-labels';
import type { CalendarEvent } from '@/types/api';

const KIND_META: Record<string, { label: string; Icon: LucideIcon }> = {
  class: { label: 'Class', Icon: CalendarDays },
  batch_start: { label: 'Batch starts', Icon: PlayCircle },
  course_start: { label: 'Course starts', Icon: PlayCircle },
  batch_end: { label: 'Batch ends', Icon: FlagTriangleRight },
  course_end: { label: 'Course ends', Icon: FlagTriangleRight },
  assignment_due: { label: 'Assignment due', Icon: ClipboardList },
  project_due: { label: 'Project due', Icon: Rocket },
  quiz: { label: 'Test', Icon: FileQuestion },
  exam: { label: 'Exam', Icon: GraduationCap },
  announcement: { label: 'Announcement', Icon: Megaphone },
};
const DEFAULT_KIND_META = { label: 'Event', Icon: CalendarDays };

export function UpcomingTimeline({
  events,
  isLoading,
  error,
  onRetry,
}: {
  events: CalendarEvent[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading what's coming up…" rows={3} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  if (events.length === 0) {
    return (
      <p className="rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        Nothing on your calendar for the next week.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {events.map((event, index) => {
        const meta = KIND_META[event.kind] ?? DEFAULT_KIND_META;
        const Icon = meta.Icon;
        return (
          <li key={`${event.kind}-${event.start}-${index}`} className="flex items-start gap-3 py-2.5">
            <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{event.title || meta.label}</p>
              <p className="text-xs text-muted-foreground">
                {meta.label} · {formatEventDay(event.start)}
                {!event.all_day ? ` · ${formatEventTime(event.start)}` : ''}
                {event.location ? ` · ${event.location}` : ''}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
