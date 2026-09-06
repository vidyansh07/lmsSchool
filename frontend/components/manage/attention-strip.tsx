'use client';

/**
 * The one KPI strip both hubs share, sitting above the table on each.
 *
 * The brief this answers to is specific: a summary of the page below it, not
 * a destination in its own right — so the headline figures here are plain
 * `KpiTile`s with nowhere to click, and only the named exceptions in
 * `attention` (a batch behind schedule, a trainer with an overdue report) are
 * links, because those are the one thing on this strip actually worth
 * drilling into. Nobody navigates to a number; people navigate to a named
 * problem.
 *
 * Self-fetching rather than fed by props: both hub pages want the exact same
 * data, and a component that loads itself means neither page carries the
 * loading/error wiring for a summary the page below it doesn't otherwise
 * need.
 */
import { AlertList, type AlertItem, type AlertSeverity } from '@/components/alert-list';
import { DashboardGrid } from '@/components/dashboard-grid';
import { ErrorState, LoadingState } from '@/components/states';
import { KpiTile } from '@/components/kpi-tile';
import { useApi } from '@/hooks/use-api';
import { formatDate } from '@/lib/format';
import type { AttentionSeverity, ManagerDashboard } from '@/lib/manage';

const SEVERITY_TO_ALERT: Record<AttentionSeverity, AlertSeverity> = {
  low: 'info',
  medium: 'warning',
  high: 'error',
};

export function ManagerAttentionStrip() {
  const { data, error, isLoading, reload } = useApi<ManagerDashboard>('/api/v1/dashboards/manager/');

  if (isLoading) return <LoadingState label="Loading the manager overview…" rows={3} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the manager overview"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }
  if (!data) return null;

  const items: AlertItem[] = data.attention.map((item) => ({
    id: item.kind,
    severity: SEVERITY_TO_ALERT[item.severity],
    title: item.label,
    count: item.count,
    href: item.href,
  }));

  return (
    <div className="space-y-3">
      <DashboardGrid>
        <KpiTile label="Active batches" value={data.batches.active} />
        <KpiTile label="Batches behind schedule" value={data.batches.behind_schedule} />
        <KpiTile label="Students at risk" value={data.students.at_risk} />
        <KpiTile label="Trainers with overdue DSR" value={data.trainers.with_overdue_dsr} />
      </DashboardGrid>
      <AlertList
        items={items}
        title="attention"
        emptyTitle="Nothing needs attention"
        emptyDescription="No batch, student or trainer is currently flagged."
      />
      <p className="text-xs text-muted-foreground">As of {formatDate(data.as_of)}.</p>
    </div>
  );
}
