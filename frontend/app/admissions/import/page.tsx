'use client';

/**
 * Bulk student import: upload, preview, then confirm or discard.
 *
 * The preview is the safety net §8.5 asks for — nothing is written until
 * `confirmImport` is called, and every row the server rejected is shown next
 * to every row it accepted, with its line number and its reason. Hiding the
 * bad rows would make the count of "how many actually happened" a mystery the
 * counsellor discovers later, on the working list, instead of here where the
 * file is still in their hand and worth fixing.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { SearchPicker, type PickerOption } from '@/components/admissions/search-picker';
import { RequireAuth } from '@/components/require-auth';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage } from '@/lib/api';
import { listBatches } from '@/lib/batches';
import { Capability } from '@/lib/capabilities';
import { confirmImport, previewStudentImport, rejectImport } from '@/lib/reporting';
import type { BatchListRow, BulkImport } from '@/types/api';

function cell(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not available';
  return String(value);
}

interface CombinedRow {
  line: number;
  ok: boolean;
  email: string;
  firstName: string;
  lastName: string;
  phone: string;
  problem: string;
}

function combinedRows(run: BulkImport): CombinedRow[] {
  const valid: CombinedRow[] = run.report.rows.map((row) => ({
    line: Number(row.line ?? 0),
    ok: true,
    email: cell(row.email),
    firstName: cell(row.first_name),
    lastName: cell(row.last_name),
    phone: cell(row.phone),
    problem: '',
  }));
  const invalid: CombinedRow[] = run.report.errors.map((error) => ({
    line: error.line,
    ok: false,
    email: error.email ? cell(error.email) : error.student_id ? cell(error.student_id) : 'Not available',
    firstName: '',
    lastName: '',
    phone: '',
    problem: error.problem,
  }));
  return [...valid, ...invalid].sort((a, b) => a.line - b.line);
}

export function ImportFlow() {
  const [batchQuery, setBatchQuery] = useState('');
  const [batchOptions, setBatchOptions] = useState<BatchListRow[]>([]);
  const [targetBatch, setTargetBatch] = useState<BatchListRow | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<BulkImport | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      listBatches({ search: batchQuery, page_size: 30, ordering: '-start_date' })
        .then((page) => setBatchOptions(page.results.filter((b) => b.status !== 'archived')))
        .catch(() => setBatchOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [batchQuery]);

  const batchOptionList: PickerOption[] = batchOptions.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: `${row.seats_available} seats left`,
  }));

  async function onUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setIsUploading(true);
    setError('');
    setNotice('');
    try {
      const result = await previewStudentImport(file, targetBatch?.id);
      setRun(result);
    } catch (cause) {
      setError(errorMessage(cause, 'Could not read this file.'));
    } finally {
      setIsUploading(false);
    }
  }

  async function onConfirm() {
    if (!run) return;
    setIsFinishing(true);
    setError('');
    try {
      const finished = await confirmImport(run.id);
      setRun(finished);
      setNotice(`${finished.created_count} student${finished.created_count === 1 ? '' : 's'} created.`);
    } catch (cause) {
      setError(errorMessage(cause, 'Could not confirm this import.'));
    } finally {
      setIsFinishing(false);
    }
  }

  async function onReject() {
    if (!run) return;
    setIsFinishing(true);
    setError('');
    try {
      await rejectImport(run.id);
      setRun(null);
      setFile(null);
      setNotice('Discarded. Nothing was created.');
    } catch (cause) {
      setError(errorMessage(cause, 'Could not discard this import.'));
    } finally {
      setIsFinishing(false);
    }
  }

  function onStartOver() {
    setRun(null);
    setFile(null);
    setError('');
    setNotice('');
  }

  const rows = run ? combinedRows(run) : [];
  const isConfirmed = run?.status === 'confirmed';
  const canConfirm = run?.status === 'preview' && run.valid_count > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Import students</h1>
          <p className="text-sm text-muted-foreground">
            A .csv or .xlsx file, up to 2&nbsp;MB and 2,000 rows. Preview it before anything is created.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/admissions">Back to admissions</Link>
        </Button>
      </div>

      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}
      {error ? <Alert variant="error">{error}</Alert> : null}

      {!run ? (
        <Card>
          <CardHeader>
            <CardTitle>Choose a file</CardTitle>
            <CardDescription>
              Columns can be named loosely — &ldquo;Email&rdquo;, &ldquo;email address&rdquo; and
              &ldquo;e mail&rdquo; all work. Only email and first name are required.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={onUpload} className="space-y-4" noValidate>
              <SearchPicker
                label="Enrol every valid row on a batch (optional)"
                query={batchQuery}
                onQueryChange={setBatchQuery}
                options={batchOptionList}
                selected={targetBatch?.id ?? ''}
                onSelect={(option) => setTargetBatch(batchOptions.find((b) => b.id === option.value) ?? null)}
                emptyMessage="No batches match."
                hint="Leave this empty to only create accounts."
              />
              {targetBatch ? (
                <p className="text-sm text-muted-foreground">
                  Chosen: {targetBatch.name} ({targetBatch.code}).{' '}
                  <button type="button" className="underline" onClick={() => setTargetBatch(null)}>
                    Clear
                  </button>
                </p>
              ) : null}
              <div>
                <label htmlFor="import-file" className="mb-1.5 block text-sm font-medium">
                  File
                </label>
                <input
                  id="import-file"
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="block w-full text-sm"
                />
              </div>
              <Button type="submit" disabled={!file || isUploading}>
                {isUploading ? 'Reading…' : 'Preview import'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{run.original_filename || 'Import preview'}</CardTitle>
              <CardDescription>
                {isConfirmed
                  ? 'This import has been confirmed.'
                  : run.status === 'failed'
                    ? 'The file could not be used — every row failed.'
                    : 'Nothing has been created yet.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                <div>
                  <dt className="text-xs text-muted-foreground">Read</dt>
                  <dd className="text-lg font-semibold">{run.report.summary.read}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Valid</dt>
                  <dd className="text-lg font-semibold">{run.report.summary.valid}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Errors</dt>
                  <dd className="text-lg font-semibold text-destructive">{run.report.summary.errors}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">
                    {isConfirmed ? 'Created' : 'Will create'}
                  </dt>
                  <dd className="text-lg font-semibold">
                    {isConfirmed ? run.created_count : run.report.summary.would_create}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Batch</dt>
                  <dd>{targetBatch ? targetBatch.code : 'None chosen'}</dd>
                </div>
              </dl>

              {run.status === 'failed' ? (
                <Alert variant="error">
                  <AlertTitle>No row in this file could be used.</AlertTitle>
                  Check the errors below, fix the file, and upload it again.
                </Alert>
              ) : null}

              <div className="flex flex-wrap gap-2">
                {canConfirm ? (
                  <Button onClick={() => void onConfirm()} disabled={isFinishing}>
                    {isFinishing ? 'Confirming…' : `Confirm — create ${run.report.summary.would_create} student${run.report.summary.would_create === 1 ? '' : 's'}`}
                  </Button>
                ) : null}
                {run.status === 'preview' ? (
                  <Button variant="outline" onClick={() => void onReject()} disabled={isFinishing}>
                    Discard
                  </Button>
                ) : null}
                <Button variant="ghost" onClick={onStartOver}>
                  {isConfirmed ? 'Import another file' : 'Start over'}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Every row</CardTitle>
              <CardDescription>Valid and invalid rows both, so nothing is hidden.</CardDescription>
            </CardHeader>
            <CardContent>
              <TableWrapper>
                <Table>
                  <thead>
                    <tr>
                      <Th>Line</Th>
                      <Th>Status</Th>
                      <Th>Email</Th>
                      <Th>First name</Th>
                      <Th>Last name</Th>
                      <Th>Phone</Th>
                      <Th>Reason</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={`${row.line}-${row.ok ? 'ok' : 'error'}`}>
                        <Td className="font-mono text-xs">{row.line || 'Not available'}</Td>
                        <Td>
                          <Badge variant={row.ok ? 'success' : 'error'}>
                            {row.ok ? 'Valid' : 'Error'}
                          </Badge>
                        </Td>
                        <Td>{row.email}</Td>
                        <Td>{row.firstName || (row.ok ? 'Not available' : '—')}</Td>
                        <Td>{row.lastName || (row.ok ? 'Not available' : '—')}</Td>
                        <Td>{row.phone || (row.ok ? 'Not available' : '—')}</Td>
                        <Td>{row.problem || 'Not available'}</Td>
                      </tr>
                    ))}
                    {rows.length === 0 ? (
                      <tr>
                        <Td colSpan={7} className="text-center text-muted-foreground">
                          Nothing to show.
                        </Td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </TableWrapper>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export default function AdmissionsImportPage() {
  return (
    <RequireAuth capability={Capability.dataImport}>
      <ImportFlow />
    </RequireAuth>
  );
}
