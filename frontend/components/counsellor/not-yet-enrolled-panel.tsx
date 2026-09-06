/**
 * "Registered, not yet enrolled" — the gap that costs money, per the brief
 * this component exists to satisfy: every day a registered student sits
 * without a batch is a day they might go elsewhere.
 *
 * There is no backend query for this — `/api/v1/students/` carries no
 * enrolment information at all, and `/api/v1/enrollments/` cannot be filtered
 * by a set of student ids (see the docstring on `listStudentEnrollments` in
 * `lib/batches.ts` for why: it takes one student's code at a time). Rather
 * than issue one lookup per recently-registered student — an N+1 this
 * dashboard would pay on every load — the caller fetches one wide recent page
 * of enrolments instead (see `app/admissions/dashboard/page.tsx`) and this
 * module just answers "does this student's code appear in it".
 *
 * That makes the result a *recent-window* answer, not a lifetime guarantee: a
 * student who registered long enough ago that their eventual enrolment has
 * scrolled out of the enrolments window fetched would be a false positive
 * here. The caption below says exactly what was checked, so nobody reads this
 * list as more certain than it is — and the false-positive failure mode is
 * cheap: a counsellor opens a student who, on the next screen, turns out to
 * already be enrolled.
 */
import Link from 'next/link';

import { AlertList, type AlertItem } from '@/components/alert-list';
import { ErrorState, LoadingState } from '@/components/states';
import { formatName, formatRelative } from '@/lib/format';
import type { StudentListRow } from '@/types/api';

/** Recently-registered students whose code does not appear among recent enrolments. */
export function studentsAwaitingEnrolment(
  recentStudents: StudentListRow[],
  enrolledStudentCodes: Set<string>,
): StudentListRow[] {
  return recentStudents.filter((student) => !enrolledStudentCodes.has(student.student_id));
}

export function NotYetEnrolledPanel({
  recentStudents,
  enrolledStudentCodes,
  isLoading,
  error,
  onRetry,
}: {
  recentStudents: StudentListRow[];
  enrolledStudentCodes: Set<string>;
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

  const outstanding = studentsAwaitingEnrolment(recentStudents, enrolledStudentCodes);
  const items: AlertItem[] = outstanding.map((student) => ({
    id: student.id,
    severity: 'warning',
    title: formatName({ full_name: student.full_name, email: student.email }),
    description: `Registered ${formatRelative(student.created_at)} · ${student.student_id || 'no student code yet'}`,
    href: `/admissions/${student.id}`,
  }));

  return (
    <div className="space-y-2">
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {outstanding.length} of the last {recentStudents.length} registrations{' '}
        {outstanding.length === 1 ? 'has' : 'have'} no enrolment yet.
      </p>
      <AlertList
        items={items}
        title="registrations without an enrolment"
        emptyTitle="Every recent registration is enrolled"
        emptyDescription="Nobody from the recent intake is waiting on a batch."
      />
      {outstanding.length > 0 ? (
        <Link href="/admissions" className="inline-block text-sm underline hover:text-foreground">
          See all admissions
        </Link>
      ) : null}
    </div>
  );
}
