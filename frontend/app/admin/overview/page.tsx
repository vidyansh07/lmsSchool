'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
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

  const headline = [
    ['Active students', data.active_students],
    ['Active trainers', data.active_trainers],
    ['Published courses', data.published_courses],
    ['Active batches', data.active_batches],
    ['Awaiting approval', data.awaiting_completion_approval],
    ['Certificates issued', data.certificates_issued],
  ] as const;

  return (
    <div className="space-y-6">
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

      <div className="grid gap-3 sm:grid-cols-3">
        {headline.map(([label, value]) => (
          <Card key={label} data-testid="headline-figure">
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="text-3xl font-semibold">{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
          <CardDescription>
            Each carries its definition. Hover or read below — the number is only
            meaningful with it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.metrics.map((metric) => (
            <div key={metric.key} className="rounded-md border border-border p-3" data-testid="metric">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium">{metric.label}</span>
                <span className="text-2xl font-semibold">
                  {metric.value === null
                    ? '—'
                    : metric.unit === 'percent'
                      ? `${metric.value}%`
                      : metric.value}
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
        <CardHeader>
          <CardTitle>Attendance by week</CardTitle>
          <CardDescription>
            Excused absences leave the denominator, so a term of excused absence does
            not read as poor attendance.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trend.length === 0 ? (
            <p className="text-sm text-muted-foreground">No registers taken yet.</p>
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Week</Th>
                    <Th>Counted</Th>
                    <Th>Attended</Th>
                    <Th>Rate</Th>
                  </tr>
                </thead>
                <tbody>
                  {trend.map((point) => (
                    <tr key={point.week}>
                      <Td>{point.week}</Td>
                      <Td>{point.counted}</Td>
                      <Td>{point.attended}</Td>
                      <Td>
                        {point.percent === null ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <Badge variant={point.percent >= 75 ? 'success' : 'warning'}>
                            {point.percent}%
                          </Badge>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
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
