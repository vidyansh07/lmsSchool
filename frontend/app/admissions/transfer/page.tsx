'use client';

/**
 * Moving people between batches — one student, or a whole batch's worth.
 *
 * Both modes show the move before it happens: who, from where, to where, and
 * how many seats that leaves. `transferEnrollment` (see `lib/batches.ts`)
 * enrols on the new batch before cancelling the old one, so a failure here —
 * a full target batch, most often — leaves the student exactly where they
 * started rather than dropped between two records. The batch mode runs one
 * transfer at a time and reports each result as it happens rather than an
 * all-or-nothing outcome, because "23 of 25 moved, here are the two that
 * didn't" is the honest answer when a batch fills up partway through.
 */

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { SearchPicker, type PickerOption } from '@/components/admissions/search-picker';
import { RequireAuth } from '@/components/require-auth';
import { LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage } from '@/lib/api';
import {
  getBatchRoster,
  getEnrollment,
  listBatches,
  listStudentEnrollments,
  transferEnrollment,
} from '@/lib/batches';
import { ENROLLMENT_STATUS_LABEL, ENROLLMENT_STATUS_VARIANT, formatDate } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { getStudent, listStudents } from '@/lib/people';
import type {
  BatchListRow,
  Enrollment,
  RosterEntry,
  StudentListRow,
  StudentProfile,
} from '@/types/api';

type Mode = 'student' | 'batch';

/** An enrolment already finished or cancelled has nowhere to be moved from. */
const MOVABLE_STATUSES = new Set(['pending', 'active', 'suspended']);

