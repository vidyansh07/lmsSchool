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
  LIFECYCLE_LABEL,
  LIFECYCLE_VARIANT,
  SUBMISSION_KIND_LABEL,
  SUBMISSION_STATUS_LABEL,
  SUBMISSION_STATUS_VARIANT,
  formatBytes,
  formatDateTime,
} from '@/lib/academic-labels';
import { NO_DATA } from '@/lib/format';
import {
  getAssignment,
  gradeSubmission,
  listSubmissions,
  returnSubmission,
  setAssignmentStatus,
  submissionFileUrl,
} from '@/lib/assignments';
import type { Assignment, StaffSubmission } from '@/types/api';

/** The brief, plus its marking queue. */
function AssignmentDetail({ assignmentId }: { assignmentId: string }) {
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [submissions, setSubmissions] = useState<StaffSubmission[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<Record<string, string>>({});

  // Reloading after an action, kept out of the effect so the initial fetch and
  // the refresh do not have to share a shape.
  const load = useCallback(async () => {
    const [brief, queue] = await Promise.all([
      getAssignment(assignmentId),
      listSubmissions(assignmentId),
    ]);
    setAssignment(brief);
    setSubmissions(queue.results);
    setMarks(Object.fromEntries(queue.results.map((row) => [row.id, row.marks_awarded ?? ''])));
    setFeedback(Object.fromEntries(queue.results.map((row) => [row.id, row.feedback])));
  }, [assignmentId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAssignment(assignmentId), listSubmissions(assignmentId)])
      .then(([brief, queue]) => {
        if (cancelled) return;
        setAssignment(brief);
        setSubmissions(queue.results);
        setMarks(
          Object.fromEntries(queue.results.map((row) => [row.id, row.marks_awarded ?? ''])),
        );
        setFeedback(Object.fromEntries(queue.results.map((row) => [row.id, row.feedback])));
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
  }, [assignmentId]);

  async function run(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key);
    setFormError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(message);
    } catch (cause) {
      setFormError(fieldErrors(cause).__all__ ?? 'That could not be done.');
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading the assignment…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the assignment"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!assignment) return null;

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={LIFECYCLE_VARIANT[assignment.status]}>
            {LIFECYCLE_LABEL[assignment.status]}
          </Badge>
          <span className="font-mono text-xs text-muted-foreground">{assignment.code}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{assignment.title}</h1>
        <p className="text-sm text-muted-foreground">
          {assignment.course_title}
          {assignment.batch_code ? ` · ${assignment.batch_code}` : ' · every batch'} ·{' '}
          {SUBMISSION_KIND_LABEL[assignment.submission_kind]} · out of {assignment.max_marks}
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
          <CardTitle>The brief</CardTitle>
          <CardDescription>
            Due {formatDateTime(assignment.due_at)}
            {assignment.allow_late ? ' · late work accepted and flagged' : ' · no late work'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {assignment.instructions ? (
            <p className="whitespace-pre-wrap text-sm">{assignment.instructions}</p>
          ) : (
            <p className="text-sm text-muted-foreground">No instructions were given.</p>
          )}

          <div className="flex flex-wrap gap-2">
            {assignment.status === 'draft' ? (
              <Button
                type="button"
                size="sm"
                disabled={busy === 'publish'}
                onClick={() =>
                  run(
                    'publish',
                    () => setAssignmentStatus(assignment.id, 'published'),
                    'Published. Students can see it now.',
                  )
                }
              >
                Publish
              </Button>
            ) : null}
            {assignment.status === 'published' ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy === 'close'}
                onClick={() =>
                  run(
                    'close',
                    () => setAssignmentStatus(assignment.id, 'closed'),
                    'Closed. No further submissions are accepted.',
                  )
                }
              >
                Close
              </Button>
            ) : null}
            {assignment.status === 'published' || assignment.status === 'closed' ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy === 'archive'}
                onClick={() =>
                  run(
                    'archive',
                    () => setAssignmentStatus(assignment.id, 'archived'),
                    'Archived. It is off the students\u2019 lists; their work is kept.',
                  )
                }
              >
                Archive
              </Button>
            ) : null}
          </div>
          {assignment.status === 'archived' ? (
            <p className="text-sm text-muted-foreground">
              Archived. Students no longer see this brief, and everything already handed in is
              unchanged \u2014 archiving retires the task, it does not undo anybody\u2019s work.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Submissions ({submissions.length})</CardTitle>
          <CardDescription>
            Files download rather than open — submitted code is never rendered in a browser.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {submissions.length === 0 ? (
            <EmptyState title="Nothing handed in yet" description="Submissions appear here." />
          ) : (
            <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
              <Table>
                <thead>
                  <tr>
                    <Th className="sticky top-0 z-10 bg-muted">Student</Th>
                    <Th className="sticky top-0 z-10 bg-muted">Submitted</Th>
                    <Th className="sticky top-0 z-10 bg-muted">Files</Th>
                    <Th className="sticky top-0 z-10 bg-muted">Mark</Th>
                    <Th className="sticky top-0 z-10 bg-muted">Action</Th>
                  </tr>
                </thead>
                <tbody className="stagger">
                  {submissions.map((row) => (
                    <tr key={row.id} className="animate-fade-in transition-colors hover:bg-muted/40">
                      <Td>
                        <div className="font-medium">{row.student_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {row.student_id}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          <Badge variant={SUBMISSION_STATUS_VARIANT[row.status]}>
                            {SUBMISSION_STATUS_LABEL[row.status]}
                          </Badge>
                          {row.is_late ? <Badge variant="warning">Late</Badge> : null}
                          <Badge variant="neutral">Attempt {row.attempt}</Badge>
                        </div>
                      </Td>
                      <Td>{formatDateTime(row.submitted_at)}</Td>
                      <Td>
                        {row.files.length === 0 ? (
                          <span className="text-muted-foreground">{NO_DATA}</span>
                        ) : (
                          <ul className="space-y-1">
                            {row.files.map((file) => (
                              <li key={file.id}>
                                <a
                                  className="underline hover:text-foreground"
                                  href={submissionFileUrl(file.id)}
                                >
                                  {file.original_filename}
                                </a>
                                <span className="ml-1 text-xs text-muted-foreground">
                                  {formatBytes(file.size_bytes)}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                        {row.text_answer ? (
                          <p className="mt-2 whitespace-pre-wrap text-xs">{row.text_answer}</p>
                        ) : null}
                        {row.link_url ? (
                          <a className="text-xs underline" href={row.link_url} rel="noreferrer">
                            {row.link_url}
                          </a>
                        ) : null}
                      </Td>
                      <Td className="min-w-56 space-y-2">
                        <Field label="Marks" htmlFor={`marks-${row.id}`}>
                          <Input
                            id={`marks-${row.id}`}
                            type="number"
                            min="0"
                            step="0.01"
                            max={assignment.max_marks}
                            value={marks[row.id] ?? ''}
                            onChange={(event) =>
                              setMarks({ ...marks, [row.id]: event.target.value })
                            }
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
                      </Td>
                      <Td className="space-y-2">
                        <Button
                          type="button"
                          size="sm"
                          disabled={busy === row.id || !marks[row.id]}
                          onClick={() =>
                            run(
                              row.id,
                              () =>
                                gradeSubmission(row.id, marks[row.id] ?? '', feedback[row.id] ?? ''),
                              `Graded ${row.student_name}.`,
                            )
                          }
                        >
                          Save grade
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busy === row.id || !feedback[row.id]}
                          onClick={() =>
                            run(
                              row.id,
                              () => returnSubmission(row.id, feedback[row.id] ?? ''),
                              `Returned to ${row.student_name} for rework.`,
                            )
                          }
                        >
                          Return for rework
                        </Button>
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

export default function TeachingAssignmentPage() {
  const params = useParams<{ assignmentId: string }>();
  return (
    <RequireAuth>
      <AssignmentDetail assignmentId={params.assignmentId} />
    </RequireAuth>
  );
}
