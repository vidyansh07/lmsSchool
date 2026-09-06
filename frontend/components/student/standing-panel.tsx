/**
 * "Am I OK" — the second priority tier, after what a student owes.
 *
 * Every number here is an average *of averages* the backend already computed
 * (`apps.performance.engine`), taken across whichever enrolments actually have
 * something to measure — never a naive mean that lets a course with no
 * assessments yet drag a score toward zero. That "nothing to measure is not
 * zero" rule is the same one the backend's own risk engine follows (see
 * `apps/performance/risk.py`'s docstring); this file does not relitigate it,
 * only carries it through to an aggregate across courses.
 *
 * Tone is the point of this file, not a detail of it. A triggered risk rule
 * is shown as `warning` (amber), never `error` (red) — the backend's own
 * `severity` field distinguishes "warning" from "critical" for a *caseload*
 * view a manager triages, and that distinction is deliberately flattened here
 * rather than carried onto a screen the student it is about reads themself.
 * The brief this file answers to is explicit: a risk flag is information, not
 * a verdict.
 */
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import { AlertList, type AlertItem } from '@/components/alert-list';
import { KpiTile } from '@/components/kpi-tile';
import { DashboardGrid } from '@/components/dashboard-grid';
import { ErrorState, LoadingState } from '@/components/states';
import { formatPercent } from '@/lib/format';
import type { StudentPerformanceEntry } from '@/lib/performance';

/** The mean of `pick(entry)` over entries where it is not `null` — `null` if none are. */
export function averageMetric(
  entries: StudentPerformanceEntry[],
  pick: (entry: StudentPerformanceEntry) => number | null,
): number | null {
  const values = entries.map(pick).filter((value): value is number => value !== null);
  if (values.length === 0) return null;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

const RISK_HREF: Record<string, string> = {
  attendance: '/my-attendance',
  academic: '/my-results',
  assignments: '/my-assignments',
  progress: '/my-progress',
};

/** Every triggered flag across every enrolment, as calm, linkable list items. */
export function collectRiskItems(entries: StudentPerformanceEntry[]): AlertItem[] {
  const items: AlertItem[] = [];
  for (const entry of entries) {
    for (const outcome of entry.risk.outcomes) {
      if (!outcome.triggered) continue;
      items.push({
        id: `${entry.enrollment_id}-${outcome.key}`,
        severity: 'warning',
        title: `${outcome.label} — ${entry.course_title}`,
        description: outcome.detail,
        href: RISK_HREF[outcome.key],
      });
    }
  }
  return items;
}

export function StandingPanel({
  performance,
  isLoading,
  error,
  onRetry,
}: {
  performance: StudentPerformanceEntry[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading how you're doing…" rows={4} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your standing"
        message={error.message}
        requestId={error.requestId}
        onRetry={onRetry}
      />
    );
  }

  const progress = averageMetric(performance, (entry) => entry.progress.percent);
  const attendance = averageMetric(performance, (entry) => entry.attendance.percent);
  const assessment = averageMetric(performance, (entry) => entry.assessment.average_percent);
  const overall = averageMetric(performance, (entry) => entry.overall_score);
  const riskItems = collectRiskItems(performance);
  const percentFormat = (value: number | string) => formatPercent(value);

  return (
    <div className="space-y-4">
      <DashboardGrid>
        <KpiTile label="Course progress" value={progress} format={percentFormat} />
        <KpiTile label="Attendance" value={attendance} format={percentFormat} />
        <KpiTile label="Assessment average" value={assessment} format={percentFormat} />
        <KpiTile label="Overall standing" value={overall} format={percentFormat} />
      </DashboardGrid>

      {riskItems.length === 0 ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-4 py-4 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
          <p>
            {performance.length === 0
              ? 'Nothing to flag yet — this fills in once you are enrolled.'
              : "You're on track. Nothing here needs your attention."}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <AlertTriangle className="size-4 text-warning" aria-hidden="true" />
            Worth a look
          </p>
          <AlertList items={riskItems} title="risk flags" />
        </div>
      )}
    </div>
  );
}
