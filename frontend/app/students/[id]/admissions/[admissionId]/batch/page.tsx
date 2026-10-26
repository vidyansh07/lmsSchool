'use client';

/**
 * Batch Details — the fifth and last step of registration, and the one that
 * was missing.
 *
 * The step bar has listed it since the flow was built, and nothing
 * implemented it. So the desk's registration created the person, their
 * guardians, the charges and the first payment, and then stopped: a student
 * who was registered and billed and on no batch at all, which is a student
 * the timetable does not know about. The fast one-screen wizard did the
 * enrolling, which is why both existed.
 *
 * One row per course on the admission. Each row either picks a batch that
 * already runs that course, or opens a new one; a trainer is optional here
 * because a batch can be staffed later and a registration should not wait on
 * it. Pressing Enrol writes the enrolment *and* the link back to the
 * admission line in one server transaction, so a line can never point at
 * nothing and an enrolment can never be orphaned.
 *
 * A row that is already enrolled says so and offers nothing: a course is
 * enrolled once, and the server refuses a second attempt anyway.
 */

import { use, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { StepBar } from '@/components/classpro/step-bar';
import { WIZARD_STEPS } from '@/app/students/new/page';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/layout';
import { errorMessage, fieldErrors } from '@/lib/api';
import { enrolAdmissionLine, getAdmission, type Admission, type AdmissionLine } from '@/lib/admissions-api';
import { assignBatchTrainer, createBatch, listBatches } from '@/lib/batches';
import { Capability } from '@/lib/capabilities';
import { formatDate, localIsoDate } from '@/lib/format';
import { listTrainers } from '@/lib/people';
import type { BatchListRow, TrainerListRow } from '@/types/api';

/** Ninety days is the shape of most courses here, and it is only a default:
 *  the field is editable and the server owns the real rule. */
const DEFAULT_WEEKS = 12;

function defaultEnd(start: string): string {
  const date = new Date(`${start}T00:00:00`);
  if (Number.isNaN(date.getTime())) return start;
  date.setDate(date.getDate() + DEFAULT_WEEKS * 7);
  return localIsoDate(date);
}

function CourseRow({
  admissionId,
  line,
  trainers,
  onEnrolled,
}: {
  admissionId: string;
  line: AdmissionLine;
  trainers: TrainerListRow[];
  /** `warning` is carried up rather than shown here: a successful enrol
   *  re-renders this row as "Enrolled" and unmounts its own state, so a
   *  trainer clash reported in here would vanish at the moment somebody
   *  needed to read it. */
  onEnrolled: (admission: Admission, warning?: string) => void;
}) {
  const [mode, setMode] = useState<'pick' | 'open'>('pick');
  const [batches, setBatches] = useState<BatchListRow[] | null>(null);
  const [picked, setPicked] = useState('');
  const [name, setName] = useState('');
  const [startDate, setStartDate] = useState(() => localIsoDate());
  const [endDate, setEndDate] = useState(() => defaultEnd(localIsoDate()));
  const [capacity, setCapacity] = useState('30');
  const [trainerId, setTrainerId] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const courseId = line.course_id;
  const enrolled = line.enrollment_id !== null;

  useEffect(() => {
    if (enrolled || !courseId) return undefined;
    let cancelled = false;
    listBatches({ course: courseId, page_size: 50 })
      .then((page) => {
        if (!cancelled) setBatches(page.results);
      })
      .catch(() => {
        if (!cancelled) setBatches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [courseId, enrolled]);

  async function enrol() {
    if (!courseId) return;
    setBusy(true);
    setFailure(null);
    setErrors({});
    try {
      let batchId = picked;
      let warning: string | undefined;
      if (mode === 'open') {
        const created = await createBatch({
          name: name.trim(),
          course: courseId,
          start_date: startDate,
          end_date: endDate,
          capacity: Number(capacity) || 1,
        });
        batchId = created.id;
        if (trainerId) {
          // A clash here must not lose the batch that was just opened, so the
          // trainer is assigned separately and its failure is reported on its
          // own — the batch stands, unstaffed, and somebody staffs it later.
          try {
            await assignBatchTrainer(created.id, trainerId);
          } catch (cause) {
            warning = `${created.name} was opened and the student enrolled, but the trainer was not assigned: ${errorMessage(cause, 'the assignment was refused.')}`;
          }
        }
      }
      if (!batchId) {
        setErrors({ batch: 'Choose a batch, or open a new one.' });
        return;
      }
      onEnrolled(await enrolAdmissionLine(admissionId, line.id, batchId), warning);
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      setFailure(fields.__all__ ?? errorMessage(cause, 'Could not enrol onto this batch.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">{line.name}</p>
        {enrolled ? (
          <Badge variant="success" dot>
            Enrolled
          </Badge>
        ) : (
          <Badge variant="warning" dot>
            Not on a batch yet
          </Badge>
        )}
      </div>

      {enrolled ? (
        <p className="mt-1 text-sm text-ink-muted">
          This course is on a batch. A course is enrolled once.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          {failure ? <Alert variant="error">{failure}</Alert> : null}

          <div
            className="flex gap-2"
            role="radiogroup"
            aria-label={`How to place ${line.name}`}
          >
            <Button
              type="button"
              size="sm"
              variant={mode === 'pick' ? 'primary' : 'outline'}
              role="radio"
              aria-checked={mode === 'pick'}
              onClick={() => setMode('pick')}
            >
              Pick a batch
            </Button>
            <Button
              type="button"
              size="sm"
              variant={mode === 'open' ? 'primary' : 'outline'}
              role="radio"
              aria-checked={mode === 'open'}
              onClick={() => setMode('open')}
            >
              Open a new one
            </Button>
          </div>

          {mode === 'pick' ? (
            <Field
              label="Batch"
              htmlFor={`batch-${line.id}`}
              required
              error={errors.batch}
              hint="Only batches teaching this course are listed."
            >
              <Select
                id={`batch-${line.id}`}
                value={picked}
                onChange={(event) => setPicked(event.target.value)}
              >
                <option value="">Choose a batch</option>
                {(batches ?? []).map((batch) => (
                  <option key={batch.id} value={batch.id}>
                    {batch.name} · {batch.code} · from {formatDate(batch.start_date)}
                    {batch.trainer_name ? ` · ${batch.trainer_name}` : ' · no trainer yet'}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Batch name" htmlFor={`name-${line.id}`} required error={errors.name}>
                <Input
                  id={`name-${line.id}`}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field label="Trainer" htmlFor={`trainer-${line.id}`} hint="Optional — a batch can be staffed later.">
                <Select
                  id={`trainer-${line.id}`}
                  value={trainerId}
                  onChange={(event) => setTrainerId(event.target.value)}
                >
                  <option value="">Not yet</option>
                  {trainers.map((trainer) => (
                    <option key={trainer.id} value={trainer.id}>
                      {trainer.full_name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Starts on" htmlFor={`start-${line.id}`} required error={errors.start_date}>
                <Input
                  id={`start-${line.id}`}
                  type="date"
                  value={startDate}
                  onChange={(event) => {
                    setStartDate(event.target.value);
                    setEndDate(defaultEnd(event.target.value));
                  }}
                />
              </Field>
              <Field label="Ends on" htmlFor={`end-${line.id}`} required error={errors.end_date}>
                <Input
                  id={`end-${line.id}`}
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                />
              </Field>
              <Field label="Seats" htmlFor={`capacity-${line.id}`} required error={errors.capacity}>
                <Input
                  id={`capacity-${line.id}`}
                  type="number"
                  min={1}
                  value={capacity}
                  onChange={(event) => setCapacity(event.target.value)}
                />
              </Field>
            </div>
          )}

          <div className="flex justify-end">
            <Button type="button" disabled={busy} onClick={() => void enrol()}>
              {busy ? 'Enrolling…' : 'Enrol onto this batch'}
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

export function BatchStep({
  studentId,
  admissionId,
}: {
  studentId: string;
  admissionId: string;
}) {
  const router = useRouter();
  const [admission, setAdmission] = useState<Admission | null>(null);
  const [trainers, setTrainers] = useState<TrainerListRow[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getAdmission(admissionId)
      .then((row) => {
        if (!cancelled) setAdmission(row);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setFailure(errorMessage(cause, 'Could not read this admission.'));
      });
    return () => {
      cancelled = true;
    };
  }, [admissionId, attempt]);

  useEffect(() => {
    let cancelled = false;
    listTrainers({ page_size: 100 })
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

  const [warnings, setWarnings] = useState<string[]>([]);
  const onEnrolled = useCallback((next: Admission, warning?: string) => {
    setAdmission(next);
    if (warning) setWarnings((current) => [...current, warning]);
  }, []);

  if (failure) {
    return <ErrorState message={failure} onRetry={() => setAttempt((value) => value + 1)} />;
  }
  if (!admission) return <LoadingState label="Reading the admission" />;

  const courses = admission.lines.filter((line) => line.kind === 'course');
  const remaining = courses.filter((line) => line.enrollment_id === null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Batch Details"
        meta={`${admission.student_name} · step 5 of 5`}
      >
        <Button type="button" variant="outline" onClick={() => router.push('/students/new')}>
          Save and start another
        </Button>
        <Button
          type="button"
          disabled={remaining.length > 0}
          onClick={() => router.push(`/students/${studentId}`)}
        >
          Finish
        </Button>
      </PageHeader>

      <StepBar steps={WIZARD_STEPS} current="batch" furthest="batch" onSelect={() => {}} />

      {remaining.length === 0 ? (
        <Alert variant="success">
          Every course on this admission is on a batch. The registration is complete.
        </Alert>
      ) : (
        <Alert variant="info">
          {remaining.length === 1
            ? 'One course still needs a batch.'
            : `${remaining.length} courses still need a batch.`}{' '}
          Until a course is on a batch the student is registered and billed but not timetabled.
        </Alert>
      )}

      {warnings.map((warning) => (
        <Alert key={warning} variant="warning">
          {warning}
        </Alert>
      ))}

      <ul className="space-y-3">
        {courses.map((line) => (
          <CourseRow
            key={line.id}
            admissionId={admissionId}
            line={line}
            trainers={trainers}
            onEnrolled={onEnrolled}
          />
        ))}
      </ul>
    </div>
  );
}

export default function AdmissionBatchPage({
  params,
}: {
  params: Promise<{ id: string; admissionId: string }>;
}) {
  const { id, admissionId } = use(params);
  return (
    <RequireAuth capability={Capability.enrolmentCreate}>
      <BatchStep studentId={id} admissionId={admissionId} />
    </RequireAuth>
  );
}
