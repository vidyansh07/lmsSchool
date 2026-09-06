'use client';

/**
 * One batch, in full — the drill-down target of the batches hub, and one of
 * the two "everything a batch contains" screens the brief asks for by name.
 *
 * Ordered so the eye lands on trouble first: a "Needs attention" banner is
 * assembled from the same numbers the sections below already render — a
 * schedule running behind, an overdue report, a student flagged at risk — so
 * it can never say something the rest of the page contradicts. Underneath it,
 * every section from the overview contract appears in a fixed order
 * regardless of what is or is not currently wrong, because a screen whose
 * layout rearranges itself around whatever is broken today is one nobody can
 * build a mental map of.
 *
 * DSR approval is the one inline, undoable action on this page; see
 * `components/manage/dsr-review-queue.tsx` for why "undo" means rollback on
 * failure rather than a literal undo button. Everything else here is read —
 * the roster, the trainer assignment and the timetable already have their own
 * editing screens under `/admin/batches`, and duplicating that here would be
 * a second place for the same edit to go stale against.
 */
import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

import { DsrReviewQueue } from '@/components/manage/dsr-review-queue';
import { Stat, StatGrid } from '@/components/manage/stat';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { BATCH_STATUS_LABEL, BATCH_STATUS_VARIANT } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { fallback, formatDate, formatNumber, formatPercent, NOT_ASSIGNED, NO_DATA } from '@/lib/format';
import {
  describeTimelineVariance,
  getBatchOverview,
  TIMELINE_STATUS_LABEL,
  TIMELINE_STATUS_VARIANT,
  type BatchOverview,
} from '@/lib/manage';

function attentionReasons(overview: BatchOverview): string[] {
  const reasons: string[] = [];
  if (overview.timeline.status === 'behind') {
    reasons.push(describeTimelineVariance(overview.timeline.status, overview.timeline.variance_percent));
  }
  if (!overview.trainer) reasons.push('No trainer is assigned to this batch.');
  if (overview.dsr.overdue > 0) {
    reasons.push(`${formatNumber(overview.dsr.overdue)} daily status report(s) overdue.`);
  }
  if (overview.dsr.pending_review > 0) {
    reasons.push(`${formatNumber(overview.dsr.pending_review)} report(s) awaiting review.`);
  }
  if (overview.students.at_risk > 0) {
    reasons.push(`${formatNumber(overview.students.at_risk)} student(s) flagged at risk.`);
  }
  return reasons;
}

