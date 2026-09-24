'use client';

/**
 * The correction trail behind one attendance record — a small, on-demand
 * panel, not a screen of its own. `AttendanceRecord.was_corrected` already
 * tells a student or trainer that a mark changed since it was first taken;
 * this answers "changed how, and why", fetched only when asked for, because
 * most records were never corrected and most of the rest are never queried.
 *
 * Gated entirely server-side: `getAttendanceHistory` hits the same
 * authorization `GET /api/v1/attendance/{record_id}/` already enforces, so a
 * 404 here reads as "not found", same as anywhere else in this app — see
 * `ErrorState`.
 */
import { useState } from 'react';

import { ErrorState, LoadingState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { ATTENDANCE_STATUS_LABEL, formatDateTime } from '@/lib/academic-labels';
import { getAttendanceHistory } from '@/lib/academics';
import type { AttendanceCorrection } from '@/types/api';

export function AttendanceHistory({ recordId }: { recordId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [corrections, setCorrections] = useState<AttendanceCorrection[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function load() {
    setIsLoading(true);
    setError(null);
    getAttendanceHistory(recordId)
      .then((rows) => setCorrections(rows))
      .catch((cause: unknown) => setError(cause instanceof ApiError ? cause : null))
      .finally(() => setIsLoading(false));
  }

  function toggle() {
    const next = !isOpen;
    setIsOpen(next);
    if (next && corrections === null && !isLoading) load();
  }

  return (
    <div className="mt-1">
      <Button type="button" variant="ghost" size="sm" className="h-auto p-0 text-xs underline-offset-4 hover:underline" onClick={toggle}>
        {isOpen ? 'Hide history' : 'View history'}
      </Button>
      {isOpen ? (
        <div className="mt-1 rounded-card border border-line bg-sunken/30 p-2 text-xs">
          {isLoading ? <LoadingState label="Loading history…" rows={1} /> : null}
          {error ? (
            <ErrorState
              title="Could not load the history"
              message={error.message}
              requestId={error.requestId || undefined}
              onRetry={load}
            />
          ) : null}
          {!isLoading && !error && corrections ? (
            corrections.length === 0 ? (
              <p className="text-ink-muted">No corrections recorded.</p>
            ) : (
              <ul className="space-y-1.5">
                {corrections.map((correction) => (
                  <li key={correction.id}>
                    <span className="font-medium">
                      {ATTENDANCE_STATUS_LABEL[correction.from_status]} → {ATTENDANCE_STATUS_LABEL[correction.to_status]}
                    </span>{' '}
                    <span className="text-ink-muted">
                      by {correction.corrected_by_name ?? 'Unknown'} · {formatDateTime(correction.created_at)}
                    </span>
                    {correction.reason ? (
                      <p className="text-ink-muted">{correction.reason}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
