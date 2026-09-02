'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ScheduleList } from '@/components/schedule-list';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { getBatch, listMyEnrollments } from '@/lib/batches';
import {
  BATCH_STATUS_LABEL,
  BATCH_STATUS_VARIANT,
  ENROLLMENT_STATUS_LABEL,
  ENROLLMENT_STATUS_VARIANT,
  formatDate,
} from '@/lib/batch-labels';
import type { BatchDetail, Enrollment } from '@/types/api';

function MyBatches() {
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [batches, setBatches] = useState<Record<string, BatchDetail>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    listMyEnrollments()
      .then(async (rows) => {
        if (cancelled) return;
        setEnrollments(rows);
        // Fetch each batch once for its timetable. The list is a student's own
        // enrolments, so it is a handful of rows, not a page of them.
        const details = await Promise.all(
          rows.map((row) => getBatch(row.batch_id).catch(() => null)),
        );
        if (cancelled) return;
        setBatches(
          Object.fromEntries(
            details.filter((item): item is BatchDetail => item !== null).map((item) => [item.id, item]),
          ),
        );
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
  }, []);

  if (isLoading) return <LoadingState label="Loading your batches…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your batches"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My batches</h1>
        <p className="text-sm text-muted-foreground">
          Every batch you have been enrolled on, including finished ones.
        </p>
      </div>

      {enrollments.length === 0 ? (
        <EmptyState
          title="No batches yet"
          description="You have not been enrolled on a batch. Browse the catalogue to see what is running."
          action={
            <Button asChild variant="outline">
              <Link href="/courses">Browse courses</Link>
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          {enrollments.map((enrollment) => {
            const batch = batches[enrollment.batch_id];
            return (
              <Card key={enrollment.id}>
                <CardHeader className="gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={ENROLLMENT_STATUS_VARIANT[enrollment.status]}>
                      {ENROLLMENT_STATUS_LABEL[enrollment.status]}
                    </Badge>
                    <Badge variant={BATCH_STATUS_VARIANT[enrollment.batch_status]}>
                      {BATCH_STATUS_LABEL[enrollment.batch_status]}
                    </Badge>
                    <span className="font-mono text-xs text-muted-foreground">
                      {enrollment.batch_code}
                    </span>
                  </div>
                  <CardTitle>{enrollment.batch_name}</CardTitle>
                  <CardDescription>
                    <Link
                      href={`/courses/${enrollment.course_slug}`}
                      className="underline hover:text-foreground"
                    >
                      {enrollment.course_title}
                    </Link>
                    {enrollment.trainer_name ? ` · ${enrollment.trainer_name}` : ''}
                  </CardDescription>
                </CardHeader>

                <CardContent className="space-y-3">
                  {!enrollment.grants_access ? (
                    <p className="text-sm text-muted-foreground">
                      {enrollment.status === 'suspended'
                        ? 'Your access is paused. Contact the administration office.'
                        : enrollment.status === 'cancelled'
                          ? 'This enrolment was cancelled. Your record is kept for reference.'
                          : 'Access has not opened yet.'}
                    </p>
                  ) : null}

                  {batch ? (
                    <>
                      <p className="text-sm text-muted-foreground">
                        {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
                      </p>
                      <ScheduleList schedules={batch.schedules} />
                    </>
                  ) : null}

                  {enrollment.grants_access ? (
                    <Button asChild size="sm">
                      <Link href={`/courses/${enrollment.course_slug}`}>Open the course</Link>
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function MyBatchesPage() {
  return (
    <RequireAuth>
      <MyBatches />
    </RequireAuth>
  );
}
