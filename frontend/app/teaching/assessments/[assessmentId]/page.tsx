'use client';

import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import {
  ASSESSMENT_DELIVERY_LABEL,
  IMPORT_STATUS_LABEL,
  IMPORT_STATUS_VARIANT,
  LIFECYCLE_LABEL,
  LIFECYCLE_VARIANT,
  formatDateTime,
} from '@/lib/academic-labels';
import {
  confirmImport,
  getMarksSheet,
  previewImport,
  recordResult,
  rejectImport,
  setAssessmentStatus,
} from '@/lib/assessments';
import type { MarksSheet, ResultImport } from '@/types/api';

/**
 * The marks sheet, and the import that fills it in.
 *
 * The import is two deliberate steps. The first reads the file and reports what
 * *would* happen; nothing reaches the results table until the trainer looks at
 * that report and confirms it.
 */
function AssessmentDetail({ assessmentId }: { assessmentId: string }) {
  const [sheet, setSheet] = useState<MarksSheet | null>(null);
  const [preview, setPreview] = useState<ResultImport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [file, setFile] = useState<File | null>(null);

  const load = useCallback(async () => {
    const data = await getMarksSheet(assessmentId);
    setSheet(data);
    setMarks(
      Object.fromEntries(
        data.entries.map((entry) => [entry.enrollment_id, entry.marks_obtained ?? '']),
      ),
    );
  }, [assessmentId]);

  useEffect(() => {
    let cancelled = false;
    getMarksSheet(assessmentId)
      .then((data) => {
        if (cancelled) return;
        setSheet(data);
        setMarks(
          Object.fromEntries(
            data.entries.map((entry) => [entry.enrollment_id, entry.marks_obtained ?? '']),
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
  }, [assessmentId]);

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

  async function uploadForPreview(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy('preview');
    setFormError(null);
    setNotice(null);
    try {
      setPreview(await previewImport(assessmentId, file));
    } catch (cause) {
      setFormError(fieldErrors(cause).file ?? fieldErrors(cause).__all__ ?? 'Import failed.');
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading the marks sheet…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the marks sheet"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!sheet) return null;

  const { assessment } = sheet;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={LIFECYCLE_VARIANT[assessment.status]}>
            {LIFECYCLE_LABEL[assessment.status]}
          </Badge>
          <span className="font-mono text-xs text-muted-foreground">{assessment.code}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{assessment.title}</h1>
        <p className="text-sm text-muted-foreground">
          {assessment.batch_code} · {ASSESSMENT_DELIVERY_LABEL[assessment.delivery]} · out of{' '}
          {assessment.max_marks} · {formatDateTime(assessment.scheduled_for)}
        </p>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      {assessment.status === 'draft' ? (
        <Button
          type="button"
          size="sm"
          disabled={busy === 'publish'}
          onClick={() =>
            run(
              'publish',
              () => setAssessmentStatus(assessment.id, 'published'),
              'Published. Students can see it now.',
            )
          }
        >
          Publish
        </Button>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Import results</CardTitle>
          <CardDescription>
            Upload a .csv or .xlsx with a `student_id` and `marks` column. Nothing is saved until
            you confirm the preview.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="space-y-3" onSubmit={uploadForPreview}>
            <Field label="Result file" htmlFor="result-file">
              <Input
                id="result-file"
                type="file"
                accept=".csv,.xlsx"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </Field>
            <Button type="submit" size="sm" disabled={!file || busy === 'preview'}>
              {busy === 'preview' ? 'Checking…' : 'Preview import'}
            </Button>
          </form>

          {preview ? (
            <div className="space-y-3 rounded-md border border-border p-3" data-testid="import-preview">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={IMPORT_STATUS_VARIANT[preview.status]}>
                  {IMPORT_STATUS_LABEL[preview.status]}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {preview.original_filename}
                </span>
              </div>

              <p className="text-sm">
                {preview.report.summary.valid} of {preview.report.summary.read} rows would apply
                · {preview.report.summary.would_create} new ·{' '}
                {preview.report.summary.would_update} updated ·{' '}
                {preview.report.summary.errors} with problems
              </p>

              {preview.report.errors.length > 0 ? (
                <div>
                  <p className="text-sm font-medium">Problems</p>
                  <ul className="mt-1 space-y-1 text-sm text-muted-foreground">
                    {preview.report.errors.map((problem) => (
                      <li key={`${problem.line}-${problem.student_id}`}>
                        Line {problem.line}
                        {problem.student_id ? ` (${problem.student_id})` : ''}: {problem.problem}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {preview.report.not_in_file.length > 0 ? (
                <p className="text-sm text-muted-foreground">
                  Not in the file:{' '}
                  {preview.report.not_in_file.map((row) => row.student_id).join(', ')}
                </p>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={
                    busy === 'confirm' ||
                    preview.status !== 'preview' ||
                    preview.error_count > 0
                  }
                  onClick={() =>
                    run(
                      'confirm',
                      async () => {
                        setPreview(await confirmImport(preview.id));
                      },
                      'Results imported.',
                    )
                  }
                >
                  Confirm import
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy === 'reject' || preview.status !== 'preview'}
                  onClick={() =>
                    run(
                      'reject',
                      async () => {
                        setPreview(await rejectImport(preview.id));
                      },
                      'Preview discarded.',
                    )
                  }
                >
                  Discard
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Marks sheet</CardTitle>
          <CardDescription>{sheet.entries.length} students in the cohort.</CardDescription>
        </CardHeader>
        <CardContent>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Student</Th>
                  <Th>Marks</Th>
                  <Th>Source</Th>
                  <Th>Action</Th>
                </tr>
              </thead>
              <tbody>
                {sheet.entries.map((entry) => (
                  <tr key={entry.enrollment_id}>
                    <Td>
                      <div className="font-medium">{entry.student_name}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {entry.student_code}
                      </div>
                    </Td>
                    <Td className="min-w-40">
                      <Field label="Marks" htmlFor={`marks-${entry.enrollment_id}`}>
                        <Input
                          id={`marks-${entry.enrollment_id}`}
                          type="number"
                          min="0"
                          step="0.01"
                          max={assessment.max_marks}
                          value={marks[entry.enrollment_id] ?? ''}
                          onChange={(event) =>
                            setMarks({ ...marks, [entry.enrollment_id]: event.target.value })
                          }
                        />
                      </Field>
                    </Td>
                    <Td>{entry.is_absent ? 'Absent' : entry.source || '—'}</Td>
                    <Td className="space-y-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={
                          !sheet.can_record ||
                          busy === entry.enrollment_id ||
                          !marks[entry.enrollment_id]
                        }
                        onClick={() =>
                          run(
                            entry.enrollment_id,
                            () =>
                              recordResult(assessmentId, {
                                enrollment_id: entry.enrollment_id,
                                marks: marks[entry.enrollment_id] ?? '',
                              }),
                            `Recorded ${entry.student_name}.`,
                          )
                        }
                      >
                        Save
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={!sheet.can_record || busy === entry.enrollment_id}
                        onClick={() =>
                          run(
                            entry.enrollment_id,
                            () =>
                              recordResult(assessmentId, {
                                enrollment_id: entry.enrollment_id,
                                is_absent: true,
                              }),
                            `${entry.student_name} marked absent.`,
                          )
                        }
                      >
                        Absent
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        </CardContent>
      </Card>
    </div>
  );
}

export default function TeachingAssessmentPage() {
  const params = useParams<{ assessmentId: string }>();
  return (
    <RequireAuth>
      <AssessmentDetail assessmentId={params.assessmentId} />
    </RequireAuth>
  );
}
