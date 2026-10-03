/**
 * "Registered, not yet enrolled" — the gap that costs money, per the brief
 * this component exists to satisfy: every day a registered student sits
 * without a batch is a day they might go elsewhere.
 *
 * It used to answer that question in the browser, because there was no backend
 * query for it: the page fetched the thirty most recent registrations and a
 * page of the hundred most recent enrolments, and this module asked "does this
 * student's code appear in that page". The two windows are ordered by
 * different columns — `created_at` on one side, `enrolled_at` on the other —
 * and need not overlap at all. On real data they did not: the panel listed
 * fifteen students who every one of them had an active enrolment, next to a
 * tile on the same screen that said 1.
 *
 * So the question now goes to the server that can answer it —
 * `/api/v1/students/?awaiting_enrolment=true`, which is
 * `apps.students.access.awaiting_enrolment`, the same definition the
 * "Unassigned batch" tile counts and the `not_enrolled` warning fires on. This
 * component renders rows and a server-reported total; it computes nothing, so
 * there is nothing left here to disagree with.
 *
 * "Not yet enrolled" means *holding no seat on any batch*: a student whose only
 * enrolment was cancelled, or who was transferred off a batch and never placed
 * on another, is in this list. That is the point — they are registered and have
 * nowhere to sit.
 */
import Link from 'next/link';

import { AlertList, type AlertItem } from '@/components/alert-list';
import { ErrorState, LoadingState } from '@/components/states';
import { formatName, formatRelative } from '@/lib/format';
import type { StudentListRow } from '@/types/api';

export function NotYetEnrolledPanel({
  students,
  totalCount,
  isLoading,
  error,
  onRetry,
}: {
  /** The page of rows fetched — newest registration first. */
  students: StudentListRow[];
  /** Every student awaiting a seat, not just the ones listed: the count comes
   *  from the server's own `count`, so a capped list never understates the
   *  problem. */
  totalCount: number;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Checking recent registrations…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not check recent registrations"
        message={error.message}
        requestId={error.requestId}
        onRetry={onRetry}
      />
    );
  }

  const items: AlertItem[] = students.map((student) => ({
    id: student.id,
    severity: 'warning',
    title: formatName({ full_name: student.full_name, email: student.email }),
    description: `Registered ${formatRelative(student.created_at)} · ${student.student_id || 'no student code yet'}`,
    href: `/admissions/${student.id}`,
  }));

  return (
    <div className="space-y-2">
      <p aria-live="polite" className="text-sm text-ink-muted">
        {totalCount === 1
          ? '1 registered student holds no seat on any batch.'
          : `${totalCount} registered students hold no seat on any batch.`}
        {totalCount > students.length ? ` Showing the ${students.length} most recent.` : ''}
      </p>
      <AlertList
        items={items}
        title="registrations without an enrolment"
        emptyTitle="Every registration is on a batch"
        emptyDescription="Nobody registered is waiting for a seat."
      />
      {totalCount > 0 ? (
        // `/admissions` carries no "awaiting enrolment" filter of its own, so
        // this links to the plain list rather than to a query parameter that
        // screen would ignore.
        <Link href="/admissions" className="inline-block text-sm underline hover:text-ink">
          See all admissions
        </Link>
      ) : null}
    </div>
  );
}
