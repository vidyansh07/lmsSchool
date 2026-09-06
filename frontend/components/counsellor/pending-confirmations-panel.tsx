/**
 * Enrolments sitting in `pending`, waiting for a counsellor to move them to
 * `active` (or cancel them) — see `EnrollmentStatus` and the transition table
 * in `apps/enrollments/services.py`. `status=pending` is a real, exact
 * server-side filter (`EnrollmentFilterSet`), unlike the recent-window
 * approximations elsewhere on this dashboard, so the count here is precise
 * even though the list beneath it is capped to a page.
 */
import { AlertList, type AlertItem } from '@/components/alert-list';
import { ErrorState, LoadingState } from '@/components/states';
import { formatName } from '@/lib/format';
import type { Enrollment } from '@/types/api';

export function PendingConfirmationsPanel({
  enrollments,
  totalCount,
  isLoading,
  error,
  onRetry,
}: {
  enrollments: Enrollment[];
  /** The exact total matching `status=pending` — may exceed `enrollments.length`. */
  totalCount: number;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading pending confirmations…" rows={3} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load pending confirmations"
        message={error.message}
        requestId={error.requestId}
        onRetry={onRetry}
      />
    );
  }

  const items: AlertItem[] = enrollments.map((entry) => ({
    id: entry.id,
    severity: 'warning',
    title: formatName({ full_name: entry.student_name, email: entry.student_email }),
    description: `${entry.course_title || 'Course not available'} · ${entry.batch_name || 'Batch not available'}`,
    href: entry.student_id ? `/admissions/${entry.student_id}` : undefined,
  }));

  return (
    <div className="space-y-2">
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {totalCount} awaiting confirmation.
      </p>
      <AlertList
        items={items}
        title="pending confirmations"
        emptyTitle="Nothing pending"
        emptyDescription="Every enrolment created recently has already been confirmed."
      />
    </div>
  );
}