function StudentTransfer({
  initialStudentId,
  initialEnrollmentId,
}: {
  initialStudentId: string;
  initialEnrollmentId: string;
}) {
  const [studentQuery, setStudentQuery] = useState('');
  const [studentOptions, setStudentOptions] = useState<StudentListRow[]>([]);
  const [student, setStudent] = useState<StudentProfile | null>(null);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [sourceEnrollment, setSourceEnrollment] = useState<Enrollment | null>(null);
  const [batchQuery, setBatchQuery] = useState('');
  const [batchOptions, setBatchOptions] = useState<BatchListRow[]>([]);
  const [targetBatch, setTargetBatch] = useState<BatchListRow | null>(null);
  const [isLoadingContext, setIsLoadingContext] = useState(Boolean(initialStudentId));
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Arriving from the "Transfer" link on a student's own page.
  useEffect(() => {
    if (!initialStudentId) return;
    let cancelled = false;
    Promise.all([
      getStudent(initialStudentId),
      initialEnrollmentId ? getEnrollment(initialEnrollmentId) : Promise.resolve(null),
    ])
      .then(([foundStudent, foundEnrollment]) => {
        if (cancelled) return;
        setStudent(foundStudent);
        if (foundEnrollment) setSourceEnrollment(foundEnrollment);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load that student or enrolment.');
      })
      .finally(() => {
        if (!cancelled) setIsLoadingContext(false);
      });
    return () => {
      cancelled = true;
    };
  }, [initialStudentId, initialEnrollmentId]);

  useEffect(() => {
    if (student || !studentQuery) return;
    const timer = setTimeout(() => {
      listStudents({ search: studentQuery, page_size: 20 })
        .then((page) => setStudentOptions(page.results))
        .catch(() => setStudentOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [studentQuery, student]);

  useEffect(() => {
    if (!student) return;
    listStudentEnrollments(student.student_id)
      .then((rows) => {
        setEnrollments(rows);
        setSourceEnrollment((current) => current ?? rows.find((row) => MOVABLE_STATUSES.has(row.status)) ?? null);
      })
      .catch(() => setEnrollments([]));
  }, [student]);

  useEffect(() => {
    const timer = setTimeout(() => {
      listBatches({ search: batchQuery, page_size: 30, ordering: '-start_date' })
        .then((page) =>
          setBatchOptions(
            page.results.filter(
              (row) => row.id !== sourceEnrollment?.batch_id && row.status !== 'archived',
            ),
          ),
        )
        .catch(() => setBatchOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [batchQuery, sourceEnrollment]);

  async function onConfirm() {
    if (!student || !sourceEnrollment || !targetBatch) return;
    setIsBusy(true);
    setError('');
    setNotice('');
    try {
      await transferEnrollment({
        studentId: student.id,
        fromEnrollmentId: sourceEnrollment.id,
        toBatchId: targetBatch.id,
      });
      setNotice(
        `${student.user.full_name || student.user.email} moved from ${sourceEnrollment.batch_name} to ${targetBatch.name}.`,
      );
      setSourceEnrollment(null);
      setTargetBatch(null);
      listStudentEnrollments(student.student_id)
        .then(setEnrollments)
        .catch(() => undefined);
    } catch (cause) {
      setError(errorMessage(cause, 'Could not complete the transfer.'));
    } finally {
      setIsBusy(false);
    }
  }

  const studentOptionList: PickerOption[] = studentOptions.map((row) => ({
    value: row.id,
    label: row.full_name || row.email,
    hint: row.student_id,
  }));
  const batchOptionList: PickerOption[] = batchOptions.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: `${row.course_title} · ${row.seats_available} left · starts ${formatDate(row.start_date)}`,
  }));

  if (isLoadingContext) return <LoadingState label="Loading student…" rows={3} />;

  return (
    <div className="space-y-4">
      {error ? <Alert variant="error">{error}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      {!student ? (
        <SearchPicker
          label="Find the student"
          query={studentQuery}
          onQueryChange={setStudentQuery}
          options={studentOptionList}
          selected=""
          onSelect={(option) => {
            const found = studentOptions.find((row) => row.id === option.value);
            if (found) {
              getStudent(found.id)
                .then(setStudent)
                .catch(() => setError('Could not load this student.'));
            }
          }}
          placeholder="Name, email or student ID"
          emptyMessage="Type to search."
          autoFocus
        />
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3">
          <div>
            <p className="font-medium">{student.user.full_name || student.user.email}</p>
            <p className="text-sm text-muted-foreground">{student.student_id}</p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setStudent(null);
              setSourceEnrollment(null);
              setEnrollments([]);
            }}
          >
            Change student
          </Button>
        </div>
      )}

      {student && enrollments.length === 0 ? (
        <Alert variant="warning">This student has no enrolment to transfer yet.</Alert>
      ) : null}

      {student && enrollments.length > 0 ? (
        <div className="space-y-1.5">
          <label htmlFor="transfer-source" className="block text-sm font-medium">
            Move which enrolment
          </label>
          <select
            id="transfer-source"
            className="h-10 w-full rounded-md border border-border bg-surface px-3 text-sm"
            value={sourceEnrollment?.id ?? ''}
            onChange={(event) =>
              setSourceEnrollment(enrollments.find((row) => row.id === event.target.value) ?? null)
            }
          >
            {enrollments.map((row) => (
              <option key={row.id} value={row.id} disabled={!MOVABLE_STATUSES.has(row.status)}>
                {row.course_title} — {row.batch_name} ({ENROLLMENT_STATUS_LABEL[row.status]})
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {student && sourceEnrollment ? (
        <SearchPicker
          label="Move to batch"
          query={batchQuery}
          onQueryChange={setBatchQuery}
          options={batchOptionList}
          selected={targetBatch?.id ?? ''}
          onSelect={(option) => setTargetBatch(batchOptions.find((row) => row.id === option.value) ?? null)}
          placeholder="Batch name or code"
          emptyMessage="Type to search for the target batch."
        />
      ) : null}

      {student && sourceEnrollment && targetBatch ? (
        <Alert variant="info" data-testid="transfer-preview">
          This withdraws {student.user.full_name || student.user.email} from{' '}
          <strong>{sourceEnrollment.batch_name}</strong> ({sourceEnrollment.course_title}) and enrols
          them on <strong>{targetBatch.name}</strong> ({targetBatch.course_title}), starting{' '}
          {formatDate(targetBatch.start_date)} with {targetBatch.seats_available} seat
          {targetBatch.seats_available === 1 ? '' : 's'} currently open.
        </Alert>
      ) : null}

      {student && sourceEnrollment && targetBatch ? (
        <Button onClick={() => void onConfirm()} disabled={isBusy}>
          {isBusy ? 'Transferring…' : 'Confirm transfer'}
        </Button>
      ) : null}
    </div>
  );
}

interface RowResult {
  entry: RosterEntry;
  status: 'pending' | 'moved' | 'failed';
  message?: string;
}

function BatchTransfer() {
  const [sourceQuery, setSourceQuery] = useState('');
  const [sourceOptions, setSourceOptions] = useState<BatchListRow[]>([]);
  const [sourceBatch, setSourceBatch] = useState<BatchListRow | null>(null);
  const [roster, setRoster] = useState<RosterEntry[] | null>(null);
  const [targetQuery, setTargetQuery] = useState('');
  const [targetOptions, setTargetOptions] = useState<BatchListRow[]>([]);
  const [targetBatch, setTargetBatch] = useState<BatchListRow | null>(null);
  const [results, setResults] = useState<RowResult[] | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      listBatches({ search: sourceQuery, page_size: 30, ordering: '-start_date' })
        .then((page) => setSourceOptions(page.results))
        .catch(() => setSourceOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [sourceQuery]);

  useEffect(() => {
    if (!sourceBatch) return;
    getBatchRoster(sourceBatch.id)
      .then(setRoster)
      .catch(() => setRoster([]));
  }, [sourceBatch]);

  useEffect(() => {
    const timer = setTimeout(() => {
      listBatches({ search: targetQuery, page_size: 30, ordering: '-start_date' })
        .then((page) => setTargetOptions(page.results.filter((row) => row.id !== sourceBatch?.id)))
        .catch(() => setTargetOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [targetQuery, sourceBatch]);

  const movable = (roster ?? []).filter((entry) => MOVABLE_STATUSES.has(entry.status));

  async function onConfirm() {
    if (!targetBatch) return;
    setIsRunning(true);
    setError('');
    let current: RowResult[] = movable.map((entry) => ({ entry, status: 'pending' }));
    setResults(current);
    for (let index = 0; index < movable.length; index += 1) {
      const entry = movable[index]!;
      let outcome: RowResult;
      try {
        await transferEnrollment({
          studentId: entry.student_id,
          fromEnrollmentId: entry.id,
          toBatchId: targetBatch.id,
        });
        outcome = { entry, status: 'moved' };
      } catch (cause) {
        outcome = {
          entry,
          status: 'failed',
          message: errorMessage(cause, 'Could not move this student.'),
        };
      }
      current = current.map((row, rowIndex) => (rowIndex === index ? outcome : row));
      setResults(current);
    }
    setIsRunning(false);
    if (sourceBatch) {
      getBatchRoster(sourceBatch.id)
        .then(setRoster)
        .catch(() => undefined);
    }
  }

  const sourceOptionList: PickerOption[] = sourceOptions.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: row.course_title,
  }));
  const targetOptionList: PickerOption[] = targetOptions.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: `${row.course_title} · ${row.seats_available} left`,
  }));

  return (
    <div className="space-y-4">
      {error ? <Alert variant="error">{error}</Alert> : null}
      <SearchPicker
        label="Move students out of"
        query={sourceQuery}
        onQueryChange={setSourceQuery}
        options={sourceOptionList}
        selected={sourceBatch?.id ?? ''}
        onSelect={(option) => {
          setSourceBatch(sourceOptions.find((row) => row.id === option.value) ?? null);
          setRoster(null);
          setResults(null);
        }}
        placeholder="Source batch"
        emptyMessage="Type to search."
        autoFocus
      />

      {sourceBatch && roster === null ? <LoadingState label="Loading roster…" rows={3} /> : null}
      {sourceBatch && roster && movable.length === 0 ? (
        <Alert variant="warning">Nobody on this batch can currently be moved.</Alert>
      ) : null}

      {sourceBatch && movable.length > 0 ? (
        <>
          <SearchPicker
            label="Move them to"
            query={targetQuery}
            onQueryChange={setTargetQuery}
            options={targetOptionList}
            selected={targetBatch?.id ?? ''}
            onSelect={(option) => setTargetBatch(targetOptions.find((row) => row.id === option.value) ?? null)}
            placeholder="Target batch"
            emptyMessage="Type to search."
          />

          {targetBatch ? (
            <Alert variant="info" data-testid="batch-transfer-preview">
              This moves {movable.length} student{movable.length === 1 ? '' : 's'} from{' '}
              <strong>{sourceBatch.name}</strong> to <strong>{targetBatch.name}</strong>
              {targetBatch.seats_available < movable.length ? (
                <>
                  {' '}
                  — only {targetBatch.seats_available} seat{targetBatch.seats_available === 1 ? '' : 's'}{' '}
                  open there, so some of these will fail.
                </>
              ) : (
                '.'
              )}
            </Alert>
          ) : null}

          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Student</Th>
                  <Th>Current status</Th>
                  {results ? <Th>Result</Th> : null}
                </tr>
              </thead>
              <tbody>
                {movable.map((entry, index) => {
                  const outcome = results?.[index];
                  return (
                    <tr key={entry.id}>
                      <Td className="font-medium">
                        {entry.full_name || entry.email}
                        <span className="block font-mono text-xs text-muted-foreground">
                          {entry.student_code}
                        </span>
                      </Td>
                      <Td>
                        <Badge variant={ENROLLMENT_STATUS_VARIANT[entry.status]}>
                          {ENROLLMENT_STATUS_LABEL[entry.status]}
                        </Badge>
                      </Td>
                      {results ? (
                        <Td>
                          {!outcome || outcome.status === 'pending' ? (
                            'Moving…'
                          ) : outcome.status === 'moved' ? (
                            <Badge variant="success">Moved</Badge>
                          ) : (
                            <span className="text-destructive">{outcome.message}</span>
                          )}
                        </Td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </TableWrapper>

          {targetBatch && !results ? (
            <Button onClick={() => void onConfirm()} disabled={isRunning}>
              {isRunning ? 'Moving…' : `Move ${movable.length} student${movable.length === 1 ? '' : 's'}`}
            </Button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function TransferContent() {
  const params = useSearchParams();
  const [mode, setMode] = useState<Mode>('student');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Transfer</h1>
          <p className="text-sm text-muted-foreground">
            Move a student, or a whole batch, without losing their seat along the way.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/admissions">Back to admissions</Link>
        </Button>
      </div>

      <div className="flex gap-2">
        <Button size="sm" variant={mode === 'student' ? 'primary' : 'outline'} onClick={() => setMode('student')}>
          Move one student
        </Button>
        <Button size="sm" variant={mode === 'batch' ? 'primary' : 'outline'} onClick={() => setMode('batch')}>
          Move a whole batch
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{mode === 'student' ? 'Move one student' : 'Move a whole batch'}</CardTitle>
          <CardDescription>
            {mode === 'student'
              ? 'Find the student, pick the enrolment to move, and choose where it goes.'
              : 'Everyone currently active, pending or suspended on the source batch moves to the target.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mode === 'student' ? (
            <StudentTransfer
              initialStudentId={params.get('student') ?? ''}
              initialEnrollmentId={params.get('enrollment') ?? ''}
            />
          ) : (
            <BatchTransfer />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function TransferPage() {
  return (
    <RequireAuth capability={Capability.enrolmentUpdateAny}>
      <Suspense fallback={<LoadingState label="Loading…" rows={4} />}>
        <TransferContent />
      </Suspense>
    </RequireAuth>
  );
}
