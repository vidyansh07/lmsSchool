'use client';

/**
 * Batches from the admissions side: open one for a course, see its seats and
 * its roster, or start one from scratch — the same three things step 3 of
 * `/admissions/new` does inline, offered here as their own page for a
 * counsellor who wants to look at batches without registering anyone.
 *
 * Deeper batch management — timetables, status transitions, reassigning a
 * trainer on a batch that already has one — stays on `/admin/batches/[id]`,
 * which a counsellor's `batch.*` capabilities already unlock; duplicating that
 * panel here would be two places to keep in sync for the same operation.
 */

import Link from 'next/link';
import { Fragment, useCallback, useEffect, useState } from 'react';

import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { fieldErrors } from '@/lib/api';
import { createBatch, getBatchRoster, listBatches } from '@/lib/batches';
import {
  BATCH_STATUS_LABEL,
  BATCH_STATUS_OPTIONS,
  BATCH_STATUS_VARIANT,
  ENROLLMENT_STATUS_LABEL,
  ENROLLMENT_STATUS_VARIANT,
  formatDate,
  isoDaysFromNow,
  isoToday,
} from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { listCourses } from '@/lib/courses';
import type { BatchListRow, CourseListRow, RosterEntry } from '@/types/api';

function CreateBatchInline({ onCreated }: { onCreated: () => void }) {
  const [courses, setCourses] = useState<CourseListRow[]>([]);
  const [name, setName] = useState('');
  const [course, setCourse] = useState('');
  const [startDate, setStartDate] = useState(isoToday());
  const [endDate, setEndDate] = useState(isoDaysFromNow(90));
  const [capacity, setCapacity] = useState('20');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    listCourses({ status: 'published', page_size: 100, ordering: 'title' })
      .then((page) => {
        setCourses(page.results);
        if (page.results.length > 0) setCourse((current) => current || page.results[0]!.id);
      })
      .catch(() => setErrors({ __all__: 'Could not load courses.' }));
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      await createBatch({
        name,
        course,
        start_date: startDate,
        end_date: endDate,
        capacity: Number(capacity) || 1,
      });
      setName('');
      onCreated();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New batch</CardTitle>
        <CardDescription>Starts as upcoming, with no trainer — assign one afterwards.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Batch name" htmlFor="ab-name" error={errors.name} required>
              <Input value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label="Course" htmlFor="ab-course" error={errors.course} required>
              <Select value={course} onChange={(event) => setCourse(event.target.value)}>
                {courses.length === 0 ? <option value="">No published courses</option> : null}
                {courses.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.title}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Start date" htmlFor="ab-start" error={errors.start_date} required>
              <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </Field>
            <Field label="End date" htmlFor="ab-end" error={errors.end_date} required>
              <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </Field>
            <Field label="Capacity" htmlFor="ab-capacity" error={errors.capacity} required>
              <Input type="number" min={1} value={capacity} onChange={(event) => setCapacity(event.target.value)} />
            </Field>
          </div>
          <Button type="submit" disabled={isSaving || courses.length === 0}>
            {isSaving ? 'Creating…' : 'Create batch'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function RosterRow({ batch }: { batch: BatchListRow }) {
  const [roster, setRoster] = useState<RosterEntry[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getBatchRoster(batch.id)
      .then(setRoster)
      .catch(() => setFailed(true));
  }, [batch.id]);

  return (
    <tr>
      <Td colSpan={7} className="bg-muted/40">
        {failed ? <Alert variant="error">Could not load this roster.</Alert> : null}
        {roster === null && !failed ? <LoadingState label="Loading roster…" rows={2} /> : null}
        {roster?.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nobody enrolled on this batch yet.</p>
        ) : null}
        {roster && roster.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {roster.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-center gap-2">
                <Link href={`/admissions/${entry.student_id}`} className="font-medium hover:text-primary">
                  {entry.full_name || entry.email}
                </Link>
                <span className="font-mono text-xs text-muted-foreground">{entry.student_code}</span>
                <Badge variant={ENROLLMENT_STATUS_VARIANT[entry.status]}>
                  {ENROLLMENT_STATUS_LABEL[entry.status]}
                </Badge>
              </li>
            ))}
          </ul>
        ) : null}
        <Link
          href={`/admin/batches/${batch.id}`}
          className="mt-2 inline-block text-sm underline hover:text-foreground"
        >
          Open the full batch record →
        </Link>
      </Td>
    </tr>
  );
}

