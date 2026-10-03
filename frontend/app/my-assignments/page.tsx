'use client';

import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import {
  SUBMISSION_KIND_LABEL,
  SUBMISSION_STATUS_LABEL,
  SUBMISSION_STATUS_VARIANT,
  formatBytes,
  formatDateTime,
} from '@/lib/academic-labels';
import { listMyAssignments, submissionFileUrl, submitAssignment } from '@/lib/assignments';
import type { StudentAssignment, SubmissionKind } from '@/types/api';

/**
 * Which inputs a hand-in form offers, per `submission_kind`.
 *
 * The backend's `_check_content` refuses a submission whose content does not
 * match the kind: `file` needs files, `text` needs a written answer, `link`
 * needs a link, `any` needs at least one of the three. The form used to be
 * built from two negations -- "not text, so show files" and "not file, so show
 * a textarea" -- which produced the right fields for three kinds and, for
 * `link`, a file picker and a textarea and no URL box at all. A link
 * assignment could not be handed in from this screen.
 *
 * Written as the positive statement of what each kind asks for, so a fourth
 * kind is one row here rather than a third negation to reason about.
 */
const KIND_FIELDS: Record<SubmissionKind, readonly SubmissionField[]> = {
  file: ['files'],
  text: ['text_answer'],
  link: ['link_url'],
  any: ['files', 'text_answer', 'link_url'],
};

type SubmissionField = 'files' | 'text_answer' | 'link_url';

function wants(kind: SubmissionKind, field: SubmissionField): boolean {
  return KIND_FIELDS[kind].includes(field);
}

/**
 * Field errors that no input on this form can display.
 *
 * `fieldErrors` returns the API's `details` keyed by field, and each `Field`
 * renders its own. Anything left over -- `__all__`, `assignment`, or a field
 * this kind does not show -- would otherwise be dropped on the floor: that is
 * how a `link_url` refusal on a form with no link box became a Submit button
 * that appeared to do nothing at all.
 */
function unplacedErrors(
  problems: Record<string, string>,
  kind: SubmissionKind,
): [string, string][] {
  const shown = new Set<string>(KIND_FIELDS[kind]);
  return Object.entries(problems).filter(([field]) => !shown.has(field));
}

