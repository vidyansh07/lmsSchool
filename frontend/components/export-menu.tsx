'use client';

/**
 * "Export" on a list: Excel, PDF, CSV or Print of the rows the screen is
 * showing.
 *
 * Choosing a format never exports straight away. It first asks the server
 * how many rows this exact, currently-filtered report would produce
 * (`GET /reports/{key}/count/`) and shows that real count in a confirmation
 * dialog — "Export 1,204 rows as CSV?" — before anything is queued or
 * downloaded. This mirrors the preflight-then-confirm shape
 * `components/communication/manual-send.tsx` uses for a send: the number a
 * person confirms is always a fresh, server-resolved number, never a
 * client-side guess or a stale prop.
 *
 * Once confirmed: small lists download at once; a large one is queued and
 * the person is told when it is ready (19a). The threshold is the server's
 * inline limit, so the same request that would be refused with a 409 is
 * queued here instead of failing. Print never queues — it opens the
 * server's returned HTML (with its own print stylesheet) in a new tab.
 * Every export is the same scoped report the screen reads, through
 * `lib/reporting`.
 */

import { useState } from 'react';
import { Download, FileSpreadsheet, FileText, Printer, Table2 } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
import { DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/toast';
import { ApiError, errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { getReportCount, queueExport, reportExportUrl, type ReportFilters } from '@/lib/reporting';
import type { ExportFormat, QueuedExportFormat } from '@/types/api';

/** The server renders Excel and PDF inline up to this many rows. */
export const INLINE_EXPORT_LIMIT = 2000;

const FORMATS: { id: ExportFormat; label: string; icon: typeof FileText }[] = [
  { id: 'xlsx', label: 'Excel', icon: FileSpreadsheet },
  { id: 'pdf', label: 'PDF', icon: FileText },
  { id: 'csv', label: 'CSV', icon: Table2 },
  { id: 'print', label: 'Print', icon: Printer },
];

const FORMAT_LABEL: Record<ExportFormat, string> = {
  xlsx: 'Excel',
  pdf: 'PDF',
  csv: 'CSV',
  print: 'print',
};

export function ExportMenu({
  reportKey,
  filters = {},
  count,
  label = 'Export',
  size = 'sm',
}: {
  reportKey: string;
  /** The filters the screen is showing — batch, course, student, dates… */
  filters?: ReportFilters;
  /** How many rows the screen knows about, if it does. Only used for the
   *  dropdown's own hint text — the confirmation always re-asks the server. */
  count?: number | null;
  label?: string;
  size?: 'sm' | 'md';
}) {
  const { can } = useAuth();
  const { toast } = useToast();
  const [busy, setBusy] = useState<ExportFormat | null>(null);

  // Confirmation step: a format has been chosen but not yet confirmed.
  const [pendingFormat, setPendingFormat] = useState<ExportFormat | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [isCounting, setIsCounting] = useState(false);
  const [countError, setCountError] = useState<string | null>(null);

  if (!can(Capability.dataExport)) return null;

  const clean: ReportFilters = Object.fromEntries(
    Object.entries(filters).filter(
      ([, value]) => value !== undefined && value !== '' && value !== null,
    ),
  );

  function closeConfirm() {
    setPendingFormat(null);
    setPendingCount(null);
    setCountError(null);
  }

  async function askCount(format: ExportFormat) {
    setPendingFormat(format);
    setPendingCount(null);
    setCountError(null);
    setIsCounting(true);
    try {
      setPendingCount(await getReportCount(reportKey, clean));
    } catch (cause) {
      setCountError(errorMessage(cause, 'Could not resolve the row count.'));
    } finally {
      setIsCounting(false);
    }
  }

  async function queue(format: QueuedExportFormat) {
    setBusy(format);
    try {
      await queueExport({ report_key: reportKey, format, ...clean } as Parameters<
        typeof queueExport
      >[0]);
      toast({
        title: 'Export queued',
        description: 'A notification will tell you when the file is ready to download.',
      });
    } catch (cause) {
      toast({
        title: 'Could not queue the export',
        description: errorMessage(cause),
        variant: 'error',
      });
    } finally {
      setBusy(null);
    }
  }

  async function download(format: QueuedExportFormat, rows: number) {
    // CSV streams at any size; Excel and PDF are bounded, so a list the
    // server would refuse is queued instead of failing in a new tab.
    const large = rows > INLINE_EXPORT_LIMIT;
    if (format !== 'csv' && large) {
      await queue(format);
      return;
    }
    const url = reportExportUrl(reportKey, clean, format);
    if (format === 'csv') {
      window.location.assign(url);
      return;
    }
    setBusy(format);
    try {
      const response = await fetch(url, { credentials: 'include' });
      if (response.status === 409) {
        await queue(format);
        return;
      }
      if (!response.ok)
        throw new ApiError(response.status, 'export_failed', 'The export failed.', '');
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = href;
      anchor.download =
        response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] ??
        `${reportKey}.${format}`;
      anchor.click();
      URL.revokeObjectURL(href);
    } catch (cause) {
      toast({ title: 'Could not export', description: errorMessage(cause), variant: 'error' });
    } finally {
      setBusy(null);
    }
  }

  function print() {
    // The server returns HTML with its own print stylesheet; open it as a
    // page of its own rather than downloading it as a file.
    const url = reportExportUrl(reportKey, clean, 'print');
    window.open(url, '_blank', 'noopener');
  }

  async function confirm() {
    if (pendingFormat === null || pendingCount === null) return;
    const format = pendingFormat;
    const rows = pendingCount;
    closeConfirm();
    if (format === 'print') {
      print();
      return;
    }
    await download(format, rows);
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="outline" size={size} disabled={busy !== null}>
            <Download className="size-4" aria-hidden="true" />
            {busy ? 'Exporting…' : label}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>
            {typeof count === 'number' && count > INLINE_EXPORT_LIMIT
              ? `${count.toLocaleString('en-IN')} rows`
              : 'Download as'}
          </DropdownMenuLabel>
          {FORMATS.map((format) => {
            const Icon = format.icon;
            return (
              <DropdownMenuItem key={format.id} onSelect={() => void askCount(format.id)}>
                <Icon className="size-4" aria-hidden="true" />
                {format.label}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={pendingFormat !== null} onOpenChange={(open) => !open && closeConfirm()}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Confirm export</DialogTitle>
            <DialogDescription>
              {pendingFormat === 'print'
                ? 'This opens a printable page in a new tab.'
                : 'This downloads a file, or queues it in the background for a large list.'}
            </DialogDescription>
          </DialogHeader>

          {isCounting ? (
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              Counting rows…
            </p>
          ) : countError ? (
            <Alert variant="error" data-testid="export-count-error">
              {countError}
            </Alert>
          ) : pendingCount !== null && pendingFormat !== null ? (
            <p data-testid="export-count-confirm" className="text-sm">
              {pendingFormat === 'print' ? 'Print' : 'Export'}{' '}
              <strong>{pendingCount.toLocaleString('en-IN')}</strong> row
              {pendingCount === 1 ? '' : 's'} as {FORMAT_LABEL[pendingFormat]}?
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={closeConfirm}>
              Cancel
            </Button>
            {countError ? (
              <Button type="button" onClick={() => pendingFormat && void askCount(pendingFormat)}>
                Try again
              </Button>
            ) : (
              <Button type="button" disabled={isCounting || pendingCount === null} onClick={() => void confirm()}>
                {pendingFormat === 'print' ? 'Print' : 'Export'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