function AttentionBanner({ overview }: { overview: BatchOverview }) {
  const reasons = attentionReasons(overview);
  if (reasons.length === 0) return null;
  return (
    <Alert variant="warning" data-testid="batch-attention-banner">
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

export function BatchDetail({ batchId }: { batchId: string }) {
  const [overview, setOverview] = useState<BatchOverview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(() => {
    let cancelled = false;
    getBatchOverview(batchId)
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
  }, [batchId]);

  useEffect(() => load(), [load]);

  if (isLoading) return <LoadingState label="Loading batch…" rows={8} />;

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Batch not found"
          description="This batch does not exist, or it is not available to you."
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
        title="Could not load this batch"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }

  if (!overview) return null;
  const { batch, course, trainer, attendance, timeline, sessions, dsr, assessments, assignments, projects, students } =
    overview;

  return (
    <div className="space-y-6">
      <Link
        href="/manage/batches"
        className="inline-block text-sm text-muted-foreground hover:text-foreground"
      >
        ← All batches
      </Link>

      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{fallback(batch.name)}</h1>
          <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>{BATCH_STATUS_LABEL[batch.status]}</Badge>
          {batch.kind ? <Badge>{batch.kind.replace(/_/g, ' ')}</Badge> : null}
          {batch.delivery_mode ? <Badge variant="neutral">{batch.delivery_mode.replace(/_/g, ' ')}</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono text-xs">{fallback(batch.code)}</span> ·{' '}
          {fallback(course?.title)} ({fallback(course?.code)}) · {formatDate(batch.start_date)} –{' '}
          {formatDate(batch.end_date)}
        </p>
        <p className="text-sm text-muted-foreground">
          Trainer:{' '}
          {trainer ? (
            <Link href={`/manage/trainers/${trainer.id}`} className="text-foreground hover:text-primary hover:underline">
              {fallback(trainer.name)}
            </Link>
          ) : (
            NOT_ASSIGNED
          )}
        </p>
      </div>

      <AttentionBanner overview={overview} />

      <Card>
        <CardHeader>
          <CardTitle>Attendance</CardTitle>
          <CardDescription>Across every class held on this batch so far.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <StatGrid>
            <Stat label="Attendance" value={formatPercent(attendance.percentage, { fallbackLabel: NO_DATA })} />
            <Stat label="Present" value={formatNumber(attendance.present)} />
            <Stat label="Absent" value={formatNumber(attendance.absent)} />
            <Stat label="Classes held" value={formatNumber(attendance.total_sessions)} />
          </StatGrid>
          <Link
            href={`/manage/batches/${batchId}/students`}
            className="inline-block text-sm text-primary hover:underline"
          >
            View the roster →
          </Link>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Plan vs actual</CardTitle>
          <CardDescription>
            {describeTimelineVariance(timeline.status, timeline.variance_percent)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={TIMELINE_STATUS_VARIANT[timeline.status]}>
              {TIMELINE_STATUS_LABEL[timeline.status]}
            </Badge>
          </div>
          <StatGrid>
            <Stat label="Actual progress" value={formatPercent(timeline.percent_complete, { fallbackLabel: NO_DATA })} />
            <Stat label="Expected by now" value={formatPercent(timeline.percent_expected, { fallbackLabel: NO_DATA })} />
            <Stat
              label="Lessons covered"
              value={`${formatNumber(timeline.lessons_covered)} / ${formatNumber(timeline.course_lessons_total)}`}
            />
            <Stat label="Next lesson" value={fallback(timeline.next_lesson?.title, NO_DATA)} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Total" value={formatNumber(sessions.total)} />
            <Stat label="Completed" value={formatNumber(sessions.completed)} />
            <Stat label="Upcoming" value={formatNumber(sessions.upcoming)} />
            <Stat label="Cancelled" value={formatNumber(sessions.cancelled)} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Daily status reports</CardTitle>
          <CardDescription>Approving a submitted report happens right here.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <StatGrid>
            <Stat label="Expected" value={formatNumber(dsr.expected)} />
            <Stat label="Submitted" value={formatNumber(dsr.submitted)} />
            <Stat label="Approved" value={formatNumber(dsr.approved)} />
            <Stat label="Awaiting review" value={formatNumber(dsr.pending_review)} tone={dsr.pending_review > 0 ? 'warning' : 'default'} />
            <Stat label="Overdue" value={formatNumber(dsr.overdue)} tone={dsr.overdue > 0 ? 'error' : 'default'} />
          </StatGrid>
          <DsrReviewQueue batchId={batchId} onReviewed={load} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Assessments</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Total" value={formatNumber(assessments.total)} />
            <Stat label="Completed" value={formatNumber(assessments.completed)} />
            <Stat label="Average score" value={formatPercent(assessments.average_percent, { fallbackLabel: NO_DATA })} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Assignments</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Total" value={formatNumber(assignments.total)} />
            <Stat label="Submitted" value={formatNumber(assignments.submitted)} />
            <Stat label="Graded" value={formatNumber(assignments.graded)} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Projects</CardTitle>
        </CardHeader>
        <CardContent>
          <StatGrid>
            <Stat label="Total" value={formatNumber(projects.total)} />
            <Stat label="Submitted" value={formatNumber(projects.submitted)} />
            <Stat label="Reviewed" value={formatNumber(projects.reviewed)} />
          </StatGrid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Students</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <StatGrid>
            <Stat label="Total" value={formatNumber(students.total)} />
            <Stat label="Active" value={formatNumber(students.active)} />
            <Stat label="At risk" value={formatNumber(students.at_risk)} tone={students.at_risk > 0 ? 'error' : 'default'} />
          </StatGrid>
          <Link
            href={`/manage/batches/${batchId}/students`}
            className="inline-block text-sm text-primary hover:underline"
          >
            View the roster →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

export default function ManageBatchDetailPage({ params }: { params: Promise<{ batchId: string }> }) {
  const { batchId } = use(params);
  return (
    <RequireAuth capability={Capability.batchViewAny}>
      <BatchDetail batchId={batchId} />
    </RequireAuth>
  );
}
