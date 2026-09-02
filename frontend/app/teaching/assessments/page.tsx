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
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import {
  ASSESSMENT_CATEGORY_LABEL,
  ASSESSMENT_DELIVERY_LABEL,
  LIFECYCLE_LABEL,
  LIFECYCLE_VARIANT,
  formatDateTime,
} from '@/lib/academic-labels';
import { createAssessment, listAssessments } from '@/lib/assessments';
import { listBatches } from '@/lib/batches';
import type { Assessment, AssessmentDelivery, BatchListRow } from '@/types/api';

/** Weekly tests: schedule them, then mark or import their results. */
function Assessments() {
  const [rows, setRows] = useState<Assessment[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState({
    batch: '',
    title: '',
    category: 'weekly_test',
    delivery: 'external_link' as AssessmentDelivery,
    external_url: '',
    external_provider: '',
    max_marks: '',
    scheduled_for: '',
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAssessments(), listBatches({ page_size: 100 })])
      .then(([assessments, batchPage]) => {
        if (cancelled) return;
        setRows(assessments.results);
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
      await createAssessment(form.batch, {
        title: form.title,
        category: form.category,
        delivery: form.delivery,
        external_url: form.delivery === 'external_link' ? form.external_url : undefined,
        external_provider: form.external_provider || undefined,
        max_marks: form.max_marks || undefined,
        scheduled_for: form.scheduled_for
          ? new Date(form.scheduled_for).toISOString()
          : undefined,
      });
      setIsOpen(false);
      setRows((await listAssessments()).results);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <LoadingState label="Loading tests…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load tests"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Weekly tests</h1>
          <p className="text-sm text-muted-foreground">
            Tests you have scheduled, however they are taken.
          </p>
        </div>
        <Button type="button" onClick={() => setIsOpen((open) => !open)}>
          {isOpen ? 'Cancel' : 'New test'}
        </Button>
      </div>

      {isOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>New test</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

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
                      {batch.code} · {batch.name}
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

              <Field label="Kind" htmlFor="category" error={errors.category}>
                <Select
                  id="category"
                  value={form.category}
                  onChange={(event) => setForm({ ...form, category: event.target.value })}
                >
                  {Object.entries(ASSESSMENT_CATEGORY_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field
                label="How it is taken"
                htmlFor="delivery"
                error={errors.delivery}
                hint="A file upload creates the hand-in for you, with the usual file rules."
              >
                <Select
                  id="delivery"
                  value={form.delivery}
                  onChange={(event) =>
                    setForm({ ...form, delivery: event.target.value as AssessmentDelivery })
                  }
                >
                  {Object.entries(ASSESSMENT_DELIVERY_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>

              {form.delivery === 'external_link' ? (
                <>
                  <Field label="Link" htmlFor="external_url" error={errors.external_url}>
                    <Input
                      id="external_url"
                      type="url"
                      required
                      placeholder="https://docs.google.com/forms/…"
                      value={form.external_url}
                      onChange={(event) =>
                        setForm({ ...form, external_url: event.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="Provider"
                    htmlFor="external_provider"
                    error={errors.external_provider}
                  >
                    <Input
                      id="external_provider"
                      placeholder="Google Forms"
                      value={form.external_provider}
                      onChange={(event) =>
                        setForm({ ...form, external_provider: event.target.value })
                      }
                    />
                  </Field>
                </>
              ) : null}

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

              <Field label="When" htmlFor="scheduled_for" error={errors.scheduled_for}>
                <Input
                  id="scheduled_for"
                  type="datetime-local"
                  value={form.scheduled_for}
                  onChange={(event) => setForm({ ...form, scheduled_for: event.target.value })}
                />
              </Field>

              <Button type="submit" disabled={isSaving || !form.batch}>
                {isSaving ? 'Creating…' : 'Create test'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title="No tests yet" description="Schedule one with the button above." />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Test</Th>
                <Th>Batch</Th>
                <Th>When</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <Td>
                    <Link
                      href={`/teaching/assessments/${row.id}`}
                      className="font-medium underline hover:text-foreground"
                    >
                      {row.title}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{row.code}</div>
                    <div className="text-xs text-muted-foreground">
                      {ASSESSMENT_DELIVERY_LABEL[row.delivery]}
                    </div>
                  </Td>
                  <Td>{row.batch_code}</Td>
                  <Td>{formatDateTime(row.scheduled_for)}</Td>
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

export default function TeachingAssessmentsPage() {
  return (
    <RequireAuth>
      <Assessments />
    </RequireAuth>
  );
}
