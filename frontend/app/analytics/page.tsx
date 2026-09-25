'use client';

/**
 * Analytics — the shape of the institution, over time.
 *
 * Its relationship to the two screens next to it is deliberate, and each
 * card states it so the three never become three answers to one question:
 *
 * - `/admin/reports` is the **runner**: row-level data, saved filters, CSV
 *   and queued exports. Every chart here links into the matching report.
 * - `/admin/overview` is the **KPI and definitions** screen -- six figures
 *   and what each one means. This page does not duplicate its tiles.
 * - This page is the **shape**: aggregates only, no row-level data.
 *
 * Every section loads independently through `useSection`, so one failing
 * endpoint costs one card rather than blanking the screen.
 *
 * Who may see it: `report.view_any` only, which is admin, manager and
 * superadmin. A trainer passes the reporting layer's own `can_read_reports`
 * (through their trainer profile) so the three trend endpoints would work
 * for them -- but `/dashboards/admin/` requires the global capability and
 * would 403, leaving them a page whose headline strip errors. Their
 * enrichment belongs on `/teaching/today`, which is their screen.
 */

import {
  Activity,
  CalendarCheck,
  ClipboardList,
  GraduationCap,
  TrendingUp,
} from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { ExportMenu } from '@/components/export-menu';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import {
  AreaChart,
  ChartCard,
  ComboChart,
  DonutChart,
  HorizontalBarChart,
  BarChart,
  paletteColor,
} from '@/components/ui/charts';
import { Field } from '@/components/ui/field';
import { Grid, GridItem, PageHeader, Section } from '@/components/ui/layout';
import { Select } from '@/components/ui/input';
import { StatStrip } from '@/components/ui/stat-strip';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useSection } from '@/hooks/use-section';
import { heldAgainstAttendance, mergeByWeek } from '@/lib/analytics';
import { formatNumber, formatPercent } from '@/lib/format';
import {
  adminDashboard,
  attendanceTrend,
  batchSummaries,
  deliveryTrend,
  dsrComplianceTrend,
  enrolmentTrend,
} from '@/lib/reporting';
import type { AdminDashboard, BatchSummary } from '@/types/api';

/** The same 75% this product already colours a weekly attendance badge with,
 *  reused here so two screens never disagree about "on target". */
const ATTENDANCE_TARGET = 75;

/** Matches `AttendanceTrendView`'s own 1..52 clamp, so a chosen value means
 *  what it says rather than being quietly narrowed server-side. */
const PERIODS = [4, 12, 26, 52] as const;

const EMPTY_DASHBOARD: AdminDashboard | null = null;

function formatWeek(iso: string): string {
  // The API sends the Monday of each week. Rendered short, because a
  // twelve-tick axis has no room for a year on every label.
  const [, month, day] = iso.split('-');
  return `${day} ${['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(month)]}`;
}

/** A chart card's link to the rows behind the shape. */
function RowsLink({ report, children }: { report: string; children: string }) {
  return (
    <Link
      href={`/admin/reports?report=${report}`}
      className="font-medium text-action hover:underline"
    >
      {children} →
    </Link>
  );
}

