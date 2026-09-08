'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ProgressRules } from '@/components/progress-rules';
import { ProgressBar } from '@/components/progress-bar';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import {
  CERTIFICATE_STATUS_LABEL,
  CERTIFICATE_STATUS_VARIANT,
  COMPLETION_STATUS_LABEL,
  COMPLETION_STATUS_VARIANT,
  DELIVERY_MODE_LABEL,
  formatDate,
} from '@/lib/academic-labels';
import { certificatePdfUrl, listMyCertificates, listMyProgress } from '@/lib/progress';
import type { Certificate, CompletionEvaluation } from '@/types/api';

/**
 * A student's own standing: how far they are, what is still required, and the
 * certificate if one has been issued.
 *
 * Every number on this page comes from the backend's single progress
 * calculation — nothing here divides two counts of its own.
 */
function MyProgress() {
  const [rows, setRows] = useState<CompletionEvaluation[]>([]);
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMyProgress(), listMyCertificates()])
      .then(([progress, certs]) => {
        if (cancelled) return;
        setRows(progress);
        setCertificates(certs);
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

  if (isLoading) return <LoadingState label="Loading your progress…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your progress"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  const byCourse = new Map(certificates.map((row) => [row.course_title, row]));

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My progress</h1>
        <p className="text-sm text-muted-foreground">
          How far you are on each course, and what is still required to complete it.
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing to show yet"
          description="Progress appears here once you are enrolled on a course."
        />
      ) : (
        rows.map((row) => {
          const { progress, completion } = row;
          const certificate = byCourse.get(progress.course_title);
          return (
            <Card key={progress.enrollment_id} data-testid="progress-card" className="animate-rise-in">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">
                    {progress.batch_code}
                  </span>
                  {completion ? (
                    <Badge variant={COMPLETION_STATUS_VARIANT[completion.status]}>
                      {COMPLETION_STATUS_LABEL[completion.status]}
                    </Badge>
                  ) : null}
                  <Badge variant="neutral">
                    {DELIVERY_MODE_LABEL[progress.delivery_mode]}
                  </Badge>
                </div>
                <CardTitle>{progress.course_title}</CardTitle>
                <CardDescription>
                  {row.met_count} of {row.required_count} required conditions met
                  {completion?.completed_on
                    ? ` · completed ${formatDate(completion.completed_on)}`
                    : ''}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span>Course content</span>
                    <span className="text-muted-foreground">
                      {progress.lessons.completed} of {progress.lessons.total} lessons
                    </span>
                  </div>
                  <ProgressBar percent={progress.lessons.percent} />
                </div>

                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  {(
                    [
                      ['Attendance', `${progress.attendance.percent}%`],
                      [
                        'Assignments',
                        `${progress.assignments.submitted}/${progress.assignments.total}`,
                      ],
                      ['Tests', `${progress.tests.recorded}/${progress.tests.total}`],
                      [
                        'Projects',
                        `${progress.projects.finished}/${progress.projects.required}`,
                      ],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-muted-foreground">{label}</dt>
                      <dd className="text-lg font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>

                <div>
                  <p className="mb-2 text-sm font-medium">What is required to complete</p>
                  <ProgressRules rules={row.rules} />
                </div>

                {certificate ? (
                  <div className="rounded-md border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={CERTIFICATE_STATUS_VARIANT[certificate.status]}>
                        {CERTIFICATE_STATUS_LABEL[certificate.status]}
                      </Badge>
                      <span className="font-mono text-xs text-muted-foreground">
                        {certificate.number}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Issued {formatDate(certificate.issued_at)}. Anyone can check it at{' '}
                      <Link
                        className="underline hover:text-foreground"
                        href={`/verify/${certificate.verification_code}`}
                      >
                        this address
                      </Link>
                      .
                    </p>
                    <Button asChild size="sm" className="mt-2" data-testid="certificate-download">
                      <a href={certificatePdfUrl(certificate.id)}>Download the certificate</a>
                    </Button>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}

export default function MyProgressPage() {
  return (
    <RequireAuth>
      <MyProgress />
    </RequireAuth>
  );
}
