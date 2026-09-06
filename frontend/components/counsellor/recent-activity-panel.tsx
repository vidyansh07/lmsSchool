/**
 * A merged, time-ordered feed of the two things that make up this pipeline:
 * a registration and an enrolment.
 *
 * The brief this dashboard answers to asks for "their own recent activity" —
 * but neither `StudentListRow` nor `Enrollment` (see `types/api.ts`) carries
 * who registered or enrolled the record, so there is no field to filter this
 * down to one counsellor's own actions. What is shown instead is the
 * pipeline's recent activity system-wide, which is the closest honest
 * approximation the API surface allows; see the module docstring on
 * `app/admissions/dashboard/page.tsx` for the full note on this gap.
 */
import Link from 'next/link';
import { UserPlus, UserRoundCheck } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { formatName, formatRelative } from '@/lib/format';
import type { Enrollment, StudentListRow } from '@/types/api';

interface ActivityRow {
  id: string;
  at: string;
  label: string;
  href: string;
  Icon: typeof UserPlus;
}

/** Registrations and enrolments, interleaved by timestamp, most recent first. */
export function buildActivityFeed(
  students: StudentListRow[],
  enrollments: Enrollment[],
): ActivityRow[] {
  const registrations: ActivityRow[] = students.map((student) => ({
    id: `student-${student.id}`,
    at: student.created_at,
    label: `${formatName({ full_name: student.full_name, email: student.email })} registered`,
    href: `/admissions/${student.id}`,
    Icon: UserPlus,
  }));
  const enrolments: ActivityRow[] = enrollments.map((entry) => ({
    id: `enrolment-${entry.id}`,
    at: entry.enrolled_at,
    label: `${formatName({ full_name: entry.student_name, email: entry.student_email })} enrolled on ${entry.batch_name || 'a batch'}`,
    href: entry.student_id ? `/admissions/${entry.student_id}` : '/admissions',
    Icon: UserRoundCheck,
  }));

  return [...registrations, ...enrolments].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

export function RecentActivityPanel({
  students,
  enrollments,
  isLoading,
  error,
  onRetry,
  limit = 8,
}: {
  students: StudentListRow[];
  enrollments: Enrollment[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  limit?: number;
}) {
  if (isLoading) return <LoadingState label="Loading recent activity…" rows={4} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  const feed = buildActivityFeed(students, enrollments).slice(0, limit);

  if (feed.length === 0) {
    return (
      <p className="rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        Nothing has happened yet — registrations and enrolments will show up here.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {feed.map((row) => (
        <li key={row.id} className="flex items-start gap-2.5 py-2 text-sm">
          <row.Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <Link href={row.href} className="min-w-0 flex-1 hover:text-primary">
            <span className="block truncate">{row.label}</span>
          </Link>
          <span className="shrink-0 text-xs text-muted-foreground">{formatRelative(row.at)}</span>
        </li>
      ))}
    </ul>
  );
}
