'use client';

/**
 * The one KPI strip both hubs share, sitting above the table on each.
 *
 * The brief this answers to is specific: a summary of the page below it, not
 * a destination in its own right — so the original four headline figures
 * here are plain `KpiTile`s with nowhere to click, and only the named
 * exceptions in `attention` (a batch behind schedule, a trainer with an
 * overdue report) are links, because those are the one thing on this strip
 * actually worth drilling into. Nobody navigates to a number; people
 * navigate to a named problem.
 *
 * ERP Phase 18 adds three more figures — `activities`, `risk`,
 * `reviews_due` — that break this rule on purpose: each of them *is* a named
 * problem already ("activities awaiting your review", "critical-risk
 * flags", "reviews due"), so they carry `href` and render as the same
 * `StatCard` the four originals use, just with its already-supported link
 * affordance turned on rather than a new tile shape invented for them.
 *
 * Self-fetching rather than fed by props: both hub pages want the exact same
 * data, and a component that loads itself means neither page carries the
 * loading/error wiring for a summary the page below it doesn't otherwise
 * need.
 */
import { AlertTriangle, CalendarClock, ClipboardCheck, ClipboardX, ListChecks, Layers } from 'lucide-react';

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
    {
      label: 'Activities awaiting review',
      accent: 'blue' as const,
      value: data.activities.under_review,
      icon: ListChecks,
      hint: `${data.activities.pending} pending · ${data.activities.overdue} overdue`,
      deltaIntent: 'down-is-good' as const,
      href: '/activities?status=under_review',
    },
    {
      label: 'Critical risk flags',
      accent: 'rose' as const,
      value: data.risk.critical,
      icon: AlertTriangle,
      hint: `${data.risk.warning} warning-level`,
      deltaIntent: 'down-is-good' as const,
      // The exact href the existing `students_at_risk` attention entry
      // already links to (`apps/reporting/dashboards.py::manager_dashboard`)
      // — one drill-down target for "at risk", not a second one.
      href: '/manage/batches?attention=at_risk',
    },
    {
      label: 'Reviews due',
      accent: 'violet' as const,
      value: data.reviews_due,
      icon: ClipboardCheck,
      hint: 'Performance reviews due for action',
      deltaIntent: 'down-is-good' as const,
      href: '/manage/reviews',
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
              href={'href' in figure ? figure.href : undefined}
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
