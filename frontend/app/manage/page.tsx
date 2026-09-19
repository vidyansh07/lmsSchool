'use client';

/**
 * The manager's overview — the landing screen `/manage` never had.
 *
 * Before this phase, `/manage` was a bare `redirect('/manage/batches')`
 * (§"two hub screens" in `components/navigation.ts`'s own comment: batches
 * and trainers are meant to "drill all the way down", not sit behind a
 * dashboard of widgets). That is still exactly right for those two hubs —
 * neither gains a KPI row or a chart here — but it left the manager role
 * itself with nowhere that answers "how is everything doing right now"
 * before diving into one table or the other. `getManagerDashboard()`
 * (`lib/manage.ts`, `GET /api/v1/dashboards/manager/`) has existed since an
 * earlier ERP phase and already computes exactly that; nothing here reads
 * from it that was not already real, tested, working data. Only the screen
 * was missing.
 *
 * Deliberately reuses rather than re-derives: `ManagerAttentionStrip`
 * already renders this exact endpoint's "named problem" figures as
 * `StatCard`s plus its `AlertList` of drill-down attention items (see that
 * file's own docstring) — both `/manage/batches` and `/manage/trainers`
 * already open with it, so this page opens with it too rather than growing
 * a second copy of the same seven tiles. This page fetches the dashboard a
 * second time for its own "totals" row and chart, the same
 * "each section owns its own fetch" pattern every other dashboard in this
 * app already uses (`WarningsStrip`, `ManagerAttentionStrip` itself) — a
 * second cheap `GET` to an idempotent, already-cached-for-a-minute endpoint,
 * not a second implementation of what it returns.
 */
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ClipboardCheck, GraduationCap, Layers, Users } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { ManagerAttentionStrip } from '@/components/manage/attention-strip';
import { QuickActions, type QuickAction } from '@/components/quick-actions';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { BarChart, DonutChart, RadialProgress, type CategoryDatum } from '@/components/ui/charts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BentoGrid, BentoTile, StatCard } from '@/components/ui/motion';
import { WarningsStrip } from '@/components/warnings-strip';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { formatNumber } from '@/lib/format';
import { greeting } from '@/lib/greeting';
import { getManagerDashboard, type ManagerDashboard } from '@/lib/manage';

/**
 * Six counts already on `ManagerDashboard` that are each, in their own way,
 * something needing a manager's attention — compared side by side rather
 * than composed into a whole, because a batch can be both behind schedule
 * *and* at risk at once (a bar chart makes no claim these sum to anything;
 * a donut would). Chosen specifically for figures the KPI strip below does
 * *not* already put its own tile on: `batches.at_risk` has no tile of its
 * own anywhere in this app today, and `risk.warning` is folded into a hint
 * rather than shown as a bar — this chart is where both finally get a
 * number a manager can compare against the rest at a glance.
 */
function attentionBreakdown(data: ManagerDashboard): CategoryDatum[] {
  return [
    { label: 'Behind schedule', value: data.batches.behind_schedule },
    { label: 'At-risk batches', value: data.batches.at_risk },
    { label: 'At-risk students', value: data.students.at_risk },
    { label: 'Overdue DSRs', value: data.trainers.with_overdue_dsr },
    { label: 'Critical flags', value: data.risk.critical },
    { label: 'Reviews due', value: data.reviews_due },
  ];
}

