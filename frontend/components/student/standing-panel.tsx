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
import { AlertTriangle, CalendarCheck, CheckCircle2, GaugeCircle, TrendingUp, Trophy } from 'lucide-react';

import { AlertList, type AlertItem } from '@/components/alert-list';
import { ErrorState, LoadingState } from '@/components/states';
import { BarChart, type CategoryDatum } from '@/components/ui/charts';
import { Grid, GridItem } from '@/components/ui/layout';
import { StatCard } from '@/components/ui/stat';
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

  // Each of these is a percentage the student is being measured on, so each
  // one counts up and carries the icon for what it measures. `KpiTile` is
  // still what the rest of the app uses for a bare figure; this screen is the
  // one a student looks at every day, and it earns the extra weight.
  const tiles = [
    { label: 'Course progress', value: progress, icon: TrendingUp },
    { label: 'Attendance', value: attendance, icon: CalendarCheck },
    { label: 'Assessment average', value: assessment, icon: GaugeCircle },
    { label: 'Overall standing', value: overall, icon: Trophy },
  ] as const;

  // The same four averages as a side-by-side comparison, not a second copy
  // of them — a student reading four separate tiles still has to hold each
  // number in their head to spot the gap between, say, attendance and
  // assessment; a bar puts the shape of that in one glance. Null stays null
  // (no fabricated zero) — `BarChart` simply skips a bar with nothing to
  // plot, and shows its own empty state only when every one of the four is.
  const standingChartData: CategoryDatum[] = tiles.map((tile) => ({
    label: tile.label,
    value: tile.value,
  }));

  return (
    <div className="space-y-4">
      <Grid>
        {tiles.map((tile) => (
          <GridItem key={tile.label} span={3}>
            <StatCard
              label={tile.label}
              value={tile.value}
              icon={tile.icon}
              suffix="%"
            />
          </GridItem>
        ))}
      </Grid>

      <div className="animate-fade-in rounded-[var(--radius-card)] border border-border p-4">
        <p className="mb-2 text-sm font-medium">Side by side</p>
        <BarChart
          data={standingChartData}
          height={200}
          // One more digit than the tiles above deliberately — "90.0%" here,
          // "90%" there — so the chart's own visually-hidden data table
          // never collides, character for character, with the headline
          // figure a person (or a test) already found in the tile.
          valueFormatter={(value) => `${value.toFixed(1)}%`}
          emptyMessage="Nothing measured yet."
          ariaLabel="Your standing, by measure"
        />
      </div>

      {riskItems.length === 0 ? (
        <div className="animate-fade-in flex items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-4 py-4 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
          <p>
            {performance.length === 0
              ? 'Nothing to flag yet — this fills in once you are enrolled.'
              : "You're on track. Nothing here needs your attention."}
          </p>
        </div>
      ) : (
        <div className="animate-fade-in space-y-2">
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