export function BatchBrowser() {
  const list = useList<BatchListRow>(listBatches, { page_size: 20 });
  const [showCreate, setShowCreate] = useState(false);
  const [expanded, setExpanded] = useState<string>('');
  const [courses, setCourses] = useState<CourseListRow[]>([]);

  const loadCourses = useCallback(() => {
    listCourses({ page_size: 100, ordering: 'title' })
      .then((page) => setCourses(page.results))
      .catch(() => setCourses([]));
  }, []);

  useEffect(loadCourses, [loadCourses]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Batches</h1>
          <p className="text-sm text-muted-foreground">Open cohorts, their seats, and their rosters.</p>
        </div>
        <Button onClick={() => setShowCreate((value) => !value)}>
          {showCreate ? 'Close' : 'New batch'}
        </Button>
      </div>

      {showCreate ? (
        <CreateBatchInline
          onCreated={() => {
            setShowCreate(false);
            list.reload();
          }}
        />
      ) : null}

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Batch code, name or course"
      >
        <div>
          <label htmlFor="ab-filter-course" className="mb-1.5 block text-sm font-medium">
            Course
          </label>
          <Select
            id="ab-filter-course"
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
          <label htmlFor="ab-filter-status" className="mb-1.5 block text-sm font-medium">
            Status
          </label>
          <Select
            id="ab-filter-status"
            value={String(list.query.status ?? '')}
            onChange={(event) => list.setQuery({ status: event.target.value })}
          >
            <option value="">All statuses</option>
            {BATCH_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
      </ListToolbar>

      {list.isLoading ? (
        <LoadingState label="Loading batches…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load batches"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState title="No batches yet" description="Create the first batch to start enrolling students." />
      ) : (
        <>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Code</Th>
                  <Th>Batch</Th>
                  <Th>Course</Th>
                  <Th>Trainer</Th>
                  <Th>Runs</Th>
                  <Th>Seats</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {list.data?.results.map((batch) => (
                  <Fragment key={batch.id}>
                    <tr>
                      <Td className="font-mono text-xs">{batch.code}</Td>
                      <Td className="font-medium">
                        <button
                          type="button"
                          className="text-left hover:text-primary"
                          onClick={() => setExpanded((current) => (current === batch.id ? '' : batch.id))}
                          aria-expanded={expanded === batch.id}
                        >
                          {batch.name}
                        </button>
                      </Td>
                      <Td>{batch.course_title}</Td>
                      <Td>{batch.trainer_name || 'Not assigned'}</Td>
                      <Td className="whitespace-nowrap text-muted-foreground">
                        {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
                      </Td>
                      <Td>
                        {batch.enrolled_count} / {batch.capacity}
                        {batch.seats_available === 0 ? (
                          <Badge variant="warning" className="ml-2">
                            Full
                          </Badge>
                        ) : null}
                      </Td>
                      <Td>
                        <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>
                          {BATCH_STATUS_LABEL[batch.status]}
                        </Badge>
                      </Td>
                    </tr>
                    {expanded === batch.id ? <RosterRow batch={batch} /> : null}
                  </Fragment>
                ))}
              </tbody>
            </Table>
          </TableWrapper>

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

export default function AdmissionsBatchesPage() {
  return (
    <RequireAuth capability={Capability.batchViewAny}>
      <BatchBrowser />
    </RequireAuth>
  );
}
