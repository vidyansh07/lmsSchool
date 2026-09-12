'use client';

/**
 * The counsellor's working list.
 *
 * This is the screen somebody leaves open all day: every recent registration,
 * with the enrolment it produced and where that enrolment stands. It reads
 * `/api/v1/enrollments/`, not `/api/v1/students/`, because "enrolment state" is
 * the whole point of the row — a student who has only been registered and not
 * yet placed on a batch has nothing to show here yet, and belongs on the "new
 * registration" screen finishing the job rather than a working list of
 * finished ones. See the module docstring on `lib/batches.ts` for the same
 * reasoning applied to one student's history.
 *
 * Course and batch filters are resolved to real query parameters the API
 * understands (`course` wants a slug, `batch` a UUID); the registration date
 * range is not one of the fields `EnrollmentFilterSet` accepts, so — rather
 * than silently send a parameter the server ignores — it is applied to
 * whatever page is already on screen and says so next to the count.
 */

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { money } from '@/components/fees/fee-ledger';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { listBatches, listEnrollments } from '@/lib/batches';
import {
  ENROLLMENT_STATUS_LABEL,
  ENROLLMENT_STATUS_OPTIONS,
  ENROLLMENT_STATUS_VARIANT,
  formatDate,
} from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { listCourses } from '@/lib/courses';
import type { BatchListRow, CourseListRow, Enrollment } from '@/types/api';

