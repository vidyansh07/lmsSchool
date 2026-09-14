'use client';

/**
 * "Export" on a list: Excel, PDF or CSV of the rows the screen is showing.
 *
 * Small lists download at once; a large one is queued and the person is
 * told when it is ready (19a). The threshold is the server's inline limit,
 * so the same request that would be refused with a 409 is queued here
 * instead of failing. Every export is the same scoped report the screen
 * reads, through `lib/reporting`.
 */

import { useState } from 'react';
import { Download, FileSpreadsheet, FileText, Table2 } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { Button } from '@/components/ui/button';
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
import { queueExport, reportExportUrl, type ReportFilters } from '@/lib/reporting';
import type { ExportFormat } from '@/types/api';

/** The server renders Excel and PDF inline up to this many rows. */
export const INLINE_EXPORT_LIMIT = 2000;

const FORMATS: { id: ExportFormat; label: string; icon: typeof FileText }[] = [
  { id: 'xlsx', label: 'Excel', icon: FileSpreadsheet },
  { id: 'pdf', label: 'PDF', icon: FileText },
  { id: 'csv', label: 'CSV', icon: Table2 },
];

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
  /** How many rows the screen knows about, if it does. Decides inline vs queued. */
  count?: number | null;
  label?: string;
  size?: 'sm' | 'md';
}) {
  const { can } = useAuth();
  const { toast } = useToast();
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  if (!can(Capability.dataExport)) return null;

  const clean: ReportFilters = Object.fromEntries(
    Object.entries(filters).filter(
      ([, value]) => value !== undefined && value !== '' && value !== null,
    ),
  );

  async function queue(format: ExportFormat) {
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

  async function download(format: ExportFormat) {
    // CSV streams at any size; Excel and PDF are bounded, so a list the
    // server would refuse is queued instead of failing in a new tab.
    const large = typeof count === 'number' && count > INLINE_EXPORT_LIMIT;
    if (format !== 'csv' && large) {
      await queue(format);
      return;
    }
    const url = reportExportUrl(reportKey, clean, format);
    if (format === 'csv' || typeof count === 'number') {
      window.location.assign(url);
      return;
    }
    // Size unknown: try inline, and fall back to the queue on the 409.
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

  return (
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
            ? `${count.toLocaleString('en-IN')} rows — prepared in the background`
            : 'Download as'}
        </DropdownMenuLabel>
        {FORMATS.map((format) => {
          const Icon = format.icon;
          return (
            <DropdownMenuItem key={format.id} onSelect={() => void download(format.id)}>
              <Icon className="size-4" aria-hidden="true" />
              {format.label}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
