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
import { AlertTriangle, CalendarClock, ClipboardX, Layers } from 'lucide-react';

import { AlertList, type AlertItem, type AlertSeverity } from '@/components/alert-list';
import { ErrorState, LoadingState } from '@/components/states';
import { BentoGrid, BentoTile, StatCard } from '@/components/ui/motion';
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

  // Three of these four are counts of a problem, so "up" is bad news. The
  // delta intent says so, which is what stops a rising at-risk count being
  // drawn in the same green as a rising batch count.
  const figures = [
    {
      label: 'Active batches',
      accent: 'blue' as const,
      value: data.batches.active,
      icon: Layers,
      hint: 'Running now',
      deltaIntent: 'up-is-good' as const,
    },
    {
      label: 'Batches behind schedule',
      accent: 'amber' as const,
      value: data.batches.behind_schedule,
      icon: CalendarClock,
      hint: 'Behind their planned session',
      deltaIntent: 'down-is-good' as const,
    },
    {
      label: 'Students at risk',
      accent: 'rose' as const,
      value: data.students.at_risk,
      icon: AlertTriangle,
      hint: 'Flagged by the risk engine',
      deltaIntent: 'down-is-good' as const,
    },
    {
      label: 'Trainers with overdue DSR',
      accent: 'violet' as const,
      value: data.trainers.with_overdue_dsr,
      icon: ClipboardX,
      hint: 'No report filed for a past class',
      deltaIntent: 'down-is-good' as const,
    },
  ];

  return (
    <div className="space-y-3">
      <BentoGrid>
        {figures.map((figure, index) => (
          <BentoTile key={figure.label} span={3} index={index}>
            <StatCard
              label={figure.label}
              value={figure.value}
              icon={figure.icon}
              hint={figure.hint}
              deltaIntent={figure.deltaIntent}
              accent={figure.accent}
            />
          </BentoTile>
        ))}
      </BentoGrid>
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
