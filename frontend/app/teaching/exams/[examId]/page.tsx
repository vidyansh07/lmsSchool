'use client';

import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import {
  ATTEMPT_STATUS_LABEL,
  ATTEMPT_STATUS_VARIANT,
  LIFECYCLE_LABEL,
  LIFECYCLE_VARIANT,
  formatDateTime,
} from '@/lib/academic-labels';
import {
  getExam,
  getExamReadiness,
  listExamAttempts,
  listMarkingQueue,
  markAnswer,
  publishExamResults,
  setExamStatus,
} from '@/lib/exams';
import type { Exam, ExamReadiness, MarkableAnswer, StaffAttempt } from '@/types/api';

/** The paper, who sat it, what still needs marking, and the release switch. */
function ExamDetail({ examId }: { examId: string }) {
  const [exam, setExam] = useState<Exam | null>(null);
  const [readiness, setReadiness] = useState<ExamReadiness | null>(null);
  const [attempts, setAttempts] = useState<StaffAttempt[]>([]);
  const [queue, setQueue] = useState<MarkableAnswer[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [detail, ready, attemptPage, marking] = await Promise.all([
      getExam(examId),
      getExamReadiness(examId),
      listExamAttempts(examId),
      listMarkingQueue(examId),
    ]);
    setExam(detail);
    setReadiness(ready);
    setAttempts(attemptPage.results);
    setQueue(marking);
    setMarks(Object.fromEntries(marking.map((row) => [row.id, row.awarded ?? ''])));
    setFeedback(Object.fromEntries(marking.map((row) => [row.id, row.marker_feedback])));
  }, [examId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getExam(examId),
      getExamReadiness(examId),
      listExamAttempts(examId),
      listMarkingQueue(examId),
    ])
      .then(([detail, ready, attemptPage, marking]) => {
        if (cancelled) return;
        setExam(detail);
        setReadiness(ready);
        setAttempts(attemptPage.results);
        setQueue(marking);
        setMarks(Object.fromEntries(marking.map((row) => [row.id, row.awarded ?? ''])));
        setFeedback(Object.fromEntries(marking.map((row) => [row.id, row.marker_feedback])));
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
  }, [examId]);

  async function run(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key);
    setFormError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(message);
    } catch (cause) {
      setFormError(fieldErrors(cause).__all__ ?? fieldErrors(cause).sections ?? 'That could not be done.');
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading the examination…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the examination"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!exam) return null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={LIFECYCLE_VARIANT[exam.status]}>{LIFECYCLE_LABEL[exam.status]}</Badge>
          {exam.results_published ? <Badge variant="success">Results released</Badge> : null}
          <span className="font-mono text-xs text-muted-foreground">{exam.code}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{exam.title}</h1>
        <p className="text-sm text-muted-foreground">
          {exam.batch_code} · {exam.duration_minutes} minutes · {exam.total_questions} questions ·{' '}
          {exam.max_attempts} attempt{exam.max_attempts === 1 ? '' : 's'}
        </p>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Readiness</CardTitle>
          <CardDescription>
            Whether the bank has enough questions for every section.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {readiness ? (
            <div data-testid="exam-readiness">
              <Badge variant={readiness.ready ? 'success' : 'error'}>
                {readiness.ready ? 'Ready to publish' : 'Not ready'}
              </Badge>
              <p className="mt-2 text-sm text-muted-foreground">
                {readiness.sections} section{readiness.sections === 1 ? '' : 's'} ·{' '}
                {readiness.questions} questions · about{' '}
                {readiness.approximate_total_marks} marks
              </p>
              {readiness.problems.length > 0 ? (
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {readiness.problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {exam.status === 'draft' ? (
              <Button
                type="button"
                size="sm"
                disabled={busy === 'publish'}
                onClick={() =>
                  run(
                    'publish',
                    () => setExamStatus(exam.id, 'published'),
                    'Published. Candidates can start it when it opens.',
                  )
                }
              >
                Publish
              </Button>
            ) : null}
            {exam.status === 'published' ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy === 'close'}
                onClick={() =>
                  run('close', () => setExamStatus(exam.id, 'closed'), 'Closed.')
                }
              >
                Close
              </Button>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant={exam.results_published ? 'outline' : 'primary'}
              disabled={busy === 'results'}
              onClick={() =>
                run(
                  'results',
                  () => publishExamResults(exam.id, !exam.results_published),
                  exam.results_published ? 'Results withheld again.' : 'Results released.',
                )
              }
            >
              {exam.results_published ? 'Withhold results' : 'Release results'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Answers awaiting marking ({queue.length})</CardTitle>
          <CardDescription>
            Written answers only. Everything else was marked by the server on submission.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {queue.length === 0 ? (
            <EmptyState title="Nothing to mark" description="No written answers are pending." />
          ) : (
            <div className="space-y-4">
              {queue.map((row) => (
                <div key={row.id} className="rounded-md border border-border p-3">
                  <div className="text-sm font-medium">
                    {row.student_name}{' '}
                    <span className="font-mono text-xs text-muted-foreground">
                      {row.student_id}
                    </span>
                  </div>
                  <p className="mt-1 text-sm">{row.question_text}</p>
                  <p className="mt-2 whitespace-pre-wrap rounded bg-muted p-2 text-sm">
                    {row.text_answer || row.answered_filename || '(nothing written)'}
                  </p>

                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Field label={`Marks (out of ${row.marks})`} htmlFor={`awarded-${row.id}`}>
                      <Input
                        id={`awarded-${row.id}`}
                        type="number"
                        min="0"
                        step="0.01"
                        max={row.marks}
                        value={marks[row.id] ?? ''}
                        onChange={(event) => setMarks({ ...marks, [row.id]: event.target.value })}
                      />
                    </Field>
                    <Field label="Feedback" htmlFor={`feedback-${row.id}`}>
                      <Textarea
                        id={`feedback-${row.id}`}
                        rows={2}
                        value={feedback[row.id] ?? ''}
                        onChange={(event) =>
                          setFeedback({ ...feedback, [row.id]: event.target.value })
                        }
                      />
                    </Field>
                  </div>

                  <Button
                    type="button"
                    size="sm"
                    className="mt-2"
                    disabled={busy === row.id || !marks[row.id]}
                    onClick={() =>
                      run(
                        row.id,
                        () => markAnswer(row.id, marks[row.id] ?? '', feedback[row.id] ?? ''),
                        `Marked ${row.student_name}'s answer.`,
                      )
                    }
                  >
                    Save mark
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Attempts ({attempts.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {attempts.length === 0 ? (
            <EmptyState title="Nobody has sat it yet" description="Attempts appear here." />
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Candidate</Th>
                    <Th>Submitted</Th>
                    <Th>Score</Th>
                    <Th>Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {attempts.map((attempt) => (
                    <tr key={attempt.id}>
                      <Td>
                        <div className="font-medium">{attempt.student_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {attempt.student_id}
                        </div>
                      </Td>
                      <Td>{formatDateTime(attempt.submitted_at)}</Td>
                      <Td>
                        {attempt.total_score === null
                          ? '—'
                          : `${attempt.total_score} / ${attempt.max_score}`}
                        {attempt.needs_manual_marking ? (
                          <div className="text-xs text-muted-foreground">awaiting marking</div>
                        ) : null}
                      </Td>
                      <Td>
                        <Badge variant={ATTEMPT_STATUS_VARIANT[attempt.status]}>
                          {ATTEMPT_STATUS_LABEL[attempt.status]}
                        </Badge>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function TeachingExamPage() {
  const params = useParams<{ examId: string }>();
  return (
    <RequireAuth>
      <ExamDetail examId={params.examId} />
    </RequireAuth>
  );
}
