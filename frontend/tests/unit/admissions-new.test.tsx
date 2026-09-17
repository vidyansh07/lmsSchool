import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RegistrationWizard } from '@/app/admissions/new/page';
import { ApiError } from '@/lib/api';
import type {
  BatchDetail,
  BatchListRow,
  CourseListRow,
  Enrollment,
  StudentDuplicateMatch,
  StudentListRow,
  StudentProfile,
  TrainerListRow,
} from '@/types/api';

const createStudent = vi.hoisted(() => vi.fn());
const checkDuplicates = vi.hoisted(() => vi.fn());
const listStudents = vi.hoisted(() => vi.fn());
const listTrainers = vi.hoisted(() => vi.fn());
const listCourses = vi.hoisted(() => vi.fn());
const listBatches = vi.hoisted(() => vi.fn());
const createBatch = vi.hoisted(() => vi.fn());
const assignBatchTrainer = vi.hoisted(() => vi.fn());
const enrolStudent = vi.hoisted(() => vi.fn());

vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ user: null, can: () => false }) }));
vi.mock('@/lib/people', () => ({ createStudent, checkDuplicates, listStudents, listTrainers }));
vi.mock('@/lib/courses', () => ({ listCourses }));
vi.mock('@/lib/batches', () => ({ listBatches, createBatch, assignBatchTrainer, enrolStudent }));

const COURSE: CourseListRow = {
  id: 'course-1',
  code: 'GRS-C-001',
  slug: 'linux-essentials',
  title: 'Linux Essentials',
  short_description: '',
  category_name: 'Linux',
  category_slug: 'linux',
  difficulty: 'beginner',
  estimated_duration_minutes: 100,
  default_fee: null,
  status: 'published',
  visibility: 'public',
  thumbnail_url: null,
  module_count: 1,
  lesson_count: 1,
  published_at: '2026-01-01',
  created_at: '2026-01-01',
};

function batch(overrides: Partial<BatchListRow> = {}): BatchListRow {
  return {
    id: 'batch-1',
    code: 'GRS-B-001',
    name: 'Morning batch',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: '',
    start_date: '2026-04-01',
    end_date: '2026-06-01',
    capacity: 20,
    enrolled_count: 5,
    seats_available: 15,
    status: 'upcoming',
    created_at: '2026-01-01',
    ...overrides,
  };
}

function trainer(overrides: Partial<TrainerListRow> = {}): TrainerListRow {
  return {
    id: 'trainer-1',
    trainer_id: 'GRS-T-001',
    user_id: 'u-trainer-1',
    email: 'tina@example.com',
    full_name: 'Tina Trainer',
    professional_title: 'Senior trainer',
    skills: [],
    years_of_experience: 5,
    is_accepting_assignments: true,
    is_active: true,
    is_email_verified: true,
    created_at: '2026-01-01',
    ...overrides,
  };
}

function student(overrides: Partial<StudentProfile> = {}): StudentProfile {
  return {
    id: 'student-1',
    student_id: 'GRS-S-00001',
    user: {
      id: 'u1',
      email: 'new.student@example.com',
      first_name: 'New',
      last_name: 'Student',
      full_name: 'New Student',
      phone: '',
      role: 'student',
      is_active: true,
      is_email_verified: false,
      profile_image_url: null,
      branch_id: null,
      branch_code: null,
      branch_name: null,
      date_joined: '2026-01-01',
    },
    date_of_birth: null,
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    country: '',
    postal_code: '',
    qualification: '',
    institution: '',
    roll_number: '',
    institution_kind: '',
    job_title: '',
    graduation_year: null,
    emergency_contact_name: '',
    emergency_contact_phone: '',
    emergency_contact_relationship: '',
    guardian_name: '',
    guardian_phone: '',
    fee_status: 'pending',
    fee_amount: null,
    fee_amount_updated_at: null,
    referred_by: null,
    referred_by_label: null,
    fee_status_updated_at: null,
    completion_percent: 0,
    is_profile_complete: false,
    created_at: '2026-01-01',
    updated_at: '2026-01-01',
    ...overrides,
  };
}

function enrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: 'enrol-1',
    code: 'GRS-E-00001',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    batch_id: 'batch-1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning batch',
    batch_status: 'upcoming',
    trainer_name: '',
    status: 'active',
    enrolled_at: '2026-01-02',
    start_date: null,
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    ...overrides,
  };
}

function emptyPage<T>(): { count: number; page: number; page_size: number; total_pages: number; next: null; previous: null; results: T[] } {
  return { count: 0, page: 1, page_size: 50, total_pages: 0, next: null, previous: null, results: [] };
}

beforeEach(() => {
  createStudent.mockReset();
  checkDuplicates.mockReset().mockResolvedValue({ results: [] as StudentDuplicateMatch[] });
  listStudents.mockReset().mockResolvedValue({ ...emptyPage<StudentListRow>(), results: [] });
  listTrainers.mockReset().mockResolvedValue({ ...emptyPage<TrainerListRow>(), results: [trainer()] });
  listCourses.mockReset().mockResolvedValue({ ...emptyPage<CourseListRow>(), results: [COURSE] });
  listBatches.mockReset().mockResolvedValue({ ...emptyPage<BatchListRow>(), results: [batch()] });
  createBatch.mockReset();
  assignBatchTrainer.mockReset();
  enrolStudent.mockReset();
});

function referrerRow(): StudentListRow {
  return {
    id: 'referrer-1',
    student_id: 'GRS-S-00012',
    user_id: 'u-referrer',
    email: 'priya@example.com',
    full_name: 'Priya Shah',
    city: 'Jaipur',
    qualification: 'bachelors',
    fee_status: 'paid',
    fee_amount: '20000.00',
    fee_payable: '20000.00',
    fee_paid: '20000.00',
    fee_balance: '0.00',
    fee_next_due_on: null,
    institution: 'Infosys',
    roll_number: '',
    institution_kind: 'employer',
    referred_by: null,
    is_active: true,
    is_email_verified: true,
    created_at: '2026-01-01T00:00:00Z',
  };
}

async function fillStudentStep(user: ReturnType<typeof userEvent.setup>, overrides: { email?: string } = {}) {
  await user.type(screen.getByLabelText('Email', { exact: false }), overrides.email ?? 'jane@example.com');
  await user.type(screen.getByLabelText('First name', { exact: false }), 'Jane');
}

async function goToConfirmWithExistingBatch(user: ReturnType<typeof userEvent.setup>) {
  render(<RegistrationWizard />);
  await fillStudentStep(user);
  await user.click(screen.getByRole('button', { name: /next: choose a course/i }));

  await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
  await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');

  await waitFor(() => expect(screen.getByLabelText('Search batches')).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText(/Morning batch/)).toBeInTheDocument());
  await user.selectOptions(screen.getByLabelText('Search batches results'), 'batch-1');
}

function existingMatch(overrides: Partial<StudentDuplicateMatch> = {}): StudentDuplicateMatch {
  return {
    id: 'existing-1',
    name: 'Jane Existing',
    student_id: 'GRS-S-00099',
    batch_code: 'MERN-02',
    created_at: '2026-08-03T00:00:00Z',
    ...overrides,
  };
}

