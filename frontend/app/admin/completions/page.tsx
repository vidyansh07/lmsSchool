'use client';

import { useCallback, useEffect, useState } from 'react';

import { ProgressRules } from '@/components/progress-rules';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { ApiError, errorMessage } from '@/lib/api';
import {
  COMPLETION_STATUS_LABEL,
  COMPLETION_STATUS_VARIANT,
  formatDate,
} from '@/lib/academic-labels';
import {
  approveCompletion,
  getEnrollmentProgress,
  issueCertificate,
  listCompletions,
  refreshBatchCompletions,
  rejectCompletion,
  reopenCompletion,
} from '@/lib/progress';
import { listBatches } from '@/lib/batches';
import type { BatchListRow, CompletionEvaluation, CourseCompletion } from '@/types/api';

/**
 * The approval queue — §6.6.
 *
 * Eligibility is recomputed by the backend on every read, so this screen never
 * caches a verdict. "Re-evaluate" exists only to populate the queue after a rule
 * change, rather than waiting for each student to open their own dashboard.
 */
function Completions() {
  const [rows, setRows] = useState<CourseCompletion[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [detail, setDetail] = useState<Record<string, CompletionEvaluation>>({});
  const [status, setStatus] = useState('eligible');
  const [batch, setBatch] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setRows((await listCompletions({ status: status || undefined, batch: batch || undefined })).results);
  }, [status, batch]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listCompletions({ status: status || undefined, batch: batch || undefined }),
      listBatches({ page_size: 100 }),
    ])
      .then(([page, batchPage]) => {
        if (cancelled) return;
        setRows(page.results);
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
  }, [status, batch]);

  async function run(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key);
    setFormError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(message);
    } catch (cause) {
      setFormError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  async function showRules(row: CourseCompletion) {
    if (detail[row.id]) {
      setDetail(({ [row.id]: _removed, ...rest }) => rest);
      return;
    }
    const evaluation = await getEnrollmentProgress(row.enrollment);
    setDetail((current) => ({ ...current, [row.id]: evaluation }));
  }

  if (isLoading) return <LoadingState label="Loading completions…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load completions"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Course completions</h1>
        <p className="text-sm text-muted-foreground">
          Students who have met the rules, waiting for a decision.
        </p>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 pt-6">
          <Field label="Status" htmlFor="status" className="min-w-48">
            <Select id="status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">Everything</option>
              <option value="eligible">Eligible</option>
              <option value="in_progress">In progress</option>
              <option value="approved">Completed</option>
              <option value="rejected">Not approved</option>
            </Select>
          </Field>
          <Field label="Batch" htmlFor="batch" className="min-w-64">
            <Select id="batch" value={batch} onChange={(event) => setBatch(event.target.value)}>
              <option value="">Every batch</option>
              {batches.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.code} · {row.name}
                </option>
              ))}
            </Select>
          </Field>
          <Button
            type="button"
            variant="outline"
            disabled={!batch || busy === 'refresh'}
            onClick={() =>
              run(
                'refresh',
                () => refreshBatchCompletions(batch),
                'Re-evaluated against the current rules.',
              )
            }
          >
            Re-evaluate this batch
          </Button>
        </CardContent>
      </Card>

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing here"
          description="No completions match. Try re-evaluating a batch after changing the rules."
        />
      ) : (
        rows.map((row) => (
          <Card key={row.id} data-testid="completion-row">
            <CardHeader className="gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={COMPLETION_STATUS_VARIANT[row.status]}>
                  {COMPLETION_STATUS_LABEL[row.status]}
                </Badge>
                <span className="font-mono text-xs text-muted-foreground">
                  {row.student_code} · {row.batch_code}
                </span>
              </div>
              <CardTitle>{row.student_name}</CardTitle>
              <CardDescription>
                {row.course_title}
                {row.completed_on ? ` · completed ${formatDate(row.completed_on)}` : ''}
                {row.decision_note ? ` · ${row.decision_note}` : ''}
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-3">
              <Button type="button" size="sm" variant="ghost" onClick={() => showRules(row)}>
                {detail[row.id] ? 'Hide the rules' : 'Show the rules'}
              </Button>
              {detail[row.id] ? (
                <ProgressRules rules={detail[row.id]?.rules ?? []} />
              ) : null}

              {row.status !== 'approved' ? (
                <>
                  <Field label="Note" htmlFor={`note-${row.id}`}>
                    <Input
                      id={`note-${row.id}`}
                      value={notes[row.id] ?? ''}
                      onChange={(event) => setNotes({ ...notes, [row.id]: event.target.value })}
                    />
                  </Field>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy === row.id}
                      onClick={() =>
                        run(
                          row.id,
                          () =>
                            approveCompletion(row.enrollment, { note: notes[row.id] ?? '' }),
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
                      disabled={busy === row.id || !notes[row.id]}
                      onClick={() =>
                        run(
                          row.id,
                          () => rejectCompletion(row.enrollment, notes[row.id] ?? ''),
                          `Declined ${row.student_name}.`,
                        )
                      }
                    >
                      Decline
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex flex-wrap items-end gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={busy === row.id}
                    onClick={() =>
                      run(
                        row.id,
                        () => issueCertificate(row.enrollment),
                        `Certificate issued for ${row.student_name}.`,
                      )
                    }
                  >
                    Issue the certificate
                  </Button>
                  <Field label="Note" htmlFor={`reopen-${row.id}`}>
                    <Input
                      id={`reopen-${row.id}`}
                      value={notes[row.id] ?? ''}
                      onChange={(event) => setNotes({ ...notes, [row.id]: event.target.value })}
                    />
                  </Field>
                  {/* People approve things by mistake. The API has always
                      allowed undoing it; withholding the button only meant an
                      administrator had to ask an engineer. Blocked while a
                      certificate is live, which the backend enforces. */}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy === row.id || !notes[row.id]}
                    onClick={() =>
                      run(
                        row.id,
                        () => reopenCompletion(row.enrollment, notes[row.id] ?? ''),
                        `Reopened ${row.student_name}.`,
                      )
                    }
                  >
                    Reopen
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

export default function CompletionsPage() {
  return (
    <RequireAuth>
      <Completions />
    </RequireAuth>
  );
}
