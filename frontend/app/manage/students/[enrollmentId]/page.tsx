'use client';

/**
 * One student's full performance picture — the bottom of the drill-down
 * chain the brief asks for: batches → roster → one student.
 *
 * There is no single-student endpoint in the fixed contract (it covers a
 * roster *list*, not one row read back on its own), so this page is built on
 * the richest real source available: `apps.performance.engine`'s own
 * per-enrolment output, already served at `GET /batches/<id>/performance/`
 * for a trainer's cohort view. Getting there takes two steps — read the
 * enrolment to learn which batch it is on, then read that batch's
 * performance list and pick this one row out of it — because nothing in the
 * API surface answers "this one enrolment's performance" more directly than
 * that. See `lib/manage.ts` for the full reasoning.
 *
 * The risk section reads directly from the engine's own `risk.outcomes`
 * rather than a flat flag list: each entry already carries the sentence a
 * risk rule produced ("78% attended, below the 75% risk threshold"), which is
 * a better "review everything" surface than a bare label ever could be.
 *
 * Feedback about this student loads separately from the rest of the page —
 * `Feedback` has no student filter on the server, so this reads the whole
 * visible set and matches by student code, and giving that its own
 * loading/error/retry means a slow or failing feedback fetch never blocks
 * the performance figures above it from rendering.
 */
import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

import { Stat, StatGrid } from '@/components/manage/stat';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { getEnrollment } from '@/lib/batches';
import { ENROLLMENT_STATUS_LABEL, ENROLLMENT_STATUS_VARIANT } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { fallback, formatDate, formatNumber, formatPercent, NO_DATA, UNKNOWN } from '@/lib/format';
import { getBatchPerformance, listFeedback, type FeedbackItem, type StudentPerformanceRow } from '@/lib/manage';
import type { Enrollment } from '@/types/api';

function progressSentence(variance: number | null): string {
  if (variance === null) return 'Not enough of the course has run yet to compare plan against actual.';
  const points = Math.abs(Math.round(variance));
  if (variance > 0) return `${points} percentage point${points === 1 ? '' : 's'} behind schedule.`;
  if (variance < 0) return `${points} percentage point${points === 1 ? '' : 's'} ahead of schedule.`;
  return 'On schedule.';
}

function RiskBanner({ performance }: { performance: StudentPerformanceRow }) {
  const triggered = performance.risk.outcomes.filter((outcome) => outcome.triggered);
  if (triggered.length === 0) return null;
  return (
    <Alert variant="warning" data-testid="student-risk-banner">
      <p className="flex items-center gap-2 font-medium">
        <AlertTriangle className="size-4" aria-hidden="true" />
        Flagged at risk
      </p>
      <ul className="mt-1.5 list-inside list-disc space-y-0.5">
        {triggered.map((outcome) => (
          <li key={outcome.key}>
            <span className="font-medium">{outcome.label}:</span> {outcome.detail}
          </li>
        ))}
      </ul>
    </Alert>
  );
}

