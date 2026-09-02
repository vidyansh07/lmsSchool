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
  PROJECT_KIND_LABEL,
  PROJECT_WORK_LABEL,
  PROJECT_WORK_VARIANT,
  formatDateTime,
} from '@/lib/academic-labels';
import {
  assignProject,
  getProject,
  listProjectWork,
  projectFileUrl,
  reviewProject,
  setProjectStatus,
} from '@/lib/projects';
import type { Project, ProjectWorkStatus, ReviewerProjectWork } from '@/types/api';

/**
 * The states a reviewer can act on.
 *
 * Mirrors the server's transition table: work that has not been handed in, or
 * has already been sent back, is not the reviewer's to decide on.
 */
const REVIEWABLE = new Set<ProjectWorkStatus>(['submitted', 'under_review']);

/** The brief, and the review queue for it. */
function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [queue, setQueue] = useState<ReviewerProjectWork[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [brief, work] = await Promise.all([
      getProject(projectId),
      listProjectWork(projectId),
    ]);
    setProject(brief);
    setQueue(work.results);
    setMarks(Object.fromEntries(work.results.map((row) => [row.id, row.marks_awarded ?? ''])));
    setFeedback(Object.fromEntries(work.results.map((row) => [row.id, row.feedback])));
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getProject(projectId), listProjectWork(projectId)])
      .then(([brief, work]) => {
        if (cancelled) return;
        setProject(brief);
        setQueue(work.results);
        setMarks(
          Object.fromEntries(work.results.map((row) => [row.id, row.marks_awarded ?? ''])),
        );
        setFeedback(Object.fromEntries(work.results.map((row) => [row.id, row.feedback])));
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
  }, [projectId]);

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

  if (isLoading) return <LoadingState label="Loading the project…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the project"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!project) return null;

  const hasRubric = project.rubric.length > 0;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={LIFECYCLE_VARIANT[project.status]}>
            {LIFECYCLE_LABEL[project.status]}
          </Badge>
          {project.is_required ? <Badge variant="warning">Required</Badge> : null}
          <span className="font-mono text-xs text-muted-foreground">{project.code}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
        <p className="text-sm text-muted-foreground">
          {project.course_title}
          {project.batch_code ? ` · ${project.batch_code}` : ' · every batch'} ·{' '}
          {PROJECT_KIND_LABEL[project.kind]} · out of {project.max_marks}
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
          <CardDescription>Due {project.end_date ?? 'no date set'}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {project.description ? (
            <p className="whitespace-pre-wrap text-sm">{project.description}</p>
          ) : null}
          {project.deliverables ? (
            <p className="text-sm">
              <span className="font-medium">Deliverables: </span>
              {project.deliverables}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {project.status === 'draft' ? (
              <Button
                type="button"
                size="sm"
                disabled={busy === 'publish'}
                onClick={() =>
                  run(
                    'publish',
                    () => setProjectStatus(project.id, 'published'),
                    'Published. Students can see it now.',
                  )
                }
              >
                Publish
              </Button>
            ) : null}
            {project.status === 'published' ? (
              <>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy === 'assign'}
                  onClick={() =>
                    run('assign', () => assignProject(project.id), 'Assigned to the cohort.')
                  }
                >
                  Assign to the cohort
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy === 'close'}
                  onClick={() =>
                    run(
                      'close',
                      () => setProjectStatus(project.id, 'closed'),
                      'Closed. No further submissions are accepted.',
                    )
                  }
                >
                  Close
                </Button>
              </>
            ) : null}
            {project.status === 'published' || project.status === 'closed' ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy === 'archive'}
                onClick={() =>
                  run(
                    'archive',
                    () => setProjectStatus(project.id, 'archived'),
                    'Archived. It is off the students\u2019 lists; their work is kept.',
                  )
                }
              >
                Archive
              </Button>
            ) : null}
          </div>
          {project.status === 'archived' ? (
            <p className="text-sm text-muted-foreground">
              Archived. Students no longer see this brief, and the work already handed in is
              unchanged \u2014 archiving retires the brief, it does not undo anybody\u2019s
              submission.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Submitted work ({queue.length})</CardTitle>
          <CardDescription>
            {hasRubric
              ? 'This project is marked against a rubric, so the total is summed by the server.'
              : 'Approve with a mark, or send it back with a reason.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {queue.length === 0 ? (
            <EmptyState
              title="Nobody has this project yet"
              description="Assign it to the cohort, or wait for a student to open it."
            />
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Student</Th>
                    <Th>Handed in</Th>
                    <Th>Deliverables</Th>
                    <Th>Decision</Th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((row) => (
                    <tr key={row.id}>
                      <Td>
                        <div className="font-medium">{row.student_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {row.student_id}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          <Badge variant={PROJECT_WORK_VARIANT[row.status]}>
                            {PROJECT_WORK_LABEL[row.status]}
                          </Badge>
                          {row.is_late ? <Badge variant="warning">Late</Badge> : null}
                        </div>
                      </Td>
                      <Td>
                        {formatDateTime(row.submitted_at)}
                        {row.submission_count > 1 ? (
                          <div className="text-xs text-muted-foreground">
                            {row.submission_count} submissions
                          </div>
                        ) : null}
                      </Td>
                      <Td>
                        {row.files.length > 0 ? (
                          <ul className="space-y-1">
                            {row.files.map((file) => (
                              <li key={file.id}>
                                <a
                                  className="underline hover:text-foreground"
                                  href={projectFileUrl(file.id)}
                                >
                                  {file.original_filename}
                                </a>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {row.repository_url ? (
                          <a className="block text-xs underline" href={row.repository_url}>
                            {row.repository_url}
                          </a>
                        ) : null}
                        {row.deployment_url ? (
                          <a className="block text-xs underline" href={row.deployment_url}>
                            {row.deployment_url}
                          </a>
                        ) : null}
                      </Td>
                      <Td className="min-w-64 space-y-2">
                        {!REVIEWABLE.has(row.status) ? (
                          <p className="text-sm text-muted-foreground">
                            {row.status === 'rework'
                              ? 'Sent back. Waiting for the student to resubmit.'
                              : row.status === 'approved' || row.status === 'completed'
                                ? 'Reviewed.'
                                : 'Not handed in yet.'}
                          </p>
                        ) : null}
                        {hasRubric || !REVIEWABLE.has(row.status) ? null : (
                          <Field label="Marks" htmlFor={`marks-${row.id}`}>
                            <Input
                              id={`marks-${row.id}`}
                              type="number"
                              min="0"
                              step="0.01"
                              max={project.max_marks}
                              value={marks[row.id] ?? ''}
                              onChange={(event) =>
                                setMarks({ ...marks, [row.id]: event.target.value })
                              }
                            />
                          </Field>
                        )}
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
                        <div
                          className={REVIEWABLE.has(row.status) ? 'flex flex-wrap gap-2' : 'hidden'}
                        >
                          <Button
                            type="button"
                            size="sm"
                            disabled={busy === row.id || (!hasRubric && !marks[row.id])}
                            onClick={() =>
                              run(
                                row.id,
                                () =>
                                  reviewProject(row.id, {
                                    outcome: 'approved',
                                    marks: hasRubric ? undefined : marks[row.id],
                                    rubric_scores: hasRubric
                                      ? Object.fromEntries(
                                          project.rubric.map((criterion) => [
                                            criterion.key,
                                            marks[`${row.id}:${criterion.key}`] ?? '0',
                                          ]),
                                        )
                                      : undefined,
                                    feedback: feedback[row.id] ?? '',
                                  }),
                                `Approved ${row.student_name}.`,
                              )
                            }
                          >
                            Approve
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy === row.id || !feedback[row.id]}
                            onClick={() =>
                              run(
                                row.id,
                                () =>
                                  reviewProject(row.id, {
                                    outcome: 'rework',
                                    feedback: feedback[row.id] ?? '',
                                  }),
                                `Sent back to ${row.student_name}.`,
                              )
                            }
                          >
                            Request rework
                          </Button>
                        </div>
                        {hasRubric && REVIEWABLE.has(row.status) ? (
                          <div className="space-y-1">
                            {project.rubric.map((criterion) => (
                              <Field
                                key={criterion.key}
                                label={`${criterion.label} (max ${criterion.max_marks})`}
                                htmlFor={`${row.id}-${criterion.key}`}
                              >
                                <Input
                                  id={`${row.id}-${criterion.key}`}
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  max={criterion.max_marks}
                                  value={marks[`${row.id}:${criterion.key}`] ?? ''}
                                  onChange={(event) =>
                                    setMarks({
                                      ...marks,
                                      [`${row.id}:${criterion.key}`]: event.target.value,
                                    })
                                  }
                                />
                              </Field>
                            ))}
                          </div>
                        ) : null}
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

export default function TeachingProjectPage() {
  const params = useParams<{ projectId: string }>();
  return (
    <RequireAuth>
      <ProjectDetail projectId={params.projectId} />
    </RequireAuth>
  );
}
