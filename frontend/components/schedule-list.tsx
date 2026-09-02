import { Clock, MapPin } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { WEEKDAY_LABEL, formatTime } from '@/lib/batch-labels';
import type { BatchSchedule } from '@/types/api';

/**
 * A batch's weekly timetable.
 *
 * Shared by the admin editor, the trainer view and the student batch page, so a
 * class looks the same wherever it appears.
 */
export function ScheduleList({
  schedules,
  emptyMessage = 'No classes scheduled yet.',
}: {
  schedules: BatchSchedule[];
  emptyMessage?: string;
}) {
  if (schedules.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }

  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {schedules.map((schedule) => (
        <li key={schedule.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
          <span className="w-24 shrink-0 font-medium">
            {schedule.weekday_label || WEEKDAY_LABEL[schedule.weekday]}
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="size-3.5" aria-hidden="true" />
            {formatTime(schedule.start_time)}–{formatTime(schedule.end_time)}
          </span>
          {schedule.location ? (
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <MapPin className="size-3.5" aria-hidden="true" />
              {schedule.location}
            </span>
          ) : null}
          {schedule.trainer_name ? (
            <span className="text-muted-foreground">{schedule.trainer_name}</span>
          ) : null}
          {!schedule.is_active ? <Badge variant="warning">Suspended</Badge> : null}
          <span className="ml-auto text-xs text-muted-foreground">
            {schedule.timezone_name}
          </span>
        </li>
      ))}
    </ul>
  );
}
