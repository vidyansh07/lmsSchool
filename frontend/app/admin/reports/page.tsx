'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, errorMessage } from '@/lib/api';
import { listBatches } from '@/lib/batches';
import { Capability, can } from '@/lib/capabilities';
import { listReports, reportExportUrl, runReport } from '@/lib/reporting';
import type { BatchListRow, ReportDefinition, ReportPage } from '@/types/api';

/** The ten reports §8.3 asks for, filtered and exportable. */
function Reports() {
  const { user } = useAuth();
  const mayExport = can(user?.capabilities, Capability.dataExport);

  const [definitions, setDefinitions] = useState<ReportDefinition[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [selected, setSelected] = useState('');
  const [batch, setBatch] = useState('');
  const [page, setPage] = useState<ReportPage | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listReports(), listBatches({ page_size: 100 })])
      .then(([reports, batchPage]) => {
        if (cancelled) return;
        setDefinitions(reports);
        setBatches(batchPage.results);
        setSelected(reports[0]?.key ?? '');
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

  const run = useCallback(async () => {
    if (!selected) return;
    setIsRunning(true);
    setFormError(null);
    try {
      setPage(await runReport(selected, { batch: batch || undefined }));
    } catch (cause) {
      setFormError(errorMessage(cause, 'That report could not be run.'));
      setPage(null);
    } finally {
      setIsRunning(false);
    }
  }, [selected, batch]);

  if (isLoading) return <LoadingState label="Loading reports…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load reports"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  const definition = definitions.find((row) => row.key === selected);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">
          Every report is scoped to what you can already see, and exports the same rows
          you are looking at.
        </p>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 pt-6">
          <Field label="Report" htmlFor="report" className="min-w-64">
            <Select
              id="report"
              value={selected}
              onChange={(event) => {
                setSelected(event.target.value);
                setPage(null);
              }}
            >
              {definitions.map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Batch" htmlFor="batch" className="min-w-64">
            <Select id="batch" value={batch} onChange={(event) => setBatch(event.target.value)}>
              <option value="">Every batch I can see</option>
              {batches.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.code} · {row.name}
                </option>
              ))}
            </Select>
          </Field>

          <Button type="button" onClick={run} disabled={isRunning || !selected}>
            {isRunning ? 'Running…' : 'Run the report'}
          </Button>

          {mayExport && selected ? (
            <Button asChild variant="outline" data-testid="export-link">
              <a href={reportExportUrl(selected, { batch: batch || undefined })}>
                Export as CSV
              </a>
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {definition ? (
        <Card>
          <CardHeader>
            <CardTitle>{definition.label}</CardTitle>
            <CardDescription>{definition.description}</CardDescription>
          </CardHeader>
          <CardContent>
            {page === null ? (
              <EmptyState
                title="Nothing run yet"
                description="Choose a report and press Run."
              />
            ) : page.rows.length === 0 ? (
              <EmptyState
                title="No rows"
                description="Nothing matches. Try a different batch."
              />
            ) : (
              <div className="space-y-3">
                {page.truncated ? (
                  <Alert variant="warning">
                    Showing the first {page.row_count} rows. Export the report for all of
                    them.
                  </Alert>
                ) : (
                  <Badge variant="neutral">{page.row_count} rows</Badge>
                )}
                <TableWrapper>
                  <Table>
                    <thead>
                      <tr>
                        {page.columns.map((column) => (
                          <Th key={column.key}>{column.label}</Th>
                        ))}
                      </tr>
                    </thead>
                    <tbody data-testid="report-body">
                      {page.rows.map((row, index) => (
                        <tr key={index}>
                          {page.columns.map((column) => (
                            <Td key={column.key}>
                              {row[column.key] === null || row[column.key] === undefined
                                ? '—'
                                : typeof row[column.key] === 'boolean'
                                  ? row[column.key]
                                    ? 'yes'
                                    : 'no'
                                  : String(row[column.key])}
                            </Td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableWrapper>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <RequireAuth>
      <Reports />
    </RequireAuth>
  );
}
