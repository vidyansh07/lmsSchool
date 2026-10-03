'use client';

/**
 * Classes that ended without a submitted report — the trainer's own, from
 * `GET /dsr/missing/`. Shown above the class picker so a report left over
 * from yesterday is the first thing a trainer sees, not something a manager
 * has to chase. Also shown inside an open class (minus that class), since a
 * trainer with one class today lands straight in it. Renders nothing when
 * there is nothing to fill.
 */
import { ClipboardList } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatClassTime, listMissingReports, type MissingReportRow } from '@/lib/dsr';
import { formatDate, formatDateTime } from '@/lib/format';

function isOverdue(row: MissingReportRow, now: number): boolean {
  return row.due_at !== null && new Date(row.due_at).getTime() < now;
}

export function ReportsToFill({ exceptSessionId }: { exceptSessionId?: string }) {
  const [rows, setRows] = useState<MissingReportRow[] | null>(null);
  const [now] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    // A failure here only hides a reminder; the class picker below still
    // works, so it is not worth an error state of its own.
    listMissingReports()
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const shown = (rows ?? []).filter((row) => row.session !== exceptSessionId);
  if (shown.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h2" className="flex items-center gap-2">
          <ClipboardList className="size-4 text-warning" aria-hidden="true" />
          Reports to fill
        </CardTitle>
        <CardDescription>
          {shown.length === 1
            ? 'One class has ended without its report.'
            : `${shown.length} classes have ended without their report.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-line">
          {shown.map((row) => {
            const overdue = isOverdue(row, now);
            return (
              <li key={row.session} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div className="min-w-0 text-sm">
                  <span className="font-mono text-xs text-ink-muted">{row.batch_code}</span>{' '}
                  <span className="text-ink">
                    {formatDate(row.date)} · {formatClassTime(row.start_time)}–
                    {formatClassTime(row.end_time)}
                  </span>
                  {row.due_at ? (
                    <span className="block text-xs text-ink-muted">
                      Due {formatDateTime(row.due_at)}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  {overdue ? (
                    <Badge variant="error">Overdue</Badge>
                  ) : row.dsr_status === 'revision_required' ? (
                    <Badge variant="warning">Changes asked for</Badge>
                  ) : row.dsr ? (
                    <Badge variant="neutral">Draft</Badge>
                  ) : null}
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/teaching/today?session=${row.session}`}>Fill in</Link>
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
