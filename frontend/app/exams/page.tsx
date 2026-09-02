'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import {
  ATTEMPT_STATUS_LABEL,
  ATTEMPT_STATUS_VARIANT,
  formatDateTime,
} from '@/lib/academic-labels';
import { listMyAttempts, listMyExams } from '@/lib/exams';
import type { AttemptResult, Exam } from '@/types/api';

/** A candidate's examinations, and their results once released. */
function MyExams() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [attempts, setAttempts] = useState<AttemptResult[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMyExams(), listMyAttempts()])
      .then(([examPage, attemptPage]) => {
        if (cancelled) return;
        setExams(examPage.results);
        setAttempts(attemptPage.results);
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

  if (isLoading) return <LoadingState label="Loading your examinations…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your examinations"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  const byExam = new Map(attempts.map((attempt) => [attempt.exam, attempt]));

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Examinations</h1>
        <p className="text-sm text-muted-foreground">
          Final examinations set for your batch. Your time starts when you open one.
        </p>
      </div>

      {exams.length === 0 ? (
        <EmptyState
          title="Nothing scheduled"
          description="Examinations appear here once your trainer publishes them."
        />
      ) : (
        exams.map((exam) => {
          const mine = byExam.get(exam.id);
          return (
            <Card key={exam.id} data-testid="exam-card">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{exam.code}</span>
                  {mine ? (
                    <Badge variant={ATTEMPT_STATUS_VARIANT[mine.status]}>
                      {ATTEMPT_STATUS_LABEL[mine.status]}
                    </Badge>
                  ) : (
                    <Badge variant={exam.is_open ? 'success' : 'neutral'}>
                      {exam.is_open ? 'Open' : 'Not open'}
                    </Badge>
                  )}
                </div>
                <CardTitle>{exam.title}</CardTitle>
                <CardDescription>
                  {exam.duration_minutes} minutes · {exam.total_questions} questions ·{' '}
                  {exam.negative_marking ? 'negative marking' : 'no negative marking'} · opens{' '}
                  {formatDateTime(exam.opens_at)}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-3">
                {exam.instructions ? (
                  <p className="whitespace-pre-wrap text-sm">{exam.instructions}</p>
                ) : null}

                {mine && mine.status !== 'in_progress' ? (
                  <div className="rounded-md border border-border p-3 text-sm">
                    {mine.results_published && mine.total_score !== null ? (
                      <p data-testid="exam-score">
                        <span className="font-semibold">
                          {mine.total_score} / {mine.max_score}
                        </span>
                        {mine.percentage === null ? null : (
                          <span className="ml-2 text-muted-foreground">{mine.percentage}%</span>
                        )}
                        {mine.is_passing === null ? null : (
                          <Badge
                            className="ml-2"
                            variant={mine.is_passing ? 'success' : 'error'}
                          >
                            {mine.is_passing ? 'Pass' : 'Below the pass mark'}
                          </Badge>
                        )}
                      </p>
                    ) : (
                      <p className="text-muted-foreground">
                        Submitted {formatDateTime(mine.submitted_at)}. Results have not been
                        released yet.
                      </p>
                    )}
                  </div>
                ) : null}

                {exam.is_open && (!mine || mine.status === 'in_progress') ? (
                  <Button asChild size="sm">
                    <Link href={`/exams/${exam.id}`}>
                      {mine ? 'Continue the examination' : 'Start the examination'}
                    </Link>
                  </Button>
                ) : null}
              </CardContent>
            </Card>
          );
        })
      )}

      {attempts.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>My attempts</CardTitle>
          </CardHeader>
          <CardContent>
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Examination</Th>
                    <Th>Submitted</Th>
                    <Th>Result</Th>
                  </tr>
                </thead>
                <tbody>
                  {attempts.map((attempt) => (
                    <tr key={attempt.id}>
                      <Td>
                        {attempt.exam_title}
                        <div className="font-mono text-xs text-muted-foreground">
                          {attempt.exam_code}
                        </div>
                      </Td>
                      <Td>{formatDateTime(attempt.submitted_at)}</Td>
                      <Td>
                        {attempt.results_published && attempt.total_score !== null ? (
                          <Link
                            className="underline hover:text-foreground"
                            href={`/attempts/${attempt.id}`}
                          >
                            {attempt.total_score} / {attempt.max_score}
                          </Link>
                        ) : (
                          <span className="text-muted-foreground">Not released</span>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function ExamsPage() {
  return (
    <RequireAuth>
      <MyExams />
    </RequireAuth>
  );
}
