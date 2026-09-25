'use client';

import { Activity, Award, BookOpen, CalendarCheck, ClipboardCheck, GraduationCap, Layers, Users } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AreaChart,
  ChartCard,
  ComboChart,
  DonutChart,
  HorizontalBarChart,
  RadialProgress,
  paletteColor,
} from '@/components/ui/charts';
import { Grid, GridItem } from '@/components/ui/layout';
import { StatCard } from '@/components/ui/stat';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { WarningsStrip } from '@/components/warnings-strip';
import { ApiError } from '@/lib/api';
import { formatNumber, formatPercent, NO_DATA } from '@/lib/format';
import { greeting } from '@/lib/greeting';
import { useSection } from '@/hooks/use-section';
import { heldAgainstAttendance, mergeByWeek } from '@/lib/analytics';
import {
  adminDashboard,
  attendanceTrend,
  batchSummaries,
  deliveryTrend,
  enrolmentTrend,
} from '@/lib/reporting';
import type {
  AdminDashboard,
  BatchSummary,
  DeliveryTrendPoint,
  EnrolmentTrendPoint,
  TrendPoint,
} from '@/types/api';

/** The exact threshold this file already colors the weekly rate badge with
 *  (`point.percent >= 75 ? 'success' : 'warning'`, below) — reused as the
 *  attendance gauge's target so the gauge and the badge never disagree
 *  about what "on target" means. */
const ATTENDANCE_TARGET = 75;