describe('RegistrationWizard — duplicate detection', () => {
  it('warns before the student can be submitted, via the disclosure-safe duplicates endpoint', async () => {
    const user = userEvent.setup();
    checkDuplicates.mockResolvedValue({ results: [existingMatch()] });
    render(<RegistrationWizard />);
    await fillStudentStep(user);

    await waitFor(() => expect(screen.getByTestId('duplicate-warning')).toBeInTheDocument());
    expect(screen.getByText(/Jane Existing/)).toBeInTheDocument();
    expect(checkDuplicates).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'jane@example.com' }),
    );
    // Never the plain, unscoped student search — that would defeat the whole
    // point of a disclosure-safe check.
    expect(listStudents).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /next: choose a course/i })).toBeDisabled();
  });

  it('offers to open the existing record', async () => {
    const user = userEvent.setup();
    checkDuplicates.mockResolvedValue({ results: [existingMatch()] });
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    await waitFor(() => expect(screen.getByTestId('duplicate-warning')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Open that record' })).toHaveAttribute(
      'href',
      '/admissions/existing-1',
    );
  });

  it('keeps "continue registering" disabled until a reason is typed, then carries it through to the final submit', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockResolvedValue({});
    enrolStudent.mockResolvedValue(enrollment());
    const user = userEvent.setup();
    checkDuplicates.mockResolvedValue({ results: [existingMatch()] });
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    await waitFor(() => expect(screen.getByTestId('duplicate-warning')).toBeInTheDocument());

    const continueButton = screen.getByRole('button', { name: /continue registering/i });
    expect(continueButton).toBeDisabled();
    await user.click(continueButton);
    // Still on the student step — nothing was created yet, and the wizard
    // did not advance without a reason.
    expect(screen.getByRole('button', { name: /next: choose a course/i })).toBeInTheDocument();

    await user.type(
      screen.getByLabelText(/this is a different person/i),
      'Different phone owner, confirmed by ID.',
    );
    expect(continueButton).toBeEnabled();
    await user.click(continueButton);

    await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');
    await waitFor(() => expect(screen.getByText(/Morning batch/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search batches results'), 'batch-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /assign a trainer later/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /confirm and enrol/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    // The reason is only sent now, bundled with the rest of the
    // registration — never at the moment it was typed.
    await waitFor(() => expect(createStudent).toHaveBeenCalledOnce());
    expect(createStudent).toHaveBeenCalledWith(
      expect.objectContaining({ override_reason: 'Different phone owner, confirmed by ID.' }),
    );
  });

  it('does not send an override reason for a registration that never showed a duplicate', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockResolvedValue({});
    enrolStudent.mockResolvedValue(enrollment());
    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /assign a trainer later/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /confirm and enrol/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(createStudent).toHaveBeenCalledOnce());
    expect(createStudent.mock.calls[0]?.[0]).not.toHaveProperty('override_reason');
  });

  it('does not warn once the email is too short to search on', async () => {
    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await user.type(screen.getByLabelText('Email', { exact: false }), 'jo');
    await user.type(screen.getByLabelText('First name', { exact: false }), 'Jo');
    expect(checkDuplicates).not.toHaveBeenCalled();
  });
});

describe('RegistrationWizard — moving through the steps', () => {
  it('requires an email and a first name before advancing', async () => {
    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));
    expect(screen.getByText('Email is required.')).toBeInTheDocument();
    expect(screen.getByText('First name is required.')).toBeInTheDocument();
  });

  it('advances to the batch step the moment a course is chosen', async () => {
    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));
    await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Batch' })).toBeInTheDocument());
  });

  it('skips the trainer step when the chosen batch already has one', async () => {
    listBatches.mockResolvedValue({
      ...emptyPage<BatchListRow>(),
      results: [batch({ trainer_name: 'Tina Trainer' })],
    });
    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument();
  });

  it('goes to the trainer step when the chosen batch has none', async () => {
    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
  });

  it('preserves the new-batch draft when stepping back to student details and forward again', async () => {
    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));
    await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');

    await waitFor(() => expect(screen.getByRole('button', { name: /create a new batch/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /create a new batch/i }));
    await user.type(screen.getByLabelText('Batch name', { exact: false }), 'Evening cohort');

    // Jump back to the first step and return.
    await user.click(screen.getByRole('button', { name: /^Student$/ }));
    await waitFor(() => expect(screen.getByText('Student details')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^Batch$/ }));

    await waitFor(() => expect(screen.getByLabelText('Batch name', { exact: false })).toHaveValue('Evening cohort'));
  });
});

