'use client';

/**
 * The fast registration flow — the reason this feature exists.
 *
 * Register → choose a course → open or pick a batch → assign a trainer →
 * enrol, done dozens of times a day by somebody who already knows the system.
 * Every one of those is a real API call, but none of them fire until the
 * counsellor presses "Confirm and enrol" at the end: nothing here creates a
 * half-finished student or an empty batch just because somebody stepped away
 * after typing an email address. `ensureStudent`/`ensureBatch` below memoise
 * whichever calls already succeeded, so a retry after (say) a trainer clash
 * does not try to create the same student twice and fail on a duplicate email.
 *
 * Selecting a course or a batch advances the wizard immediately — the point of
 * a one-screen flow is that choosing the next thing *is* the click that moves
 * forward, not a separate "Next" after it. The one place that is not true is
 * the student-details step, because a duplicate warning has to be seen and
 * dismissed before moving on.
 *
 * "Save and start another" is the actual time-saver the brief asked for: it
 * clears only the person-specific fields and keeps the course and batch
 * selected, because a counsellor enrolling five people from one intake form
 * should not re-pick the same batch five times.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { DuplicateMatch } from '@/components/admissions/duplicate-match';
import { SearchPicker, type PickerOption } from '@/components/admissions/search-picker';
import { StepIndicator, type WizardStep } from '@/components/admissions/step-indicator';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { errorMessage, fieldErrors } from '@/lib/api';
import { assignBatchTrainer, createBatch, enrolStudent, listBatches } from '@/lib/batches';
import { formatDate, isoDaysFromNow, isoToday } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { listCourses } from '@/lib/courses';
import { QUALIFICATION_OPTIONS } from '@/lib/labels';
import { createStudent, listStudents, listTrainers } from '@/lib/people';
import type {
  BatchDetail,
  BatchListRow,
  CourseListRow,
  Enrollment,
  StudentListRow,
  StudentProfile,
  TrainerListRow,
} from '@/types/api';

type StepKey = 'student' | 'course' | 'batch' | 'trainer' | 'confirm';

const STEPS: WizardStep[] = [
  { key: 'student', label: 'Student' },
  { key: 'course', label: 'Course' },
  { key: 'batch', label: 'Batch' },
  { key: 'trainer', label: 'Trainer' },
  { key: 'confirm', label: 'Confirm' },
];

interface DraftBatch {
  name: string;
  startDate: string;
  endDate: string;
  capacity: string;
}

function freshDraftBatch(): DraftBatch {
  return { name: '', startDate: isoToday(), endDate: isoDaysFromNow(90), capacity: '20' };
}

interface Result {
  student: StudentProfile;
  batchName: string;
  batchCode: string;
  enrollment: Enrollment;
}

export function RegistrationWizard() {
  const [step, setStep] = useState<StepKey>('student');
  const [completed, setCompleted] = useState<Set<StepKey>>(new Set());

  // --- Step 1: student -------------------------------------------------
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [city, setCity] = useState('');
  const [qualification, setQualification] = useState('');
  const [studentErrors, setStudentErrors] = useState<Record<string, string>>({});
  const [duplicates, setDuplicates] = useState<StudentListRow[]>([]);
  const [duplicateChecking, setDuplicateChecking] = useState(false);
  const [acknowledgedDuplicate, setAcknowledgedDuplicate] = useState(false);
  const [createdStudent, setCreatedStudent] = useState<StudentProfile | null>(null);

  // --- Step 2: course ----------------------------------------------------
  const [courseQuery, setCourseQuery] = useState('');
  const [courseOptions, setCourseOptions] = useState<CourseListRow[]>([]);
  const [courseLoading, setCourseLoading] = useState(false);
  const [course, setCourse] = useState<CourseListRow | null>(null);

  // --- Step 3: batch -------------------------------------------------------
  const [batchMode, setBatchMode] = useState<'pick' | 'create'>('pick');
  const [batchQuery, setBatchQuery] = useState('');
  const [batchOptions, setBatchOptions] = useState<BatchListRow[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [pickedBatch, setPickedBatch] = useState<BatchListRow | null>(null);
  const [draftBatch, setDraftBatch] = useState<DraftBatch>(freshDraftBatch());
  const [batchErrors, setBatchErrors] = useState<Record<string, string>>({});
  const [createdBatch, setCreatedBatch] = useState<BatchDetail | null>(null);

  // --- Step 4: trainer -----------------------------------------------------
  const [trainerQuery, setTrainerQuery] = useState('');
  const [trainerOptions, setTrainerOptions] = useState<TrainerListRow[]>([]);
  const [trainerLoading, setTrainerLoading] = useState(false);
  const [trainerId, setTrainerId] = useState('');
  const [trainerName, setTrainerName] = useState('');
  const [trainerErrors, setTrainerErrors] = useState<Record<string, string>>({});
  const [trainerAssigned, setTrainerAssigned] = useState(false);

  // --- Step 5: confirm -------------------------------------------------
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmError, setConfirmError] = useState('');
  const [result, setResult] = useState<Result | null>(null);

  const batchHasTrainer = batchMode === 'pick' && Boolean(pickedBatch?.trainer_name);

  // Recomputed at render time rather than reset from the debounce effect
  // above: once the identifying fields are too short to search on, the
  // warning disappears immediately even though the last search result is
  // still sitting in `duplicates`.
  const duplicateQuery =
    email.trim().length >= 3 ? email.trim() : phone.trim().length >= 4 ? phone.trim() : '';
  const visibleDuplicates = duplicateQuery ? duplicates : [];

  // Every step the counsellor has landed on, which is not the same as the ones
  // they finished. Going back has to be reversible — see `StepIndicator`.
  const [visited, setVisited] = useState<Set<StepKey>>(new Set(['student']));

  function goToStep(next: StepKey) {
    setVisited((current) => new Set(current).add(next));
    setStep(next);
  }

  function advanceTo(next: StepKey, from: StepKey = step) {
    setCompleted((current) => new Set(current).add(from));
    goToStep(next);
  }

  // Duplicate detection: search as the identifying fields are typed, before
  // there is anything to submit. `user__phone` is not currently one of the
  // fields `/api/v1/students/` searches on, so a phone-only match will not
  // surface until that is added server-side — this still checks it, on the
  // chance the number also appears elsewhere on the record, and email (which
  // *is* indexed for search, and unique besides) is the reliable half of this.
  // The empty-query case is left to render time (see `duplicateQuery` and
  // `visibleDuplicates` below) rather than reset here, so nothing sets state
  // synchronously from inside the effect body itself.
  useEffect(() => {
    const query = email.trim().length >= 3 ? email.trim() : phone.trim().length >= 4 ? phone.trim() : '';
    if (!query) return;
    const timer = setTimeout(() => {
      setDuplicateChecking(true);
      listStudents({ search: query, page_size: 5 })
        .then((page) => setDuplicates(page.results))
        .catch(() => setDuplicates([]))
        .finally(() => setDuplicateChecking(false));
    }, 350);
    return () => clearTimeout(timer);
  }, [email, phone]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setCourseLoading(true);
      listCourses({ status: 'published', search: courseQuery, page_size: 50, ordering: 'title' })
        .then((page) => setCourseOptions(page.results))
        .catch(() => setCourseOptions([]))
        .finally(() => setCourseLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [courseQuery]);

  useEffect(() => {
    if (!course) return;
    const timer = setTimeout(() => {
      setBatchLoading(true);
      listBatches({ course: course.slug, search: batchQuery, page_size: 50, ordering: 'start_date' })
        .then((page) =>
          setBatchOptions(
            page.results.filter((batch) => batch.status === 'upcoming' || batch.status === 'active'),
          ),
        )
        .catch(() => setBatchOptions([]))
        .finally(() => setBatchLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [course, batchQuery]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setTrainerLoading(true);
      listTrainers({ is_active: 'true', search: trainerQuery, page_size: 50 })
        .then((page) =>
          setTrainerOptions(
            [...page.results].sort(
              (a, b) => Number(b.is_accepting_assignments) - Number(a.is_accepting_assignments),
            ),
          ),
        )
        .catch(() => setTrainerOptions([]))
        .finally(() => setTrainerLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [trainerQuery]);

  // --- Step 1 handlers -----------------------------------------------------

  // After "save and start another", the course and batch are already known —
  // that carried-forward context is the point of the button. So the next
  // student's details step goes straight to Confirm rather than making the
  // counsellor click back through steps that have nothing new to decide; the
  // step indicator still lets them jump back in and change either one.
  function goPastStudentDetails() {
    const batchChosen = batchMode === 'pick' ? Boolean(pickedBatch) : Boolean(draftBatch.name.trim());
    if (course && batchChosen) {
      setCompleted((current) => {
        const next = new Set(current);
        next.add('student').add('course').add('batch').add('trainer');
        return next;
      });
      goToStep('confirm');
    } else {
      advanceTo('course', 'student');
    }
  }

  function onStudentSubmit(event: React.FormEvent) {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!email.trim()) errors.email = 'Email is required.';
    if (!firstName.trim()) errors.first_name = 'First name is required.';
    setStudentErrors(errors);
    if (Object.keys(errors).length > 0) return;
    if (visibleDuplicates.length > 0 && !acknowledgedDuplicate) return;
    goPastStudentDetails();
  }

  function onContinuePastDuplicate() {
    setAcknowledgedDuplicate(true);
    if (email.trim() && firstName.trim()) goPastStudentDetails();
  }

  // --- Step 2 handlers -----------------------------------------------------

  const courseOptionList: PickerOption[] = courseOptions.map((row) => ({
    value: row.id,
    label: row.title,
    hint: row.category_name || row.code,
  }));

  function onCourseSelect(option: PickerOption) {
    const found = courseOptions.find((row) => row.id === option.value);
    if (!found) return;
    setCourse(found);
    setPickedBatch(null);
    setBatchQuery('');
    advanceTo('batch', 'course');
  }

  // --- Step 3 handlers -----------------------------------------------------

  const batchOptionList: PickerOption[] = batchOptions.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: `${row.seats_available} seat${row.seats_available === 1 ? '' : 's'} left · starts ${formatDate(row.start_date)}${row.seats_available === 0 ? ' · full' : ''}`,
  }));

  function onBatchSelect(option: PickerOption) {
    const found = batchOptions.find((row) => row.id === option.value);
    if (!found) return;
    setPickedBatch(found);
    setBatchErrors({});
    if (found.trainer_name) {
      // Already staffed — nothing to do on this pass, so skip straight ahead.
      setCompleted((current) => new Set(current).add('trainer'));
      advanceTo('confirm', 'batch');
    } else {
      advanceTo('trainer', 'batch');
    }
  }

  function onDraftBatchSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!draftBatch.name.trim()) {
      setBatchErrors({ name: 'Give the batch a name.' });
      return;
    }
    setBatchErrors({});
    // A brand-new batch never starts with a trainer (see create-batch-inline's
    // reasoning) — so the next step is always the trainer step.
    advanceTo('trainer', 'batch');
  }

  // --- Step 4 handlers -----------------------------------------------------

  const trainerOptionList: PickerOption[] = trainerOptions.map((row) => ({
    value: row.id,
    label: row.full_name || row.email,
    hint: row.is_accepting_assignments ? row.trainer_id : `${row.trainer_id} · not taking new batches`,
  }));

  function onTrainerSelect(option: PickerOption) {
    setTrainerId(option.value);
    setTrainerName(option.label);
    advanceTo('confirm', 'trainer');
  }

  function onSkipTrainer() {
    setTrainerId('');
    setTrainerName('');
    advanceTo('confirm', 'trainer');
  }

  // --- Final submission ------------------------------------------------

  async function ensureStudent(): Promise<StudentProfile> {
    if (createdStudent) return createdStudent;
    const created = await createStudent({
      email: email.trim(),
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      phone: phone.trim(),
      profile: { city: city.trim(), qualification },
    });
    setCreatedStudent(created);
    return created;
  }

  async function ensureBatch(): Promise<{ id: string; name: string; code: string; hasTrainer: boolean }> {
    if (batchMode === 'pick' && pickedBatch) {
      return {
        id: pickedBatch.id,
        name: pickedBatch.name,
        code: pickedBatch.code,
        hasTrainer: Boolean(pickedBatch.trainer_name),
      };
    }
    if (createdBatch) {
      return { id: createdBatch.id, name: createdBatch.name, code: createdBatch.code, hasTrainer: false };
    }
    const created = await createBatch({
      name: draftBatch.name.trim(),
      course: course!.id,
      start_date: draftBatch.startDate,
      end_date: draftBatch.endDate,
      capacity: Number(draftBatch.capacity) || 1,
    });
    setCreatedBatch(created);
    return { id: created.id, name: created.name, code: created.code, hasTrainer: false };
  }

  async function onConfirm() {
    setIsSubmitting(true);
    setConfirmError('');

    let student: StudentProfile;
    try {
      student = await ensureStudent();
    } catch (cause) {
      setStudentErrors(fieldErrors(cause));
      goToStep('student');
      setIsSubmitting(false);
      return;
    }

    let batchInfo: { id: string; name: string; code: string; hasTrainer: boolean };
    try {
      batchInfo = await ensureBatch();
    } catch (cause) {
      setBatchErrors(fieldErrors(cause));
      goToStep('batch');
      setIsSubmitting(false);
      return;
    }

    if (trainerId && !batchInfo.hasTrainer && !trainerAssigned) {
      try {
        await assignBatchTrainer(batchInfo.id, trainerId);
        setTrainerAssigned(true);
      } catch (cause) {
        // The clash message the backend returns names the class it collides
        // with — that sentence is the useful part, so it is shown exactly as
        // received rather than replaced with a generic "could not assign".
        setTrainerErrors(fieldErrors(cause));
        goToStep('trainer');
        setIsSubmitting(false);
        return;
      }
    }

    try {
      const enrollment = await enrolStudent({ student_id: student.id, batch_id: batchInfo.id });
      setResult({ student, batchName: batchInfo.name, batchCode: batchInfo.code, enrollment });
    } catch (cause) {
      setConfirmError(errorMessage(cause, 'Could not enrol this student.'));
    } finally {
      setIsSubmitting(false);
    }
  }

  function onSaveAndStartAnother() {
    // Keep the course and the batch — the whole point of this button — and
    // fold whatever just happened (a trainer assigned, a batch created) into
    // the state the next student will reuse.
    if (createdBatch) {
      setPickedBatch({
        id: createdBatch.id,
        code: createdBatch.code,
        name: createdBatch.name,
        course_id: createdBatch.course_id,
        course_code: createdBatch.course_code,
        course_title: createdBatch.course_title,
        course_slug: createdBatch.course_slug,
        trainer_name: trainerAssigned ? trainerName : '',
        start_date: createdBatch.start_date,
        end_date: createdBatch.end_date,
        capacity: createdBatch.capacity,
        enrolled_count: createdBatch.enrolled_count + 1,
        seats_available: Math.max(0, createdBatch.seats_available - 1),
        status: createdBatch.status,
        created_at: createdBatch.created_at,
      });
      setBatchMode('pick');
      setCreatedBatch(null);
    } else if (pickedBatch) {
      setPickedBatch({
        ...pickedBatch,
        trainer_name: trainerAssigned ? trainerName : pickedBatch.trainer_name,
        enrolled_count: pickedBatch.enrolled_count + 1,
        seats_available: Math.max(0, pickedBatch.seats_available - 1),
      });
    }

    setEmail('');
    setFirstName('');
    setLastName('');
    setPhone('');
    setCity('');
    setQualification('');
    setStudentErrors({});
    setDuplicates([]);
    setAcknowledgedDuplicate(false);
    setCreatedStudent(null);
    setTrainerId('');
    setTrainerName('');
    setTrainerAssigned(false);
    setTrainerErrors({});
    setTrainerQuery('');
    setResult(null);
    setConfirmError('');
    goToStep('student');
    setCompleted(new Set());
  }

  const batchSummaryLabel =
    batchMode === 'pick'
      ? pickedBatch
        ? `${pickedBatch.name} (${pickedBatch.code})`
        : 'Not chosen yet'
      : draftBatch.name
        ? `${draftBatch.name} (new batch)`
        : 'Not named yet';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Register a student</h1>
          <p className="text-sm text-muted-foreground">
            One screen, start to finish. Nothing is created until you confirm at the end.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/admissions">Back to admissions</Link>
        </Button>
      </div>

      <StepIndicator
        steps={STEPS}
        current={step}
        completed={completed}
        reachable={visited}
        onJump={(key) => goToStep(key as StepKey)}
      />

      {step === 'student' ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Student details</CardTitle>
            <CardDescription>
              The student receives an email invitation and sets their own password.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onStudentSubmit} className="space-y-4" noValidate>
              {studentErrors.__all__ ? <Alert variant="error">{studentErrors.__all__}</Alert> : null}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Email" htmlFor="reg-email" error={studentErrors.email} required>
                  <Input
                    type="email"
                    autoFocus
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      setAcknowledgedDuplicate(false);
                    }}
                  />
                </Field>
                <Field label="Phone" htmlFor="reg-phone" error={studentErrors.phone}>
                  <Input
                    value={phone}
                    onChange={(event) => {
                      setPhone(event.target.value);
                      setAcknowledgedDuplicate(false);
                    }}
                  />
                </Field>
                <Field label="First name" htmlFor="reg-first" error={studentErrors.first_name} required>
                  <Input value={firstName} onChange={(event) => setFirstName(event.target.value)} />
                </Field>
                <Field label="Last name" htmlFor="reg-last" error={studentErrors.last_name}>
                  <Input value={lastName} onChange={(event) => setLastName(event.target.value)} />
                </Field>
                <Field label="City" htmlFor="reg-city" error={studentErrors.city}>
                  <Input value={city} onChange={(event) => setCity(event.target.value)} />
                </Field>
                <Field label="Qualification" htmlFor="reg-qualification" error={studentErrors.qualification}>
                  <Select value={qualification} onChange={(event) => setQualification(event.target.value)}>
                    <option value="">Not specified</option>
                    {QUALIFICATION_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>

              {duplicateChecking ? (
                <p className="text-xs text-muted-foreground">Checking for existing students…</p>
              ) : null}
              <DuplicateMatch matches={visibleDuplicates} onContinueAnyway={onContinuePastDuplicate} />

              <Button type="submit" disabled={visibleDuplicates.length > 0 && !acknowledgedDuplicate}>
                Next: choose a course
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {step === 'course' ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Course</CardTitle>
            <CardDescription>What is {firstName || 'this student'} enrolling on?</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SearchPicker
              label="Search courses"
              query={courseQuery}
              onQueryChange={setCourseQuery}
              options={courseOptionList}
              selected={course?.id ?? ''}
              onSelect={onCourseSelect}
              isLoading={courseLoading}
              placeholder="Course title or code"
              emptyMessage="No published courses match."
              autoFocus
            />
          </CardContent>
        </Card>
      ) : null}

      {step === 'batch' ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Batch</CardTitle>
            <CardDescription>
              A cohort of {course?.title ?? 'the chosen course'} to put {firstName || 'the student'} on.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant={batchMode === 'pick' ? 'primary' : 'outline'}
                onClick={() => setBatchMode('pick')}
              >
                Choose an existing batch
              </Button>
              <Button
                type="button"
                size="sm"
                variant={batchMode === 'create' ? 'primary' : 'outline'}
                onClick={() => setBatchMode('create')}
              >
                Create a new batch
              </Button>
            </div>

            {batchErrors.__all__ ? <Alert variant="error">{batchErrors.__all__}</Alert> : null}

            {batchMode === 'pick' ? (
              <SearchPicker
                label="Search batches"
                query={batchQuery}
                onQueryChange={setBatchQuery}
                options={batchOptionList}
                selected={pickedBatch?.id ?? ''}
                onSelect={onBatchSelect}
                isLoading={batchLoading}
                placeholder="Batch name or code"
                emptyMessage="No open batch for this course yet — create one instead."
              />
            ) : (
              <form onSubmit={onDraftBatchSubmit} className="space-y-4" noValidate>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Batch name" htmlFor="new-batch-name" error={batchErrors.name} required>
                    <Input
                      autoFocus
                      value={draftBatch.name}
                      onChange={(event) => setDraftBatch({ ...draftBatch, name: event.target.value })}
                    />
                  </Field>
                  <Field label="Capacity" htmlFor="new-batch-capacity" error={batchErrors.capacity} required>
                    <Input
                      type="number"
                      min={1}
                      value={draftBatch.capacity}
                      onChange={(event) => setDraftBatch({ ...draftBatch, capacity: event.target.value })}
                    />
                  </Field>
                  <Field label="Start date" htmlFor="new-batch-start" error={batchErrors.start_date} required>
                    <Input
                      type="date"
                      value={draftBatch.startDate}
                      onChange={(event) => setDraftBatch({ ...draftBatch, startDate: event.target.value })}
                    />
                  </Field>
                  <Field label="End date" htmlFor="new-batch-end" error={batchErrors.end_date} required>
                    <Input
                      type="date"
                      value={draftBatch.endDate}
                      onChange={(event) => setDraftBatch({ ...draftBatch, endDate: event.target.value })}
                    />
                  </Field>
                </div>
                <p className="text-sm text-muted-foreground">
                  The batch is created when you confirm at the end, and starts with no trainer — that
                  is the next step.
                </p>
                <Button type="submit">Next: assign a trainer</Button>
              </form>
            )}
          </CardContent>
        </Card>
      ) : null}

      {step === 'trainer' ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Trainer</CardTitle>
            <CardDescription>
              Assigning a trainer checks their whole timetable — a clash is refused, named, and shown
              below rather than swallowed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {trainerErrors.trainer || trainerErrors.__all__ ? (
              <Alert variant="error" data-testid="trainer-clash">
                {trainerErrors.trainer ?? trainerErrors.__all__}
              </Alert>
            ) : null}

            {batchHasTrainer ? (
              <Alert variant="info">
                This batch already has a trainer ({pickedBatch?.trainer_name}). Change that from{' '}
                <Link href="/admissions/batches" className="underline">
                  the batch list
                </Link>{' '}
                rather than here, since it affects everyone on it.
              </Alert>
            ) : (
              <>
                <SearchPicker
                  label="Search trainers"
                  query={trainerQuery}
                  onQueryChange={setTrainerQuery}
                  options={trainerOptionList}
                  selected={trainerId}
                  onSelect={onTrainerSelect}
                  isLoading={trainerLoading}
                  placeholder="Trainer name"
                  emptyMessage="No active trainers found."
                />
                <Button type="button" variant="ghost" size="sm" onClick={onSkipTrainer}>
                  Assign a trainer later
                </Button>
              </>
            )}

            {batchHasTrainer ? (
              <Button type="button" onClick={() => advanceTo('confirm', 'trainer')}>
                Next: confirm
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {step === 'confirm' ? (
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Confirm and enrol</CardTitle>
            <CardDescription>Nothing has been created yet. This is the step that does it.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {confirmError ? <Alert variant="error">{confirmError}</Alert> : null}

            {result ? (
              <Alert variant="success" role="status" className="space-y-2">
                <p className="font-medium">
                  {result.student.user.full_name || result.student.user.email} is enrolled on{' '}
                  {result.batchName} ({result.batchCode}).
                </p>
                <p className="text-sm">Enrolment {result.enrollment.code}.</p>
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button size="sm" onClick={onSaveAndStartAnother}>
                    Save and register another
                  </Button>
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/admissions/${result.student.id}`}>View this student</Link>
                  </Button>
                </div>
              </Alert>
            ) : (
              <>
                <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs text-muted-foreground">Student</dt>
                    <dd className="font-medium">
                      {firstName || lastName ? `${firstName} ${lastName}`.trim() : 'Not named yet'}
                      <span className="block text-sm font-normal text-muted-foreground">
                        {email || 'No email yet'}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Course</dt>
                    <dd className="font-medium">{course?.title ?? 'Not chosen yet'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Batch</dt>
                    <dd className="font-medium">{batchSummaryLabel}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Trainer</dt>
                    <dd className="font-medium">
                      {batchHasTrainer ? (
                        pickedBatch?.trainer_name
                      ) : trainerId ? (
                        trainerName
                      ) : (
                        <Badge variant="warning">Not assigned yet</Badge>
                      )}
                    </dd>
                  </div>
                </dl>
                <Button onClick={() => void onConfirm()} disabled={isSubmitting}>
                  {isSubmitting ? 'Enrolling…' : 'Confirm and enrol'}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function NewAdmissionPage() {
  return (
    <RequireAuth capability={Capability.studentCreate}>
      <RegistrationWizard />
    </RequireAuth>
  );
}
