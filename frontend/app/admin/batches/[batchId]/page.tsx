'use client';

import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { CalendarPlus, Trash2, UserPlus } from 'lucide-react';

import { generateSessions } from '@/lib/academics';
import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { ScheduleList } from '@/components/schedule-list';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, fieldErrors } from '@/lib/api';
import {
  assignBatchTrainer,
  createSchedule,
  deleteSchedule,
  enrolStudent,
  getBatch,
  getBatchRoster,
  setBatchStatus,
  setEnrollmentStatus,
} from '@/lib/batches';
import {
  BATCH_STATUS_LABEL,
  BATCH_STATUS_VARIANT,
  ENROLLMENT_STATUS_LABEL,
  ENROLLMENT_STATUS_VARIANT,
  WEEKDAY_OPTIONS,
  formatDate,
} from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { listStudents, listTrainers } from '@/lib/people';
import type {
  BatchDetail,
  BatchStatus,
  RosterEntry,
  StudentListRow,
  TrainerListRow,
  Weekday,
} from '@/types/api';

/** Which transitions to offer. The server owns the real table. */
function transitionsFor(status: BatchStatus): { target: BatchStatus; label: string }[] {
  if (status === 'upcoming') {
    return [
      { target: 'active', label: 'Activate' },
      { target: 'cancelled', label: 'Cancel' },
    ];
  }
  if (status === 'active') {
    return [
      { target: 'completed', label: 'Mark complete' },
      { target: 'cancelled', label: 'Cancel' },
    ];
  }
  if (status === 'completed' || status === 'cancelled') {
    return [{ target: 'archived', label: 'Archive' }];
  }
  return [];
}

