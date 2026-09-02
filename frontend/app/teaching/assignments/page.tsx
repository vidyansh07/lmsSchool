'use client';

import Link from 'next/link';
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
import { LIFECYCLE_LABEL, LIFECYCLE_VARIANT, formatDateTime } from '@/lib/academic-labels';
import { createAssignment, listAssignments } from '@/lib/assignments';
import { listBatches } from '@/lib/batches';
import type { Assignment, BatchListRow } from '@/types/api';

/** Set work, and see what has been set. */
function Assignments() {
  const [rows, setRows] = useState<Assignment[]>([]);
  // Work is set from a *batch*, and the course is derived from it. A trainer's
  // authority comes from the batches they teach, so offering them a course they
  // cannot set work on would be a menu item that only ever fails.
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);

  const [form, setForm] = useState({
    batch: '',
    everyBatch: false,
    title: '',
    instructions: '',
    max_marks: '',
    due_at: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  async function reload() {
    setRows((await listAssignments({ ordering: '-created_at' })).results);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAssignments({ ordering: '-created_at' }), listBatches({ page_size: 100 })])
      .then(([assignments, batchPage]) => {
        if (cancelled) return;
        setRows(assignments.results);
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
    setIsSaving(true);
    setErrors({});
    const batch = batches.find((row) => row.id === form.batch);
    if (!batch) {
      setErrors({ batch: 'Choose a batch.' });
      setIsSaving(false);
      return;
    }
    try {
      await createAssignment(batch.course_id, {
        title: form.title,
        instructions: form.instructions || undefined,
        max_marks: form.max_marks || undefined,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : undefined,
        batch: form.everyBatch ? undefined : batch.id,
      });
      setForm({
        batch: '',
        everyBatch: false,
        title: '',
        instructions: '',
        max_marks: '',
        due_at: '',
      });
      setIsOpen(false);
      await reload();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading assignments…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load assignments"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Assignments</h1>
          <p className="text-sm text-muted-foreground">
            Work you have set. New work starts as a draft until you publish it.
          </p>
        </div>
        <Button type="button" onClick={() => setIsOpen((open) => !open)}>
          {isOpen ? 'Cancel' : 'New assignment'}
        </Button>
      </div>

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>New assignment</CardTitle>
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

              <Field label="Applies to" htmlFor="every-batch">
                <label className="flex items-center gap-2 text-sm" htmlFor="every-batch">
                  <input
                    id="every-batch"
                    type="checkbox"
                    checked={form.everyBatch}
                    onChange={(event) =>
                      setForm({ ...form, everyBatch: event.target.checked })
                    }
                  />
                  Set this for every batch running the course
                </label>
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

              <Field label="Instructions" htmlFor="instructions" error={errors.instructions}>
                <Textarea
                  id="instructions"
                  rows={4}
                  value={form.instructions}
                  onChange={(event) => setForm({ ...form, instructions: event.target.value })}
                />
              </Field>

              <Field
                label="Marks out of"
                htmlFor="max_marks"
                error={errors.max_marks}
                hint="Leave empty to use the institution's default."
              >
                <Input
                  id="max_marks"
                  type="number"
                  min="1"
                  step="0.01"
                  value={form.max_marks}
                  onChange={(event) => setForm({ ...form, max_marks: event.target.value })}
                />
              </Field>

              <Field label="Due" htmlFor="due_at" error={errors.due_at}>
                <Input
                  id="due_at"
                  type="datetime-local"
                  value={form.due_at}
                  onChange={(event) => setForm({ ...form, due_at: event.target.value })}
                />
              </Field>

              <Button type="submit" disabled={isSaving || !form.batch}>
                {isSaving ? 'Creating…' : 'Create assignment'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState
          title="No assignments yet"
          description="Set your first piece of work with the button above."
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Assignment</Th>
                <Th>Course</Th>
                <Th>Due</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <Td>
                    <Link
                      href={`/teaching/assignments/${row.id}`}
                      className="font-medium underline hover:text-foreground"
                    >
                      {row.title}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{row.code}</div>
                  </Td>
                  <Td>
                    {row.course_title}
                    {row.batch_code ? ` · ${row.batch_code}` : ''}
                  </Td>
                  <Td>{formatDateTime(row.due_at)}</Td>
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

export default function TeachingAssignmentsPage() {
  return (
    <RequireAuth>
      <Assignments />
    </RequireAuth>
  );
}
