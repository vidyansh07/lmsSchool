'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import { LIFECYCLE_LABEL, LIFECYCLE_VARIANT, PROJECT_KIND_LABEL } from '@/lib/academic-labels';
import { formatDate, NO_DATA } from '@/lib/format';
import { createProject, listProjects } from '@/lib/projects';
import { listBatches } from '@/lib/batches';
import type { BatchListRow, Project, ProjectKind } from '@/types/api';

/** Projects a trainer has set. */
function Projects() {
  const router = useRouter();
  const [rows, setRows] = useState<Project[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState({
    batch: '',
    title: '',
    description: '',
    deliverables: '',
    kind: 'small' as ProjectKind,
    is_required: true,
    end_date: '',
    max_marks: '',
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listProjects(), listBatches({ page_size: 100 })])
      .then(([projects, batchPage]) => {
        if (cancelled) return;
        setRows(projects.results);
        setBatches(batchPage.results);
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

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const batch = batches.find((row) => row.id === form.batch);
    if (!batch) {
      setErrors({ batch: 'Choose a batch.' });
      return;
    }
    setIsSaving(true);
    setErrors({});
    try {
      await createProject(batch.course_id, {
        title: form.title,
        description: form.description || undefined,
        deliverables: form.deliverables || undefined,
        kind: form.kind,
        is_required: form.is_required,
        end_date: form.end_date || undefined,
        max_marks: form.max_marks || undefined,
        batch: batch.id,
      });
      setIsOpen(false);
      setRows((await listProjects()).results);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading projects…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load projects"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="animate-rise-in space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Longer work, reviewed rather than simply marked. New projects start as drafts.
          </p>
        </div>
        <Button type="button" onClick={() => setIsOpen((open) => !open)}>
          {isOpen ? 'Cancel' : 'New project'}
        </Button>
      </div>

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>New project</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

              <Field
                label="Batch"
                htmlFor="batch"
                error={errors.batch ?? errors.course}
                hint="The course is taken from the batch."
              >
                <Select
                  id="batch"
                  required
                  value={form.batch}
                  onChange={(event) => setForm({ ...form, batch: event.target.value })}
                >
                  <option value="">Choose a batch…</option>
                  {batches.map((batch) => (
                    <option key={batch.id} value={batch.id}>
                      {batch.code} · {batch.name} · {batch.course_title}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Title" htmlFor="title" error={errors.title}>
                <Input
                  id="title"
                  required
                  maxLength={200}
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </Field>

              <Field label="Description" htmlFor="description" error={errors.description}>
                <Textarea
                  id="description"
                  rows={3}
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </Field>

              <Field label="Deliverables" htmlFor="deliverables" error={errors.deliverables}>
                <Textarea
                  id="deliverables"
                  rows={2}
                  value={form.deliverables}
                  onChange={(event) => setForm({ ...form, deliverables: event.target.value })}
                />
              </Field>

              <Field label="Kind" htmlFor="kind" error={errors.kind}>
                <Select
                  id="kind"
                  value={form.kind}
                  onChange={(event) =>
                    setForm({ ...form, kind: event.target.value as ProjectKind })
                  }
                >
                  {Object.entries(PROJECT_KIND_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Required" htmlFor="is_required">
                <label className="flex items-center gap-2 text-sm" htmlFor="is_required">
                  <input
                    id="is_required"
                    type="checkbox"
                    checked={form.is_required}
                    onChange={(event) =>
                      setForm({ ...form, is_required: event.target.checked })
                    }
                  />
                  Must be finished before the course can be completed
                </label>
              </Field>

              <Field label="Due" htmlFor="end_date" error={errors.end_date}>
                <Input
                  id="end_date"
                  type="date"
                  value={form.end_date}
                  onChange={(event) => setForm({ ...form, end_date: event.target.value })}
                />
              </Field>

              <Field label="Marks out of" htmlFor="max_marks" error={errors.max_marks}>
                <Input
                  id="max_marks"
                  type="number"
                  min="1"
                  step="0.01"
                  value={form.max_marks}
                  onChange={(event) => setForm({ ...form, max_marks: event.target.value })}
                />
              </Field>

              <Button type="submit" disabled={isSaving || !form.batch}>
                {isSaving ? 'Creating…' : 'Create project'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="No projects yet" description="Set one with the button above." />
      ) : (
        <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
          <Table>
            <thead>
              <tr>
                <Th className="sticky top-0 z-10 bg-muted">Project</Th>
                <Th className="sticky top-0 z-10 bg-muted">Course</Th>
                <Th className="sticky top-0 z-10 bg-muted">Due</Th>
                <Th className="sticky top-0 z-10 bg-muted">Status</Th>
              </tr>
            </thead>
            <tbody className="stagger">
              {rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => router.push(`/teaching/projects/${row.id}`)}
                  className="animate-fade-in cursor-pointer transition-colors hover:bg-muted/60 active:bg-muted"
                >
                  <Td>
                    <Link
                      href={`/teaching/projects/${row.id}`}
                      onClick={(event) => event.stopPropagation()}
                      className="font-medium underline hover:text-foreground"
                    >
                      {row.title}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{row.code}</div>
                    <div className="text-xs text-muted-foreground">
                      {PROJECT_KIND_LABEL[row.kind]}
                      {row.is_required ? ' · required' : ' · optional'}
                    </div>
                  </Td>
                  <Td>
                    {row.course_title}
                    {row.batch_code ? ` · ${row.batch_code}` : ''}
                  </Td>
                  <Td>{formatDate(row.end_date, NO_DATA)}</Td>
                  <Td>
                    <Badge variant={LIFECYCLE_VARIANT[row.status]}>
                      {LIFECYCLE_LABEL[row.status]}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}
    </div>
  );
}

export default function TeachingProjectsPage() {
  return (
    <RequireAuth>
      <Projects />
    </RequireAuth>
  );
}
