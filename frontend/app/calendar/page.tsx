'use client';

import { CalendarView } from '@/components/calendar-view';
import { RequireAuth } from '@/components/require-auth';

export default function CalendarPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Your classes and batch milestones. Only what you are part of appears here.
          </p>
        </div>
        <CalendarView />
      </div>
    </RequireAuth>
  );
}
