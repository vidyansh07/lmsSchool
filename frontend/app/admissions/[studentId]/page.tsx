'use client';

/**
 * One student's record, from the counsellor's side of it: contact details,
 * every enrolment they have ever held, and the quick actions that keep the
 * job moving — suspend, withdraw, transfer, or put them on another batch.
 *
 * Enrolment history has no dedicated endpoint (`/api/v1/enrollments/` filters
 * by batch or course, not by student — see the comment on
 * `listStudentEnrollments` in `lib/batches.ts` for why searching by the
 * student's own code stands in for it safely).
 */

import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { ArrowLeft, ExternalLink } from 'lucide-react';

import { PlanFollowUp } from '@/components/admissions/plan-follow-up';
import { FollowUpsPanel } from '@/components/students/follow-ups-panel';
import { SearchPicker, type PickerOption } from '@/components/admissions/search-picker';
import { FeeLedger, useStudentFees } from '@/components/fees/fee-ledger';
import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  EnrollmentStatusDialog,
  type EnrollmentStatusChange,
} from '@/components/students/enrollment-status-dialog';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ApiError, errorMessage } from '@/lib/api';
import {
  enrolStudent,
  listBatches,
  listStudentEnrollments,
  setEnrollmentStatus,
} from '@/lib/batches';
import { ENROLLMENT_STATUS_LABEL, ENROLLMENT_STATUS_VARIANT, formatDate } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { listCourses } from '@/lib/courses';
import { getStudentFees } from '@/lib/fees';
import {
  FEE_STATUS_LABEL,
  FEE_STATUS_VARIANT,
  INSTITUTION_KIND_LABEL,
  QUALIFICATION_LABEL,
  labelFor,
} from '@/lib/labels';
import { getStudent } from '@/lib/people';
import type { BatchListRow, CourseListRow, Enrollment, StudentProfile } from '@/types/api';

