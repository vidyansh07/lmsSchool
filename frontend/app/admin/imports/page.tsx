'use client';

import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, errorMessage } from '@/lib/api';
import { listBatches } from '@/lib/batches';
import { confirmImport, previewStudentImport, rejectImport } from '@/lib/reporting';
import type { BatchListRow, BulkImport } from '@/types/api';

/**
 * Bulk student import — §8.5.
 *
 * Two deliberate steps. The first reads the file and reports what *would*
 * happen; nothing reaches the database until somebody looks at that and
 * confirms. The same shape as the result import in §4.6, for the same reason.
 */
function Imports() {
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [batch, setBatch] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BulkImport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listBatches({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setBatches(page.results);
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

  async function run(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key);
    setFormError(null);
    setNotice(null);
    try {
      await action();
      setNotice(message);
    } catch (cause) {
      setFormError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading…" rows={3} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the import screen"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Bulk import</h1>
        <p className="text-sm text-muted-foreground">
          Upload a .csv or .xlsx of students. Nothing is created until you confirm the
          preview.
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
          <CardTitle>Students</CardTitle>
          <CardDescription>
            Columns: <code>email</code> and <code>first name</code> are required;{' '}
            <code>last name</code> and <code>phone</code> are optional. An address that
            already exists is reported rather than changed.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (!file) return;
              void run(
                'preview',
                async () => {
                  setPreview(await previewStudentImport(file, batch || undefined));
                },
                'Checked. Nothing has been created yet.',
              );
            }}
          >
            <Field label="File" htmlFor="file">
              <Input
                id="file"
                type="file"
                accept=".csv,.xlsx"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </Field>

            <Field
              label="Enrol on a batch"
              htmlFor="batch"
              hint="Optional. Everybody in the file is enrolled on it as well."
            >
              <Select id="batch" value={batch} onChange={(event) => setBatch(event.target.value)}>
                <option value="">Do not enrol</option>
                {batches.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.code} · {row.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Button type="submit" size="sm" disabled={!file || busy === 'preview'}>
              {busy === 'preview' ? 'Checking…' : 'Preview the import'}
            </Button>
          </form>

          {preview ? (
            <div className="space-y-3 rounded-md border border-border p-3" data-testid="import-preview">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant={
                    preview.status === 'confirmed'
                      ? 'success'
                      : preview.error_count
                        ? 'error'
                        : 'warning'
                  }
                >
                  {preview.status}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {preview.original_filename}
                </span>
              </div>

              <p className="text-sm">
                {preview.valid_count} of {preview.row_count} rows would apply ·{' '}
                {preview.error_count} with problems
                {preview.status === 'confirmed'
                  ? ` · ${preview.created_count} created`
                  : ''}
              </p>

              {preview.report.errors?.length ? (
                <div>
                  <p className="text-sm font-medium">Problems</p>
                  <ul className="mt-1 space-y-1 text-sm text-muted-foreground">
                    {preview.report.errors.map((problem) => (
                      <li key={`${problem.line}-${problem.problem}`}>
                        Line {problem.line}
                        {problem.email ? ` (${problem.email})` : ''}: {problem.problem}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {preview.report.rows?.length ? (
                <TableWrapper>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Line</Th>
                        <Th>Email</Th>
                        <Th>Name</Th>
                      </tr>
                    </thead>
                    <tbody className="stagger">
                      {preview.report.rows.slice(0, 20).map((row, index) => (
                        <tr key={index} className="animate-fade-in hover:bg-muted/40">
                          <Td>{String(row.line)}</Td>
                          <Td>{String(row.email)}</Td>
                          <Td>
                            {String(row.first_name)} {String(row.last_name ?? '')}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableWrapper>
              ) : null}

              {preview.status === 'failed' ? (
                <Alert variant="error">
                  Nothing in this file can be imported. Fix the rows listed above and
                  upload it again.
                </Alert>
              ) : null}

              {preview.status === 'preview' ? (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={busy === 'confirm' || preview.error_count > 0}
                    onClick={() =>
                      run(
                        'confirm',
                        async () => {
                          setPreview(await confirmImport(preview.id));
                        },
                        'Imported.',
                      )
                    }
                  >
                    Confirm the import
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy === 'reject'}
                    onClick={() =>
                      run(
                        'reject',
                        async () => {
                          setPreview(await rejectImport(preview.id));
                        },
                        'Discarded.',
                      )
                    }
                  >
                    Discard
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ImportsPage() {
  return (
    <RequireAuth>
      <Imports />
    </RequireAuth>
  );
}