/** Loads and filters independently of the rest of the page — see the module docstring. */
function StudentFeedbackSection({ studentCode }: { studentCode: string | null }) {
  const [items, setItems] = useState<FeedbackItem[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  // No studentCode still resolves through a promise, rather than setting
  // `items` synchronously here — a setState call reachable directly from the
  // effect body (not from inside a `.then()`) risks a cascading render, the
  // same reasoning `hooks/use-api.ts` documents for its own request effect.
  const load = useCallback(() => {
    let cancelled = false;
    const request = studentCode ? listFeedback() : Promise.resolve<FeedbackItem[]>([]);
    request
      .then((all) => {
        if (cancelled) return;
        setItems(studentCode ? all.filter((item) => item.student_code === studentCode) : []);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, [studentCode]);

  useEffect(() => load(), [load]);

  if (error) {
    return (
      <ErrorState
        title="Could not load feedback"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }
  if (items === null) return <LoadingState label="Loading feedback…" rows={2} />;
  if (items.length === 0) {
    return <EmptyState title="No feedback yet" description="Nothing has been left for this student." />;
  }
  return (
    <ul className="stagger divide-y divide-border rounded-[var(--radius-card)] border border-border">
      {items.map((item) => (
        <li
          key={item.id}
          className="animate-fade-in space-y-1 px-4 py-3 transition-colors hover:bg-muted/40"
          data-testid="student-feedback-item"
        >
          <p className="text-sm">{fallback(item.body, NO_DATA)}</p>
          <p className="text-xs text-muted-foreground">
            {fallback(item.author_name, UNKNOWN)} · {fallback(item.batch_code)} · {formatDate(item.created_at)}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function StudentPerformance({ enrollmentId }: { enrollmentId: string }) {
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [performance, setPerformance] = useState<StudentPerformanceRow | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(() => {
    let cancelled = false;
    getEnrollment(enrollmentId)
      .then(async (row) => {
        if (cancelled) return;
        setEnrollment(row);
        const rows = await getBatchPerformance(row.batch_id);
        if (cancelled) return;
        setPerformance(rows.find((entry) => entry.enrollment_id === enrollmentId) ?? null);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enrollmentId]);

  useEffect(() => load(), [load]);

  if (isLoading) return <LoadingState label="Loading student…" rows={8} />;

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Enrolment not found"
          description="This enrolment does not exist, or it is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href="/manage/batches">Back to batches</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this student"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }

  if (!enrollment) return null;
  const studentCode = enrollment.student_code ?? null;

  return (
    <div className="animate-rise-in space-y-6">
      <Link
        href={`/manage/batches/${enrollment.batch_id}/students`}
        className="inline-block text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back to roster
      </Link>

      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{fallback(enrollment.student_name, UNKNOWN)}</h1>
          <Badge variant={ENROLLMENT_STATUS_VARIANT[enrollment.status]}>
            {ENROLLMENT_STATUS_LABEL[enrollment.status]}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono text-xs">{fallback(studentCode)}</span> · {fallback(enrollment.course_title)} on{' '}
          <Link href={`/manage/batches/${enrollment.batch_id}`} className="text-foreground hover:text-primary hover:underline">
            {fallback(enrollment.batch_name)}
          </Link>
        </p>
      </div>

      {!performance ? (
        <EmptyState
          title="No performance data yet"
          description="This enrolment has no recorded activity to report on yet."
        />
      ) : (
        <>
          <RiskBanner performance={performance} />

          <Card>
            <CardHeader>
              <CardTitle>Attendance</CardTitle>
            </CardHeader>
            <CardContent>
              {performance.attendance.has_records ? (
                <StatGrid>
                  <Stat label="Attendance" value={formatPercent(performance.attendance.percent, { fallbackLabel: NO_DATA })} />
                  <Stat label="Attended" value={formatNumber(performance.attendance.attended)} />
                  <Stat label="Classes held" value={formatNumber(performance.attendance.total_sessions)} />
                </StatGrid>
              ) : (
                <p className="text-sm text-muted-foreground">No classes have been registered yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Assessments</CardTitle>
            </CardHeader>
            <CardContent>
              <StatGrid>
                <Stat label="Average score" value={formatPercent(performance.assessment.average_percent, { fallbackLabel: NO_DATA })} />
                <Stat label="Sat" value={formatPercent(performance.assessment.sitting_percent, { fallbackLabel: NO_DATA })} />
                <Stat
                  label="Recorded"
                  value={`${formatNumber(performance.assessment.recorded)} / ${formatNumber(performance.assessment.total)}`}
                />
              </StatGrid>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Assignments</CardTitle>
            </CardHeader>
            <CardContent>
              <StatGrid>
                <Stat label="Completion" value={formatPercent(performance.assignments.percent, { fallbackLabel: NO_DATA })} />
                <Stat
                  label="Submitted"
                  value={`${formatNumber(performance.assignments.submitted)} / ${formatNumber(performance.assignments.total)}`}
                />
                <Stat label="Graded" value={formatNumber(performance.assignments.graded)} />
                <Stat
                  label="Missed"
                  value={formatNumber(performance.assignments.missed)}
                  tone={performance.assignments.missed > 0 ? 'error' : 'default'}
                />
              </StatGrid>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Projects</CardTitle>
            </CardHeader>
            <CardContent>
              <StatGrid>
                <Stat label="Completion" value={formatPercent(performance.projects.percent, { fallbackLabel: NO_DATA })} />
                <Stat
                  label="Finished"
                  value={`${formatNumber(performance.projects.finished)} / ${formatNumber(performance.projects.required)}`}
                />
              </StatGrid>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Course progress</CardTitle>
              <CardDescription>{progressSentence(performance.progress.variance)}</CardDescription>
            </CardHeader>
            <CardContent>
              <StatGrid>
                <Stat label="Actual progress" value={formatPercent(performance.progress.percent, { fallbackLabel: NO_DATA })} />
                <Stat label="Expected by now" value={formatPercent(performance.progress.expected_percent, { fallbackLabel: NO_DATA })} />
                <Stat label="Overall score" value={formatPercent(performance.overall_score, { fallbackLabel: NO_DATA })} />
              </StatGrid>
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Feedback</CardTitle>
          <CardDescription>What has been left for this student.</CardDescription>
        </CardHeader>
        <CardContent>
          <StudentFeedbackSection studentCode={studentCode} />
        </CardContent>
      </Card>
    </div>
  );
}

export default function ManageStudentPerformancePage({
  params,
}: {
  params: Promise<{ enrollmentId: string }>;
}) {
  const { enrollmentId } = use(params);
  return (
    <RequireAuth capability={Capability.performanceViewAny}>
      <StudentPerformance enrollmentId={enrollmentId} />
    </RequireAuth>
  );
}