export function AdmissionsList() {
  const list = useList<Enrollment>(listEnrollments, { page_size: 20 });
  const [courses, setCourses] = useState<CourseListRow[]>([]);
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [registeredFrom, setRegisteredFrom] = useState('');
  const [registeredTo, setRegisteredTo] = useState('');

  useEffect(() => {
    listCourses({ page_size: 100, ordering: 'title' })
      .then((page) => setCourses(page.results))
      .catch(() => setCourses([]));
    listBatches({ page_size: 100, ordering: '-start_date' })
      .then((page) => setBatches(page.results))
      .catch(() => setBatches([]));
  }, []);

  const sortDirection = list.query.ordering?.startsWith('-') ? 'desc' : 'asc';
  const sortField = list.query.ordering?.replace(/^-/, '');

  // The API cannot filter by registration date, so this narrows only the rows
  // already on the page rather than pretending to search the whole table.
  const visibleRows = useMemo(() => {
    const rows = list.data?.results ?? [];
    if (!registeredFrom && !registeredTo) return rows;
    return rows.filter((row) => {
      const day = row.enrolled_at.slice(0, 10);
      if (registeredFrom && day < registeredFrom) return false;
      if (registeredTo && day > registeredTo) return false;
      return true;
    });
  }, [list.data, registeredFrom, registeredTo]);

  const dateFilterActive = Boolean(registeredFrom || registeredTo);

  return (
    <div className="space-y-4">
      <div className="animate-rise-in flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Admissions</h1>
          <p className="text-sm text-muted-foreground">
            Recent registrations and where each one stands. Open a row to transfer, withdraw or
            re-enrol.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href="/admissions/import">Import students</Link>
          </Button>
          <Button asChild>
            <Link href="/admissions/new">Register a student</Link>
          </Button>
        </div>
      </div>

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Enrolment code, student ID, email or batch code"
      >
        <div>
          <label htmlFor="filter-course" className="mb-1.5 block text-sm font-medium">
            Course
          </label>
          <Select
            id="filter-course"
            value={String(list.query.course ?? '')}
            onChange={(event) => list.setQuery({ course: event.target.value })}
          >
            <option value="">All courses</option>
            {courses.map((course) => (
              <option key={course.id} value={course.slug}>
                {course.title}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-batch" className="mb-1.5 block text-sm font-medium">
            Batch
          </label>
          <Select
            id="filter-batch"
            value={String(list.query.batch ?? '')}
            onChange={(event) => list.setQuery({ batch: event.target.value })}
          >
            <option value="">All batches</option>
            {batches.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.code} — {batch.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-status" className="mb-1.5 block text-sm font-medium">
            Status
          </label>
          <Select
            id="filter-status"
            value={String(list.query.status ?? '')}
            onChange={(event) => list.setQuery({ status: event.target.value })}
          >
            <option value="">All statuses</option>
            {ENROLLMENT_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-registered-from" className="mb-1.5 block text-sm font-medium">
            Registered from
          </label>
          <Input
            id="filter-registered-from"
            type="date"
            value={registeredFrom}
            onChange={(event) => setRegisteredFrom(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="filter-registered-to" className="mb-1.5 block text-sm font-medium">
            Registered to
          </label>
          <Input
            id="filter-registered-to"
            type="date"
            value={registeredTo}
            onChange={(event) => setRegisteredTo(event.target.value)}
          />
        </div>
      </ListToolbar>

      {list.isLoading ? (
        <LoadingState label="Loading admissions…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load admissions"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title="No registrations match these filters"
          description="Try a different search term, or register the first student."
          action={
            <Button asChild variant="outline">
              <Link href="/admissions/new">Register a student</Link>
            </Button>
          }
        />
      ) : (
        <>
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {visibleRows.length} of {list.data?.count ?? 0} shown
            {dateFilterActive ? ' — narrowed to this page by registration date' : ''}.
          </p>
          {visibleRows.length === 0 ? (
            <EmptyState
              title="Nothing on this page falls in that date range"
              description="Clear the date filter, or turn the page to look further back."
            />
          ) : (
            <TableWrapper className="animate-fade-in">
              <Table>
                <thead>
                  <tr>
                    <Th>Student</Th>
                    <Th>Course</Th>
                    <Th>Batch</Th>
                    <Th>Trainer</Th>
                    <Th className="text-right">Fee</Th>
                    <Th
                      sortable
                      active={sortField === 'enrolled_at'}
                      direction={sortDirection}
                      onSort={() => list.toggleSort('enrolled_at')}
                    >
                      Registered
                    </Th>
                    <Th
                      sortable
                      active={sortField === 'status'}
                      direction={sortDirection}
                      onSort={() => list.toggleSort('status')}
                    >
                      Status
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={row.id}>
                      <Td className="font-medium">
                        {row.student_id ? (
                          <Link href={`/admissions/${row.student_id}`} className="hover:text-primary">
                            {row.student_name || row.student_email || 'Unnamed student'}
                          </Link>
                        ) : (
                          row.student_name || row.student_email || 'Unnamed student'
                        )}
                        <span className="block font-mono text-xs text-muted-foreground">
                          {row.student_code || 'No student code'}
                        </span>
                      </Td>
                      <Td>{row.course_title || 'Not available'}</Td>
                      <Td>
                        {row.batch_name || 'Not available'}
                        <span className="block font-mono text-xs text-muted-foreground">
                          {row.batch_code || ''}
                        </span>
                      </Td>
                      <Td>{row.trainer_name || 'Not assigned'}</Td>
                      <Td className="whitespace-nowrap text-right tabular-nums">
                        {row.fee_payable === null || row.fee_payable === undefined ? (
                          <span className="text-xs text-muted-foreground">Not set</span>
                        ) : Number(row.fee_balance) > 0 ? (
                          <>
                            <span className="font-medium text-amber">{money(row.fee_balance)} due</span>
                            <span className="block text-xs text-muted-foreground">
                              {money(row.fee_paid)} of {money(row.fee_payable)}
                              {row.fee_next_due_on ? ` · by ${formatDate(row.fee_next_due_on)}` : ''}
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="font-medium text-green">Paid</span>
                            <span className="block text-xs text-muted-foreground">{money(row.fee_payable)}</span>
                          </>
                        )}
                      </Td>
                      <Td className="whitespace-nowrap text-muted-foreground">
                        {formatDate(row.enrolled_at)}
                      </Td>
                      <Td>
                        <Badge variant={ENROLLMENT_STATUS_VARIANT[row.status]}>
                          {ENROLLMENT_STATUS_LABEL[row.status]}
                        </Badge>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          )}

          {list.data ? (
            <Pagination
              page={list.data.page}
              totalPages={list.data.total_pages}
              count={list.data.count}
              pageSize={list.data.page_size}
              onPageChange={list.setPage}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

export default function AdmissionsPage() {
  return (
    <RequireAuth capability={Capability.enrolmentViewAny}>
      <AdmissionsList />
    </RequireAuth>
  );
}