function TrainerPanel({ batch, onChanged }: { batch: BatchDetail; onChanged: () => void }) {
  const [trainers, setTrainers] = useState<TrainerListRow[]>([]);
  const [selected, setSelected] = useState(batch.trainer_id ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listTrainers({ page_size: 100, is_active: 'true' })
      .then((page) => {
        if (!cancelled) setTrainers(page.results);
      })
      .catch(() => {
        if (!cancelled) setTrainers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onAssign() {
    setIsSaving(true);
    setErrors({});
    setMessage('');
    try {
      await assignBatchTrainer(batch.id, selected || null);
      // Said out loud. Reassigning a trainer is a change somebody else feels —
      // a different person turns up to teach — and a control that answers
      // silently leaves the administrator wondering whether it took.
      setMessage(selected ? 'Trainer assigned.' : 'Trainer removed from this batch.');
      onChanged();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trainer</CardTitle>
        <CardDescription>
          Assigning a trainer checks their whole timetable — a clash is refused.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* The API returns the clashing class by name, which is what makes the
            refusal actionable rather than merely a rejection. */}
        {errors.trainer || errors.__all__ ? (
          <Alert variant="error">{errors.trainer ?? errors.__all__}</Alert>
        ) : null}
        {message ? (
          <Alert variant="success" role="status">
            {message}
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-end gap-3">
          <Field label="Assigned trainer" htmlFor="batch-trainer" className="min-w-[16rem] flex-1">
            <Select value={selected} onChange={(event) => setSelected(event.target.value)}>
              <option value="">Nobody assigned</option>
              {trainers.map((trainer) => (
                <option key={trainer.id} value={trainer.id}>
                  {trainer.full_name || trainer.email} ({trainer.trainer_id})
                </option>
              ))}
            </Select>
          </Field>
          <Button onClick={() => void onAssign()} disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Assign'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SchedulePanel({ batch, onChanged }: { batch: BatchDetail; onChanged: () => void }) {
  const [weekday, setWeekday] = useState<Weekday>(0);
  const [start, setStart] = useState('09:00');
  const [end, setEnd] = useState('11:00');
  const [location, setLocation] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [generated, setGenerated] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  async function onGenerate() {
    setIsGenerating(true);
    setErrors({});
    setGenerated('');
    try {
      const result = await generateSessions(batch.id);
      const parts = [`${result.created} class${result.created === 1 ? '' : 'es'} created`];
      if (result.skipped) parts.push(`${result.skipped} already existed`);
      if (result.on_holiday) parts.push(`${result.on_holiday} skipped as holidays`);
      setGenerated(`${parts.join(', ')}, ${result.start} to ${result.end}.`);
      onChanged();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsGenerating(false);
    }
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      await createSchedule(batch.id, {
        weekday,
        start_time: start,
        end_time: end,
        location,
      });
      onChanged();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  async function onRemove(scheduleId: string) {
    try {
      await deleteSchedule(scheduleId);
      onChanged();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Timetable</CardTitle>
        <CardDescription>
          Weekly classes within the batch dates. Overlapping classes are refused.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {errors.schedule || errors.__all__ ? (
          <Alert variant="error">{errors.schedule ?? errors.__all__}</Alert>
        ) : null}

        {batch.schedules.length > 0 ? (
          <ul className="divide-y divide-border rounded-md border border-border">
            {batch.schedules.map((schedule) => (
              <li key={schedule.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                <span className="w-24 font-medium">{schedule.weekday_label}</span>
                <span className="text-muted-foreground">
                  {schedule.start_time.slice(0, 5)}–{schedule.end_time.slice(0, 5)}
                </span>
                {schedule.location ? (
                  <span className="text-muted-foreground">{schedule.location}</span>
                ) : null}
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => void onRemove(schedule.id)}
                  aria-label={`Remove the ${schedule.weekday_label} class`}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <ScheduleList schedules={[]} />
        )}

        <form onSubmit={onAdd} className="flex flex-wrap items-end gap-3">
          <Field label="Day" htmlFor="schedule-day" error={errors.weekday}>
            <Select
              value={String(weekday)}
              onChange={(event) => setWeekday(Number(event.target.value) as Weekday)}
            >
              {WEEKDAY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Start" htmlFor="schedule-start" error={errors.start_time}>
            <Input type="time" value={start} onChange={(event) => setStart(event.target.value)} />
          </Field>
          <Field label="End" htmlFor="schedule-end" error={errors.end_time}>
            <Input type="time" value={end} onChange={(event) => setEnd(event.target.value)} />
          </Field>
          <Field label="Location" htmlFor="schedule-location" className="min-w-[10rem]">
            <Input value={location} onChange={(event) => setLocation(event.target.value)} />
          </Field>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Adding…' : 'Add class'}
          </Button>
        </form>

        <div className="space-y-2 rounded-md border border-border p-3">
          <p className="text-sm font-medium">Classes from this timetable</p>
          <p className="text-sm text-muted-foreground">
            Turns the weekly pattern above into dated classes across the batch, skipping any day
            marked as a holiday. Safe to run again — classes that already exist are left alone.
          </p>
          {generated ? (
            <Alert variant="success" role="status">
              {generated}
            </Alert>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isGenerating || batch.schedules.length === 0}
            onClick={() => void onGenerate()}
          >
            <CalendarPlus className="size-4" aria-hidden="true" />
            {isGenerating ? 'Generating…' : 'Generate classes'}
          </Button>
          {batch.schedules.length === 0 ? (
            <p className="text-sm text-muted-foreground">Add a weekly class first.</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function RosterPanel({ batch, onChanged }: { batch: BatchDetail; onChanged: () => void }) {
  const { can } = useAuth();
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [students, setStudents] = useState<StudentListRow[]>([]);
  const [selected, setSelected] = useState('');
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isBusy, setIsBusy] = useState(false);

  const loadRoster = useCallback(() => {
    getBatchRoster(batch.id)
      .then(setRoster)
      .catch(() => setRoster([]));
  }, [batch.id]);

  useEffect(() => {
    loadRoster();
  }, [loadRoster]);

  useEffect(() => {
    if (!can(Capability.enrolmentCreate)) return;
    let cancelled = false;
    listStudents({ page_size: 100, is_active: 'true' })
      .then((page) => {
        if (cancelled) return;
        setStudents(page.results);
        if (page.results.length > 0) setSelected(page.results[0]!.user_id);
      })
      .catch(() => {
        if (!cancelled) setStudents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [can]);

  async function onEnrol() {
    const student = students.find((row) => row.user_id === selected);
    if (!student) return;
    setIsBusy(true);
    setErrors({});
    setMessage('');
    try {
      await enrolStudent({ student_id: student.id, batch_id: batch.id });
      // Enrolment opens a course to somebody. Confirming it is not decoration:
      // the roster below is long, and "did that work?" should not be answered
      // by scrolling to look for a name.
      setNotice(`${student.full_name || student.email} is enrolled.`);
      loadRoster();
      onChanged();
    } catch (cause) {
      const mapped = fieldErrors(cause);
      setErrors(mapped);
      setNotice('');
      if (cause instanceof ApiError) setMessage(cause.message);
    } finally {
      setIsBusy(false);
    }
  }

  async function onSetStatus(entry: RosterEntry, status: RosterEntry['status']) {
    try {
      await setEnrollmentStatus(entry.id, status);
      loadRoster();
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not update the enrolment.');
    }
  }

  const canEnrol = can(Capability.enrolmentCreate);
  const canManage = can(Capability.enrolmentUpdateAny);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Students</CardTitle>
        <CardDescription>
          {batch.enrolled_count} of {batch.capacity} seats taken.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {notice ? (
          <Alert variant="success" role="status">
            {notice}
          </Alert>
        ) : null}
        {message || errors.__all__ ? (
          <Alert variant="error">{message || errors.__all__}</Alert>
        ) : null}

        {roster.length === 0 ? (
          <EmptyState title="Nobody enrolled yet" description="Add the first student below." />
        ) : (
          <TableWrapper>
            <Table className="min-w-[36rem]">
              <thead>
                <tr>
                  <Th>Student ID</Th>
                  <Th>Name</Th>
                  <Th>Status</Th>
                  {canManage ? <Th>Actions</Th> : null}
                </tr>
              </thead>
              <tbody>
                {roster.map((entry) => (
                  <tr key={entry.id}>
                    <Td className="font-mono text-xs">{entry.student_code}</Td>
                    <Td className="font-medium">{entry.full_name || entry.email}</Td>
                    <Td>
                      <Badge variant={ENROLLMENT_STATUS_VARIANT[entry.status]}>
                        {ENROLLMENT_STATUS_LABEL[entry.status]}
                      </Badge>
                    </Td>
                    {canManage ? (
                      <Td>
                        <div className="flex flex-wrap gap-2">
                          {entry.status === 'active' ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void onSetStatus(entry, 'suspended')}
                            >
                              Suspend
                            </Button>
                          ) : null}
                          {entry.status === 'suspended' ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void onSetStatus(entry, 'active')}
                            >
                              Reactivate
                            </Button>
                          ) : null}
                          {entry.status === 'active' || entry.status === 'suspended' ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => void onSetStatus(entry, 'cancelled')}
                            >
                              Remove
                            </Button>
                          ) : null}
                        </div>
                      </Td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        )}

        {canEnrol ? (
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Add a student" htmlFor="enrol-student" className="min-w-[18rem] flex-1">
              <Select value={selected} onChange={(event) => setSelected(event.target.value)}>
                {students.length === 0 ? <option value="">No students available</option> : null}
                {students.map((student) => (
                  <option key={student.id} value={student.user_id}>
                    {student.full_name || student.email} ({student.student_id})
                  </option>
                ))}
              </Select>
            </Field>
            <Button onClick={() => void onEnrol()} disabled={isBusy || students.length === 0}>
              <UserPlus className="size-4" aria-hidden="true" />
              {isBusy ? 'Enrolling…' : 'Enrol'}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function BatchDetailView({ batchId }: { batchId: string }) {
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    try {
      setBatch(await getBatch(batchId));
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause : null);
    } finally {
      setIsLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    let cancelled = false;
    getBatch(batchId)
      .then((result) => {
        if (!cancelled) setBatch(result);
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
  }, [batchId]);

  async function onTransition(target: BatchStatus) {
    setMessage('');
    try {
      await setBatchStatus(batchId, target);
      await load();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not change the status.');
    }
  }

  if (isLoading) return <LoadingState label="Loading batch…" rows={6} />;

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Batch not found"
          description="This batch does not exist, or it is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href="/admin/batches">Back to batches</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this batch"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  if (!batch) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{batch.name}</h1>
            <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>
              {BATCH_STATUS_LABEL[batch.status]}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono text-xs">{batch.code}</span> ·{' '}
            <Link href={`/courses/${batch.course_slug}`} className="underline hover:text-foreground">
              {batch.course_title}
            </Link>{' '}
            · {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
          </p>
        </div>
      </div>

      {message ? <Alert variant="error">{message}</Alert> : null}

      {batch.can_manage ? (
        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
            <CardDescription>
              Cancelling a batch cancels its enrolments; completing it completes them.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {transitionsFor(batch.status).length === 0 ? (
              <p className="text-sm text-muted-foreground">No status changes are available.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {transitionsFor(batch.status).map((transition) => (
                  <Button
                    key={transition.target}
                    size="sm"
                    variant={transition.target === 'active' ? 'primary' : 'outline'}
                    onClick={() => void onTransition(transition.target)}
                  >
                    {transition.label}
                  </Button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {batch.can_manage ? <TrainerPanel batch={batch} onChanged={load} /> : null}

      {batch.can_manage ? (
        <SchedulePanel batch={batch} onChanged={load} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Timetable</CardTitle>
          </CardHeader>
          <CardContent>
            <ScheduleList schedules={batch.schedules} />
          </CardContent>
        </Card>
      )}

      {batch.can_view_roster ? <RosterPanel batch={batch} onChanged={load} /> : null}
    </div>
  );
}

export default function AdminBatchPage({ params }: { params: Promise<{ batchId: string }> }) {
  const { batchId } = use(params);
  return (
    <RequireAuth>
      <BatchDetailView batchId={batchId} />
    </RequireAuth>
  );
}