function ManagerOverview() {
  const { user } = useAuth();
  // Same "compare during render, never `setState` unconditionally inside the
  // effect body" pattern `Dashboard()` (`app/dashboard/page.tsx`) and every
  // `useDashboardSection` call site already use in this app — an
  // unconditional `setState` at the top of an effect reads as a synchronous
  // write inside that effect, which this repo's lint config (correctly)
  // refuses.
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    data: ManagerDashboard | null;
    error: ApiError | null;
    isLoading: boolean;
    attempt: number;
  }>({ data: null, error: null, isLoading: true, attempt });

  if (state.attempt !== attempt) {
    setState({ data: null, error: null, isLoading: true, attempt });
  }

  useEffect(() => {
    let cancelled = false;
    getManagerDashboard()
      .then((result) => {
        if (!cancelled) setState({ data: result, error: null, isLoading: false, attempt });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            data: null,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            attempt,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const { data, error, isLoading } = state;

  if (isLoading) return <LoadingState label="Loading the manager overview…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the manager overview"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={() => setAttempt((current) => current + 1)}
      />
    );
  }
  if (!data) return null;

  const quickActions: QuickAction[] = [
    {
      id: 'batches',
      label: 'Batch review',
      href: '/manage/batches',
      icon: <Layers className="size-4" />,
    },
    {
      id: 'trainers',
      label: 'Trainer review',
      href: '/manage/trainers',
      icon: <GraduationCap className="size-4" />,
    },
    {
      id: 'reviews',
      label: 'Reviews due',
      href: '/manage/reviews',
      icon: <ClipboardCheck className="size-4" />,
    },
  ];

  // Headcount, not a snapshot of a problem — `ManagerAttentionStrip` below
  // already covers "what needs doing"; these three answer "how big is my
  // world", which nothing on either hub page states plainly today
  // (`batches.total`, `students.total`, `trainers.total` are real fields on
  // `ManagerDashboard` that no screen has ever rendered).
  const totals = [
    {
      label: 'Total batches',
      accent: 'blue' as const,
      value: data.batches.total,
      icon: Layers,
      period: 'All-time',
      hint: `${data.batches.active} running now`,
      href: '/manage/batches',
    },
    {
      label: 'Total students',
      accent: 'green' as const,
      value: data.students.total,
      icon: Users,
      period: 'All-time',
      hint: `${data.students.active} active`,
    },
    {
      label: 'Total trainers',
      accent: 'violet' as const,
      value: data.trainers.total,
      icon: GraduationCap,
      period: 'All-time',
      hint: 'Teaching at least one batch',
      href: '/manage/trainers',
    },
  ] as const;

  // `behind_schedule` is a subset of `active` (`_behind_schedule_batch_ids`
  // in `backend/apps/reporting/dashboards.py` filters from the active set),
  // so this is a real, trivially-derived share — the positive-framing
  // counterpart to the "Behind schedule" bar the chart below already shows,
  // not a second, invented figure.
  const onTrackPercent =
    data.batches.active > 0
      ? Math.max(
          0,
          Math.min(100, ((data.batches.active - data.batches.behind_schedule) / data.batches.active) * 100),
        )
      : null;

  // A genuine, mutually-exclusive partition of `students.total` (active vs.
  // not-currently-active) — unlike `batches.behind_schedule`/`at_risk`/
  // `risk.critical`, which this file's own comment above says can overlap
  // and are deliberately kept as a bar chart, not a donut, for exactly that
  // reason. This one is a real composition question, not a comparison one.
  const otherStudents = Math.max(0, data.students.total - data.students.active);

  return (
    <div className="animate-rise-in space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-medium text-muted-foreground">
            {greeting(user?.full_name || user?.email)}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Manager overview</h1>
          <p className="text-sm text-muted-foreground">
            Every cohort, trainer and student under your review, before you drill into either hub.
          </p>
        </div>
      </div>

      <QuickActions actions={quickActions} />

      <WarningsStrip />

      <BentoGrid>
        {totals.map((figure, index) => (
          <BentoTile key={figure.label} span={4} index={index}>
            <StatCard
              label={figure.label}
              value={figure.value}
              icon={figure.icon}
              period={figure.period}
              hint={figure.hint}
              href={'href' in figure ? figure.href : undefined}
              accent={figure.accent}
            />
          </BentoTile>
        ))}
      </BentoGrid>

      <Card>
        <CardHeader>
          <CardTitle as="h2">What needs attention, by kind</CardTitle>
          <CardDescription>
            The same kinds of problem the strip below names individually, compared side by side.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BarChart
            data={attentionBreakdown(data)}
            height={260}
            emptyMessage="Nothing needs attention right now."
            ariaLabel="What needs attention, by kind"
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle as="h2">Batches on schedule</CardTitle>
            <CardDescription>
              The positive counterpart to &ldquo;Behind schedule&rdquo; above — the same figure,
              read the other way.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center justify-center gap-2">
            {onTrackPercent !== null ? (
              <>
                <RadialProgress
                  value={onTrackPercent}
                  target={100}
                  label="of batches on schedule"
                  valueFormatter={(value) => `${Math.round(value)}%`}
                />
                <p className="sr-only">
                  {`${Math.round(onTrackPercent)}% of active batches (${
                    data.batches.active - data.batches.behind_schedule
                  } of ${data.batches.active}) are on schedule.`}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No active batches right now.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle as="h2">Students, active vs. other</CardTitle>
            <CardDescription>
              A real, mutually-exclusive split of the total headcount above — unlike the overlapping
              risk figures above, a student is either active or not.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DonutChart
              data={[
                { label: 'Active students', value: data.students.active },
                { label: 'Other', value: otherStudents },
              ]}
              centerLabel="All students"
              height={220}
              valueFormatter={(value) => formatNumber(value)}
              ariaLabel="Active students vs. other students"
              emptyMessage="No students on record."
            />
          </CardContent>
        </Card>
      </div>

      <ManagerAttentionStrip />

      <p className="text-xs text-muted-foreground">
        <Link href="/manage/batches" className="underline hover:text-foreground">
          Open the batches hub
        </Link>
        {' · '}
        <Link href="/manage/trainers" className="underline hover:text-foreground">
          Open the trainers hub
        </Link>
      </p>
    </div>
  );
}

export default function ManagePage() {
  return (
    <RequireAuth capability={Capability.performanceViewAny}>
      <ManagerOverview />
    </RequireAuth>
  );
}
