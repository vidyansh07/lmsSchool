'use client';

import { Award, BookOpen, ClipboardCheck, GraduationCap, Layers, Users } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AreaChart, DonutChart, RadialProgress } from '@/components/ui/charts';
import { Grid, GridItem } from '@/components/ui/layout';
import { StatCard } from '@/components/ui/stat';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { WarningsStrip } from '@/components/warnings-strip';
import { ApiError } from '@/lib/api';
import { formatNumber, formatPercent, NO_DATA } from '@/lib/format';
import { greeting } from '@/lib/greeting';
import { adminDashboard, attendanceTrend } from '@/lib/reporting';
import type { AdminDashboard, TrendPoint } from '@/types/api';

/** The exact threshold this file already colors the weekly rate badge with
 *  (`point.percent >= 75 ? 'success' : 'warning'`, below) — reused as the
 *  attendance gauge's target so the gauge and the badge never disagree
 *  about what "on target" means. */
const ATTENDANCE_TARGET = 75;

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

      <Card>
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
