'use client';

/**
 * One batch's class reports at a glance — `GET /batches/<id>/dsr-summary/`:
 * how much of the course the reports say is covered, a strip of the last
 * classes coloured by report state, and the CSV export. Submitted is done;
 * nothing here waits on a manager (the owner's call, 3 October 2026).
 */
import { Download } from 'lucide-react';
import { useState } from 'react';

import { DsrReportSheet } from '@/components/manage/dsr-report-sheet';

import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { useApi } from '@/hooks/use-api';
import {
  batchReportExportUrl,
  formatClassTime,
  type BatchReportSummary,
  type ClassReportState,
} from '@/lib/dsr';
import { formatDate, formatNumber } from '@/lib/format';

export const CLASS_REPORT_STATE_LABEL: Record<ClassReportState, string> = {
  upcoming: 'Not over yet',
  missing: 'Not written',
  overdue: 'Overdue',
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Submitted',
  changes_requested: 'Changes asked for',
};

const STATE_VARIANT: Record<ClassReportState, 'neutral' | 'success' | 'warning' | 'error'> = {
  upcoming: 'neutral',
  missing: 'warning',
  overdue: 'error',
  draft: 'warning',
  submitted: 'success',
  approved: 'success',
  changes_requested: 'warning',
};

const WINDOWS = [7, 30, 90];

export function BatchClassReports({ batchId }: { batchId: string }) {
  const [days, setDays] = useState(30);
  const [openId, setOpenId] = useState<string | null>(null);
  const summary = useApi<BatchReportSummary>(`/api/v1/batches/${batchId}/dsr-summary/?days=${days}`);

  if (summary.isLoading) return <LoadingState label="Loading class reports…" rows={3} />;
  if (summary.error || !summary.data) {
    return (
      <ErrorState
        title="Could not load the class reports"
        message={summary.error?.message ?? 'The request failed.'}
        requestId={summary.error?.requestId || undefined}
        onRetry={summary.reload}
      />
    );
  }

  const { counts, coverage, classes } = summary.data;
  const held = classes.filter((row) => row.state !== 'upcoming');

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span>
            <span className="text-ink-muted">Classes held: </span>
            <strong className="tabular-nums">{formatNumber(counts.held)}</strong>
          </span>
          <span>
            <span className="text-ink-muted">Reported: </span>
            <strong className="tabular-nums">{formatNumber(counts.submitted)}</strong>
            <span className="text-ink-muted"> ({formatNumber(counts.on_time)} on time)</span>
          </span>
          <span>
            <span className="text-ink-muted">Missing: </span>
            <strong className={counts.missing > 0 ? 'tabular-nums text-warning' : 'tabular-nums'}>
              {formatNumber(counts.missing)}
            </strong>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor={`batch-reports-days-${batchId}`} className="text-xs text-ink-muted">
            Last
          </label>
          <Select
            id={`batch-reports-days-${batchId}`}
            uiSize="sm"
            className="w-28"
            value={String(days)}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {WINDOWS.map((value) => (
              <option key={value} value={value}>
                {value} days
              </option>
            ))}
          </Select>
          <Button asChild size="sm" variant="outline">
            <a href={batchReportExportUrl(batchId, days)} download>
              <Download className="size-4" aria-hidden="true" />
              Export CSV
            </a>
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-sm">
          <span className="text-ink-muted">Course covered, by the reports</span>
          <span className="tabular-nums">
            {coverage.percent === null
              ? 'No lessons'
              : `${formatNumber(coverage.lessons_covered)} of ${formatNumber(coverage.lessons_total)} lessons`}
          </span>
        </div>
        <Progress value={coverage.percent ?? 0} label="Course covered" />
        {coverage.next_lesson ? (
          <p className="text-xs text-ink-muted">Next up: {coverage.next_lesson.title}</p>
        ) : null}
      </div>

      {held.length === 0 ? (
        <p className="text-sm text-ink-muted">No classes in this window.</p>
      ) : (
        <ul className="divide-y divide-line">
          {held
            .slice()
            .reverse()
            .slice(0, 12)
            .map((row) => (
              <li key={row.session} className="flex flex-wrap items-start justify-between gap-2 py-2 text-sm">
                <div className="min-w-0">
                  <span className="text-ink">
                    {formatDate(row.date)} · {formatClassTime(row.start_time)}
                  </span>
                  <span className="text-ink-muted"> · {row.trainer_name}</span>
                  <span className="block truncate text-xs text-ink-muted">
                    {row.topic || row.lessons.join(', ') || 'No topic recorded'}
                    {row.present !== null
                      ? ` · ${formatNumber(row.present)} present, ${formatNumber(row.absent ?? 0)} absent`
                      : ''}
                    {row.student_notes > 0 ? ` · ${formatNumber(row.student_notes)} student note(s)` : ''}
                    {row.homework ? ' · homework set' : ''}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={STATE_VARIANT[row.state]}>{CLASS_REPORT_STATE_LABEL[row.state]}</Badge>
                  {row.dsr ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Read the report for ${formatDate(row.date)}`}
                      onClick={() => setOpenId(row.dsr)}
                    >
                      Read
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
        </ul>
      )}
      <DsrReportSheet dsrId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
