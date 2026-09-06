/**
 * Integration coverage for the rebuilt student dashboard: `StudentView` (the
 * content itself, exported so a test can mount it with a prop-built payload
 * without wrestling `useAuth`) and `Dashboard` (the role router around it,
 * which does need `useAuth` mocked — covered in its own small block below).
 *
 * The brand-new-student test is the one the brief calls out as the most
 * valuable in the file: every list empty, every number absent, all six
 * secondary endpoints returning nothing, at once. If any panel were to leak
 * `undefined`, `NaN` or `Invalid Date` past its own guard, this is where it
 * would show up.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Dashboard, StudentView } from '@/app/dashboard/page';
import { ApiError } from '@/lib/api';
import type {
  AppNotification,
  Certificate,
  DashboardCourse,
  Paginated,
  StudentAssignment,
  StudentDashboard,
  StudentProject,
  TrainerDashboard,
} from '@/types/api';
import type { PerformanceFeedback, StudentPerformanceEntry } from '@/lib/performance';

const listMyAssignments = vi.hoisted(() => vi.fn());
const listMyProjects = vi.hoisted(() => vi.fn());
const getMyPerformance = vi.hoisted(() => vi.fn());
const listMyFeedback = vi.hoisted(() => vi.fn());
const listMyCertificates = vi.hoisted(() => vi.fn());
const listNotifications = vi.hoisted(() => vi.fn());
const getStudentDashboard = vi.hoisted(() => vi.fn());
const getTrainerDashboard = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('@/lib/assignments', () => ({ listMyAssignments }));
vi.mock('@/lib/projects', () => ({ listMyProjects }));
vi.mock('@/lib/performance', () => ({ getMyPerformance, listMyFeedback }));
vi.mock('@/lib/progress', () => ({ listMyCertificates, certificatePdfUrl: (id: string) => `/pdf/${id}` }));
vi.mock('@/lib/communication', () => ({ listNotifications }));
vi.mock('@/lib/batches', () => ({ getStudentDashboard, getTrainerDashboard }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => useAuthMock.value }));

function paginated<T>(results: T[]): Paginated<T> {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function emptyBuckets() {
  listMyAssignments.mockResolvedValue(paginated<StudentAssignment>([]));
  listMyProjects.mockResolvedValue(paginated<StudentProject>([]));
  getMyPerformance.mockResolvedValue([] as StudentPerformanceEntry[]);
  listMyFeedback.mockResolvedValue([] as PerformanceFeedback[]);
  listMyCertificates.mockResolvedValue([] as Certificate[]);
  listNotifications.mockResolvedValue(paginated<AppNotification>([]));
}

function dashboardCourse(overrides: Partial<DashboardCourse> = {}): DashboardCourse {
  return {
    enrollment_id: 'enrol-1',
    course_id: 'course-1',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning batch',
    status: 'active',
    grants_access: true,
    progress_percent: 40,
    completed_lessons: 4,
    total_lessons: 10,
    last_lesson_id: 'lesson-5',
    last_lesson_title: 'Permissions',
    ...overrides,
  };
}

function emptyStudentDashboard(): StudentDashboard {
  return {
    is_student: true,
    courses: [],
    batches: [],
    upcoming_classes: [],
    continue_learning: null,
    recent_activity: [],
    notifications: [],
  };
}

async function waitForBucketsToSettle() {
  // All five secondary fetches resolve; waiting on one that only appears
  // once loading finishes is enough to know the others (mocked to resolve
  // immediately too) have settled as well.
  await waitFor(() => expect(getMyPerformance).toHaveBeenCalled());
}

describe('StudentView — brand-new student (every source empty)', () => {
  it('renders clean, encouraging empty states everywhere and never a raw undefined/NaN/Invalid Date/null', async () => {
    emptyBuckets();
    render(<StudentView data={emptyStudentDashboard()} />);
    await waitForBucketsToSettle();

    // Encouraging, not alarming or blank. "All caught up" legitimately
    // appears twice — the status line and the notifications panel both say
    // it independently — so that one is an `getAllByText` length check
    // rather than a single-match query.
    expect(await screen.findByText(/no active courses/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing outstanding/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing on your calendar/i)).toBeInTheDocument();
    expect(screen.getByText(/no certificates yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no feedback/i)).toBeInTheDocument();
    expect(screen.getAllByText(/all caught up/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/no batches yet/i)).toBeInTheDocument();

    const bodyText = document.body.textContent ?? '';
    expect(bodyText).not.toMatch(/undefined/);
    expect(bodyText).not.toMatch(/\bNaN\b/);
    expect(bodyText).not.toMatch(/Invalid Date/);
    expect(bodyText).not.toMatch(/\bnull\b/);
  });

  it('shows the all-caught-up status line rather than a count of nothing', async () => {
    emptyBuckets();
    render(<StudentView data={emptyStudentDashboard()} />);
    await waitForBucketsToSettle();
    expect(await screen.findByText(/everything looks on track/i)).toBeInTheDocument();
  });
});

describe('StudentView — full data', () => {
  it('renders continue learning, courses, pending work and standing together', async () => {
    listMyAssignments.mockResolvedValue(
      paginated<StudentAssignment>([
        {
          id: 'a1',
          code: 'GRS-A-001',
          course: 'course-1',
          course_title: 'Linux Essentials',
          module: null,
          lesson: null,
          title: 'Shell scripting',
          instructions: '',
          submission_kind: 'file',
          max_marks: '100',
          passing_marks: '40',
          due_at: '2026-04-01T23:59:00Z',
          allow_late: false,
          late_cutoff_at: null,
          allow_resubmission: false,
          max_attempts: 1,
          status: 'published',
          is_open: true,
          attachments: [],
          my_submission: null,
        },
      ]),
    );
    listMyProjects.mockResolvedValue(paginated<StudentProject>([]));
    getMyPerformance.mockResolvedValue([
      {
        enrollment_id: 'enrol-1',
        course_title: 'Linux Essentials',
        batch_code: 'GRS-B-001',
        attendance: { percent: 90, total_sessions: 10, attended: 9, has_records: true },
        assessment: { average_percent: 75, sitting_percent: 75, recorded: 2, total: 2 },
        assignments: { percent: 50, total: 2, submitted: 1, graded: 1, passed: 1, missed: 0 },
        projects: { percent: null, required: 0, finished: 0 },
        progress: { percent: 40, expected_percent: 45, variance: 5 },
        overall_score: 72,
        risk: { at_risk: false, outcomes: [], triggered: [], triggered_count: 0 },
        counts: { components_measured: 4, risk_flags: 0 },
      } satisfies StudentPerformanceEntry,
    ]);
    listMyFeedback.mockResolvedValue([]);
    listMyCertificates.mockResolvedValue([]);
    listNotifications.mockResolvedValue(paginated<AppNotification>([]));

    const data: StudentDashboard = {
      is_student: true,
      courses: [dashboardCourse()],
      batches: [
        {
          id: 'batch-1',
          code: 'GRS-B-001',
          name: 'Morning batch',
          course_title: 'Linux Essentials',
          status: 'active',
          enrollment_status: 'active',
          start_date: '2026-01-01',
          end_date: '2026-06-01',
        },
      ],
      upcoming_classes: [],
      continue_learning: { ...dashboardCourse(), last_lesson_id: 'lesson-5' },
      recent_activity: [],
      notifications: [],
    };

    render(<StudentView data={data} />);
    await waitForBucketsToSettle();

    expect(screen.getByText('Continue learning')).toBeInTheDocument();
    expect(screen.getAllByText('Linux Essentials').length).toBeGreaterThan(0);
    expect(await screen.findByText(/1 assignment/i)).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('renders a partially-loaded course — attendance known, results not yet recorded', async () => {
    emptyBuckets();
    getMyPerformance.mockResolvedValue([
      {
        enrollment_id: 'enrol-1',
        course_title: 'Linux Essentials',
        batch_code: 'GRS-B-001',
        attendance: { percent: 62, total_sessions: 4, attended: 2, has_records: true },
        assessment: { average_percent: null, sitting_percent: null, recorded: 0, total: 0 },
        assignments: { percent: null, total: 0, submitted: 0, graded: 0, passed: 0, missed: 0 },
        projects: { percent: null, required: 0, finished: 0 },
        progress: { percent: null, expected_percent: null, variance: null },
        // Deliberately not 62 — the attendance tile already renders "62%",
        // and a coincidentally identical overall score would make that text
        // ambiguous on the page.
        overall_score: 58,
        risk: {
          at_risk: true,
          triggered: ['attendance'],
          triggered_count: 1,
          outcomes: [
            {
              key: 'attendance',
              label: 'Attendance',
              triggered: true,
              severity: 'warning',
              detail: '62% attended, below the 75% risk threshold.',
              numbers: { percent: 62, threshold: '75' },
            },
          ],
        },
        counts: { components_measured: 1, risk_flags: 1 },
      } satisfies StudentPerformanceEntry,
    ]);

    render(<StudentView data={emptyStudentDashboard()} />);
    await waitForBucketsToSettle();

    expect(await screen.findByText('62%')).toBeInTheDocument();
    // Assessment average has nothing recorded — a real "Not available", not 0% or NaN%.
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
    expect(screen.getByText(/62% attended/)).toBeInTheDocument();
    expect(document.body.textContent ?? '').not.toMatch(/NaN/);
  });

  it('keeps the rest of the page working when one secondary section fails to load', async () => {
    listMyAssignments.mockResolvedValue(paginated<StudentAssignment>([]));
    listMyProjects.mockResolvedValue(paginated<StudentProject>([]));
    getMyPerformance.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    listMyFeedback.mockResolvedValue([]);
    listMyCertificates.mockResolvedValue([]);
    listNotifications.mockResolvedValue(paginated<AppNotification>([]));

    render(<StudentView data={emptyStudentDashboard()} />);
    await waitFor(() => expect(screen.getByText('Down.')).toBeInTheDocument());

    // The pending-work panel, a wholly independent fetch, still rendered its
    // own content rather than the whole page going blank.
    expect(screen.getByText(/nothing outstanding/i)).toBeInTheDocument();
  });

  it('is laid out mobile-first: the priority sections only widen to two columns from lg: up', async () => {
    emptyBuckets();
    const { container } = render(<StudentView data={emptyStudentDashboard()} />);
    await waitForBucketsToSettle();

    expect(container.querySelector('[class*="lg:grid-cols-2"]')).not.toBeNull();
    expect(container.querySelector('[class*="sm:grid-cols-2"]')).not.toBeNull();

    // No column count is forced below a breakpoint anywhere in these
    // wrappers — a bare, un-prefixed `grid-cols-2` token would defeat
    // single-column mobile stacking. Checked as whole class tokens (split on
    // whitespace), not a substring match: a substring check would wrongly
    // flag "sm:grid-cols-2" as containing "grid-cols-2".
    // `.getAttribute`, not `.className`: several rendered nodes are `<svg>`
    // icons, whose `className` is an `SVGAnimatedString`, not a plain string.
    const classTokens = Array.from(container.querySelectorAll('[class]')).flatMap((el) =>
      (el.getAttribute('class') ?? '').split(/\s+/).filter(Boolean),
    );
    expect(classTokens).not.toContain('grid-cols-2');
  });
});

describe('Dashboard — role routing', () => {
  it('shows a loading state, then the student view for a signed-in student', async () => {
    useAuthMock.value = {
      user: { first_name: 'Asha', email: 'asha@example.com', role: 'student' },
    };
    emptyBuckets();
    getStudentDashboard.mockResolvedValue(emptyStudentDashboard());

    render(<Dashboard />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    expect(await screen.findByText(/welcome back, asha/i)).toBeInTheDocument();
    expect(await screen.findByText(/no active courses/i)).toBeInTheDocument();
  });

  it('shows the non-student card when the account has no student profile', async () => {
    useAuthMock.value = { user: { first_name: 'Priya', role: 'student' } };
    getStudentDashboard.mockResolvedValue({ ...emptyStudentDashboard(), is_student: false });

    render(<Dashboard />);
    expect(await screen.findByText(/nothing to show here/i)).toBeInTheDocument();
  });

  it('offers a working retry from the top-level error state', async () => {
    useAuthMock.value = { user: { first_name: 'Priya', role: 'student' } };
    getStudentDashboard
      .mockRejectedValueOnce(new ApiError(500, 'server_error', 'Could not reach the server.', 'req-9'))
      .mockResolvedValueOnce(emptyStudentDashboard());
    emptyBuckets();

    render(<Dashboard />);
    const retry = await screen.findByRole('button', { name: /try again/i });
    retry.click();

    expect(await screen.findByText(/welcome back, priya/i)).toBeInTheDocument();
  });

  it('routes a trainer to the trainer view untouched by this rebuild', async () => {
    useAuthMock.value = { user: { first_name: 'Tina', role: 'trainer' } };
    const trainerData: TrainerDashboard = {
      is_trainer: true,
      batches: [],
      today_classes: [],
      upcoming_classes: [],
      student_count: 0,
      courses: [],
    };
    getTrainerDashboard.mockResolvedValue(trainerData);

    render(<Dashboard />);
    expect(await within(document.body).findByText(/your batches, classes and students/i)).toBeInTheDocument();
  });
});
