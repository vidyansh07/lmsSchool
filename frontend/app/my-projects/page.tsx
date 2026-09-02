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
  PROJECT_KIND_LABEL,
  PROJECT_WORK_LABEL,
  PROJECT_WORK_VARIANT,
  formatBytes,
  formatDateTime,
} from '@/lib/academic-labels';
import {
  listMyProjects,
  listRequiredProjectProgress,
  projectFileUrl,
  submitProjectWork,
} from '@/lib/projects';
import type { RequiredProjectProgress, StudentProject, StudentProjectWork } from '@/types/api';

/** A student's projects, with the hand-in form on the same screen. */
function MyProjects() {
  const [rows, setRows] = useState<StudentProject[]>([]);
  const [work, setWork] = useState<Record<string, StudentProjectWork>>({});
  const [progress, setProgress] = useState<RequiredProjectProgress[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, Record<string, string>>>({});
  const [drafts, setDrafts] = useState<
    Record<string, { repository_url: string; deployment_url: string; notes: string }>
  >({});
  const [files, setFiles] = useState<Record<string, FileList | null>>({});

  const load = useCallback(async () => {
    const [projects, required] = await Promise.all([
      listMyProjects({ ordering: 'end_date' }),
      listRequiredProjectProgress(),
    ]);
    setRows(projects.results);
    setProgress(required);
    setWork(
      Object.fromEntries(
        projects.results
          .filter((project) => project.my_work !== null)
          .map((project) => [project.id, project.my_work as StudentProjectWork]),
      ),
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMyProjects({ ordering: 'end_date' }), listRequiredProjectProgress()])
      .then(([projects, required]) => {
        if (cancelled) return;
        setRows(projects.results);
        setProgress(required);
        // The list already carries each project's own row — one request, not
        // one plus one per project.
        setWork(
          Object.fromEntries(
            projects.results
              .filter((project) => project.my_work !== null)
              .map((project) => [project.id, project.my_work as StudentProjectWork]),
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

  async function hand(project: StudentProject, event: React.FormEvent) {
    event.preventDefault();
    setBusy(project.id);
    setNotice(null);
    setErrors({ ...errors, [project.id]: {} });
    try {
      const chosen = files[project.id];
      const draft = drafts[project.id] ?? {
        repository_url: '',
        deployment_url: '',
        notes: '',
      };
      await submitProjectWork(project.id, {
        files: chosen ? Array.from(chosen) : [],
        repository_url: draft.repository_url,
        deployment_url: draft.deployment_url,
        notes: draft.notes,
      });
      setFiles({ ...files, [project.id]: null });
      await load();
      setNotice(`Handed in "${project.title}".`);
    } catch (cause) {
      setErrors({ ...errors, [project.id]: fieldErrors(cause) });
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading your projects…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your projects"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My projects</h1>
        <p className="text-sm text-muted-foreground">
          Project work set on your courses, and where each one stands.
        </p>
      </div>

      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      {progress.map((row) => (
        <Card key={row.enrollment_id} data-testid="required-progress">
          <CardHeader>
            <CardTitle>{row.course_title}</CardTitle>
            <CardDescription>
              {row.finished} of {row.required} required projects finished
              {row.met ? '' : ` · outstanding: ${row.outstanding.map((p) => p.title).join(', ')}`}
            </CardDescription>
          </CardHeader>
        </Card>
      ))}

      {rows.length === 0 ? (
        <EmptyState
          title="No projects yet"
          description="Projects appear here once your trainer publishes them."
        />
      ) : (
        rows.map((project) => {
          const mine = work[project.id];
          const problems = errors[project.id] ?? {};
          const draft = drafts[project.id] ?? {
            repository_url: mine?.repository_url ?? '',
            deployment_url: mine?.deployment_url ?? '',
            notes: mine?.notes ?? '',
          };
          const canSubmit = project.is_open && (mine?.is_open_to_student ?? true);

          return (
            <Card key={project.id} data-testid="project-card">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{project.code}</span>
                  {mine ? (
                    <Badge variant={PROJECT_WORK_VARIANT[mine.status]}>
                      {PROJECT_WORK_LABEL[mine.status]}
                    </Badge>
                  ) : null}
                  {project.is_required ? <Badge variant="warning">Required</Badge> : null}
                </div>
                <CardTitle>{project.title}</CardTitle>
                <CardDescription>
                  {project.course_title} · {PROJECT_KIND_LABEL[project.kind]} · due{' '}
                  {project.end_date ?? 'no date set'} · out of {project.max_marks}
                </CardDescription>
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

                {mine && mine.submission_count > 0 ? (
                  <div className="rounded-md border border-border p-3 text-sm">
                    <p className="font-medium">
                      Handed in {formatDateTime(mine.submitted_at)}
                      {mine.submission_count > 1 ? ` (${mine.submission_count} times)` : ''}
                    </p>
                    {mine.files.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {mine.files.map((file) => (
                          <li key={file.id}>
                            <a
                              className="underline hover:text-foreground"
                              href={projectFileUrl(file.id)}
                            >
                              {file.original_filename}
                            </a>
                            <span className="ml-1 text-xs text-muted-foreground">
                              {formatBytes(file.size_bytes)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {mine.marks_awarded !== null ? (
                      <p className="mt-2" data-testid="project-grade">
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
                      <p
                        className="mt-2 whitespace-pre-wrap text-muted-foreground"
                        data-testid="project-feedback"
                      >
                        {mine.feedback}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {canSubmit ? (
                  <form className="space-y-3" onSubmit={(event) => hand(project, event)}>
                    {problems.__all__ ? <Alert variant="error">{problems.__all__}</Alert> : null}
                    {problems.project ? <Alert variant="error">{problems.project}</Alert> : null}

                    <Field
                      label="Files"
                      htmlFor={`files-${project.id}`}
                      error={problems.files}
                      hint="Source code, documents or a zip. Executables are refused."
                    >
                      <Input
                        id={`files-${project.id}`}
                        type="file"
                        multiple
                        onChange={(event) =>
                          setFiles({ ...files, [project.id]: event.target.files })
                        }
                      />
                    </Field>

                    <Field
                      label="Repository URL"
                      htmlFor={`repo-${project.id}`}
                      error={problems.repository_url}
                    >
                      <Input
                        id={`repo-${project.id}`}
                        type="url"
                        value={draft.repository_url}
                        onChange={(event) =>
                          setDrafts({
                            ...drafts,
                            [project.id]: { ...draft, repository_url: event.target.value },
                          })
                        }
                      />
                    </Field>

                    <Field label="Notes" htmlFor={`notes-${project.id}`} error={problems.notes}>
                      <Textarea
                        id={`notes-${project.id}`}
                        rows={2}
                        value={draft.notes}
                        onChange={(event) =>
                          setDrafts({
                            ...drafts,
                            [project.id]: { ...draft, notes: event.target.value },
                          })
                        }
                      />
                    </Field>

                    <Button type="submit" size="sm" disabled={busy === project.id}>
                      {busy === project.id ? 'Handing in…' : 'Hand in'}
                    </Button>
                  </form>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {!project.is_open
                      ? 'This project is closed.'
                      : 'Your work is with your reviewer.'}
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

export default function MyProjectsPage() {
  return (
    <RequireAuth>
      <MyProjects />
    </RequireAuth>
  );
}