describe('RegistrationWizard — confirming', () => {
  it('creates the student, assigns the trainer and enrols on confirm', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockResolvedValue({});
    enrolStudent.mockResolvedValue(enrollment());

    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search trainers results'), 'trainer-1');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(createStudent).toHaveBeenCalledOnce());
    expect(assignBatchTrainer).toHaveBeenCalledWith('batch-1', 'trainer-1');
    expect(enrolStudent).toHaveBeenCalledWith({ student_id: 'student-1', batch_id: 'batch-1' });
    await waitFor(() => expect(screen.getByText(/is enrolled on Morning batch/)).toBeInTheDocument());
  });

  it('sends the agreed fee and where the student works, decided at the desk', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockResolvedValue({});
    enrolStudent.mockResolvedValue(enrollment());

    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    // Choosing "working professional" is what makes the company and
    // designation questions appear; a college student is never asked them.
    expect(screen.queryByLabelText('Company name')).not.toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: /working professional/i }));
    await user.type(screen.getByLabelText('Company name'), 'Infosys');
    await user.type(screen.getByLabelText('Designation'), 'Senior Engineer');
    await user.type(screen.getByLabelText(/Agreed fee/), '25000');
    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));

    await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');
    await waitFor(() => expect(screen.getByText(/Morning batch/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search batches results'), 'batch-1');
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search trainers results'), 'trainer-1');

    // The confirm step repeats both back before anything is created — the
    // background as one line, the way a counsellor would say it aloud.
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    expect(screen.getByText('Working professional')).toBeInTheDocument();
    expect(screen.getByText('Infosys — Senior Engineer')).toBeInTheDocument();
    expect(screen.getByText('₹25,000')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(createStudent).toHaveBeenCalledOnce());
    expect(createStudent).toHaveBeenCalledWith(
      expect.objectContaining({
        fee_amount: '25000',
        profile: expect.objectContaining({
          institution: 'Infosys',
          institution_kind: 'employer',
          job_title: 'Senior Engineer',
          graduation_year: null,
        }),
      }),
    );
  });

  it('credits the existing student who sent them', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockResolvedValue({});
    enrolStudent.mockResolvedValue(enrollment());
    // Only the referrer search uses `listStudents` now — the duplicate check
    // is a separate call (`checkDuplicates`) that defaults to no matches.
    listStudents.mockImplementation(async ({ search }: { search?: string } = {}) =>
      search === 'Priya'
        ? { ...emptyPage<StudentListRow>(), count: 1, results: [referrerRow()] }
        : { ...emptyPage<StudentListRow>(), results: [] },
    );

    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    await user.type(screen.getByLabelText('Search students to credit'), 'Priya');
    await waitFor(() => expect(screen.getByText(/Priya Shah/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search students to credit results'), 'referrer-1');
    // Picked: the picker gives way to the chosen student and a way to undo it.
    expect(screen.getByText('GRS-S-00012')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));
    await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');
    await waitFor(() => expect(screen.getByText(/Morning batch/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search batches results'), 'batch-1');
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search trainers results'), 'trainer-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    expect(screen.getByText('Priya Shah (GRS-S-00012)')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(createStudent).toHaveBeenCalledOnce());
    expect(createStudent).toHaveBeenCalledWith(
      expect.objectContaining({ profile: expect.objectContaining({ referred_by: 'referrer-1' }) }),
    );
  });

  it('sends no fee at all when none was decided, rather than a fee of nothing', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockResolvedValue({});
    enrolStudent.mockResolvedValue(enrollment());

    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search trainers results'), 'trainer-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    expect(screen.getByText('Not decided yet')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(createStudent).toHaveBeenCalledOnce());
    expect(createStudent).toHaveBeenCalledWith(expect.objectContaining({ fee_amount: null }));
  });

  it('does not assign a trainer when the batch already has one', async () => {
    listBatches.mockResolvedValue({
      ...emptyPage<BatchListRow>(),
      results: [batch({ trainer_name: 'Tina Trainer' })],
    });
    createStudent.mockResolvedValue(student());
    enrolStudent.mockResolvedValue(enrollment());

    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(enrolStudent).toHaveBeenCalledOnce());
    expect(assignBatchTrainer).not.toHaveBeenCalled();
  });

  it('creates a new batch on confirm when one was drafted', async () => {
    createStudent.mockResolvedValue(student());
    createBatch.mockResolvedValue({
      id: 'batch-new',
      code: 'GRS-B-002',
      name: 'Evening cohort',
      course_id: 'course-1',
      course_code: 'GRS-C-001',
      course_title: 'Linux Essentials',
      course_slug: 'linux-essentials',
      trainer_name: '',
      trainer_id: null,
      trainer_code: '',
      start_date: '2026-05-01',
      end_date: '2026-07-01',
      capacity: 20,
      enrolled_count: 0,
      seats_available: 20,
      status: 'upcoming',
      created_at: '2026-01-01',
      description: '',
      schedules: [],
      updated_at: '2026-01-01',
      can_manage: true,
      can_view_roster: true,
    } satisfies BatchDetail);
    enrolStudent.mockResolvedValue(enrollment({ batch_id: 'batch-new', batch_name: 'Evening cohort' }));

    const user = userEvent.setup();
    render(<RegistrationWizard />);
    await fillStudentStep(user);
    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));
    await waitFor(() => expect(screen.getByText(/Linux Essentials/)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search courses results'), 'course-1');

    await user.click(screen.getByRole('button', { name: /create a new batch/i }));
    await user.type(screen.getByLabelText('Batch name', { exact: false }), 'Evening cohort');
    await user.click(screen.getByRole('button', { name: /next: assign a trainer/i }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /assign a trainer later/i }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(createBatch).toHaveBeenCalledOnce());
    expect(createBatch).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Evening cohort', course: 'course-1' }),
    );
  });

  it('routes a student field error back to the student step', async () => {
    createStudent.mockRejectedValue(
      new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'req-1', {
        email: ['This email is already registered.'],
      }),
    );
    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /assign a trainer later/i }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(screen.getByText('Student details')).toBeInTheDocument());
    expect(screen.getByText('This email is already registered.')).toBeInTheDocument();
  });

  it('shows a trainer clash message verbatim, without paraphrasing it', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockRejectedValue(
      new ApiError(409, 'trainer_clash', 'The submitted data is invalid.', 'req-2', {
        trainer: ['Tina Trainer is teaching GRS-B-777 at this time.'],
      }),
    );
    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search trainers results'), 'trainer-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() =>
      expect(screen.getByTestId('trainer-clash')).toHaveTextContent(
        'Tina Trainer is teaching GRS-B-777 at this time.',
      ),
    );
  });

  it('does not create the student twice when retrying after a later failure', async () => {
    createStudent.mockResolvedValue(student());
    assignBatchTrainer.mockRejectedValueOnce(
      new ApiError(409, 'trainer_clash', 'clash', 'req', { trainer: ['Clash.'] }),
    );
    assignBatchTrainer.mockResolvedValueOnce({});
    enrolStudent.mockResolvedValue(enrollment());

    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Search trainers results'), 'trainer-1');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));
    await waitFor(() => expect(screen.getByTestId('trainer-clash')).toBeInTheDocument());

    // A trainer clash is a trainer problem, so the wizard puts the counsellor
    // back on the trainer step with the message attached. Getting to the
    // confirm step again is therefore a real navigation, not a second click on
    // a button that is no longer on screen.
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /assign a trainer later/i }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));
    await waitFor(() => expect(enrolStudent).toHaveBeenCalledOnce());

    // The point of the test: the student was created on the first attempt and
    // must not be created a second time by the retry.
    expect(createStudent).toHaveBeenCalledOnce();
  });

  it('keeps the course and batch for "save and start another"', async () => {
    createStudent.mockResolvedValue(student());
    enrolStudent.mockResolvedValue(enrollment());

    const user = userEvent.setup();
    await goToConfirmWithExistingBatch(user);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /assign a trainer later/i }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /confirm and enrol/i }));

    await waitFor(() => expect(screen.getByRole('button', { name: /save and register another/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /save and register another/i }));

    await waitFor(() => expect(screen.getByText('Student details')).toBeInTheDocument());
    expect(screen.getByLabelText('Email', { exact: false })).toHaveValue('');

    // The course and batch are already resolved, so submitting the next
    // student's details goes straight to the confirmation summary.
    createStudent.mockResolvedValue(student({ id: 'student-2', student_id: 'GRS-S-00002' }));
    await user.type(screen.getByLabelText('Email', { exact: false }), 'second@example.com');
    await user.type(screen.getByLabelText('First name', { exact: false }), 'Second');
    await user.click(screen.getByRole('button', { name: /next: choose a course/i }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Confirm and enrol' })).toBeInTheDocument());
    expect(screen.getByText(/Morning batch \(GRS-B-001\)/)).toBeInTheDocument();
  });
});