/** A week's Monday, short enough for a twelve-tick axis. */
function formatWeekLabel(iso: string): string {
  const [, month, day] = iso.split('-');
  const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${day} ${months[Number(month)]}`;
}

/**
 * The administrator's overview — §8.4.
 *
 * Every figure comes from the reporting layer, so the number here and the number
 * in the report beneath it are the same number. Each metric shows its own
 * definition, because a percentage nobody can define is a percentage two people
 * will act on differently.
 */
function Overview() {
  const { user } = useAuth();
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // The attendance trend is fetched independently of the dashboard's own
  // figures, and errors independently too: `adminDashboard()` failing is a
  // page-level problem (every KPI tile and the metrics list depend on it,
  // so there is genuinely nothing else worth showing), but
  // `attendanceTrend()` failing is not — the six KPI tiles and the metrics
  // list above have already loaded and are real, useful data on their own.
  // A single `Promise.all` used to make one endpoint's failure take the
  // whole page down with it; this keeps that failure scoped to the one
  // card that actually needs it.
  // Same "compare during render, never `setState` unconditionally inside the
  // effect body" pattern every other multi-section dashboard in this app
  // already uses (`useDashboardSection` in `app/dashboard/page.tsx` and
  // `app/admissions/dashboard/page.tsx`, `ManagerOverview` in
  // `app/manage/page.tsx`) — an unconditional `setState` at the top of an
  // effect reads as a synchronous write inside that effect, which this
  // repo's lint config refuses.
  const [trendAttempt, setTrendAttempt] = useState(0);
  const [trendState, setTrendState] = useState<{
    trend: TrendPoint[];
    error: ApiError | null;
    isLoading: boolean;
    attempt: number;
  }>({ trend: [], error: null, isLoading: true, attempt: trendAttempt });

  if (trendState.attempt !== trendAttempt) {
    setTrendState({ trend: [], error: null, isLoading: true, attempt: trendAttempt });
  }
  const { trend, error: trendError, isLoading: isTrendLoading } = trendState;

  // The chart shows the shape of the trend; counted/attended are the exact
  // figures someone reconciling a register actually needs, so they stay
  // available rather than disappearing when the table became a chart.
  const [showTrendTable, setShowTrendTable] = useState(false);

  // Three more sections, each loading and failing on its own.
  const delivery = useSection(() => deliveryTrend({ weeks: 12 }), [] as DeliveryTrendPoint[]);
  const enrolments = useSection(() => enrolmentTrend({ weeks: 12 }), [] as EnrolmentTrendPoint[]);
  const batches = useSection(batchSummaries, [] as BatchSummary[]);

  const deliverySeries = heldAgainstAttendance(delivery.data, trend).map((row) => ({
    ...row,
    date: formatWeekLabel(String(row.date)),
  }));
  const enrolmentSeries = mergeByWeek([
    { rows: enrolments.data, keys: ['started', 'completed'] },
  ]).map((row) => ({ ...row, date: formatWeekLabel(String(row.date)) }));
  const attendanceByBatch = [...batches.data]
    .filter((batch) => batch.attendance_percent !== null)
    .sort((a, b) => (a.attendance_percent ?? 0) - (b.attendance_percent ?? 0))
    .slice(0, 10)
    .map((batch) => ({
      label: batch.code,
      value: batch.attendance_percent ?? 0,
      colour:
        (batch.attendance_percent ?? 0) >= ATTENDANCE_TARGET
          ? 'var(--color-success)'
          : 'var(--color-warning)',
    }));

  useEffect(() => {
    let cancelled = false;
    adminDashboard()
      .then((dashboard) => {
        if (!cancelled) setData(dashboard);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    attendanceTrend({ weeks: 12 })
      .then((points) => {
        if (!cancelled) {
          setTrendState({ trend: points, error: null, isLoading: false, attempt: trendAttempt });
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setTrendState({
            trend: [],
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            attempt: trendAttempt,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [trendAttempt]);

  if (isLoading) return <LoadingState label="Loading the overview…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the overview"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!data) return null;

  // The attendance series doubles as the sparkline behind the headline tiles.
  // It is the only trend the dashboard endpoint returns, so only the figures
  // it genuinely describes get one — a sparkline under "Published courses"
  // drawn from attendance data would be a decoration that lies. The other
  // five headline tiles (trainers, courses, batches, awaiting approval,
  // certificates) have no backing time series anywhere in `AdminDashboard`,
  // so they deliberately stay without one rather than reusing this series a
  // second time or inventing one — a genuine data gap, not an oversight.
  const attendanceSeries = trend.map((point) => point.percent);

  // The dashboard's own `attendance_rate` metric — a real snapshot, reused
  // as a gauge rather than duplicated as a second number. `75` is not a new
  // threshold: it is the exact value this same file already uses to color
  // the weekly rate badge below (`point.percent >= 75 ? 'success' :
  // 'warning'`), so the gauge and the badge agree about what "on target"
  // means.
  const attendanceRateMetric = data.metrics.find((metric) => metric.key === 'attendance_rate');

  // A true, mutually-exclusive partition of the same `counted` figure the
  // table already shows — attended vs. not-attended — summed over the
  // fetched weeks. Not a new fetch and not a new category: `TrendPoint`
  // already carries both fields.
  const attendedSum = trend.reduce((sum, point) => sum + point.attended, 0);
  const countedSum = trend.reduce((sum, point) => sum + point.counted, 0);
  const notAttendedSum = Math.max(0, countedSum - attendedSum);

  const headline = [
    {
      label: 'Active students',
      value: data.active_students,
      icon: Users,
      href: '/admin/students',
      hint: 'Enrolled and not suspended',
    },
    {
      label: 'Active trainers',
      value: data.active_trainers,
      icon: GraduationCap,
      href: '/admin/trainers',
      hint: 'Assigned to at least one batch',
    },
    {
      label: 'Published courses',
      value: data.published_courses,
      icon: BookOpen,
      href: '/admin/courses',
      hint: 'Visible in the catalogue',
    },
    {
      label: 'Active batches',
      value: data.active_batches,
      icon: Layers,
      href: '/admin/batches',
      hint: 'Running now',
    },
    {
      label: 'Awaiting approval',
      value: data.awaiting_completion_approval,
      icon: ClipboardCheck,
      href: '/admin/completions',
      hint: 'Completions needing a decision',
    },
    {
      label: 'Certificates issued',
      value: data.certificates_issued,
      icon: Award,
      href: '/admin/certificates',
      hint: 'Live, not revoked',
    },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-medium text-ink-muted">
            {greeting(user?.full_name || user?.email)}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="text-sm text-ink-muted">
            The institution at a glance. Every figure is the one the reports use.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/reports">Reports</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/imports">Bulk import</Link>
          </Button>
        </div>
      </div>

      <WarningsStrip />

      <Grid>
        {headline.map((figure) => (
          <GridItem key={figure.label} span={4}>
            <div data-testid="headline-figure" className="h-full">
              <StatCard
                label={figure.label}
                value={figure.value}
                icon={figure.icon}
                hint={figure.hint}
                href={figure.href}
                trend={figure.label === 'Active students' ? attendanceSeries : undefined}
              />
            </div>
          </GridItem>
        ))}
      </Grid>

      <Card>
        <CardHeader>
          <CardTitle as="h2">Metrics</CardTitle>
          <CardDescription>
            Each carries its definition. Hover or read below — the number is only meaningful with
            it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.metrics.map((metric) => (
            <div
              key={metric.key}
              className="rounded-md border border-line p-3"
              data-testid="metric"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium">{metric.label}</span>
                <span className="text-2xl font-semibold tabular-nums">
                  {metric.unit === 'percent'
                    ? formatPercent(metric.value, { fallbackLabel: NO_DATA })
                    : formatNumber(metric.value, { fallbackLabel: NO_DATA })}
                </span>
              </div>
              <p className="mt-1 text-sm text-ink-muted" data-testid="metric-definition">
                {metric.definition}
              </p>
              {metric.denominator ? (
                <p className="mt-1 text-xs text-ink-muted">
                  {metric.numerator} of {metric.denominator}
                </p>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>

      {/* `data-testid` so its test can scope Recharts queries to this card
          rather than counting `.recharts-area` across the page -- the three
          chart cards below would otherwise break every one of those
          assertions. */}
      <Card data-testid="attendance-trend-card">
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Attendance by week</CardTitle>
            <CardDescription>
              Excused absences leave the denominator, so a term of excused absence does not read as
              poor attendance.
            </CardDescription>
          </div>
          {!isTrendLoading && !trendError && trend.length > 0 ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowTrendTable((value) => !value)}
              aria-expanded={showTrendTable}
            >
              {showTrendTable ? 'Show chart' : 'Show exact figures'}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-6">
          {!isTrendLoading && !trendError && trend.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {attendanceRateMetric && attendanceRateMetric.value !== null ? (
                <div
                  className="flex flex-col items-center justify-center gap-2 rounded-md border border-line p-4"
                  data-testid="attendance-rate-gauge"
                >
                  <RadialProgress
                    value={attendanceRateMetric.value}
                    target={ATTENDANCE_TARGET}
                    label={`of ${ATTENDANCE_TARGET}% target`}
                    valueFormatter={(value) => `${Math.round(value)}%`}
                  />
                  <p className="text-center text-xs text-ink-muted">
                    Attendance rate against the {ATTENDANCE_TARGET}% target
                    {attendanceRateMetric.numerator != null && attendanceRateMetric.denominator != null
                      ? ` — ${formatNumber(attendanceRateMetric.numerator)} of ${formatNumber(attendanceRateMetric.denominator)}`
                      : null}
                  </p>
                  <p className="sr-only">
                    {`Attendance rate is ${Math.round(attendanceRateMetric.value)}%, against a ${ATTENDANCE_TARGET}% target`}
                    {attendanceRateMetric.numerator != null && attendanceRateMetric.denominator != null
                      ? `, based on ${attendanceRateMetric.numerator} of ${attendanceRateMetric.denominator} sessions.`
                      : '.'}
                  </p>
                </div>
              ) : null}
              <div className="rounded-md border border-line p-4">
                <DonutChart
                  data={[
                    { label: 'Attended', value: attendedSum },
                    { label: 'Not attended', value: notAttendedSum },
                  ]}
                  centerLabel="Sessions counted"
                  height={200}
                  valueFormatter={(value) => formatNumber(value)}
                  ariaLabel="Attended vs not-attended sessions, last 12 weeks"
                  emptyMessage="No registers taken yet."
                />
              </div>
            </div>
          ) : null}
          {isTrendLoading ? (
            <LoadingState label="Loading the attendance trend…" rows={4} />
          ) : trendError ? (
            <ErrorState
              title="Could not load the attendance trend"
              message={trendError.message}
              requestId={trendError.requestId || undefined}
              onRetry={() => setTrendAttempt((value) => value + 1)}
            />
          ) : showTrendTable && trend.length > 0 ? (
            <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
              <Table>
                <thead>
                  <tr>
                    <Th className="sticky top-0 z-10 bg-sunken">Week</Th>
                    <Th className="sticky top-0 z-10 bg-sunken text-right">Counted</Th>
                    <Th className="sticky top-0 z-10 bg-sunken text-right">Attended</Th>
                    <Th className="sticky top-0 z-10 bg-sunken text-right">Rate</Th>
                  </tr>
                </thead>
                <tbody className="">
                  {trend.map((point) => (
                    <tr key={point.week} className="animate-fade-in hover:bg-sunken/40">
                      <Td>{point.week}</Td>
                      <Td className="text-right tabular-nums">{formatNumber(point.counted)}</Td>
                      <Td className="text-right tabular-nums">{formatNumber(point.attended)}</Td>
                      <Td className="text-right">
                        {point.percent === null ? (
                          <span className="text-ink-muted">{NO_DATA}</span>
                        ) : (
                          <Badge variant={point.percent >= 75 ? 'success' : 'warning'}>
                            {formatPercent(point.percent)}
                          </Badge>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          ) : (
            <AreaChart
              data={trend.map((point) => ({ date: point.week, value: point.percent }))}
              series={[{ key: 'value', label: 'Attendance rate' }]}
              xLabel="Week"
              height={280}
              valueFormatter={(value) => formatPercent(value)}
              emptyMessage="No registers taken yet."
              ariaLabel="Attendance rate by week"
            />
          )}
        </CardContent>
      </Card>

      <Grid>
        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Classes held and attendance rate"
            subtitle="Volume against rate — a busy week and a well-attended one are not the same week"
            icon={Activity}
            testId="delivery-combo-card"
            footer={
              <Link href="/analytics" className="font-medium text-action hover:underline">
                See the full analytics →
              </Link>
            }
          >
            <ComboChart
              data={deliverySeries}
              bars={[{ key: 'held', label: 'Classes held' }]}
              lines={[{ key: 'percent', label: 'Attendance rate' }]}
              rightAxisKeys={['percent']}
              leftLabel="Classes"
              rightLabel="Attendance %"
              xLabel="Week"
              height={240}
              loading={delivery.isLoading || isTrendLoading}
              emptyMessage="No classes in the last twelve weeks"
              valueFormatter={(value) => formatNumber(value)}
              rightValueFormatter={(value) => formatPercent(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Enrolments over time"
            subtitle="Enrolments started each week, and how many of them completed"
            icon={GraduationCap}
            iconTone="info"
            testId="enrolment-trend-card"
            legend={[
              { label: 'Started', color: paletteColor(0) },
              { label: 'Completed', color: paletteColor(1) },
            ]}
          >
            <AreaChart
              data={enrolmentSeries}
              series={[
                { key: 'started', label: 'Started' },
                { key: 'completed', label: 'Completed' },
              ]}
              gradient
              hideLegend
              xLabel="Week"
              height={240}
              loading={enrolments.isLoading}
              emptyMessage="No enrolments in the last twelve weeks"
              valueFormatter={(value) => formatNumber(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12}>
          <ChartCard
            title="Attendance by batch"
            subtitle={`The ten lowest of the batches you can see. Amber is below the ${ATTENDANCE_TARGET}% target.`}
            icon={CalendarCheck}
            iconTone="success"
            testId="attendance-by-batch-card"
          >
            <HorizontalBarChart
              data={attendanceByBatch}
              series={[{ key: 'value', label: 'Attendance' }]}
              colorKey="colour"
              categoryWidth={120}
              height={Math.max(180, attendanceByBatch.length * 32)}
              loading={batches.isLoading}
              emptyMessage="No batch has a register yet"
              valueFormatter={(value) => formatPercent(value)}
            />
          </ChartCard>
        </GridItem>
      </Grid>
    </div>
  );
}

export default function OverviewPage() {
  return (
    <RequireAuth>
      <Overview />
    </RequireAuth>
  );
}
