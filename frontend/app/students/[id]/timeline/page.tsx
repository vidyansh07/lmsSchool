'use client';

/**
 * A minimal host for `StudentTimeline` (Phase 10).
 *
 * The codebase has no tabbed student-detail page yet to extend
 * (`app/admissions/[studentId]/page.tsx` is the closest existing
 * single-student screen, but it is one flat page, not tabs, and it is
 * counsellor-flavoured — contact details, fees, enrolment actions). Rather
 * than force the timeline into that unrelated page, this adds the smallest
 * possible route so the component is exercised end-to-end. Phase 11
 * (Student 360) is expected to introduce the real tabbed student page and
 * fold this in as one of its tabs; nothing here (gating, data fetching)
 * needs to survive that move, only the `StudentTimeline` component itself.
 *
 * Gated the same way `app/admissions/[studentId]/page.tsx` gates its own
 * single-student screen: `student.view_any`, the capability that covers
 * seeing any one student's record.
 */

import Link from 'next/link';
import { use, useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';

import { RequireAuth } from '@/components/require-auth';
import { StudentTimeline } from '@/components/students/timeline';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { getStudent } from '@/lib/people';
import type { StudentProfile } from '@/types/api';

function StudentTimelinePage({ studentId }: { studentId: string }) {
  const [student, setStudent] = useState<StudentProfile | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    getStudent(studentId)
      .then((row) => {
        if (!cancelled) setStudent(row);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The request failed.', ''));
      });
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  return (
    <div className="animate-rise-in space-y-4">
      <Link
        href="/admissions"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All admissions
      </Link>

      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {student ? student.user.full_name || student.user.email : 'Student timeline'}
        </h1>
        {student ? <Badge>{student.student_id}</Badge> : null}
      </div>

      {error ? (
        <ErrorState
          title="Could not load this student"
          message={error.message}
          requestId={error.requestId || undefined}
        />
      ) : !student ? (
        <LoadingState label="Loading student…" rows={2} />
      ) : null}

      <StudentTimeline studentId={studentId} />
    </div>
  );
}

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth capability={Capability.studentViewAny}>
      <StudentTimelinePage studentId={id} />
    </RequireAuth>
  );
}
