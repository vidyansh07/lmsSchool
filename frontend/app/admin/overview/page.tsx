'use client';

import { Award, BookOpen, ClipboardCheck, GraduationCap, Layers, Users } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AreaChart } from '@/components/ui/charts';
import { BentoGrid, BentoTile, StatCard } from '@/components/ui/motion';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { WarningsStrip } from '@/components/warnings-strip';
import { ApiError } from '@/lib/api';
import { formatNumber, formatPercent, NO_DATA } from '@/lib/format';
import { adminDashboard, attendanceTrend } from '@/lib/reporting';
import type { AdminDashboard, TrendPoint } from '@/types/api';

/**
 * The administrator's overview — §8.4.
 *
 * Every figure comes from the reporting layer, so the number here and the number
 * in the report beneath it are the same number. Each metric shows its own
 * definition, because a percentage nobody can define is a percentage two people
 * will act on differently.
 */
function Overview() {
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // The chart shows the shape of the trend; counted/attended are the exact
  // figures someone reconciling a register actually needs, so they stay
  // available rather than disappearing when the table became a chart.
  const [showTrendTable, setShowTrendTable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([adminDashboard(), attendanceTrend({ weeks: 12 })])
      .then(([dashboard, points]) => {
        if (cancelled) return;
        setData(dashboard);
        setTrend(points);
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
  // drawn from attendance data would be a decoration that lies.
  const attendanceSeries = trend.map((point) => point.percent);

  const headline = [
    {
      label: 'Active students',
      accent: 'blue' as const,
      value: data.active_students,
      icon: Users,
      href: '/admin/students',
      hint: 'Enrolled and not suspended',
    },
    {
      label: 'Active trainers',
      accent: 'violet' as const,
      value: data.active_trainers,
      icon: GraduationCap,
      href: '/admin/trainers',
      hint: 'Assigned to at least one batch',
    },
    {
      label: 'Published courses',
      accent: 'amber' as const,
      value: data.published_courses,
      icon: BookOpen,
      href: '/admin/courses',
      hint: 'Visible in the catalogue',
    },
    {
      label: 'Active batches',
      accent: 'green' as const,
      value: data.active_batches,
      icon: Layers,
      href: '/admin/batches',
      hint: 'Running now',
    },
    {
      label: 'Awaiting approval',
      accent: 'rose' as const,
      value: data.awaiting_completion_approval,
      icon: ClipboardCheck,
      href: '/admin/completions',
      hint: 'Completions needing a decision',
    },
    {
      label: 'Certificates issued',
      accent: 'pink' as const,
      value: data.certificates_issued,
      icon: Award,
      href: '/admin/certificates',
      hint: 'Live, not revoked',
    },
  ] as const;

  return (
    <div className="animate-rise-in space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="text-sm text-muted-foreground">
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

      <BentoGrid>
        {headline.map((figure, index) => (
          <BentoTile key={figure.label} span={4} index={index}>
            <div data-testid="headline-figure" className="h-full">
              <StatCard
                label={figure.label}
                value={figure.value}
                icon={figure.icon}
                hint={figure.hint}
                href={figure.href}
                accent={figure.accent}
                trend={figure.label === 'Active students' ? attendanceSeries : undefined}
              />
            </div>
          </BentoTile>
        ))}
      </BentoGrid>

      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
          <CardDescription>
            Each carries its definition. Hover or read below — the number is only meaningful with
            it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.metrics.map((metric) => (
            <div
              key={metric.key}
              className="rounded-md border border-border p-3"
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
              <p className="mt-1 text-sm text-muted-foreground" data-testid="metric-definition">
                {metric.definition}
              </p>
              {metric.denominator ? (
                <p className="mt-1 text-xs text-muted-foreground">
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
          {trend.length > 0 ? (
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
        <CardContent>
          {showTrendTable && trend.length > 0 ? (
            <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
              <Table>
                <thead>
                  <tr>
                    <Th className="sticky top-0 z-10 bg-muted">Week</Th>
                    <Th className="sticky top-0 z-10 bg-muted text-right">Counted</Th>
                    <Th className="sticky top-0 z-10 bg-muted text-right">Attended</Th>
                    <Th className="sticky top-0 z-10 bg-muted text-right">Rate</Th>
                  </tr>
                </thead>
                <tbody className="stagger">
                  {trend.map((point) => (
                    <tr key={point.week} className="animate-fade-in hover:bg-muted/40">
                      <Td>{point.week}</Td>
                      <Td className="text-right tabular-nums">{formatNumber(point.counted)}</Td>
                      <Td className="text-right tabular-nums">{formatNumber(point.attended)}</Td>
                      <Td className="text-right">
                        {point.percent === null ? (
                          <span className="text-muted-foreground">{NO_DATA}</span>
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
