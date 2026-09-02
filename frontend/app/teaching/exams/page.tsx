'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import { LIFECYCLE_LABEL, LIFECYCLE_VARIANT, formatDateTime } from '@/lib/academic-labels';
import { createExam, listExams } from '@/lib/exams';
import { listBatches } from '@/lib/batches';
import type { BatchListRow, Exam } from '@/types/api';

/** Examinations, and the form that sets one. */
function Exams() {
  const [rows, setRows] = useState<Exam[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState({
    batch: '',
    title: '',
    instructions: '',
    duration_minutes: '60',
    max_attempts: '1',
    negative_marking: false,
    opens_at: '',
    closes_at: '',
    section_title: 'Section A',
    question_count: '5',
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listExams(), listBatches({ page_size: 100 })])
      .then(([examPage, batchPage]) => {
        if (cancelled) return;
        setRows(examPage.results);
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
    try {
      await createExam(form.batch, {
        title: form.title,
        instructions: form.instructions || undefined,
        duration_minutes: Number(form.duration_minutes),
        max_attempts: Number(form.max_attempts),
        negative_marking: form.negative_marking,
        opens_at: form.opens_at ? new Date(form.opens_at).toISOString() : undefined,
        closes_at: form.closes_at ? new Date(form.closes_at).toISOString() : undefined,
        sections: [
          { title: form.section_title, question_count: Number(form.question_count) },
        ],
      });
      setIsOpen(false);
      setRows((await listExams()).results);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading examinations…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load examinations"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Examinations</h1>
          <p className="text-sm text-muted-foreground">
            Papers are drawn from the question bank when each candidate starts.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href="/teaching/questions">Question bank</Link>
          </Button>
          <Button type="button" onClick={() => setIsOpen((open) => !open)}>
            {isOpen ? 'Cancel' : 'New examination'}
          </Button>
        </div>
      </div>

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>New examination</CardTitle>
            <CardDescription>
              It starts as a draft. Publishing checks the bank has enough questions first.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
              {errors.sections ? <Alert variant="error">{errors.sections}</Alert> : null}

              <Field label="Batch" htmlFor="batch" error={errors.batch}>
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

              <Field label="Instructions" htmlFor="instructions" error={errors.instructions}>
                <Textarea
                  id="instructions"
                  rows={2}
                  value={form.instructions}
                  onChange={(event) => setForm({ ...form, instructions: event.target.value })}
                />
              </Field>

              <Field
                label="Duration in minutes"
                htmlFor="duration_minutes"
                error={errors.duration_minutes}
              >
                <Input
                  id="duration_minutes"
                  type="number"
                  min="1"
                  max="1440"
                  value={form.duration_minutes}
                  onChange={(event) =>
                    setForm({ ...form, duration_minutes: event.target.value })
                  }
                />
              </Field>

              <Field label="Attempts allowed" htmlFor="max_attempts" error={errors.max_attempts}>
                <Input
                  id="max_attempts"
                  type="number"
                  min="1"
                  max="10"
                  value={form.max_attempts}
                  onChange={(event) => setForm({ ...form, max_attempts: event.target.value })}
                />
              </Field>

              <Field label="Negative marking" htmlFor="negative_marking">
                <label className="flex items-center gap-2 text-sm" htmlFor="negative_marking">
                  <input
                    id="negative_marking"
                    type="checkbox"
                    checked={form.negative_marking}
                    onChange={(event) =>
                      setForm({ ...form, negative_marking: event.target.checked })
                    }
                  />
                  Deduct each question&apos;s negative marks for a wrong answer
                </label>
              </Field>

              <Field label="Opens" htmlFor="opens_at" error={errors.opens_at}>
                <Input
                  id="opens_at"
                  type="datetime-local"
                  value={form.opens_at}
                  onChange={(event) => setForm({ ...form, opens_at: event.target.value })}
                />
              </Field>

              <Field label="Closes" htmlFor="closes_at" error={errors.closes_at}>
                <Input
                  id="closes_at"
                  type="datetime-local"
                  value={form.closes_at}
                  onChange={(event) => setForm({ ...form, closes_at: event.target.value })}
                />
              </Field>

              <Field label="Section title" htmlFor="section_title">
                <Input
                  id="section_title"
                  value={form.section_title}
                  onChange={(event) => setForm({ ...form, section_title: event.target.value })}
                />
              </Field>

              <Field
                label="Questions to draw"
                htmlFor="question_count"
                hint="Picked at random from the bank for each candidate."
              >
                <Input
                  id="question_count"
                  type="number"
                  min="1"
                  max="200"
                  value={form.question_count}
                  onChange={(event) => setForm({ ...form, question_count: event.target.value })}
                />
              </Field>

              <Button type="submit" disabled={isSaving || !form.batch}>
                {isSaving ? 'Creating…' : 'Create examination'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="No examinations yet" description="Set one with the button above." />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Examination</Th>
                <Th>Batch</Th>
                <Th>Opens</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <Td>
                    <Link
                      href={`/teaching/exams/${row.id}`}
                      className="font-medium underline hover:text-foreground"
                    >
                      {row.title}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{row.code}</div>
                    <div className="text-xs text-muted-foreground">
                      {row.total_questions} questions · {row.duration_minutes} minutes
                    </div>
                  </Td>
                  <Td>{row.batch_code}</Td>
                  <Td>{formatDateTime(row.opens_at)}</Td>
                  <Td>
                    <Badge variant={LIFECYCLE_VARIANT[row.status]}>
                      {LIFECYCLE_LABEL[row.status]}
                    </Badge>
                    {row.results_published ? (
                      <Badge variant="success" className="ml-1">
                        Results out
                      </Badge>
                    ) : null}
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

export default function TeachingExamsPage() {
  return (
    <RequireAuth>
      <Exams />
    </RequireAuth>
  );
}