/** A student's work list, with the hand-in form on the same screen. */
function MyAssignments() {
  const [rows, setRows] = useState<StudentAssignment[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, Record<string, string>>>({});
  const [files, setFiles] = useState<Record<string, FileList | null>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [links, setLinks] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setRows((await listMyAssignments({ ordering: 'due_at' })).results);
  }, []);

  useEffect(() => {
    let cancelled = false;
    listMyAssignments({ ordering: 'due_at' })
      .then((page) => {
        if (!cancelled) setRows(page.results);
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

  async function hand(assignment: StudentAssignment, event: React.FormEvent) {
    event.preventDefault();
    setBusy(assignment.id);
    setNotice(null);
    setErrors({ ...errors, [assignment.id]: {} });
    try {
      const chosen = files[assignment.id];
      await submitAssignment(assignment.id, {
        files: chosen ? Array.from(chosen) : [],
        text_answer: answers[assignment.id] ?? '',
        link_url: links[assignment.id] ?? '',
      });
      setFiles({ ...files, [assignment.id]: null });
      setAnswers({ ...answers, [assignment.id]: '' });
      setLinks({ ...links, [assignment.id]: '' });
      await load();
      setNotice(`Submitted "${assignment.title}".`);
    } catch (cause) {
      setErrors({ ...errors, [assignment.id]: fieldErrors(cause) });
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading your assignments…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your assignments"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My assignments</h1>
        <p className="text-sm text-ink-muted">
          Work set on your courses, with what you have handed in.
        </p>
      </div>

      {notice ? (
        <Alert variant="success" role="status" className="">
          {notice}
        </Alert>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing set yet"
          description="Assignments appear here once your trainer publishes them."
        />
      ) : (
        rows.map((assignment) => {
          const mine = assignment.my_submission;
          const problems = errors[assignment.id] ?? {};
          const canSubmit =
            assignment.is_open &&
            (mine === null ||
              mine.status === 'returned' ||
              (assignment.allow_resubmission &&
                mine.status !== 'graded' &&
                mine.attempt < assignment.max_attempts));

          return (
            <Card key={assignment.id} data-testid="assignment-card" className="">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-ink-muted">
                    {assignment.code}
                  </span>
                  {mine ? (
                    <Badge variant={SUBMISSION_STATUS_VARIANT[mine.status]}>
                      {SUBMISSION_STATUS_LABEL[mine.status]}
                    </Badge>
                  ) : (
                    <Badge variant={assignment.is_open ? 'warning' : 'neutral'}>
                      {assignment.is_open ? 'Not submitted' : 'Closed'}
                    </Badge>
                  )}
                  {mine?.is_late ? <Badge variant="warning">Late</Badge> : null}
                </div>
                <CardTitle>{assignment.title}</CardTitle>
                <CardDescription>
                  {assignment.course_title} · due {formatDateTime(assignment.due_at)} · out of{' '}
                  {assignment.max_marks} · {SUBMISSION_KIND_LABEL[assignment.submission_kind]}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                {assignment.instructions ? (
                  <p className="whitespace-pre-wrap text-sm">{assignment.instructions}</p>
                ) : null}

                {mine ? (
                  <div className="rounded-md border border-line p-3 text-sm">
                    <p className="font-medium">
                      Attempt {mine.attempt} · submitted {formatDateTime(mine.submitted_at)}
                    </p>
                    {mine.files.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {mine.files.map((file) => (
                          <li key={file.id}>
                            <a
                              className="underline hover:text-ink"
                              href={submissionFileUrl(file.id)}
                            >
                              {file.original_filename}
                            </a>
                            <span className="ml-1 text-xs text-ink-muted">
                              {formatBytes(file.size_bytes)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {mine.marks_awarded !== null ? (
                      <p className="mt-2" data-testid="my-grade">
                        <span className="font-semibold">
                          {mine.marks_awarded} / {mine.max_marks}
                        </span>
                        {mine.is_passing === null ? null : (
                          <Badge
                            className="ml-2"
                            variant={mine.is_passing ? 'success' : 'error'}
                          >
                            {mine.is_passing ? 'Pass' : 'Below the pass mark'}
                          </Badge>
                        )}
                      </p>
                    ) : null}
                    {mine.feedback ? (
                      <p className="mt-2 whitespace-pre-wrap text-ink-muted">
                        {mine.feedback}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {canSubmit ? (
                  <form className="space-y-3" onSubmit={(event) => hand(assignment, event)}>
                    {unplacedErrors(problems, assignment.submission_kind).map(
                      ([field, message]) => (
                        <Alert variant="error" key={field}>
                          {message}
                        </Alert>
                      ),
                    )}

                    {wants(assignment.submission_kind, 'files') ? (
                      <Field
                        label="Files"
                        htmlFor={`files-${assignment.id}`}
                        error={problems.files}
                        hint="Source code, documents or a zip. Executables are refused."
                      >
                        <Input
                          id={`files-${assignment.id}`}
                          type="file"
                          multiple
                          onChange={(event) =>
                            setFiles({ ...files, [assignment.id]: event.target.files })
                          }
                        />
                      </Field>
                    ) : null}

                    {wants(assignment.submission_kind, 'text_answer') ? (
                      <Field
                        label="Written answer"
                        htmlFor={`text-${assignment.id}`}
                        error={problems.text_answer}
                      >
                        <Textarea
                          id={`text-${assignment.id}`}
                          rows={4}
                          value={answers[assignment.id] ?? ''}
                          onChange={(event) =>
                            setAnswers({ ...answers, [assignment.id]: event.target.value })
                          }
                        />
                      </Field>
                    ) : null}

                    {wants(assignment.submission_kind, 'link_url') ? (
                      <Field
                        label="Link"
                        htmlFor={`link-${assignment.id}`}
                        error={problems.link_url}
                        hint="A repository, a published notebook or a deployed URL."
                      >
                        <Input
                          id={`link-${assignment.id}`}
                          type="url"
                          inputMode="url"
                          placeholder="https://"
                          value={links[assignment.id] ?? ''}
                          onChange={(event) =>
                            setLinks({ ...links, [assignment.id]: event.target.value })
                          }
                        />
                      </Field>
                    ) : null}

                    <Button type="submit" size="sm" disabled={busy === assignment.id}>
                      {busy === assignment.id ? 'Submitting…' : 'Submit'}
                    </Button>
                  </form>
                ) : (
                  <p className="text-sm text-ink-muted">
                    {!assignment.is_open
                      ? 'This assignment is closed.'
                      : mine?.status === 'graded'
                        ? 'This has been graded and cannot be resubmitted.'
                        : 'You have used your submissions for this assignment.'}
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}

export default function MyAssignmentsPage() {
  return (
    <RequireAuth>
      <MyAssignments />
    </RequireAuth>
  );
}
