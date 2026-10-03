'use client';

/**
 * One class report, read in full from a side sheet — what a manager opens
 * from the reports list or a batch's class strip. Read-only: submitted is
 * done, and asking for changes stays on the list row.
 */
import { DsrClassDetailsSummary } from '@/components/teaching/dsr-class-details';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { useApi } from '@/hooks/use-api';
import { formatClassTime, type DSR } from '@/lib/dsr';
import { fallback, formatDate, formatDateTime, formatNumber, NO_DATA } from '@/lib/format';
import { DSR_STATUS_LABEL, DSR_STATUS_VARIANT } from '@/lib/manage';

function Report({ dsrId }: { dsrId: string }) {
  const report = useApi<DSR>(`/api/v1/dsr/${dsrId}/`);
  if (report.isLoading) return <LoadingState label="Loading the report…" rows={4} />;
  if (report.error || !report.data) {
    return (
      <ErrorState
        title="Could not load this report"
        message={report.error?.message ?? 'The request failed.'}
        requestId={report.error?.requestId || undefined}
        onRetry={report.reload}
      />
    );
  }
  const dsr = report.data;
  const text = [
    { label: 'Teaching notes', value: dsr.teaching_notes },
    { label: 'Issues', value: dsr.issues },
    { label: 'Student concerns', value: dsr.student_concerns },
  ].filter((row) => row.value);

  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={DSR_STATUS_VARIANT[dsr.status]}>{DSR_STATUS_LABEL[dsr.status]}</Badge>
        {dsr.submitted_at ? (
          <span className="text-xs text-ink-muted">Submitted {formatDateTime(dsr.submitted_at)}</span>
        ) : null}
        {dsr.is_overdue ? <Badge variant="error">Overdue</Badge> : null}
      </div>
      {dsr.manager_comments ? <Alert variant="warning">{dsr.manager_comments}</Alert> : null}
      <p className="text-base text-ink">{fallback(dsr.actual_topic, NO_DATA)}</p>
      <p className="text-ink-muted">
        {formatNumber(dsr.present_count)} present, {formatNumber(dsr.absent_count)} absent of{' '}
        {formatNumber(dsr.student_count)}
      </p>
      <DsrClassDetailsSummary dsr={dsr} />
      {text.map((row) => (
        <div key={row.label}>
          <p className="text-xs font-medium text-ink-muted">{row.label}</p>
          <p className="whitespace-pre-line">{row.value}</p>
        </div>
      ))}
    </div>
  );
}

export function DsrReportSheet({
  dsrId,
  heading,
  onClose,
}: {
  dsrId: string | null;
  /** Batch, date and time, when the caller already knows them. */
  heading?: { batchCode: string; date: string; startTime: string; trainerName: string };
  onClose: () => void;
}) {
  return (
    <Sheet open={dsrId !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent size="lg" className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Class report</SheetTitle>
          {heading ? (
            <SheetDescription>
              {heading.batchCode} · {formatDate(heading.date)} · {formatClassTime(heading.startTime)} ·{' '}
              {heading.trainerName}
            </SheetDescription>
          ) : null}
        </SheetHeader>
        <div className="mt-4">{dsrId ? <Report dsrId={dsrId} /> : null}</div>
      </SheetContent>
    </Sheet>
  );
}
