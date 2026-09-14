'use client';

/**
 * "Your exports": every background export the caller may see, newest first,
 * with a download link once it is ready and the reason if it failed.
 */

import { useCallback, useEffect, useState } from 'react';
import { Download, XCircle } from 'lucide-react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { cancelExport, exportDownloadUrl, listExportJobs } from '@/lib/reporting';
import type { ExportJob, ExportStatus } from '@/types/api';

const STATUS_VARIANT: Record<ExportStatus, 'neutral' | 'success' | 'warning' | 'error'> = {
  queued: 'neutral',
  processing: 'warning',
  completed: 'success',
  failed: 'error',
  cancelled: 'neutral',
};

const STATUS_LABEL: Record<ExportStatus, string> = {
  queued: 'Queued',
  processing: 'Preparing',
  completed: 'Ready',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export function ExportJobsPanel() {
  const [jobs, setJobs] = useState<ExportJob[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listExportJobs()
      .then((rows) => {
        if (!cancelled) setJobs(rows);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  const pending = jobs?.some((job) => job.status === 'queued' || job.status === 'processing');

  // A job in flight finishes without the person doing anything; poll gently.
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [pending, reload]);

  return (
    <Card id="exports" className="animate-rise-in">
      <CardHeader>
        <CardTitle>Your exports</CardTitle>
        <CardDescription>
          Large exports are prepared in the background and kept for a while; download them here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorState
            title="Could not load your exports"
            message={error.message}
            requestId={error.requestId || undefined}
            onRetry={reload}
          />
        ) : jobs === null ? (
          <LoadingState label="Loading exports…" rows={2} />
        ) : jobs.length === 0 ? (
          <EmptyState
            title="No exports yet"
            description="Choose Export on any list, or queue one from a report."
          />
        ) : (
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Report</Th>
                  <Th>Format</Th>
                  <Th>Queued</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Rows</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const href = exportDownloadUrl(job);
                  return (
                    <Tr key={job.id}>
                      <Td className="font-medium">{job.report_key.replaceAll('_', ' ')}</Td>
                      <Td className="uppercase">{job.format}</Td>
                      <Td className="whitespace-nowrap text-muted-foreground">
                        {formatDateTime(job.queued_at)}
                      </Td>
                      <Td>
                        <Badge variant={STATUS_VARIANT[job.status]} dot>
                          {STATUS_LABEL[job.status]}
                        </Badge>
                        {job.status === 'failed' && job.error ? (
                          <span className="block text-xs text-muted-foreground">{job.error}</span>
                        ) : null}
                      </Td>
                      <Td className="text-right tabular-nums">
                        {job.status === 'completed' ? job.row_count : '—'}
                      </Td>
                      <Td className="text-right">
                        {job.status === 'completed' && href ? (
                          <Button asChild size="sm" variant="outline">
                            <a href={href}>
                              <Download className="size-4" aria-hidden="true" />
                              Download
                            </a>
                          </Button>
                        ) : job.status === 'queued' || job.status === 'processing' ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void cancelExport(job.id).then(reload)}
                          >
                            <XCircle className="size-4" aria-hidden="true" />
                            Cancel
                          </Button>
                        ) : null}
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          </TableWrapper>
        )}
      </CardContent>
    </Card>
  );
}