function Analytics() {
  const [weeks, setWeeks] = useState<number>(12);

  const dashboard = useSection(adminDashboard, EMPTY_DASHBOARD);
  const attendance = useSection(() => attendanceTrend({ weeks }), [], [weeks]);
  const enrolments = useSection(() => enrolmentTrend({ weeks }), [], [weeks]);
  const delivery = useSection(() => deliveryTrend({ weeks }), [], [weeks]);
  const dsr = useSection(() => dsrComplianceTrend({ weeks }), [], [weeks]);
  const batches = useSection(batchSummaries, [] as BatchSummary[]);

  const attendanceRate = attendance.data.length
    ? (attendance.data.reduce((total, point) => total + (point.percent ?? 0), 0) /
        attendance.data.filter((point) => point.percent !== null).length || null)
    : null;

  const enrolmentSeries = mergeByWeek([
    { rows: enrolments.data, keys: ['started', 'active', 'completed', 'cancelled'] },
  ]).map((row) => ({ ...row, date: formatWeek(String(row.date)) }));

  const deliverySeries = heldAgainstAttendance(delivery.data, attendance.data).map((row) => ({
    ...row,
    date: formatWeek(String(row.date)),
  }));

  const dsrSeries = mergeByWeek([
    { rows: dsr.data, keys: ['submitted', 'approved', 'rejected'] },
  ]).map((row) => ({ ...row, date: formatWeek(String(row.date)) }));

  const outstandingByWeek = delivery.data.map((point) => ({
    label: formatWeek(point.week),
    value: point.registers_outstanding,
  }));

  // Ranked lowest-first, and coloured by whether each batch clears the
  // target rather than by its position. A per-bar hue here would be pure
  // decoration -- every bar is the same metric, so a rainbow says nothing --
  // whereas "below target" is a state, which is what colour is for.
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

  // Five slices at most: `DonutChart` warns past that, and rightly -- a
  // composition of seven categories is a comparison wearing a donut.
  // `started` is every enrolment opened in the window; active, completed
  // and cancelled are three of the six statuses it can be in. Without the
  // remainder the donut's total came out below the strip's "Enrolments"
  // figure beside it, which reads as one of the two being wrong.
  const enrolmentTotals = enrolments.data.reduce(
    (totals, point) => ({
      started: totals.started + point.started,
      active: totals.active + point.active,
      completed: totals.completed + point.completed,
      cancelled: totals.cancelled + point.cancelled,
    }),
    { started: 0, active: 0, completed: 0, cancelled: 0 },
  );
  const enrolmentMix = [
    { label: 'Active', value: enrolmentTotals.active },
    { label: 'Completed', value: enrolmentTotals.completed },
    { label: 'Cancelled', value: enrolmentTotals.cancelled },
    {
      label: 'Pending or on hold',
      value: Math.max(
        0,
        enrolmentTotals.started -
          enrolmentTotals.active -
          enrolmentTotals.completed -
          enrolmentTotals.cancelled,
      ),
    },
  ].filter((slice) => slice.value > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        meta={`The last ${weeks} weeks, to today. Aggregates only — the rows behind each shape live in Reports.`}
      >
        <Field label="Period" htmlFor="analytics-period" className="min-w-40">
          <Select
            id="analytics-period"
            value={String(weeks)}
            onChange={(event) => setWeeks(Number(event.target.value))}
          >
            {PERIODS.map((value) => (
              <option key={value} value={value}>
                Last {value} weeks
              </option>
            ))}
          </Select>
        </Field>
        <ExportMenu reportKey="attendance" filters={{}} size="md" />
      </PageHeader>

      <Section title="Overview" meta="Where the institution stands right now">
        {dashboard.error ? (
          <ErrorState
            title="The headline figures did not load"
            message={dashboard.error.message}
            requestId={dashboard.error.requestId ?? undefined}
            onRetry={dashboard.reload}
          />
        ) : (
          <StatStrip
            items={[
              { label: 'Active students', value: dashboard.data?.active_students },
              { label: 'Active batches', value: dashboard.data?.active_batches },
              { label: 'Published courses', value: dashboard.data?.published_courses },
              { label: 'Active trainers', value: dashboard.data?.active_trainers },
              {
                label: 'Attendance',
                value: attendanceRate === null ? null : Math.round(attendanceRate),
                suffix: '%',
              },
              { label: 'Enrolments', value: enrolmentTotals.started },
              { label: 'Certificates', value: dashboard.data?.certificates_issued },
            ]}
          />
        )}
      </Section>

      <Grid>
        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Enrolments over time"
            subtitle="Enrolments started each week, and where each cohort stands now"
            icon={GraduationCap}
            iconTone="info"
            testId="enrolment-trend-card"
            legend={[
              { label: 'Started', color: paletteColor(0) },
              { label: 'Completed', color: paletteColor(1) },
            ]}
            footer={<RowsLink report="enrollments">View the enrolments</RowsLink>}
          >
            {/* Two series, not four. `started` and `active` are nearly the
                same line in practice, and four overlapping gradient fills
                render as grey mud rather than as four readable areas -- the
                full status mix is the donut below, which is the right shape
                for a composition. */}
            <AreaChart
              data={enrolmentSeries}
              series={[
                { key: 'started', label: 'Started' },
                { key: 'completed', label: 'Completed' },
              ]}
              gradient
              hideLegend
              xLabel="Week"
              height={260}
              loading={enrolments.isLoading}
              emptyMessage="No enrolments in this period"
              valueFormatter={(value) => formatNumber(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Registers still owed"
            subtitle="Classes that finished and were marked complete with no register taken"
            icon={ClipboardList}
            iconTone="warning"
            testId="registers-outstanding-card"
            footer={<RowsLink report="attendance">View the registers</RowsLink>}
          >
            <BarChart
              data={outstandingByWeek}
              series={[{ key: 'value', label: 'Outstanding' }]}
              colorPerBar
              height={260}
              loading={delivery.isLoading}
              emptyMessage="Every register is in"
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
            footer={<RowsLink report="batch_performance">View batch performance</RowsLink>}
          >
            <HorizontalBarChart
              data={attendanceByBatch}
              series={[{ key: 'value', label: 'Attendance' }]}
              colorKey="colour"
              categoryWidth={120}
              height={Math.max(200, attendanceByBatch.length * 34)}
              loading={batches.isLoading}
              emptyMessage="No batch has a register yet"
              valueFormatter={(value) => formatPercent(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Classes held and attendance rate"
            subtitle="Volume against rate — a busy week and a well-attended one are not the same week"
            icon={Activity}
            iconTone="neutral"
            testId="delivery-combo-card"
            footer={<RowsLink report="daily_reports">View the daily reports</RowsLink>}
          >
            <ComboChart
              data={deliverySeries}
              bars={[{ key: 'held', label: 'Classes held' }]}
              lines={[{ key: 'percent', label: 'Attendance rate' }]}
              rightAxisKeys={['percent']}
              leftLabel="Classes"
              rightLabel="Attendance %"
              xLabel="Week"
              height={260}
              loading={delivery.isLoading || attendance.isLoading}
              emptyMessage="No classes in this period"
              valueFormatter={(value) => formatNumber(value)}
              rightValueFormatter={(value) => formatPercent(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Enrolment mix"
            subtitle="Where every enrolment started in this period now stands"
            icon={TrendingUp}
            iconTone="info"
            testId="enrolment-mix-card"
          >
            <DonutChart
              data={enrolmentMix}
              centerLabel="Enrolments"
              height={260}
              loading={enrolments.isLoading}
              emptyMessage="No enrolments in this period"
              valueFormatter={(value) => formatNumber(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12}>
          <ChartCard
            title="Daily report compliance"
            subtitle="Reports submitted, approved and sent back each week — submission only, not the attendance they carry"
            icon={ClipboardList}
            iconTone="neutral"
            testId="dsr-compliance-card"
            legend={[
              { label: 'Submitted', color: paletteColor(0) },
              { label: 'Approved', color: paletteColor(1) },
              { label: 'Sent back', color: paletteColor(2) },
            ]}
            footer={<RowsLink report="daily_reports">View the daily reports</RowsLink>}
          >
            <AreaChart
              data={dsrSeries}
              series={[
                { key: 'submitted', label: 'Submitted' },
                { key: 'approved', label: 'Approved' },
                { key: 'rejected', label: 'Sent back' },
              ]}
              gradient
              hideLegend
              xLabel="Week"
              height={240}
              loading={dsr.isLoading}
              emptyMessage="No daily reports in this period"
              valueFormatter={(value) => formatNumber(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12}>
          <ChartCard
            title="Batch performance"
            subtitle="Every batch you can see, with how many students and how well they attend"
            icon={CalendarCheck}
            iconTone="neutral"
            testId="batch-table-card"
            footer={<RowsLink report="batch_performance">Run the full report</RowsLink>}
          >
            {batches.data.length === 0 ? null : (
              <TableWrapper className="border-0 ring-0">
                <Table>
                  <thead>
                    <tr>
                      <Th>Batch</Th>
                      <Th>Course</Th>
                      <Th>Status</Th>
                      <Th>Students</Th>
                      <Th>Attendance</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {batches.data.map((batch) => (
                      <tr key={batch.id}>
                        <Td>
                          <span className="font-medium">{batch.code}</span>
                          <span className="block text-xs text-ink-faint">{batch.name}</span>
                        </Td>
                        <Td>{batch.course_title}</Td>
                        <Td>
                          <Badge variant="neutral" dot={false}>
                            {batch.status}
                          </Badge>
                        </Td>
                        <Td data-numeric>{formatNumber(batch.students)}</Td>
                        <Td>
                          {batch.attendance_percent === null ? (
                            <span className="text-ink-faint">No register yet</span>
                          ) : (
                            <span
                              data-numeric
                              className={
                                batch.attendance_percent >= ATTENDANCE_TARGET
                                  ? 'font-medium text-success'
                                  : 'font-medium text-warning'
                              }
                            >
                              {formatPercent(batch.attendance_percent)}
                            </span>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrapper>
            )}
          </ChartCard>
        </GridItem>
      </Grid>
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <RequireAuth capability="report.view_any">
      <Analytics />
    </RequireAuth>
  );
}
