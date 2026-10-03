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
import { attemptBadge, formatDateTime } from '@/lib/academic-labels';
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

  /**
   * The attempt to show per exam, and how many that exam has used.
   *
   * The list arrives newest-first (`MyAttemptsView` orders by `-started_at`),
   * so building the map straight from it left the *oldest* attempt as the
   * survivor of each key -- a candidate on their second sitting was shown their
   * first. Highest `attempt_number` wins instead, which is the current one
   * whatever the server's ordering does next.
   */
  const latestByExam = new Map<string, AttemptResult>();
  const usedByExam = new Map<string, number>();
  for (const attempt of attempts) {
    usedByExam.set(attempt.exam, (usedByExam.get(attempt.exam) ?? 0) + 1);
    const held = latestByExam.get(attempt.exam);
    if (!held || attempt.attempt_number > held.attempt_number) {
      latestByExam.set(attempt.exam, attempt);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Examinations</h1>
        <p className="text-sm text-ink-muted">
          Final examinations set for your batch. Your time starts when you open one.
        </p>
      </div>

      {exams.length === 0 ? (
        <EmptyState
          title="Nothing scheduled"
          description="Examinations appear here once your trainer publishes them."
        />
      ) : (
        <>
        <h2 className="sr-only">Examinations</h2>
        {exams.map((exam) => {
          const mine = latestByExam.get(exam.id);
          const used = usedByExam.get(exam.id) ?? 0;
          const badge = mine ? attemptBadge(mine) : null;
          /**
           * Whether this candidate may open the paper.
           *
           * An attempt still running is resumed. Otherwise a fresh one is
           * offered while the exam has attempts left -- which is what
           * `services.start_attempt` will actually allow, and what an exam
           * advertising "two attempts allowed" promises. The condition used to
           * be "no attempt at all, or one in progress", so submitting the first
           * attempt on a two-attempt exam removed the only control that could
           * start the second and there was no way back to the paper.
           */
          const resumable = mine?.status === 'in_progress';
          const attemptsLeft = Math.max(0, exam.max_attempts - used);
          const canOpen = exam.is_open && (resumable || attemptsLeft > 0);
          return (
            <Card key={exam.id} data-testid="exam-card" className="">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-ink-muted">{exam.code}</span>
                  {badge ? (
                    <Badge variant={badge.variant}>{badge.label}</Badge>
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
                  <div className="rounded-md border border-line p-3 text-sm">
                    {mine.results_published && mine.total_score !== null ? (
                      <p data-testid="exam-score">
                        <span className="font-semibold">
                          {mine.total_score} / {mine.max_score}
                        </span>
                        {mine.percentage === null ? null : (
                          <span className="ml-2 text-ink-muted">{mine.percentage}%</span>
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
                      <p className="text-ink-muted">
                        Submitted {formatDateTime(mine.submitted_at)}. Results have not been
                        released yet.
                      </p>
                    )}
                  </div>
                ) : null}

                {canOpen ? (
                  <div className="space-y-2">
                    <Button asChild size="sm">
                      <Link href={`/exams/${exam.id}`}>
                        {resumable
                          ? 'Continue the examination'
                          : used > 0
                            ? `Start attempt ${used + 1}`
                            : 'Start the examination'}
                      </Link>
                    </Button>
                    {!resumable && exam.max_attempts > 1 ? (
                      <p className="text-xs text-ink-muted" data-testid="attempts-left">
                        {attemptsLeft} of {exam.max_attempts} attempts left.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
        </>
      )}

      {attempts.length > 0 ? (
        <Card className="">
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
                        <div className="font-mono text-xs text-ink-muted">
                          {attempt.exam_code}
                        </div>
                      </Td>
                      <Td>{formatDateTime(attempt.submitted_at)}</Td>
                      <Td>
                        {attempt.results_published && attempt.total_score !== null ? (
                          <Link
                            className="underline hover:text-ink"
                            href={`/attempts/${attempt.id}`}
                          >
                            {attempt.total_score} / {attempt.max_score}
                          </Link>
                        ) : (
                          <span className="text-ink-muted">Not released</span>
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
