'use client';

/**
 * One trainer, in full — performance figures, the reviews written about
 * them, and the feedback their own students left. The client asked for the
 * student-feedback piece by name, so it is its own section here rather than
 * folded into "reviews": a review is a manager's periodic judgement with a
 * rating attached, a piece of feedback is a student's own remark, and
 * collapsing the two would make it impossible to tell which is which when
 * reading the page.
 *
 * Writing a review happens inline, on this same page — see
 * `components/manage/review-form.tsx` for why a seven-field form is still an
 * inline action here rather than a separate screen: this page *is* the full
 * screen the brief reserves multi-field actions for.
 */
import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { Stat, StatGrid } from '@/components/manage/stat';
import { TrainerReviewForm } from '@/components/manage/review-form';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { fallback, formatDate, formatNumber, formatPercent, NO_DATA, UNKNOWN } from '@/lib/format';
import { getTrainerOverview, type TrainerOverview } from '@/lib/manage';

function TrainerAttentionBanner({ overview }: { overview: TrainerOverview }) {
  const reasons: string[] = [];
  if (overview.pending.overdue > 0) {
    reasons.push(`${formatNumber(overview.pending.overdue)} item(s) of pending work are overdue.`);
  }
  if (overview.students.at_risk > 0) {
    reasons.push(`${formatNumber(overview.students.at_risk)} of this trainer's students are flagged at risk.`);
  }
  if (reasons.length === 0) return null;
  return (
    <Alert variant="warning" data-testid="trainer-attention-banner">
      <p className="flex items-center gap-2 font-medium">
        <AlertTriangle className="size-4" aria-hidden="true" />
        Needs attention
      </p>
      <ul className="mt-1.5 list-inside list-disc space-y-0.5">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </Alert>
  );
}

export function TrainerDetail({ trainerId }: { trainerId: string }) {
  const { can } = useAuth();
  const [overview, setOverview] = useState<TrainerOverview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(() => {
    let cancelled = false;
    getTrainerOverview(trainerId)
      .then((result) => {
        if (!cancelled) {
          setOverview(result);
          setError(null);
        }
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
  }, [trainerId]);

  useEffect(() => load(), [load]);

  if (isLoading) return <LoadingState label="Loading trainer…" rows={8} />;

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Trainer not found"
          description="This trainer does not exist, or is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href="/manage/trainers">Back to trainers</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this trainer"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }

  if (!overview) return null;
  const { trainer, batches, students, submission, completion, outcomes, pending, reviews, student_feedback } = overview;

  return (
    <div className="animate-rise-in space-y-6">
      <Link href="/manage/trainers" className="inline-block text-sm text-muted-foreground hover:text-foreground">
        ← All trainers
      </Link>

      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{fallback(trainer.name, UNKNOWN)}</h1>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono text-xs">{fallback(trainer.trainer_id)}</span> · {fallback(trainer.email)}
        </p>
      </div>

      <TrainerAttentionBanner overview={overview} />

      <Card>
        <CardHeader>
          <CardTitle>Workload</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Batches" value={formatNumber(batches.total)} />
            <Stat label="Active batches" value={formatNumber(batches.active)} />
            <Stat label="Students" value={formatNumber(students.total)} />
            <Stat
              label="Students at risk"
              value={formatNumber(students.at_risk)}
              tone={students.at_risk > 0 ? 'error' : 'default'}
            />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Submission</CardTitle>
          <CardDescription>How reliably classes and daily status reports are recorded.</CardDescription>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Attendance taken" value={formatPercent(submission.attendance_rate, { fallbackLabel: NO_DATA })} />
            <Stat label="DSR submitted" value={formatPercent(submission.dsr_rate, { fallbackLabel: NO_DATA })} />
            <Stat label="DSR approved on first review" value={formatPercent(submission.dsr_approval_rate, { fallbackLabel: NO_DATA })} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Completion</CardTitle>
          <CardDescription>How much of the required work on this trainer&rsquo;s batches is done.</CardDescription>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Assessments" value={formatPercent(completion.assessments, { fallbackLabel: NO_DATA })} />
            <Stat label="Assignments" value={formatPercent(completion.assignments, { fallbackLabel: NO_DATA })} />
            <Stat label="Projects" value={formatPercent(completion.projects, { fallbackLabel: NO_DATA })} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Student outcomes</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Average student score" value={formatPercent(outcomes.student_average_score, { fallbackLabel: NO_DATA })} />
            <Stat label="Average student attendance" value={formatPercent(outcomes.student_attendance_percent, { fallbackLabel: NO_DATA })} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pending work</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="DSR to submit" value={formatNumber(pending.dsr_to_submit)} />
            <Stat label="Assignments to grade" value={formatNumber(pending.assignments_to_grade)} />
            <Stat label="Projects to review" value={formatNumber(pending.projects_to_review)} />
            <Stat label="Overdue" value={formatNumber(pending.overdue)} tone={pending.overdue > 0 ? 'error' : 'default'} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Performance reviews</CardTitle>
          <CardDescription>What managers have formally recorded about this trainer.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {reviews.length === 0 ? (
            <EmptyState title="No reviews yet" description="Nobody has recorded a review for this trainer." />
          ) : (
            <ul className="stagger divide-y divide-border rounded-[var(--radius-card)] border border-border">
              {reviews.map((review) => (
                <li
                  key={review.id}
                  className="animate-fade-in space-y-1 px-4 py-3 transition-colors hover:bg-muted/40"
                  data-testid="trainer-review"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium">
                      {formatDate(review.period_start)} – {formatDate(review.period_end)}
                    </p>
                    <Badge>{review.rating} / 5</Badge>
                  </div>
                  <p className="text-sm">{fallback(review.summary, NO_DATA)}</p>
                  <p className="text-xs text-muted-foreground">
                    By {fallback(review.reviewer, UNKNOWN)} · {formatDate(review.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {can(Capability.reviewManageAny) ? <TrainerReviewForm trainerId={trainerId} onSaved={load} /> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Student feedback</CardTitle>
          <CardDescription>What this trainer&rsquo;s own students have said about them.</CardDescription>
        </CardHeader>
        <CardContent>
          {student_feedback.length === 0 ? (
            <EmptyState title="No feedback yet" description="No student has left feedback for this trainer." />
          ) : (
            <ul className="stagger divide-y divide-border rounded-[var(--radius-card)] border border-border">
              {student_feedback.map((item) => (
                <li
                  key={item.id}
                  className="animate-fade-in space-y-1 px-4 py-3 transition-colors hover:bg-muted/40"
                  data-testid="student-feedback"
                >
                  <p className="text-sm">{fallback(item.body, NO_DATA)}</p>
                  <p className="text-xs text-muted-foreground">
                    {fallback(item.batch_code)} · {formatDate(item.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ManageTrainerDetailPage({ params }: { params: Promise<{ trainerId: string }> }) {
  const { trainerId } = use(params);
  return (
    <RequireAuth capability={Capability.trainerViewAny}>
      <TrainerDetail trainerId={trainerId} />
    </RequireAuth>
  );
}