function EnrolPanel({ student, onEnrolled }: { student: StudentProfile; onEnrolled: () => void }) {
  const [courseQuery, setCourseQuery] = useState('');
  const [courseOptions, setCourseOptions] = useState<CourseListRow[]>([]);
  const [course, setCourse] = useState<CourseListRow | null>(null);
  const [batchQuery, setBatchQuery] = useState('');
  const [batchOptions, setBatchOptions] = useState<BatchListRow[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      listCourses({ search: courseQuery, page_size: 50, ordering: 'title' })
        .then((page) =>
          setCourseOptions(page.results.filter((course) => course.status !== 'archived')),
        )
        .catch(() => setCourseOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [courseQuery]);

  useEffect(() => {
    if (!course) return;
    const timer = setTimeout(() => {
      listBatches({
        course: course.slug,
        search: batchQuery,
        page_size: 50,
        ordering: 'start_date',
      })
        .then((page) =>
          setBatchOptions(
            page.results.filter((b) => b.status === 'upcoming' || b.status === 'active'),
          ),
        )
        .catch(() => setBatchOptions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [course, batchQuery]);

  async function onEnrol(option: PickerOption) {
    setIsBusy(true);
    setError('');
    setMessage('');
    try {
      const batch = batchOptions.find((row) => row.id === option.value);
      await enrolStudent({ student_id: student.id, batch_id: option.value });
      setMessage(`Enrolled on ${batch?.name ?? 'the batch'}.`);
      setCourse(null);
      setCourseQuery('');
      setBatchQuery('');
      onEnrolled();
    } catch (cause) {
      setError(errorMessage(cause, 'Could not enrol this student.'));
    } finally {
      setIsBusy(false);
    }
  }

  const courseOptionList: PickerOption[] = courseOptions.map((row) => ({
    value: row.id,
    label: row.title,
    hint: row.category_name || row.code,
  }));
  const batchOptionList: PickerOption[] = batchOptions.map((row) => ({
    value: row.id,
    label: `${row.name} (${row.code})`,
    hint: `${row.seats_available} left · starts ${formatDate(row.start_date)}`,
  }));

  return (
    <Card className="">
      <CardHeader>
        <CardTitle>Enrol on another batch</CardTitle>
        <CardDescription>Adds a new enrolment without touching any existing one.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {message ? (
          <Alert variant="success" role="status">
            {message}
          </Alert>
        ) : null}
        {error ? <Alert variant="error">{error}</Alert> : null}
        <SearchPicker
          label="Course"
          query={courseQuery}
          onQueryChange={setCourseQuery}
          options={courseOptionList}
          selected={course?.id ?? ''}
          onSelect={(option) => {
            const found = courseOptions.find((row) => row.id === option.value);
            setCourse(found ?? null);
          }}
          emptyMessage="No courses match."
        />
        {course ? (
          <SearchPicker
            label="Batch"
            query={batchQuery}
            onQueryChange={setBatchQuery}
            options={batchOptionList}
            selected=""
            onSelect={(option) => void onEnrol(option)}
            emptyMessage="No open batch for this course."
          />
        ) : null}
        {isBusy ? <p className="text-sm text-ink-muted">Enrolling…</p> : null}
      </CardContent>
    </Card>
  );
}

function EnrolmentHistory({
  studentId,
  studentCode,
  refreshToken,
}: {
  studentId: string;
  studentCode: string;
  refreshToken: number;
}) {
  const [rows, setRows] = useState<Enrollment[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [message, setMessage] = useState('');
  const [pendingChange, setPendingChange] = useState<EnrollmentStatusChange | null>(null);

  const load = useCallback(() => {
    listStudentEnrollments(studentCode)
      .then(setRows)
      .catch(() => setFailed(true));
  }, [studentCode]);

  useEffect(load, [load, refreshToken]);

  function ask(entry: Enrollment, status: EnrollmentStatusChange['status']) {
    setMessage('');
    setPendingChange({
      enrollmentId: entry.id,
      subject: `${entry.course_title || 'This course'} · ${entry.batch_name || entry.batch_code || 'batch'}`,
      status,
    });
  }

  async function onTransition(entry: Enrollment, status: 'active') {
    setBusyId(entry.id);
    setMessage('');
    try {
      await setEnrollmentStatus(entry.id, status);
      load();
    } catch (cause) {
      setMessage(errorMessage(cause, 'Could not update this enrolment.'));
    } finally {
      setBusyId('');
    }
  }

  return (
    <Card className="">
      <CardHeader>
        <CardTitle>Enrolment history</CardTitle>
        <CardDescription>
          Every batch this student has been placed on, most recent first.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {message ? <Alert variant="error">{message}</Alert> : null}
        {failed ? <Alert variant="error">Could not load the enrolment history.</Alert> : null}
        {rows === null && !failed ? <LoadingState label="Loading enrolments…" rows={3} /> : null}
        {rows?.length === 0 ? (
          <EmptyState
            title="No enrolments yet"
            description="This student was registered but has not been placed on a batch."
          />
        ) : null}
        {rows && rows.length > 0 ? (
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Course</Th>
                  <Th>Batch</Th>
                  <Th>Registered</Th>
                  <Th>Status</Th>
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((entry) => (
                  <tr key={entry.id}>
                    <Td className="font-medium">{entry.course_title || 'Not available'}</Td>
                    <Td>
                      {entry.batch_name || 'Not available'}
                      <span className="block font-mono text-xs text-ink-muted">
                        {entry.batch_code}
                      </span>
                    </Td>
                    <Td className="whitespace-nowrap text-ink-muted">
                      {formatDate(entry.enrolled_at)}
                    </Td>
                    <Td>
                      <Badge variant={ENROLLMENT_STATUS_VARIANT[entry.status]}>
                        {ENROLLMENT_STATUS_LABEL[entry.status]}
                      </Badge>
                    </Td>
                    <Td>
                      <div className="flex flex-wrap gap-2">
                        {entry.status === 'active' ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busyId === entry.id}
                            onClick={() => ask(entry, 'suspended')}
                          >
                            Suspend
                          </Button>
                        ) : null}
                        {entry.status === 'suspended' ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busyId === entry.id}
                            onClick={() => void onTransition(entry, 'active')}
                          >
                            Reactivate
                          </Button>
                        ) : null}
                        {entry.status === 'active' || entry.status === 'suspended' ? (
                          <>
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={busyId === entry.id}
                              onClick={() => ask(entry, 'cancelled')}
                            >
                              Withdraw
                            </Button>
                            <Button asChild size="sm" variant="outline">
                              <Link
                                href={`/admissions/transfer?student=${studentId}&enrollment=${entry.id}`}
                              >
                                Transfer
                              </Link>
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        ) : null}
      </CardContent>
      <EnrollmentStatusDialog
        change={pendingChange}
        onClose={() => setPendingChange(null)}
        onChanged={load}
      />
    </Card>
  );
}

export function StudentDetail({ studentId }: { studentId: string }) {
  const { can } = useAuth();
  const [student, setStudent] = useState<StudentProfile | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [followUpsVersion, setFollowUpsVersion] = useState(0);
  const fees = useStudentFees(() => getStudentFees(studentId), [studentId, reloadToken]);
  const [enrollments, setEnrollments] = useState<Enrollment[] | null>(null);

  useEffect(() => {
    if (!student) return;
    let cancelled = false;
    listStudentEnrollments(student.student_id)
      .then((rows) => {
        if (!cancelled) setEnrollments(rows);
      })
      .catch(() => {
        if (!cancelled) setEnrollments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [student, reloadToken]);

  useEffect(() => {
    let cancelled = false;
    getStudent(studentId)
      .then((row) => {
        if (!cancelled) setStudent(row);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, reloadToken]);

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Student not found"
          description="This record does not exist, or is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href="/admissions">Back to admissions</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this student"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  if (!student) return <LoadingState label="Loading student…" rows={6} />;

  return (
    <div className="space-y-4">
      <Link
        href="/admissions"
        className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        All admissions
      </Link>

      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {student.user.full_name || student.user.email}
        </h1>
        <Badge>{student.student_id}</Badge>
        <Badge variant={student.user.is_active ? 'success' : 'error'}>
          {student.user.is_active ? 'Active' : 'Inactive'}
        </Badge>
        <Badge variant={FEE_STATUS_VARIANT[student.fee_status]}>
          {FEE_STATUS_LABEL[student.fee_status]}
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          {/* This record keeps its own fee ledger below and never redirects
              (DESIGN_DECISIONS.md, "Student 360") — it only links out to the
              full cross-role profile: activities, timeline, progress, risk. */}
          <Button asChild variant="outline" size="sm">
            <Link href={`/students/${studentId}`}>
              <ExternalLink className="size-3.5" aria-hidden="true" />
              View 360 profile
            </Link>
          </Button>
          {can(Capability.userViewAny) ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/admin/users/${student.user.id}`}>Account</Link>
            </Button>
          ) : null}
        </div>
      </div>

      <FollowUpsPanel
        studentId={student.id}
        mayComplete
        refreshKey={followUpsVersion}
        action={
          <PlanFollowUp
            studentId={student.id}
            onCreated={() => setFollowUpsVersion((value) => value + 1)}
          />
        }
      />

      <FeeLedger
        studentId={studentId}
        summary={fees.summary}
        enrollments={enrollments}
        mayManage={can(Capability.feeManageAny)}
        mayReadComments={can(Capability.feeViewAny)}
        isLoading={fees.isLoading}
        error={fees.error}
        onChanged={() => {
          fees.reload();
          setReloadToken((value) => value + 1);
        }}
      />

      <Card className="">
        <CardHeader>
          <CardTitle>Contact and background</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs text-ink-muted">Email</dt>
              <dd>{student.user.email}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Phone</dt>
              <dd>{student.user.phone || 'Not provided'}</dd>
            </div>
            <div className="sm:col-span-2">
              {/* The whole address, on the first screen.
                  A city on its own answers almost nothing — somebody ringing
                  a student to say the class has moved needs the part of town
                  and the landmark, which is how an address is given here.
                  Assembled from the parts that are filled in, so a half-known
                  address reads as a line rather than as a row of commas. */}
              <dt className="text-xs text-ink-muted">Address</dt>
              <dd>
                {[
                  student.address_line1,
                  student.address_line2,
                  student.area,
                  student.city,
                  student.state,
                  student.postal_code,
                ]
                  .filter(Boolean)
                  .join(', ') || 'Not provided'}
                {student.landmark ? (
                  <span className="block text-sm text-ink-muted">
                    Near {student.landmark}
                  </span>
                ) : null}
              </dd>
            </div>
            {student.roll_number ? (
              <div>
                <dt className="text-xs text-ink-muted">Roll number</dt>
                <dd className="font-mono">{student.roll_number}</dd>
              </div>
            ) : null}
            <div>
              <dt className="text-xs text-ink-muted">Qualification</dt>
              <dd>
                {student.qualification
                  ? labelFor(QUALIFICATION_LABEL, student.qualification)
                  : 'Not provided'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">
                {student.institution_kind
                  ? labelFor(INSTITUTION_KIND_LABEL, student.institution_kind)
                  : 'College or employer'}
              </dt>
              <dd>{student.institution || 'Not provided'}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Referred by</dt>
              <dd>
                {student.referred_by && student.referred_by_label ? (
                  <Link
                    href={`/admissions/${student.referred_by}`}
                    className="text-action hover:underline"
                  >
                    {student.referred_by_label}
                  </Link>
                ) : (
                  'Nobody'
                )}
              </dd>
            </div>
            {typeof student.referrals_count === 'number' && student.referrals_count > 0 ? (
              <div>
                <dt className="text-xs text-ink-muted">Has referred</dt>
                <dd>
                  <Link
                    href={`/admin/students?referred_by=${student.id}`}
                    className="text-action hover:underline"
                  >
                    {student.referrals_count === 1
                      ? '1 student'
                      : `${student.referrals_count} students`}
                  </Link>
                </dd>
              </div>
            ) : null}
            <div>
              <dt className="text-xs text-ink-muted">Guardian</dt>
              <dd>
                {student.guardian_name
                  ? `${student.guardian_name}${student.guardian_phone ? ` · ${student.guardian_phone}` : ''}`
                  : 'Not provided'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Emergency contact</dt>
              <dd>
                {student.emergency_contact_name
                  ? `${student.emergency_contact_name}${
                      student.emergency_contact_phone ? ` · ${student.emergency_contact_phone}` : ''
                    }`
                  : 'Not provided'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Registered</dt>
              <dd>{formatDate(student.created_at)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* What the student wrote about themselves.
          Shown only when they have written something: a card of "Not
          provided" six times over teaches a counsellor to stop looking, and
          the whole value of this is that somebody looks. */}
      {student.career_goal ||
      student.about ||
      student.interests?.length ||
      student.skills?.length ||
      student.open_to_placement ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">In their own words</CardTitle>
            <CardDescription>
              Written by the student. Nobody else can answer these.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {student.open_to_placement ? (
              <Badge variant="success">
                Looking for a job{student.willing_to_relocate ? ' · will relocate' : ''}
              </Badge>
            ) : null}
            {student.career_goal ? (
              <div>
                <dt className="text-xs text-ink-muted">Wants to be</dt>
                <dd className="font-medium">{student.career_goal}</dd>
              </div>
            ) : null}
            {student.about ? (
              <p className="whitespace-pre-line text-sm text-ink-muted">{student.about}</p>
            ) : null}
            {student.skills?.length ? (
              <div>
                <dt className="text-xs text-ink-muted">Can already do</dt>
                <dd className="mt-1 flex flex-wrap gap-1">
                  {student.skills.map((skill) => (
                    <Badge key={skill} variant="neutral">
                      {skill}
                    </Badge>
                  ))}
                </dd>
              </div>
            ) : null}
            {student.interests?.length ? (
              <div>
                <dt className="text-xs text-ink-muted">Enjoys</dt>
                <dd className="mt-1 flex flex-wrap gap-1">
                  {student.interests.map((interest) => (
                    <Badge key={interest} variant="neutral">
                      {interest}
                    </Badge>
                  ))}
                </dd>
              </div>
            ) : null}
            {student.preferred_class_time ? (
              <div>
                <dt className="text-xs text-ink-muted">Can attend</dt>
                <dd className="capitalize">{student.preferred_class_time}</dd>
              </div>
            ) : null}
            {student.linkedin_url || student.github_url || student.portfolio_url ? (
              <div className="flex flex-wrap gap-3 text-sm">
                {[
                  ['LinkedIn', student.linkedin_url],
                  ['GitHub', student.github_url],
                  ['Portfolio', student.portfolio_url],
                ]
                  .filter(([, href]) => href)
                  .map(([label, href]) => (
                    <a
                      key={label}
                      href={href as string}
                      target="_blank"
                      // A link to a student's own site leaves this product, so
                      // it must not hand the destination a handle on the tab
                      // it came from.
                      rel="noopener noreferrer"
                      className="text-action hover:underline"
                    >
                      {label}
                    </a>
                  ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <EnrolmentHistory
        studentId={student.id}
        studentCode={student.student_id}
        refreshToken={reloadToken}
      />

      <EnrolPanel student={student} onEnrolled={() => setReloadToken((value) => value + 1)} />
    </div>
  );
}

export default function AdmissionStudentPage({
  params,
}: {
  params: Promise<{ studentId: string }>;
}) {
  const { studentId } = use(params);
  return (
    <RequireAuth capability={Capability.studentViewAny}>
      <StudentDetail studentId={studentId} />
    </RequireAuth>
  );
}
