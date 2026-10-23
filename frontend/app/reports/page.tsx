'use client';

/**
 * Reports — the five tabs the desk reads its month from.
 *
 * Tiles across the top, the filter row above them, the rows underneath. The
 * tiles are the server's figures for exactly the rows below: a report that
 * totals more than it lists is worse than no report, because somebody reads
 * the tile out loud and nobody can find the missing money.
 *
 * The filter set is the screen's own, minus two. "Standard" and "Subject" are
 * school vocabulary — a standard here is how courses are grouped, and the
 * course filter already says it better — so they are left out rather than
 * drawn as selects that would narrow nothing.
 */

import { useEffect, useMemo, useState } from 'react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { RequireAuth } from '@/components/require-auth';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/layout';
import { useSection } from '@/hooks/use-section';
import {
  getAdmissionReport,
  REPORT_TABS,
  type AdmissionReport,
  type ReportFilters,
  type ReportTab,
} from '@/lib/admission-reports';
import { listAcademicYears, type AcademicYear } from '@/lib/academic-years';
import { Capability } from '@/lib/capabilities';
import { listCourses } from '@/lib/courses';
import { formatDate, formatRupees } from '@/lib/format';
import type { CourseListRow } from '@/types/api';

/** What each tab's table shows, in the order the original draws it. The
 *  `money` flag decides the alignment and the "Rs." prefix in one place. */
const COLUMNS: Record<ReportTab, { key: string; header: string; money?: boolean; date?: boolean }[]> = {
  overall: [
    { key: 'admission_date', header: 'Admission Date', date: true },
    { key: 'student_name', header: 'Name' },
    { key: 'courses', header: 'Courses' },
    { key: 'total', header: 'Total', money: true },
    { key: 'paid', header: 'Paid', money: true },
    { key: 'uncleared', header: 'Uncleared', money: true },
    { key: 'refund', header: 'Refund', money: true },
    { key: 'balance', header: 'Balance', money: true },
  ],
  discount: [
    { key: 'admission_date', header: 'Admission Date', date: true },
    { key: 'student_name', header: 'Name' },
    { key: 'courses', header: 'Courses' },
    { key: 'gross_total', header: 'Fees', money: true },
    { key: 'discount', header: 'Discount', money: true },
    { key: 'total', header: 'Total', money: true },
  ],
  expiry: [
    { key: 'student_name', header: 'Name' },
    { key: 'course', header: 'Course' },
    { key: 'batch', header: 'Batch' },
    { key: 'access_end_date', header: 'Expires', date: true },
    { key: 'days_left', header: 'Days left' },
    { key: 'balance', header: 'Balance', money: true },
  ],
  'additional-fees': [
    { key: 'admission_date', header: 'Admission Date', date: true },
    { key: 'student_name', header: 'Name' },
    { key: 'label', header: 'Fee' },
    { key: 'charged_on', header: 'Charged on' },
    { key: 'quantity', header: 'Qty' },
    { key: 'amount', header: 'Amount', money: true },
  ],
  coursewise: [
    { key: 'course', header: 'Course' },
    { key: 'admissions', header: 'Admissions' },
    { key: 'total', header: 'Total', money: true },
    { key: 'received', header: 'Received', money: true },
    { key: 'balance', header: 'Balance', money: true },
  ],
};

/** The tiles, in the order each tab shows them, with the colour each wears.
 *  Colour means state here as everywhere: money in is `success`, money owed
 *  is `danger`, money waiting is `warning`. */
const TILES: Record<ReportTab, { key: string; label: string; money?: boolean; tone: string }[]> = {
  overall: [
    { key: 'admissions', label: 'Admissions', tone: 'bg-warning/10 text-ink' },
    { key: 'total', label: 'Total', money: true, tone: 'bg-action/10 text-action' },
    { key: 'received', label: 'Received', money: true, tone: 'bg-success/10 text-success' },
    { key: 'cleared', label: 'Cleared', money: true, tone: 'bg-success/10 text-success' },
    { key: 'uncleared', label: 'Uncleared', money: true, tone: 'bg-warning/10 text-warning' },
    { key: 'balance', label: 'Balance', money: true, tone: 'bg-danger/10 text-danger' },
    { key: 'refund', label: 'Refund', money: true, tone: 'bg-sunken text-ink' },
    { key: 'cancelled', label: 'Cancelled', money: true, tone: 'bg-danger/10 text-danger' },
  ],
  discount: [
    { key: 'admissions', label: 'Admissions', tone: 'bg-warning/10 text-ink' },
    { key: 'discount', label: 'Discount given', money: true, tone: 'bg-danger/10 text-danger' },
    { key: 'total', label: 'Total after discount', money: true, tone: 'bg-action/10 text-action' },
  ],
  expiry: [
    { key: 'enrolments', label: 'Enrolments', tone: 'bg-action/10 text-action' },
    { key: 'expired', label: 'Already expired', tone: 'bg-danger/10 text-danger' },
    { key: 'expiring_in_30_days', label: 'Expiring in 30 days', tone: 'bg-warning/10 text-warning' },
    { key: 'balance', label: 'Balance', money: true, tone: 'bg-danger/10 text-danger' },
  ],
  'additional-fees': [
    { key: 'fees', label: 'Fees charged', tone: 'bg-action/10 text-action' },
    { key: 'total', label: 'Total', money: true, tone: 'bg-success/10 text-success' },
  ],
  coursewise: [
    { key: 'courses', label: 'Courses', tone: 'bg-action/10 text-action' },
    { key: 'admissions', label: 'Admissions', tone: 'bg-warning/10 text-ink' },
    { key: 'total', label: 'Total', money: true, tone: 'bg-success/10 text-success' },
  ],
};

export function ReportsScreen() {
  const [tab, setTab] = useState<ReportTab>('overall');
  const [filters, setFilters] = useState<ReportFilters>({});
  const [years, setYears] = useState<AcademicYear[]>([]);
  const [courses, setCourses] = useState<CourseListRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAcademicYears(), listCourses({ page_size: 200 })])
      .then(([yearRows, coursePage]) => {
        if (cancelled) return;
        setYears(yearRows);
        setCourses(coursePage.results);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const key = JSON.stringify([tab, filters]);
  const report = useSection<AdmissionReport | null>(
    () => getAdmissionReport(tab, filters),
    null,
    [key],
  );

  const columns: DataTableColumn<Record<string, string | number | null>>[] = useMemo(
    () =>
      COLUMNS[tab].map((column) => ({
        key: column.key,
        header: column.header,
        align: column.money ? ('right' as const) : undefined,
        render: (row) => {
          const value = row[column.key];
          if (value === null || value === undefined || value === '') return '—';
          if (column.money) {
            return <span className="tabular-nums">{formatRupees(value)}</span>;
          }
          if (column.date) return <span className="tabular-nums">{formatDate(value)}</span>;
          return String(value);
        },
      })),
    [tab],
  );

  function set(patch: ReportFilters) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Reports" meta="Across the admissions you are allowed to see." />

      <nav className="flex flex-wrap gap-1" aria-label="Reports">
        {REPORT_TABS.map((entry) => (
          <button
            key={entry.key}
            type="button"
            onClick={() => setTab(entry.key)}
            aria-current={tab === entry.key ? 'page' : undefined}
            className={
              tab === entry.key
                ? 'rounded-control bg-action px-3 py-1.5 text-sm font-medium text-action-fg'
                : 'rounded-control px-3 py-1.5 text-sm text-action hover:bg-sunken'
            }
          >
            {entry.label}
          </button>
        ))}
      </nav>

      <div className="grid gap-3 rounded-card bg-sunken/50 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Academic Year" htmlFor="report-year">
          <Select
            id="report-year"
            value={filters.academic_year ?? ''}
            onChange={(event) => set({ academic_year: event.target.value })}
          >
            <option value="">All</option>
            {years.map((year) => (
              <option key={year.id} value={year.id}>
                {year.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Status" htmlFor="report-status">
          <Select
            id="report-status"
            value={filters.status ?? ''}
            onChange={(event) => set({ status: event.target.value })}
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="cancelled">Cancelled</option>
          </Select>
        </Field>
        <Field label="Course" htmlFor="report-course">
          <Select
            id="report-course"
            value={filters.course ?? ''}
            onChange={(event) => set({ course: event.target.value })}
          >
            <option value="">Select Course</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.title}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Start Date" htmlFor="report-start">
            <Input
              id="report-start"
              type="date"
              value={filters.start_date ?? ''}
              onChange={(event) => set({ start_date: event.target.value })}
            />
          </Field>
          <Field label="End Date" htmlFor="report-end">
            <Input
              id="report-end"
              type="date"
              value={filters.end_date ?? ''}
              onChange={(event) => set({ end_date: event.target.value })}
            />
          </Field>
        </div>
        <div className="sm:col-span-2 lg:col-span-4">
          <Button variant="outline" size="sm" onClick={() => setFilters({})}>
            Clear filters
          </Button>
        </div>
      </div>

      {/* Named, because several of these labels ("Total", "Balance") are also
          column headings in the table below, and a screen reader meeting the
          second one needs to know which it is in. */}
      <ul aria-label="Report totals" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {TILES[tab].map((tile) => (
          <li key={tile.key} className={`rounded-card p-4 ${tile.tone}`}>
            <p className="text-sm font-medium">{tile.label}</p>
            <p className="text-xl font-semibold tabular-nums">
              {report.data
                ? tile.money
                  ? formatRupees(report.data.tiles[tile.key])
                  : String(report.data.tiles[tile.key] ?? 0)
                : '—'}
            </p>
          </li>
        ))}
      </ul>

      <DataTable
        columns={columns}
        rows={report.data?.rows ?? []}
        getRowId={(row, index = 0) => String(row.id ?? row.enrollment_id ?? row.course_id ?? index)}
        isLoading={report.isLoading}
        loadingLabel="Running the report…"
        error={
          report.error
            ? { message: report.error.message, requestId: report.error.requestId || undefined }
            : null
        }
        onRetry={report.reload}
        emptyTitle="Nothing in this range"
        emptyDescription="Widen the dates, or clear the filters."
        caption="Report results"
        densityStorageKey="admission-reports"
      />
    </div>
  );
}

export default function ReportsPage() {
  return (
    <RequireAuth capability={Capability.feeViewAny}>
      <ReportsScreen />
    </RequireAuth>
  );
}
